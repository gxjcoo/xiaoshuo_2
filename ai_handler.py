import httpx
import json
import time
import openai

# 从 config 模块导入配置
from config import (
    LLM_PROVIDER,
    API_KEY,
    BASE_URL,
    API_HTTP_CONNECT_TIMEOUT,
    API_HTTP_READ_TIMEOUT,
    STYLE_ANALYSIS_MODEL,
    CHAPTER_GENERATION_MODEL,
    CONTEXT_ANALYSIS_MODEL,
    CONTEXT_ANALYSIS_MAX_TOKENS,
    CONTEXT_ANALYSIS_TEMPERATURE,
    STYLE_ANALYSIS_MAX_TOKENS,
    STYLE_ANALYSIS_TEMPERATURE,
    CHAPTER_GENERATION_TEMPERATURE,
    MAX_CHAPTER_CONTENT_LENGTH,
    VOLUME_CHAPTER_SIZE,
)

def _extract_text_from_ark_response(data):
    """从 Ark /responses 返回中尽量提取纯文本。"""
    if isinstance(data, dict):
        if isinstance(data.get("output_text"), str) and data.get("output_text", "").strip():
            return data["output_text"].strip()

        output = data.get("output")
        if isinstance(output, list):
            chunks = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        text = c.get("text")
                        if isinstance(text, str) and text.strip():
                            chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks).strip()
    return ""


