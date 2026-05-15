"""根据新章节正文更新 protagonist / world_setting 的 JSON 片段。"""

import json

from config import (
    CONTEXT_ANALYSIS_MODEL,
    CONTEXT_ANALYSIS_MAX_TOKENS,
    CONTEXT_ANALYSIS_TEMPERATURE,
)

from .client import call_deepseek_api


def analyze_context_with_ai(current_context, chapter_content):
    """使用 AI 分析章节内容以更新上下文的核心部分"""
    print("正在调用 AI 分析章节以更新上下文...")
    context_to_update = {
        "protagonist_info": current_context.get("protagonist_info", {}),
        "world_setting": current_context.get("world_setting", {}),
    }
    current_context_json = json.dumps(context_to_update, ensure_ascii=False, indent=2)

    prompt = (
        f"你是一个精通小说内容理解和信息提取的作家。你的任务是根据提供的【本章节内容】，更新【当前故事背景信息 (JSON)】中的 `protagonist_info` 和 `world_setting` 部分。\n\n"
        f"【重要分析规则】:\n"
        f"1. **超精准内容提取**: 只提取章节中明确出现的信息，不要推断、不要想象、不要创造未在文本中明确存在的内容。\n"
        f"2. **语言风格识别**: 特别注意原文语言风格的幽默感、诙谐表达和口语化特点，这是原作的核心风格特征。\n"
        f"3. **情节逻辑关联**: 精确捕捉事件发生的顺序和逻辑关系，确保剧情发展线索清晰连贯。\n"
        f"4. **人物特征聚焦**: 准确记录每个角色的独特言行举止、性格特点和对话风格，不要模板化处理人物。\n"
        f"【关键更新字段】:\n"
        f"1. `protagonist_info.status_summary`: 提取主角当前状态、心态和境遇的关键信息\n"
        f"2. `protagonist_info.key_items_abilities`: 主角拥有或获得的物品、能力或技能\n"
        f"3. `protagonist_info.key_relationships`: 主角与其他角色的关系发展\n"
        f"4. `world_setting.location`: 当前故事发生的具体地点和环境描述\n"
        f"5. `world_setting.key_elements`: 世界观中的规则、设定和重要背景元素\n\n"
        f"【精准判断准则】:\n"
        f"- 宁可少提取也不要过度推断\n"
        f"- 宁可保留已有内容也不要用不确定信息覆盖\n"
        f"- 确保每条记录的信息都能在原文中找到对应段落\n\n"
        f"--- 当前故事背景信息 (JSON) ---\n{current_context_json}\n\n"
        f"--- 本章节内容 ---\n{chapter_content[:6000]}\n\n"
        f"--- 请严格按照上述规则，输出【完整且有效的 JSON 对象】，结构如下示例：---\n"
        f"{{\n"
        f'  "protagonist_info": {{...内容...}},\n'
        f'  "world_setting": {{...内容...}}\n'
        f"}}"
    )

    messages = [
        {"role": "system", "content": "你是一个极其精准的信息提取和故事分析专家。你擅长捕捉小说的独特风格、细节和人物特征，能够准确区分原文明确包含的信息与推测内容。请记住：原文中没有明确的内容就不要添加，保持对原始文本的绝对忠实。"},
        {"role": "user", "content": prompt},
    ]

    updated_data_text = None
    try:
        updated_data_text = call_deepseek_api(
            messages,
            CONTEXT_ANALYSIS_MODEL,
            max_tokens=CONTEXT_ANALYSIS_MAX_TOKENS,
            temperature=CONTEXT_ANALYSIS_TEMPERATURE,
            response_format={"type": "json_object"},
        )

        if not updated_data_text:
            print("警告: 调用 AI 分析上下文失败。跳过 AI 上下文更新。")
            return None

        updated_data = json.loads(updated_data_text)

        if isinstance(updated_data, dict) and ("protagonist_info" in updated_data or "world_setting" in updated_data):
            print("AI 上下文分析完成，成功解析更新数据。")
            return updated_data
        print("警告: AI 返回的 JSON 结构不符合预期。跳过 AI 上下文更新。")
        print(f"AI Raw Response Snippet: {str(updated_data_text)[:500]}...")
        return None

    except json.JSONDecodeError as e:
        print(f"警告: 解析 AI 返回的 JSON 时出错: {e}。跳过 AI 上下文更新。")
        print(f"AI Raw Response Snippet: {str(updated_data_text)[:500] if updated_data_text else 'None'}...")
        return None
    except Exception as e:
        print(f"警告: 调用 AI 分析上下文时发生错误: {e}。跳过 AI 上下文更新。")
        return None
