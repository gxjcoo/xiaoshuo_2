import openai
import argparse
import httpx 
import time
import os
import re 
import json 
import copy
import datetime

API_KEY = "sk-1c6c5c08ade4448690f5b4d2358eaf6a"
BASE_URL = "https://api.deepseek.com"

STORY_CONTEXT_FILE = "story_context.json"
PRUNED_ARCHIVE_FILE = 'pruned_context_archive.json'
story_context = {}

http_client = httpx.Client()

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    http_client=http_client
)

def load_story_context():
    global story_context
    if os.path.exists(STORY_CONTEXT_FILE):
        try:
            with open(STORY_CONTEXT_FILE, 'r', encoding='utf-8') as f:
                story_context = json.load(f)
            print(f"Loaded context: {STORY_CONTEXT_FILE}")
        except Exception as e:
            print(f"Error loading context: {e}")
            story_context = {'last_chapter': 0, 'protagonist': {}, 'world': {}, 'plot_nodes': []}
    else:
        story_context = {'last_chapter': 0, 'protagonist': {}, 'world': {}, 'plot_nodes': []}
        save_story_context()

def save_story_context():
    global story_context
    try:
        with open(STORY_CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(story_context, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving context: {e}")

def analyze_structure(original_content):
    """分析原文章节结构并提取关键剧情节点"""
    print("Analyzing original chapter structure...")
    try:
        messages = [
            {"role": "system", "content": "你是一个专业的小说结构分析助手"},
            {"role": "user", "content": f"请分析以下小说章节内容，提取关键剧情节点（包括：重要事件、转折点、角色发展、新设定引入），用简洁的中文短语列表表示。不要包含解释，直接输出JSON数组：\n\n{original_content[:6000]}"}
        ]
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        nodes = json.loads(response.choices[0].message.content).get("plot_nodes", [])
        return nodes[:8]  # 保留最多8个关键节点
    except Exception as e:
        print(f"结构分析失败: {e}")
        return []

def analyze_style(original_content):
    """增强版风格分析"""
    print("Analyzing writing style...")
    try:
        messages = [
            {"role": "system", "content": "你是一个专业的文学风格分析助手"},
            {"role": "user", "content": f"分析以下文本的：1.常用修辞手法 2.典型句式结构 3.标志性词汇 4.叙事节奏 5.对话风格。用JSON格式输出分析结果，包含style_features字段：\n\n{original_content[:6000]}"}
        ]
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"风格分析失败: {e}")
        return {}

def generate_chapter(original_content, style_data, plot_nodes, chapter_num):
    """生成模仿原剧情的新章节"""
    print(f"Generating chapter {chapter_num}...")
    try:
        current_context = f"当前进度：{story_context.get('last_chapter',0)}章 角色状态：{story_context.get('protagonist',{})}"
        messages = [
            {"role": "system", "content": "你是一个专业的小说模仿写作助手。严格遵循以下规则：1.完全按照提供的剧情结构创作 2.保持原有角色关系发展 3.关键节点出现顺序不变"},
            {"role": "user", "content": f"""
# 创作任务
请根据以下要素创作新的第{chapter_num}章内容：

## 原章节关键节点（按顺序出现）
{json.dumps(plot_nodes, ensure_ascii=False, indent=2)}

## 需要模仿的写作风格
{json.dumps(style_data.get('style_features',{}), ensure_ascii=False, indent=2)}

## 上下文状态
{current_context}

## 创作要求
1. 严格保持原章节的关键事件顺序和故事转折点
2. 使用全新的场景描写和对话内容
3. 章节长度保持4000字左右
4. 使用Markdown格式，以# 第{chapter_num}章 [标题] 开头
"""}
        ]
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.65,
            max_tokens=3500
        )
        content = response.choices[0].message.content
        return format_content(content, chapter_num)
    except Exception as e:
        print(f"生成失败: {e}")
        return None

