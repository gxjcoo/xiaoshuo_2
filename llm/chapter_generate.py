"""同结构改编：章节正文生成。"""

import json

from config import CHAPTER_GENERATION_MODEL, CHAPTER_GENERATION_TEMPERATURE, ENABLE_LLM_TITLE_GENERATION

from .client import call_deepseek_api
from .prompts import (
    _brief_style_for_generation,
    _reference_prose_snippet,
    _entity_rewrite_block,
    _entity_rewrite_system_addon,
    _slim_context_for_generation,
    _chapter_completion_max_tokens,
)
from .titles import generate_title_from_chapter_content, title_from_existing_heading


def generate_chapter_content(
    current_context,
    writing_style,
    target_length,
    previous_chapter_content=None,
    next_chapter_preview="",
    target_chapter_number=None,
    chapter_plan_text="",
    current_focus_text="",
    audit_requirements_text="",
    reference_chapter_text="",
    reference_plot_outline="",
    strict_source_plot=False,
    prev_chapter_end="",
    next_chapter_start="",
    entity_rewrite=False,
    entity_map=None,
):
    """使用 AI 生成新的章节内容。

    reference_chapter_text: 输入目录参考章原文（仅用于标题兜底；生成阶段不直接注入正文片段）。
    reference_plot_outline: 从参考章提取的结构功能骨架，用于代替原文片段以降低相似度。
    strict_source_plot: 结构功能以参考章为准，衔接上一章优先原作（由调用方传入 previous 内容）。
    """
    if target_chapter_number is None:
        chapter_number = current_context.get("last_generated_chapter", 0) + 1
    else:
        chapter_number = target_chapter_number

    rolling_summaries = current_context.get("recent_chapter_summaries", [])
    if isinstance(rolling_summaries, list) and rolling_summaries:
        rolling_text = "\n".join(
            f"- 第{item.get('chapter', '?')}章：{(item.get('summary', '') or '')[:160]}"
            for item in rolling_summaries[-8:]
            if isinstance(item, dict)
        ).strip()
    else:
        rolling_text = ""

    slim_ctx = _slim_context_for_generation(current_context, writing_chapter_number=chapter_number)
    chapter_number_guard = (
        f"【章节编号（硬约束）】\n"
        f"你必须写且仅写「第 {chapter_number} 章」：第一行标题必须是 `# 第{chapter_number}章`（阿拉伯数字与「章」之间无空格亦可）加空格加副题。\n"
        f"禁止因 JSON 中出现 last_generated_chapter、滚动摘要或其它字段而自行把章号加一（例如已记录到第 1 章却仍要求你写第 1 章时，不得写成第 2 章）。\n\n"
    )
    current_context_summary = (
        f"{chapter_number_guard}"
        "【故事状态（生成侧已压缩，勿逐条扩写成目录式正文）】\n"
        f"{json.dumps(slim_ctx, ensure_ascii=False, indent=2)}\n"
        f"最近章节滚动记忆：\n{rolling_text if rolling_text else '无'}\n"
        f"分卷摘要：{(current_context.get('volume_summaries') or [])[-2:]}"
    )

    style_brief = _brief_style_for_generation(writing_style)
    next_head = (next_chapter_preview or "")[:1800].strip()
    reference_block = ""
    if reference_plot_outline:
        reference_block = (
            "【本章结构功能骨架（由参考章抽取；生成正文只能依据这些结构功能，不得复刻参考原文表达或实体体系）】\n"
            f"```json\n{reference_plot_outline}\n```\n\n"
        )
    elif reference_chapter_text:
        fallback_ref = _reference_prose_snippet(reference_chapter_text, max_chars=900)
        reference_block = (
            "【本章参考结构兜底片段（骨架抽取失败时使用；只取事件功能，禁止沿用句式、实体名和段落推进）】\n"
            f"```\n{fallback_ref}\n```\n\n"
        )

    if strict_source_plot:
        strict_plot_contract = (
            "【同结构改编｜结构功能以骨架为真值，表达与实体必须拉开距离】\n"
            "1) 主事件功能、场景功能、因果位置、人物登场/退场功能与冲突结果功能须与结构骨架一致；不是续写新书、不是扩写无关支线。\n"
            "2) 允许更换人物名、地点名、事件名、动物/物件名和局部承接方式；不得写入骨架中不存在的关键结构功能。\n"
            "3) 禁止沿用参考原文的连续句式、段落推进、开头落点、结尾收束方式和实体体系；同一功能事件必须换一种现场展开。\n"
            "4) 若近期焦点、JSON 上下文或本章意图与结构骨架冲突，一律以结构骨架为准。\n"
            "5) 不得新增改变本章结构功能的支线或替换结局功能。\n\n"
        )
    else:
        strict_plot_contract = (
            "【同结构改编（实验模式：上一段衔接可能来自已生成 output）】\n"
            "本章主干仍以结构骨架为真：不得仅凭 output 衔接或 JSON 上下文编造冲突的新主线、新结局功能或重要结构节点。\n"
            "允许：语气、对白颗粒、感官扩写、镜头入口变化、实体名更换；禁止：贴着参考原文句式或实体体系洗稿。\n\n"
        )

    core_characters = current_context.get('core_characters', [])
    core_items = current_context.get('core_items', [])
    core_elements = f"核心角色：{', '.join(core_characters) if core_characters else '无'}, 核心道具：{', '.join(core_items) if core_items else '无'}"

    if strict_source_plot:
        production_hard_rules = (
            f"【成文忌口（同结构改编专用，从简）】\n"
            f"- 句长错落，少排比；对话两人以上时口气要能区分。\n"
            f"- 少用段尾万能收束（总之/不禁/这一刻/他明白）；少连续内心说明书。\n"
            f"- 系统提示用打断、半句、动作混进戏里，不要连发同一腔调通知框。\n"
            f"- 结构功能跟着骨架走，但实体名、镜头、承接、句式要换，不要贴原文段落。\n"
            f"- 禁止连续 12 个字以上与参考原文相同；避免复用参考章的实体体系、开头句、结尾句和标志性比喻。\n\n"
        )
    else:
        production_hard_rules = (
            f"【产出侧结构硬约束（必须执行）】\n"
            f"1. **事件密度**：每 500-700 字须有一次不可逆变化（冲突升级/关系变化/代价落地/任务状态跃迁其一），"
            f"禁止用大段「解释世界/复盘策略/施工流水账」代替剧情。\n"
            f"2. **解释上限**：连续解释/判断型段落最多 2 段，其后必须插入动作、意外或人物交锋。\n"
            f"3. **角色声纹**：至少两名核心角色在句长、语气词或口癖上稳定可区分，禁止全员书面腔。\n"
            f"4. **开篇信息节奏（尤其无上一章时）**：前 700 字禁止用内心独白/旁白连续「打卡」交代穿越原因、系统功能表、世界观词条；"
            f"设定只通过当下动作、半截对话、被打断的念头漏出，一次只漏一点。\n"
            f"5. **反同构**：开头用动作或异常切入；结尾落在新变量或新压力，不用「总之/这一刻/他明白」式抽象收束。\n"
            f"6. **拒绝清单体**：禁止把「本章意图/待回收线索」写成编号小节或目录句；系统与建设必须长在戏里，不要说明书顺序。\n"
            f"7. **句式**：禁止连续三句长度与节奏几乎相同的陈述；每 400-600 字用环境声、动作或他人插话打断说明腔。\n"
            f"8. **写前自检（脑内即可，禁止输出）**：本段有没有发生新变化？是不是在解释代替戏剧？\n\n"
        )

    if strict_source_plot:
        implicit_two_phase_contract = ""
    else:
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

    zhuque_anti_detection_contract = (
        "【朱雀检测报告针对性避坑】\n"
        "- 不要把氛围写成一串整齐短段：如“风起了/天黑了/灯笼响了/哭声来了”连续排队。需要时把两三句并进人物动作、对话或误判里。\n"
        "- 少用“唰/蹭/咻/猛地/突然/稳稳/直挺挺”等舞台指令词；同一章每类最多偶尔出现，优先写具体物件和身体反应。\n"
        "- 每 800 字左右至少给一处不太规整的人声：抱怨、抢话、半句吞回去、顺手提钱/吃食/旧账/小算盘，让段落有真人岔气。\n"
        "- 不要用旁白替角色贴标签：避免“这是他的固定习惯/专属小动作/标准性子/每句末尾总爱……”这类说明。让习惯自己出现，别解释它。\n"
        "- 口癖只能点到为止。同一段对白里同一个尾音最多 1-2 次，其余用停顿、吞字、动作和具体抱怨区分声线。\n"
        "- 设定交代不要连续三段平铺。能从动作看出来的别解释，必须交代时夹在人物正在做的事里。\n"
        "- 保留一点粗糙边角：长短段混排，允许一句话没说满，避免每段都像完成了起承转合。\n\n"
    )

    core_requirements = (
        f"{reference_block}"
        f"{strict_plot_contract}"
        + (
            "【下一章开头硬约束（用于避免断章冲突）】\n"
            "本章结尾必须能自然接入下列下一章开头；不得改变下一章开头已经确定的追问对象、冲突对象、人物关系和误会指向。\n"
            "如果下一章开头揭示某句喊话并非冲着主角，就不能在本章结尾写成主角已被明确抓捕或定罪。\n"
            f"```\n{next_head}\n```\n\n"
            if next_head else ""
        )
        + f"【语言风格备忘（非提纲；禁止模仿下列编号、小标题或分析腔落笔）】\n{style_brief}\n\n"
        f"{current_context_summary}\n\n"
        f"{core_elements}\n\n"
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}"
        f"{'（严格模式下若与参考原文冲突则忽略）' if strict_source_plot else '（优先于长期意图）'}\n\n"
        f"【审计规则前置约束（写作时必须遵守）】\n{audit_requirements_text if audit_requirements_text else '无'}\n\n"
        f"【本章意图（须融化进场景；不得脱离结构骨架编造新主线）】\n"
        f"{chapter_plan_text if chapter_plan_text else '无（仍须严格按结构骨架的功能节点与场次写）'}\n\n"
        f"{implicit_two_phase_contract}"
        f"{zhuque_anti_detection_contract}"
        f"{production_hard_rules}"
        f"{_entity_rewrite_block(entity_rewrite, entity_map)}"
        f"【核心创作要求】：\n"
        f"1. **风格**：同结构改编也要像真人落笔；幽默从处境里长出来，不要为搞笑而堆梗。\n"
        f"2. **连贯**：人物反应符合参考中的当下压力；设定不与参考冲突。\n"
        f"3. **标题**：第 {chapter_number} 章单行标题，格式 `# 第{chapter_number}章 …` 置于最前。\n"
        f"4. **字数**：约 {target_length} 字；允许语意跳跃，不必写满「说明」才算完成。\n"
        f"5. **表达**：对话/叙述/内心交替出现，但内心勿承担世界观说明书职能。\n"
        f"6. **系统/UI**：用打断、误触、半句播报或动作衔接，避免连发同一腔调提示框。\n\n"
    )

    prompt_instruction = ""

    if previous_chapter_content:
        print(f"正在同结构改编第 {chapter_number} 章（带上一段衔接）…")
        previous_ending = previous_chapter_content[-2000:]
        cont_note = ""
        if strict_source_plot:
            cont_note = (
                "【衔接说明】下列「上一章节选」来自 input 原作上一章（若曾回退则为 output，仍以本章参考为情节真值）。\n"
            )
        else:
            cont_note = "【衔接说明】上一段可能来自 output；本章情节仍以 input 参考为准，不得据衔接段新编主线。\n"
        prompt_instruction = (
            core_requirements +
            f"【同结构改编衔接（仅连贯口语气与镜头，不另起故事）】：\n"
            f"{cont_note}"
            f"1. 正文从下列节选自然接入，时间线连续；不得引入参考结构中尚未出现的重大新功能节点。\n"
            f"   上一章节选：\n   ```\n   {previous_ending}\n   ```\n"
            f"2. 情绪与信息推进须落在本章结构骨架已有的功能节点上，不得写成「续写下一本书」。\n"
            f"3. 角色反应功能与参考一致，但实体名、动作细节、对白颗粒应改编。\n"
            f"4. 禁止为拉长篇幅而插入与参考结构无关的重要支线。\n"
        )
    else:
        print(f"正在同结构改编第 {chapter_number} 章（无上一段衔接）…")
        prompt_instruction = (
            core_requirements +
            f"【同结构改编开篇】：\n"
            f"1. 仅覆盖本章 input 参考中的结构功能与场次功能，不得改主线因果位置，也不是创作全新开篇故事。\n"
            f"{'2. 不得跳过参考中的关键功能场次，但可以更换实体名和局部承接。' if strict_source_plot else '2. 勿整段复述，可作对白、实体和感官改编。'}\n"
            f"3. 从现场与动作进入，少用说明书式内心。\n"
            f"4. 结尾若出现追喊、追杀、误会、拦路等钩子，必须与下一章开头的真实指向一致。\n"
        )

    bidirectional_contract = ""
    if prev_chapter_end or next_chapter_start:
        bidirectional_contract = "【双向衔接硬约束（必须遵守）】\n"
        if prev_chapter_end:
            bidirectional_contract += (
                f"上一章结尾的真实内容如下（本开头必须与之自然衔接，时间线和情绪不可断裂）：\n"
                f"```\n{prev_chapter_end}\n```\n"
            )
        if next_chapter_start:
            bidirectional_contract += (
                f"下一章开头的真实内容如下（本结尾钩子必须与之匹配，对象/指向/事件不可矛盾）：\n"
                f"```\n{next_chapter_start}\n```\n"
            )
        bidirectional_contract += (
            "核心规则：\n"
            "1. 开头：必须从上章结尾自然接入，不可「强行切换场景」或「跳时间线」。\n"
            "2. 结尾：生成钩子的对象/事件/指向必须与下一章开头一致。"
            " 例如：下一章开头是「妖道追杀」，本章结尾就应当是「妖道出现」，而不是「主角被抓」。\n\n"
        )

    prompt = prompt_instruction + bidirectional_contract
    system_content = (
        "你是一位小说同结构改编作家：依据结构骨架输出同一功能链的新正文，语气有松有紧、句子有长有短，拒绝范文腔。"
        "不是自由续写、不是扩写新故事线、不是同人另起炉灶；提示中的分析/意图是备忘，禁止把提示结构映射成新章节大纲。"
        "必须主动避开参考原文的实体体系、句式骨架、段落推进、开头和结尾表达。"
        "禁止用「心里咯噔一下/不禁/这一刻/显然」等万能情绪套话收束段落。"
    )
    if strict_source_plot:
        system_content += " 当前为严格结构适配：本章结构骨架即功能真值，可以换实体、表达和镜头承接，不可改结构功能。"
    else:
        system_content += " 当前为同结构改编实验模式：衔接可能非原作，但本章主干仍以结构骨架为准。"
    system_content += _entity_rewrite_system_addon(entity_rewrite, entity_map)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]

    try:
        new_content = call_deepseek_api(
            messages,
            CHAPTER_GENERATION_MODEL,
            max_tokens=_chapter_completion_max_tokens(target_length),
            temperature=CHAPTER_GENERATION_TEMPERATURE,
            task_label=f"第{chapter_number}章正文生成",
        )
        if not new_content:
            return None

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

        content_lines = new_content.splitlines()
        original_heading = content_lines[0].strip() if content_lines else ""
        body_lines = content_lines
        if content_lines and content_lines[0].strip().startswith("#"):
            body_lines = content_lines[1:]
            if body_lines and not body_lines[0].strip():
                body_lines = body_lines[1:]
        body_text = "\n".join(body_lines).strip()
        if ENABLE_LLM_TITLE_GENERATION:
            generated_title = generate_title_from_chapter_content(
                chapter_number,
                body_text,
                reference_chapter_text=reference_chapter_text,
            )
        else:
            generated_title = title_from_existing_heading(
                chapter_number,
                heading_text=original_heading,
                chapter_content=body_text,
                reference_chapter_text=reference_chapter_text,
            )
        new_content = f"# {generated_title}\n\n{body_text}" if body_text else f"# {generated_title}\n"

        return new_content
    except Exception as e:
        print(f"生成新章节内容时发生错误: {e}")
        return None
