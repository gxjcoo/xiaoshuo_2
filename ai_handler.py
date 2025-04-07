import httpx
import json
import time
import random
import openai

# 从 config 模块导入配置
from config import (
    API_KEY, BASE_URL, 
    STYLE_ANALYSIS_MODEL, CHAPTER_GENERATION_MODEL, CONTEXT_ANALYSIS_MODEL,
    CONTEXT_ANALYSIS_MAX_TOKENS, CONTEXT_ANALYSIS_TEMPERATURE,
    STYLE_ANALYSIS_MAX_TOKENS, STYLE_ANALYSIS_TEMPERATURE,
    CHAPTER_GENERATION_TEMPERATURE,
    STYLE_ANALYSIS_MAX_TOKENS, STYLE_ANALYSIS_TEMPERATURE,
    MAX_CHAPTER_CONTENT_LENGTH
)

def call_deepseek_api(messages, model, max_tokens=None, temperature=0.7, response_format=None):
    """调用 DeepSeek API 的通用函数，包含重试逻辑"""
    http_client = httpx.Client()

    client = openai.OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=http_client
    )
    
    retries = 3
    delay = 5
    last_exception = None
    
    for attempt in range(retries):
        try:
            print(f"API 请求 (尝试 {attempt + 1}/{retries}): 模型={model}, 温度={temperature}")
            
            # 构建请求参数
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            
            # 添加可选参数
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
                
            if response_format is not None:
                kwargs["response_format"] = response_format
            
            # 发送请求
            try:
                # 尝试使用新版API
                response = client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content.strip()
            except AttributeError:
                # 如果新版API失败，尝试使用旧版API
                kwargs["model"] = model  # 确保模型名称正确设置
                response = openai.Completion.create(**kwargs)
                content = response.choices[0].text.strip()
            
            return content
            
        except Exception as e:
            last_exception = e
            print(f"请求失败 (尝试 {attempt + 1}/{retries}): {str(e)}")
            if attempt < retries - 1:  # 不是最后一次尝试
                print(f"将在 {delay} 秒后重试...")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"已达到最大重试次数 ({retries})，请求失败。")
    
    # 所有尝试都失败
    if last_exception:
        print(f"所有 API 调用尝试均失败。最后的错误: {str(last_exception)}")
    return None

