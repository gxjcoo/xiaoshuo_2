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

    # 构建提示指令
    prompt_instruction = ""
    
    # 根据是否有前文构建不同的提示指令
    if previous_chapter_content:
        print(f"正在根据上一章内容、语言风格和全局上下文生成续写章节 {chapter_number}...")
        prompt_instruction = (
            f"分析出的原文语言风格：\n{writing_style}\n\n"
            f"以下是上一章的内容：\n{previous_chapter_content[-4000:]}\n\n"
            f"{current_context_summary}\n\n"
            f"【严格续写要求】：\n"
            f"1. **严格维持剧情连贯性**：新章节必须是上一章的直接逻辑延续，不允许出现剧情跳跃或逻辑断层。所有情节发展必须建立在已有事件基础上，不得随意引入与已建立背景冲突的元素。\n\n"
            f"2. **保持角色一致性**：所有角色的性格、能力、动机和行为模式必须与之前章节保持一致。不得出现角色反常行为，除非有合理的剧情铺垫。每个角色的台词和行动都应符合其既定特点。\n\n"
            f"3. **遵循世界设定**：严格遵守已建立的世界规则、魔法系统或科技水平等设定，不得随意改变或违背这些规则。\n\n"
            f"4. **维持时间线清晰**：事件发展应有明确的时间顺序，避免时间线混乱。新章节应从上一章结束的时间点直接开始，或清晰标明时间流逝。\n\n"
            f"5. **复用关键元素**：适当引用上一章出现的关键物品、地点、人物或概念，确保章节间的紧密关联。\n\n"
            f"【写作技巧要求】：\n"
            f"1. 严格遵循分析出的原文语言风格，包括叙述视角、对话特点、描写方式和节奏感。\n"
            f"2. 确保主角在故事中保持活跃且符合其性格特点。\n"
            f"3. 新章节开头必须直接且自然地从上一章结尾场景衔接，不要重复已发生的事件。\n"
            f"4. 在保持原有风格的同时，为情节发展注入适当的矛盾和悬念。\n\n"
            f"**重要：请为这第 {chapter_number} 章构思一个独特且相关的标题（确保标题以'第{chapter_number}章'开头），并将其放在生成内容的最开始，使用 Markdown 一级标题格式（例如： # 第{chapter_number}章 惊险的遭遇）。**\n"
            f"生成大约 {target_length} 字的新章节内容（包含标题）。"
        )
    else:  # 生成开篇章节，通常是第一章
        print(f"正在根据语言风格分析生成开篇第 {chapter_number} 章...")
        prompt_instruction = (
            f"分析出的原文语言风格：\n{writing_style}\n\n"
            f"{current_context_summary}\n\n"
            f"【创作要求】：\n"
            f"1. **建立基础世界观与规则**：在第一章中清晰地建立故事世界的基本规则、背景设定和运作机制，为后续发展奠定稳固基础。\n\n"
            f"2. **塑造鲜明角色**：通过具体行动、对话和思想展现角色的性格特点、能力限制和核心动机，确保角色形象立体且有发展潜力。\n\n"
            f"3. **设置引人入胜的开端**：创造一个能够迅速吸引读者注意的开场情境，可以是一个谜团、冲突或特殊事件。\n\n"
            f"4. **暗示主要冲突**：初步引入或暗示故事的核心冲突和可能的发展方向，但不必完全揭示。\n\n"
            f"5. **语言风格一致性**：严格遵循分析出的原文语言风格，包括叙述视角、句式结构、词汇选择和节奏感等各个方面。\n\n"
            f"**重要：请为这第 {chapter_number} 章构思一个独特且相关的标题（确保标题以'第{chapter_number}章'开头），并将其放在生成内容的最开始，使用 Markdown 一级标题格式。**\n"
            f"生成大约 {target_length} 字的新章节内容（包含标题）。"
        )
    
    prompt = prompt_instruction
    messages = [
        {"role": "system", "content": "你是一位精通小说创作的专业作家，擅长创作逻辑严密、剧情连贯的故事。你的创作必须保持角色、世界设定和情节的一致性，严格避免任何逻辑漏洞或剧情矛盾。你会确保每个新章节都是前文的自然延续，无缝衔接已有情节，同时保持原作的语言风格和叙事特点。"},
        {"role": "user", "content": prompt}
    ]
    
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
        f"【重要规则】:\n"
        f"1.  **只基于本章节内容**: 你的更新必须严格基于【本章节内容】中明确发生的情节、对话、新物品/能力、新地点、新角色关系等。不要猜测或引入章节外的信息。\n"
        f"2.  **增量更新**: 保留 JSON 中未被本章内容直接修改或覆盖的原有信息。只添加或修改本章引入的新变化。\n"
        f"3.  **更新指定字段**: 重点更新 `protagonist_info` 下的 `status_summary`, `key_items_abilities`, `key_relationships` 和 `world_setting` 下的 `location`, `key_elements`。\n"
        f"4.  **严格的 JSON 输出**: 你的输出【必须】是一个语法完全正确、结构完整的 JSON 对象。此 JSON 对象【必须】只包含 `protagonist_info` 和 `world_setting` 这两个顶级键。不要在 JSON 前后添加任何解释、注释或多余的文字。\n"
        f"5.  **列表处理**: 如果信息是列表形式（如能力、物品），通常应在原有列表基础上追加新项，除非本章明确说明要替换或删除。\n\n"
        f"--- 当前故事背景信息 (JSON) ---\n{current_context_json}\n\n"
        f"--- 本章节内容 ---\n{chapter_content[:6000]}\n\n" # 限制输入长度
        f"--- 请严格按照上述规则，输出【完整且有效的 JSON 对象】，结构如下示例：---\n"
        f"{{\n"
        f'  "protagonist_info": {{...内容...}},\n' # 省略号表示内容，不是字面的...
        f'  "world_setting": {{...内容...}}\n'
        f"}}"
    )

    messages = [
        {"role": "system", "content": "你是一个信息提取和JSON格式化助手。"},
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