def _call_ark_responses_api(messages, model, timeout, max_tokens=None, temperature=0.7):
    """调用豆包 Ark /responses 接口。"""
    input_payload = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        input_payload.append({
            "role": role,
            "content": [{"type": "input_text", "text": content}],
        })

    payload = {
        "model": model,
        "input": input_payload,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_output_tokens"] = int(max_tokens)

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    endpoint = f"{BASE_URL.rstrip('/')}/responses"

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = _extract_text_from_ark_response(data)
        if text:
            return text
        raise RuntimeError(f"Ark 返回中未提取到文本: {str(data)[:600]}")


def call_deepseek_api(messages, model, max_tokens=None, temperature=0.7, response_format=None):
    """调用 LLM 的通用函数（DeepSeek / 豆包 Ark）。"""
    timeout = httpx.Timeout(
        connect=API_HTTP_CONNECT_TIMEOUT,
        read=API_HTTP_READ_TIMEOUT,
        write=API_HTTP_CONNECT_TIMEOUT,
        pool=API_HTTP_CONNECT_TIMEOUT,
    )

    retries = 3
    delay = 5
    last_exception = None

    for attempt in range(retries):
        try:
            print(
                f"API 请求 (尝试 {attempt + 1}/{retries}): 模型={model}, 温度={temperature}, "
                f"读超时={API_HTTP_READ_TIMEOUT}s",
                flush=True,
            )
            print(
                "  → 等待服务端响应中（网络慢或模型排队时可能需一至数分钟，并非死机）…",
                flush=True,
            )

            if LLM_PROVIDER == "doubao":
                content = _call_ark_responses_api(
                    messages=messages,
                    model=model,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            else:
                with httpx.Client(timeout=timeout) as http_client:
                    client = openai.OpenAI(
                        api_key=API_KEY,
                        base_url=BASE_URL,
                        http_client=http_client,
                    )

                    kwargs = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if max_tokens is not None:
                        kwargs["max_tokens"] = max_tokens
                    if response_format is not None:
                        kwargs["response_format"] = response_format

                    try:
                        response = client.chat.completions.create(**kwargs)
                        content = response.choices[0].message.content.strip()
                    except AttributeError:
                        kwargs["model"] = model
                        response = openai.Completion.create(**kwargs)
                        content = response.choices[0].text.strip()

            return content

        except Exception as e:
            last_exception = e
            print(f"请求失败 (尝试 {attempt + 1}/{retries}): {str(e)}", flush=True)
            if attempt < retries - 1:
                print(f"将在 {delay} 秒后重试...", flush=True)
                time.sleep(delay)
                delay *= 2
            else:
                print(f"已达到最大重试次数 ({retries})，请求失败。", flush=True)

    if last_exception:
        print(f"所有 API 调用尝试均失败。最后的错误: {str(last_exception)}", flush=True)
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
        f"\n2. **叙事结构特点**：\n"
        f"   - 章节组织：章节长度、内部段落结构、章节间的过渡方式\n"
        f"   - 情节节奏：快慢变化、紧张与舒缓的交替模式\n"
        f"   - 叙事技巧：闪回、伏笔、悬念等技巧的使用频率和方式\n"
        f"\n3. **对话与内心独白**：\n"
        f"   - 对话风格：对话的长短、节奏、口语化程度\n"
        f"   - 内心独白：内心活动的表达方式和频率\n"
        f"   - 角色语言：不同角色的语言特点区分\n"
        f"\n4. **环境与氛围描写**：\n"
        f"   - 场景描写：场景细节的呈现方式和详略取舍\n"
        f"   - 氛围营造：通过何种感官描写和语言手段营造氛围\n"
        f"\n5. **主题与情感基调**：\n"
        f"   - 核心主题：文本传达的核心思想或情感\n"
        f"   - 情感表达：喜怒哀乐等情感的表达方式和强度\n\n"
        f"原始文本样本：\n\n{limited_sample}\n\n"
        f"请提供详细分析，确保捕捉到原文的独特风格特征。分析应当足够具体，能够指导后续内容创作。\n\n"
    )

    messages = [
        {"role": "system", "content": "你是一位精通文学分析的专家，擅长捕捉文本的语言风格、叙事结构和表达特点。请对提供的文本样本进行深入分析。"},
        {"role": "user", "content": prompt}
    ]
    
    try:
        # 使用通用 API 调用函数
        style_analysis = call_deepseek_api(
            messages, 
            STYLE_ANALYSIS_MODEL, 
            max_tokens=STYLE_ANALYSIS_MAX_TOKENS, 
            temperature=STYLE_ANALYSIS_TEMPERATURE
        )
        
        if not style_analysis:
            print("警告: 调用 AI 分析风格失败。返回默认风格描述。")
            return "未能分析出风格，将使用默认风格。文本应当保持轻松幽默的基调，使用生动形象的比喻和适度的夸张手法。"
            
        print("风格分析完成。")
        return style_analysis
        
    except Exception as e:
        print(f"分析风格时发生错误: {e}")
        return "未能分析出风格，将使用默认风格。文本应当保持轻松幽默的基调，使用生动形象的比喻和适度的夸张手法。"


def plan_chapter_with_ai(
    current_context,
    target_chapter_number,
    previous_chapter_content=None,
    author_intent_text="",
    current_focus_text="",
):
    """生成本章意图规划（短文本），用于约束正文生成焦点。"""
    context_json = json.dumps(current_context, ensure_ascii=False, indent=2)
    previous_tail = (previous_chapter_content or "")[-1200:]
    prompt = (
        f"你是小说章节规划师。请为第 {target_chapter_number} 章输出一份简洁可执行的写作意图。\n\n"
        f"输出要求：\n"
        f"1) 只输出纯文本，不要 Markdown 表格。\n"
        f"2) 控制在 8 条以内，每条一句话。\n"
        f"3) 至少包含：主线推进、角色变化、关键冲突、伏笔/回收点。\n"
        f"4) 不得与既有设定冲突，不得新增未铺垫的大设定。\n\n"
        f"【当前上下文】\n{context_json}\n\n"
        f"【上一章结尾（可选）】\n{previous_tail if previous_tail else '无'}\n\n"
        f"【作者长期意图（可选）】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点（可选，优先考虑）】\n{current_focus_text if current_focus_text else '无'}\n"
    )
    messages = [
        {"role": "system", "content": "你擅长将长篇小说连载目标拆成可执行章节意图，强调连贯与可落地。"},
        {"role": "user", "content": prompt},
    ]
    plan_text = call_deepseek_api(messages, CHAPTER_GENERATION_MODEL, max_tokens=800, temperature=0.3)
    if not plan_text:
        return ""
    return plan_text.strip()


def analyze_hooks_and_volume_update(current_context, chapter_content, chapter_number):
    """提取本章 hooks 变更，并在分卷节点产出卷摘要。"""
    context_slice = {
        "pending_hooks": current_context.get("pending_hooks", [])[-20:],
        "recent_chapter_summaries": current_context.get("recent_chapter_summaries", [])[-8:],
        "last_generated_chapter": current_context.get("last_generated_chapter", 0),
    }
    volume_boundary = (chapter_number % VOLUME_CHAPTER_SIZE == 0)
    prompt = (
        "你是小说连载状态维护助手。请基于当前章节与既有未回收线索，输出 JSON。\n"
        "字段要求：\n"
        '1) "new_hooks": 本章新增且应保留到后文的线索数组（字符串）\n'
        '2) "resolved_hooks": 本章明确回收/兑现的旧线索数组（字符串）\n'
        '3) "volume_summary": 仅当到达分卷边界时输出该卷摘要，否则输出空字符串\n'
        "规则：\n"
        "- 只提取文本中明确存在的线索，不要脑补。\n"
        "- 用短语表达线索，避免整句复述。\n"
        f"- 当前章节号: {chapter_number}，分卷边界: {'是' if volume_boundary else '否'}。\n\n"
        f"【当前状态片段】\n{json.dumps(context_slice, ensure_ascii=False, indent=2)}\n\n"
        f"【本章内容】\n{chapter_content[:7000]}"
    )
    messages = [
        {"role": "system", "content": "你擅长抽取连载线索状态并维护分卷摘要，输出必须是合法 JSON 对象。"},
        {"role": "user", "content": prompt},
    ]
    result_text = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=1200,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    if not result_text:
        return {"new_hooks": [], "resolved_hooks": [], "volume_summary": ""}

    try:
        parsed = json.loads(result_text)
        if not isinstance(parsed, dict):
            return {"new_hooks": [], "resolved_hooks": [], "volume_summary": ""}
        return {
            "new_hooks": [x for x in parsed.get("new_hooks", []) if isinstance(x, str) and x.strip()],
            "resolved_hooks": [x for x in parsed.get("resolved_hooks", []) if isinstance(x, str) and x.strip()],
            "volume_summary": parsed.get("volume_summary", "").strip() if isinstance(parsed.get("volume_summary", ""), str) else "",
        }
    except Exception:
        return {"new_hooks": [], "resolved_hooks": [], "volume_summary": ""}

def generate_chapter_content(
    current_context,
    writing_style,
    target_length,
    previous_chapter_content=None,
    target_chapter_number=None,
    domain_text="",
    chapter_plan_text="",
    author_intent_text="",
    current_focus_text="",
    audit_requirements_text="",
):
    """使用 AI 生成新的章节内容。

    domain_text: 领域圣经（DDD），静态设定与统一说法。
    """
    if target_chapter_number is None:
        chapter_number = current_context.get("last_generated_chapter", 0) + 1
    else:
        chapter_number = target_chapter_number

    # 构建当前故事背景摘要
    rolling_summaries = current_context.get("recent_chapter_summaries", [])
    if isinstance(rolling_summaries, list) and rolling_summaries:
        rolling_text = "\n".join(
            f"- 第{item.get('chapter', '?')}章：{item.get('summary', '')}"
            for item in rolling_summaries[-8:]
            if isinstance(item, dict)
        ).strip()
    else:
        rolling_text = ""

    current_context_summary = (
        f"当前故事背景：章节 {current_context.get('last_generated_chapter', 0)}，"
        f"主角信息：{current_context.get('protagonist_info', {})}, "
        f"世界设定：{current_context.get('world_setting', {})}, "
        f"近期情节摘要：{current_context.get('recent_plot_summary', '无')}\n"
        f"最近章节滚动记忆：\n{rolling_text if rolling_text else '无'}\n"
        f"待回收线索：{current_context.get('pending_hooks', [])[-12:]}\n"
        f"分卷摘要：{current_context.get('volume_summaries', [])[-3:]}"
    )

    # 获取核心角色和道具
    core_characters = current_context.get('core_characters', [])
    core_items = current_context.get('core_items', [])
    core_elements = f"核心角色：{', '.join(core_characters) if core_characters else '无'}, 核心道具：{', '.join(core_items) if core_items else '无'}"

    ddd_block = ""
    if domain_text:
        ddd_block += (
            f"【领域圣经 DDD（静态设定，优先级高）】\n"
            f"以下内容为项目约定的世界观、术语与硬约束；与下文冲突时以本节为准，不得自相矛盾。\n\n"
            f"{domain_text}\n\n"
        )

    # --- 核心创作要求 (共同部分) ---
    production_hard_rules = (
        f"【产出侧结构硬约束（必须执行）】\n"
        f"1. **事件密度硬约束**：每 500-700 字必须出现一次不可逆变化（冲突升级/关系变化/代价落地/任务状态跃迁其一），"
        f"禁止连续大段“解释世界/复盘策略/施工过程”替代剧情推进。\n"
        f"2. **解释上限硬约束**：连续解释/判断型段落最多 2 段，第 3 段前必须插入动作对抗、意外反馈或人物交锋。\n"
        f"3. **角色声纹硬约束**：至少两名核心角色呈现稳定差异化说话方式（句长、语气词、反问习惯或口癖），"
        f"禁止全员同一书面腔。\n"
        f"4. **开头/结尾反同构**：开篇入口与收束方式都要避免模板化；"
        f"开头优先用动作或异常信息切入，结尾优先落在新变量/新压力，不用解释性总结句收尾。\n"
        f"5. **拒绝任务清单文**：系统、建设、筹备类内容必须嵌入冲突和人物反应中呈现，"
        f"禁止按“先做A再做B再做C”的说明书顺序平铺。\n"
        f"6. **写前自检（只在脑内执行，不要输出）**："
        f"“本段是否发生变化？”“是否在用解释代替戏剧？”“角色说话是否可被区分？”。\n\n"
    )

    implicit_two_phase_contract = (
        f"【隐式两阶段写作契约（强制）】\n"
        f"你必须先在内部完成“结构计划”，再写正文；但结构计划属于隐式推理，不得出现在输出中。\n"
        f"阶段A（内部静默规划，不输出）：\n"
        f"- 先为本章规划 4-7 个叙事节拍（每个节拍必须有事件变化）\n"
        f"- 标注每个节拍的冲突点、信息释放点、角色声纹策略\n"
        f"- 规划开头入口和结尾落点，确保不与近章同构\n"
        f"阶段B（仅输出正文）：\n"
        f"- 严格按阶段A的节拍写作，但语言自然，不要像提纲复述\n"
        f"- 禁止输出任何计划痕迹：如“节拍1/阶段A/结构计划/写作意图/自检”等字样\n"
        f"- 最终输出只能是章节标题+正文，不得包含解释、注释、清单、表格\n\n"
    )

    core_requirements = (
        f"分析出的原文语言风格：\n{writing_style}\n\n"
        f"{current_context_summary}\n\n"
        f"{core_elements}\n\n"
        f"{ddd_block}"
        f"【作者长期意图】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点（优先于长期意图）】\n{current_focus_text if current_focus_text else '无'}\n\n"
        f"【审计规则前置约束（写作时必须遵守）】\n{audit_requirements_text if audit_requirements_text else '无'}\n\n"
        f"【本章意图规划（必须落实）】\n{chapter_plan_text if chapter_plan_text else '无（请按上下文自主规划）'}\n\n"
        f"{implicit_two_phase_contract}"
        f"{production_hard_rules}"
        f"【核心创作要求】：\n"
        f"1. **风格平衡**：保持原文的风格，但同时注重主线推进。\n"
        f"2. **内容连贯**：严格维持剧情、角色性格和世界设定的连贯性。\n"
        f"3. **主线推进**：每章应当推进主要剧情或角色发展，而不仅仅提供笑点，幽默应服务于情节而非喧宾夺主。\n"
        f"4. **标题要求**：为第 {chapter_number} 章构思一个标题（格式：'第{chapter_number}章 标题内容...'），放在内容最开始。\n"
        f"5. **字数要求**：生成约 {target_length} 字正文内容。\n"
        f"6. **结构平衡**：保持对话、叙述和内心活动的平衡，不过分倚重单一表达方式。\n"
        f"7. **领域设定一致性**：若上方提供了领域圣经，必须严格遵守；无法满足时优先删减次要描写，不得编造与圣经冲突的设定。\n"
        f"8. **人味儿与反模板（降低「AI 腔」，与剧情要求同等重要）**：\n"
        f"   - 句式长短必须错落，避免连续多句长度、节奏几乎相同；少用排比、对仗、三句一组的 slogan 式金句。\n"
        f"   - 少用说明文收束：避免段尾高频出现「这一刻/总之/显然/不禁/他明白」类万能升华；允许信息不完整、留一点语意跳跃。\n"
        f"   - 对话要有不同角色的口气与打断，避免所有人说话都像同一份标准书面语；可适度加入口语、半截话、停顿。\n"
        f"   - 描写优先具体动作、物件与感官细节，少用抽象形容词和成语堆叠。\n"
        f"   - 若有系统/提示播报，不要连续多条同一腔调的通知，用环境声、动作、角色吐槽或走神打断。\n"
        f"   - 禁止整段「百科词条」「论文摘要」「产品说明书」语气；禁止列表式交代世界观（除非原作明显如此）。\n\n"
        f"【88+ 执行型硬约束】\n"
        f"- 禁止出现连续三句长度接近且节奏一致的陈述句（必须主动打散句长）。\n"
        f"- 每 400-600 字至少出现一次“动作/环境干扰”来打断说明式叙述。\n"
        f"- 每个关键场景至少落实一条可感知细节（动作、物件、触感、声响、气味其一）。\n"
        f"- 对话段必须出现角色差异：至少一人使用口语短句或半句，避免全员书面腔。\n"
        f"- 禁止在段尾连续使用总结性抽象句（如“他终于明白了”类收束）。\n\n"
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
            f"2. **情节推进**：在保持风格和连贯性的前提下，合理推进主线故事发展。\n"
            f"3. **核心角色发展**：注重刻画核心角色的动机与成长。\n"
            f"4. **情感深化**：循序渐进地增加人物情感和关系复杂性。\n"
        )
    else:  # 生成开篇章节，通常是第一章
        print(f"正在根据语言风格分析生成开篇第 {chapter_number} 章...")
        prompt_instruction = (
            core_requirements +
            f"【开篇特定要求】：\n"
            f"1. 保持原文的风格和剧情。\n"
        )

    prompt = prompt_instruction
    messages = [
        {
            "role": "system",
            "content": (
                "你是一位小说续写作家，用笔要像真人连载：语气有松有紧、句子有长有短，不要写成工整的范文。"
                "若提示中含「领域圣经 DDD」，设定与术语仍须严格遵守，但落实方式要走剧情与细节，"
                "不要用排比和总结句硬凑。"
            ),
        },
        {"role": "user", "content": prompt},
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
        if not new_content:
            return None

        # 清洗误泄露的“计划/提纲/自检”内容，确保只保留章节成文
        leakage_markers = (
            "阶段A", "阶段B", "结构计划", "节拍", "写作意图", "自检",
            "仅内部", "隐式推理", "提纲", "PLAN", "CHECKLIST"
        )
        lines = (new_content or "").splitlines()
        cleaned_lines = []
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                cleaned_lines.append(ln)
                continue
            if any(marker in stripped for marker in leakage_markers):
                continue
            cleaned_lines.append(ln)
        new_content = "\n".join(cleaned_lines).strip()
        
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