def format_content(text, chapter_num):
    """规范化生成内容格式"""
    text = re.sub(r'^#{1,3}\s*', f'# 第{chapter_num}章 ', text, count=1)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def update_context(original_content, new_content):
    """双上下文更新：同时分析原文和生成内容"""
    print("Updating story context...")
    # 分析原文获取设定更新
    original_nodes = analyze_structure(original_content)
    if original_nodes:
        # 保持逻辑不变：存储原文的关键节点以备参考
        # 如果需要存储新内容的节点，需要调用 analyze_structure(new_content)
        story_context['plot_nodes'] = original_nodes[-5:]

    # 分析生成内容更新角色状态和世界信息
    try:
        messages = [
            {"role": "system", "content": "你是一个上下文更新助手。请仔细阅读文本，并提取关键信息，以指定的JSON格式返回。"},
            # 修改提示，明确要求返回包含 protagonist 和 world 键的JSON
            {"role": "user", "content": f"""从以下生成的小说章节内容中提取关键信息：

1.  **主角状态更新**: 包括获得的新物品、新技能、重要状态变化等。
2.  **世界信息更新**: 包括新地点、重要世界设定变化、角色关系变化等。

请将提取的信息整理成JSON格式返回，必须包含 'protagonist' 和 'world' 两个顶级键。'protagonist' 键的值是一个对象，包含主角相关的更新；'world' 键的值是一个对象，包含世界信息和角色关系的更新。

如果某方面没有提取到信息，请返回空对象 {{}}。

小说内容：
{new_content[:3000]}  # 限制输入长度以防超限

输出示例 (如果提取到信息):
```json
{{
  "protagonist": {{
    "new_ability": "火焰掌握",
    "status_change": "身受重伤"
  }},
  "world": {{
    "new_location": "迷雾森林",
    "relationship_change": "与艾莉关系缓和"
  }}
}}
```

输出示例 (如果未提取到信息):
```json
{{
  "protagonist": {{}},
  "world": {{}}
}}
```
"""}
        ]
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        # 尝试解析响应内容
        response_content = response.choices[0].message.content
        print(f"Debug: AI response for context update:\n{response_content}") # 添加调试输出
        updates = json.loads(response_content)

        # 确保 updates 是字典
        if isinstance(updates, dict):
            # 更新主角信息，合并字典
            if 'protagonist' in updates and isinstance(updates['protagonist'], dict):
                story_context['protagonist'].update(updates['protagonist'])
            else:
                print("Warning: 'protagonist' key missing or not a dict in AI response.")

            # 更新世界信息，合并字典
            if 'world' in updates and isinstance(updates['world'], dict):
                story_context['world'].update(updates['world'])
            else:
                print("Warning: 'world' key missing or not a dict in AI response.")
        else:
             print(f"Error: AI response for context update is not a valid JSON object: {updates}")

    except json.JSONDecodeError as e:
        print(f"上下文更新失败: 无法解析 AI 返回的 JSON - {e}")
        print(f"Raw AI response: {response_content}") # 输出原始响应帮助调试
    except Exception as e:
        print(f"上下文更新失败: {e}")

def process_chapter(args, chapter_num):
    original_path = os.path.join(args.input_dir, f"{chapter_num}.md")
    output_path = os.path.join(args.output_dir, f"{chapter_num}.md")
    
    if not os.path.exists(original_path):
        print(f"Missing original chapter {chapter_num}")
        return

    # 读取原文
    with open(original_path, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    # 分析阶段
    style_data = analyze_style(original_content)
    plot_nodes = analyze_structure(original_content)
    
    # 生成阶段
    new_content = generate_chapter(original_content, style_data, plot_nodes, chapter_num)
    
    if new_content:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        update_context(original_content, new_content)
        story_context['last_chapter'] = chapter_num
        save_story_context()

def main():
    parser = argparse.ArgumentParser(description="小说模仿生成器")
    parser.add_argument('--input_dir', required=True, help="原文目录")
    parser.add_argument('--output_dir', required=True, help="输出目录")
    parser.add_argument('--start', type=int, default=1, help="起始章节")
    parser.add_argument('--end', type=int, required=True, help="结束章节")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    
    load_story_context()
    
    for chap in range(args.start, args.end+1):
        start_time = time.time()
        print(f"\nProcessing Chapter {chap}")
        process_chapter(args, chap)
        print(f"Completed in {time.time()-start_time:.1f}s")
    
    print("\nProcess completed. Final context saved.")

if __name__ == '__main__':
    main()