def analyze_writing_style(text_sample):
    """使用 AI 分析文本的语言风格"""
    print("正在分析原始章节的语言风格...")
    
    # 限制发送到 API 的样本大小
    if not text_sample:
        print("错误: 提供的文本样本为空，无法分析风格。")
        return "未能分析出风格，原始文本可能为空。"
        
    limited_sample = text_sample[:MAX_CHAPTER_CONTENT_LENGTH]

    # 使用针对风格分析优化的提示词
    prompt = (
        f"请对以下原始小说文本进行全面、深入的分析，确保后续生成的内容能与原作保持高度一致。分析需涵盖以下几个关键维度：\n\n"
        f"1. **语言风格细节**：\n"
        f"   - 语气和基调：文本的情感色彩和总体氛围（庄重、轻松、紧张、诙谐等）\n"
        f"   - 句法结构：句子长短、复杂度，常用句式模式，有无特殊断句或排版特点\n" 
        f"   - 词汇选择：专业术语、俚语、方言、成语使用频率，是否有特定词汇偏好\n"
        f"   - 修辞手法：常用的修辞技巧（比喻、夸张、拟人等）及其具体表现方式\n"
        f"   - 叙述视角：视角选择（第一/三人称等）及视角转换模式\n"
        f"   - 节奏感：段落长短变化，快慢节奏转换，如何处理高潮与平缓情节\n\n"
        f"2. **剧情发展特征**：\n"
        f"   - 情节推进方式：如何引入新情节，转场手法，悬念设置方式\n"
        f"   - 冲突构建模式：冲突如何设置、发展和解决\n"
        f"   - 场景描写风格：环境描写的详略程度，感官细节使用特点\n\n"
        f"3. **人物塑造特点**：\n"
        f"   - 人物对话风格：各角色的独特说话方式，对话与内心独白的区分方法\n"
        f"   - 角色性格展现：如何通过行动、语言、心理描写表现角色性格\n\n"
        f"4. **主题与世界观呈现**：\n"
        f"   - 核心主题表达：如何渗透作品核心思想\n"
        f"   - 世界规则呈现：特殊设定或规则的展示方式\n\n"
        f"**重要说明**：请提供足够详细的分析，捕捉原文独特的写作特征，以便后续内容生成能完美模仿原作风格和剧情连贯性。分析应该聚焦文本本身的特点，不需要概括故事内容。\n\n"
        f"文本内容如下：\n{limited_sample}"
    )

    messages = [
        {"role": "system", "content": "你是一位精通文学分析与写作技巧的专家，擅长识别文本独特的风格特征、叙事技巧和创作手法。请详尽分析原文的语言特点、情节构建模式、人物塑造方法和世界观呈现，确保能提取出原作最核心的风格元素，使后续续写内容能无缝对接原作。请全面而精准地分析，注重可执行性的细节，便于后续模仿。"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        # 调用 AI API 分析风格
        style = call_deepseek_api(
            messages, 
            STYLE_ANALYSIS_MODEL, 
            max_tokens=STYLE_ANALYSIS_MAX_TOKENS, 
            temperature=STYLE_ANALYSIS_TEMPERATURE
        )
        
        if style:
            print("风格分析完成。")
            return style
        else:
            print("风格分析失败。")
            return "未能分析出风格，API 调用失败。"
    except Exception as e:
        print(f"分析风格时发生错误: {e}")
        return f"未能分析出风格，出现错误: {str(e)}"

def generate_chapter_content(current_context, writing_style, target_length, previous_chapter_content=None, target_chapter_number=None):
    """使用 AI 生成新的章节内容"""
    context_json = json.dumps(current_context, ensure_ascii=False, indent=2)
    if target_chapter_number is None:
        chapter_number = current_context.get("last_generated_chapter", 0) + 1
    else:
        chapter_number = target_chapter_number

    # 构建当前故事背景摘要
    current_context_summary = f"当前故事背景：章节 {current_context.get('last_generated_chapter', 0)}，主角信息：{current_context.get('protagonist_info', {})}, 世界设定：{current_context.get('world_setting', {})}, 近期情节摘要：{current_context.get('recent_plot_summary', '无')}"

    # --- 核心创作要求 (共同部分) ---
    core_requirements = (
        f"分析出的原文语言风格：\n{writing_style}\n\n"
        f"{current_context_summary}\n\n"
        f"【核心创作要求】：\n"
        f"1. **风格模仿**：严格模仿原文独特的诙谐幽默、口语化风格，避免严肃。注重幽默对话和内心独白。\n"
        f"2. **内容连贯**：严格维持剧情、角色性格和世界设定的连贯性。\n"
        f"3. **结构模仿**：模仿原文的短段落和生动对话结构。\n"
        f"4. **标题要求**：为第 {chapter_number} 章构思一个模仿原文风格的幽默标题（格式：'第{chapter_number}章 标题内容...'），放在内容最开始。\n"
        f"5. **字数要求**：生成约 {target_length} 字（含标题）。\n\n"
    )

    # 构建提示指令
    prompt_instruction = ""

    # 根据是否有前文构建不同的提示指令
    if previous_chapter_content:
        print(f"正在根据上一章内容、语言风格和全局上下文生成续写章节 {chapter_number}...")
        # 截取上一章最后部分作为更直接的上下文
        previous_ending = previous_chapter_content[-2000:] # 可调整长度
        prompt_instruction = (
            core_requirements +
            f"【续写特定要求】：\n"
            f"1. **直接续写**：新章节必须从上一章的结尾处（如下）无缝衔接，直接延续情节。\n"
            f"   上一章结尾片段：\n   ```\n   {previous_ending}\n   ```\n"
            f"2. **情节推进**：在保持风格和连贯性的前提下，合理推进故事发展。\n"
        )
    else:  # 生成开篇章节，通常是第一章
        print(f"正在根据语言风格分析生成开篇第 {chapter_number} 章...")
        prompt_instruction = (
            core_requirements +
            f"【开篇特定要求】：\n"
            f"1. **开场场景**：请设定在雨天，主角陆阳首次前往问道宗求仙问道，他对出门遇雨有所抱怨。\n"
            f"2. **奠定基调**：通过开篇确立故事轻松诙谐的基调。\n"
        )

    prompt = prompt_instruction
    messages = [
        # 保持或微调 System Message，确保其简洁有效
        # 示例 System Message (如果需要修改):
        # {"role": "system", "content": "你是一位精通创作轻松诙谐、口语化修仙故事的幽默作家。请严格模仿提供的语言风格和核心要求进行创作。"},
        # 保留原来的 system message 逻辑，或根据需要取消下面的注释并调整
        {"role": "system", "content": "你是一位精通小说创作的幽默作家，特别擅长创作轻松诙谐、充满生活气息的修仙故事。你的风格不同于传统严肃的修仙小说，而是注重角色的鲜活对话、内心吐槽和轻松幽默的情节。请严格遵循用户的要求进行创作。"}, # 稍微精简和聚焦的system message
        {"role": "user", "content": prompt}
    ]

    # ... (后续的 API 调用逻辑保持不变)
    try:
        print(f"API 请求 (尝试 1/3): 模型={CHAPTER_GENERATION_MODEL}, 温度={CHAPTER_GENERATION_TEMPERATURE}")
        new_content = call_deepseek_api(
            messages, 
            CHAPTER_GENERATION_MODEL, 
            max_tokens=target_length, 
            temperature=CHAPTER_GENERATION_TEMPERATURE
        )
        
        if not new_content.startswith("# "):
            print("警告：生成的内容未按预期以 '# ' 开头。可能缺少标题。尝试在开头添加默认标题。")
            first_sentence = new_content.split('\n')[0]
            potential_title = f"第{chapter_number}章 {first_sentence[:20]}"
            new_content = f"# {potential_title}\n\n{new_content}"
            print(f"已添加临时标题：# {potential_title}")
            
        return new_content
    except Exception as e:
        
        print(f"生成新章节内容时发生错误: {e}")
        return None

def analyze_context_with_ai(current_context, chapter_content):
    """使用 AI 分析章节内容以更新上下文的核心部分"""
    print("正在调用 AI 分析章节以更新上下文...")
    # 提取需要 AI 更新的部分 (只传递相关的上下文)
    context_to_update = {
        "protagonist_info": current_context.get("protagonist_info", {}),
        "world_setting": current_context.get("world_setting", {})
    }
    current_context_json = json.dumps(context_to_update, ensure_ascii=False, indent=2)

    # 优化后的提示词
    prompt = (
        f"你是一个精通小说内容理解和信息提取的 AI 助手。你的任务是根据提供的【本章节内容】，更新【当前故事背景信息 (JSON)】中的 `protagonist_info` 和 `world_setting` 部分。\n\n"
        f"【重要分析规则】:\n"
        f"1. **超精准内容提取**: 只提取章节中明确出现的信息，不要推断、不要想象、不要创造未在文本中明确存在的内容。\n"
        f"2. **语言风格识别**: 特别注意原文语言风格的幽默感、诙谐表达和口语化特点，这是原作的核心风格特征。\n"
        f"3. **情节逻辑关联**: 精确捕捉事件发生的顺序和逻辑关系，确保剧情发展线索清晰连贯。\n"
        f"4. **人物特征聚焦**: 准确记录每个角色的独特言行举止、性格特点和对话风格，不要模板化处理人物。\n\n"
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
        f"--- 本章节内容 ---\n{chapter_content[:6000]}\n\n" # 限制输入长度
        f"--- 请严格按照上述规则，输出【完整且有效的 JSON 对象】，结构如下示例：---\n"
        f"{{\n"
        f'  "protagonist_info": {{...内容...}},\n' # 省略号表示内容，不是字面的...
        f'  "world_setting": {{...内容...}}\n'
        f"}}"
    )

    messages = [
        {"role": "system", "content": "你是一个极其精准的信息提取和故事分析专家。你擅长捕捉小说的独特风格、细节和人物特征，能够准确区分原文明确包含的信息与推测内容。请记住：原文中没有明确的内容就不要添加，保持对原始文本的绝对忠实。"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        # 使用通用 API 调用函数，并要求 JSON 对象格式
        updated_data_text = call_deepseek_api(
            messages, 
            CONTEXT_ANALYSIS_MODEL, 
            max_tokens=CONTEXT_ANALYSIS_MAX_TOKENS, 
            temperature=CONTEXT_ANALYSIS_TEMPERATURE,
            response_format={"type": "json_object"}
        )
        
        if not updated_data_text:
            print("警告: 调用 AI 分析上下文失败。跳过 AI 上下文更新。")
            return None
            
        # 尝试解析AI返回的JSON
        updated_data = json.loads(updated_data_text)
        
        # 验证返回的数据结构是否基本正确
        if isinstance(updated_data, dict) and ("protagonist_info" in updated_data or "world_setting" in updated_data):
            print("AI 上下文分析完成，成功解析更新数据。")
            return updated_data
        else:
            print("警告: AI 返回的 JSON 结构不符合预期。跳过 AI 上下文更新。")
            print(f"AI Raw Response Snippet: {str(updated_data_text)[:500]}...") # 打印部分原始响应以便调试
            return None
            
    except json.JSONDecodeError as e:
        print(f"警告: 解析 AI 返回的 JSON 时出错: {e}。跳过 AI 上下文更新。")
        print(f"AI Raw Response Snippet: {str(updated_data_text)[:500] if updated_data_text else 'None'}...") # 打印部分原始响应以便调试
        return None
    except Exception as e:
        print(f"警告: 调用 AI 分析上下文时发生错误: {e}。跳过 AI 上下文更新。")
        return None
