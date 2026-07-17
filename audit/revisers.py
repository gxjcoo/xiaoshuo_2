"""LLM 驱动的修订器：四种针对不同失败模式的定向重写。

- `revise_for_plot_fidelity`：结构骨架偏离
- `rewrite_for_expression_distance`：与参考章表达过像
- `anti_ai_rewrite_with_reference`：AI 味重
- `revise_chapter_by_audit_feedback`：按审计反馈做最小修订（通用兜底）
"""

import json

from ai_handler import call_deepseek_api
from .metrics import _basic_style_metrics


def _normalize_revised_output(revised: str, chapter_number: int, original_title: str) -> str:
    """统一处理修订后输出：提取标题、规范化、重组。

    Args:
        revised: LLM 返回的修订后文本
        chapter_number: 章节号
        original_title: 原始标题（LLM 未返回标题时使用）

    Returns:
        规范化后的文本，格式为 "# 标题\n\n正文"
    """
    from llm.titles import normalize_chapter_title

    if not revised or not revised.strip():
        return revised

    revised = revised.strip()

    # 提取正文内容用于副标题提取
    body_content = ""
    has_title = revised.startswith("# ")

    if has_title:
        lines = revised.split("\n")
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        body_content = "\n".join(body_lines)
    else:
        body_content = revised

    # 标准化标题格式
    if has_title:
        lines = revised.split("\n")
        title_text = lines[0].lstrip("# ").strip()
        normalized_title = normalize_chapter_title(title_text, chapter_number, body_content)
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        return f"# {normalized_title}\n\n" + "\n".join(body_lines)
    elif original_title:
        normalized_title = normalize_chapter_title(original_title, chapter_number, body_content)
        return f"# {normalized_title}\n\n{revised}"

    return revised


def revise_for_plot_fidelity(
    reference_plot_outline,
    chapter_content,
    plot_report,
    chapter_number,
    chapter_plan_text="",
    model="deepseek-chat",
):
    """按结构骨架审计结果修正文稿，优先补齐缺失功能节点与纠正偏离。"""
    # 提取原标题（如果有）
    original_title = ""
    content_body = chapter_content
    if chapter_content and chapter_content.strip().startswith("# "):
        lines = chapter_content.strip().splitlines()
        original_title = lines[0].lstrip("# ").strip()
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        content_body = "\n".join(body_lines)
    
    report_json = json.dumps(plot_report, ensure_ascii=False, indent=2)
    prompt = (
        f"请修订第 {chapter_number} 章，使其重新贴合结构功能骨架。\n"
        "硬要求：\n"
        "1) 补齐 missing_events，纠正 drift_issues，删除或弱化 wrong_added_facts。\n"
        "2) 不要照抄结构骨架或参考原文，要写成自然小说正文。\n"
        "3) 保持当前正文已有的表达与实体差异，不要为了贴合结构而改回参考章句式或实体体系。\n"
        f"4) 保留原标题「{original_title}」，只输出标题和修订后正文。标题格式必须为 `# 标题`，标题后直接开始正文，不要在正文中重复标题。\n\n"
        f"【结构骨架】\n```json\n{reference_plot_outline}\n```\n\n"
        f"【剧情偏离报告】\n{report_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【当前正文】\n{content_body}"
    )
    messages = [
        {"role": "system", "content": "你是小说结构修订编辑，优先修正结构偏离，同时保持表达和实体体系与参考文拉开距离。"},
        {"role": "user", "content": prompt},
    ]
    revised = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1600,
        temperature=0.42,
        task_label=f"第{chapter_number}章结构纠偏修订",
    )
    if not revised:
        return chapter_content
    return _normalize_revised_output(revised.strip(), chapter_number, original_title)


def rewrite_for_expression_distance(
    reference_text,
    chapter_content,
    similarity_report,
    chapter_number,
    chapter_plan_text="",
    model="deepseek-chat",
):
    """保留剧情事实，重写表达结构，专门处理与参考章过像的问题。"""
    # 提取原标题（如果有）
    original_title = ""
    content_body = chapter_content
    if chapter_content and chapter_content.strip().startswith("# "):
        lines = chapter_content.strip().splitlines()
        original_title = lines[0].lstrip("# ").strip()
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        content_body = "\n".join(body_lines)
    
    report_json = json.dumps(similarity_report, ensure_ascii=False, indent=2)
    prompt = (
        f"请对第 {chapter_number} 章做一次'剧情不变、表达降重'的完整重写。\n"
        "目标：降低与参考章的连续字串、句式骨架、段落推进和开头/结尾相似度。\n\n"
        "硬要求：\n"
        "1) 保留当前正文里的主事件、人物动机、因果关系和结尾状态。\n"
        "2) 重排镜头入口、动作承接、对话切入顺序和段落节奏；同一事件换一种现场展开。\n"
        "3) 禁止连续 12 个字以上与参考章一致，尤其避开 matched_samples 中的表达。\n"
        "4) 不要新增改变剧情的关键事实，不要改人物关系结果。\n"
        f"5) 保留原标题「{original_title}」，只输出标题和修订后正文。标题格式必须为 `# 标题`，标题后直接开始正文，不要在正文中重复标题。\n\n"
        f"【相似度报告】\n{report_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【参考章片段（只用于避开重复表达，不得仿句）】\n{(reference_text or '')[:1200]}\n\n"
        f"【待降重正文】\n{content_body}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是小说降重改稿编辑。你的任务不是润色得更像参考文，"
                "而是在剧情不变的前提下主动拉开表达距离，避免句式和段落同构。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    rewritten = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1600,
        temperature=0.58,
        task_label=f"第{chapter_number}章表达降重重写",
    )
    if not rewritten:
        return chapter_content
    return _normalize_revised_output(rewritten.strip(), chapter_number, original_title)


def anti_ai_rewrite_with_reference(
    reference_text,
    chapter_content,
    style_compare,
    chapter_number,
    writing_style,
    chapter_plan_text="",
    ai_trace_findings=None,
    model="deepseek-chat",
):
    """参考原文风格和差异，执行定向去模板化重写。"""
    # 提取原标题（如果有）
    original_title = ""
    content_body = chapter_content
    if chapter_content and chapter_content.strip().startswith("# "):
        lines = chapter_content.strip().splitlines()
        original_title = lines[0].lstrip("# ").strip()
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        content_body = "\n".join(body_lines)
    
    findings_text = ""
    if ai_trace_findings:
        lines = []
        for item in ai_trace_findings[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- [{item.get('rule', 'unknown')}] {item.get('description', '')}；修复建议：{item.get('suggestion', '')}"
            )
        if lines:
            findings_text = "【规则命中（必须优先修复）】\n" + "\n".join(lines) + "\n\n"

    style_snip = (writing_style or "").strip()
    if len(style_snip) > 1400:
        style_snip = style_snip[:1400] + "\n…（风格分析已截断）"

    prompt = (
        f"请对第 {chapter_number} 章做一次'保剧情、不改设定'的去模板化改写，以降低 AI 痕迹。\n"
        f"硬要求：\n"
        f"1) 不改变主事件、人物关系、世界设定、章节目标。\n"
        f"2) 主要修表达层：句长错落、减少说明文收束、减少工整排比。\n"
        f"3) 对话更口语化，允许打断、半句、停顿、抢话、说一半咽回去。\n"
        f"4) 增加动作/感官细节，减少抽象总结；允许略「糙」、略碎，不要润成光滑范文。\n"
        f"5) 刻意制造几处短段、一声一动的顿挫，少用「然而/因此/这一刻」类连接与收束。\n"
        f"6) 必须优先修复【规则命中】中的问题，逐项消除。\n"
        f"7) 针对朱雀类检测：打散连续短句氛围铺陈，删减'唰/蹭/咻/猛地/突然/稳稳/直挺挺'等镜头指令词。\n"
        f"8) 至少保留或新增两处不规整的人声：抱怨、抢话、旧账、小算盘、吃食/钱数等生活化岔话；不要都写成工整对白。\n"
        f"9) 删除或改写旁白标签句：如'这是他的固定习惯/专属小动作/标准性子/每句末尾总爱……'。让读者从动作和对话看出来。\n"
        f"10) 口癖不要刷屏，同一段对白同一个语气尾音最多保留 1-2 个。\n"
        f"11) 降低'圆满解释腔'：少用'据说/总算/反而/徒增变数/名正言顺/幸不辱命/日后清净/风险几乎为零'等官样连接和结论词。\n"
        f"12) 不要把所有因果补齐到教案程度；保留误判、临时借口、吞字、前后小算盘，让读者从现场拼出来。\n"
        f"13) 保留原标题「{original_title}」，只输出标题和修订后正文。标题格式必须为 `# 标题`，标题后直接开始正文，不要在正文中重复标题。\n\n"
        f"{findings_text}"
        f"【参考文风格指标（只用于节奏差异判断，不得仿句）】\n{json.dumps(_basic_style_metrics(reference_text), ensure_ascii=False, indent=2)}\n\n"
        f"【风格差异对比(JSON)】\n{json.dumps(style_compare, ensure_ascii=False, indent=2)}\n\n"
        f"【既有风格分析（节选）】\n{style_snip if style_snip else '无'}\n\n"
        f"【本章意图规划】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【待改写章节】\n{content_body}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深网文改稿编辑：保留结构骨架，专门打掉模板腔、说明腔、排比与段尾万能升华。"
                "改完要像人在连载站点直接发章——允许碎、糙、打断，不要改成语文阅读题标准答案。"
                "朱雀报告中人工占比更高的段落通常有不规整对白、生活化岔话和长短段混排，优先往这个方向修。"
                "不要用说明标签介绍角色声纹或习惯，也不要用重复口癖硬凹人设。"
                "尤其避免把所有转折、动机、后果都解释得干净圆整；网文连载稿可以有半截话和现场小毛边。"
                "参考原文片段只借语感与节奏，不要全文仿句式堆砌。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    rewritten = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1200,
        temperature=0.62,
        task_label=f"第{chapter_number}章去AI味修订",
    )
    if not rewritten:
        return chapter_content
    return _normalize_revised_output(rewritten.strip(), chapter_number, original_title)


def revise_chapter_by_audit_feedback(
    chapter_content,
    chapter_number,
    writing_style,
    audit_result,
    chapter_plan_text="",
    current_focus_text="",
    focus_dimensions=None,
    model="deepseek-chat",
):
    """基于审计反馈做一次针对性修订。"""
    # 提取原标题（如果有）
    original_title = ""
    content_body = chapter_content
    if chapter_content and chapter_content.strip().startswith("# "):
        lines = chapter_content.strip().splitlines()
        original_title = lines[0].lstrip("# ").strip()
        body_lines = lines[1:]
        while body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
        content_body = "\n".join(body_lines)
    
    feedback_json = json.dumps(audit_result, ensure_ascii=False, indent=2)
    focus_dimensions = focus_dimensions or []
    focus_text = "、".join(str(x).strip() for x in focus_dimensions if str(x).strip()) or "issues 中最高优先级问题"
    prompt = (
        f"请根据审计结果修订第 {chapter_number} 章，仅修复问题，不改变核心剧情走向。\n"
        f"要求：\n"
        f"1) 本轮只优先修复这些维度：{focus_text}。\n"
        f"2) 保持原文风格与角色设定。\n"
        f"3) 除上述维度外，其他内容仅做最小改动，禁止大改剧情结构。\n"
        f"4) 如果审计结果包含'镜头指令词过密/短句阶梯铺陈/句长同质化'，优先把连续短段并入动作或对白，减少'唰/蹭/猛地/突然'式调度词。\n"
        f"5) 如果审计结果包含'角色标签说明过密/口癖刷屏'，删掉旁白标签句，压缩重复口癖，让习惯从动作和反应里露出来。\n"
        f"6) 保留原标题「{original_title}」，只输出标题和修订后正文。标题格式必须为 `# 标题`，标题后直接开始正文，不要在正文中重复标题。\n\n"
        f"【审计结果】\n{feedback_json}\n\n"
        f"【风格分析】\n{writing_style}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}\n\n"
        f"【当前正文】\n{content_body}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是小说改稿编辑，按反馈精修但不改剧情主干。"
                "遇到 AI 痕迹反馈时，优先制造真人写作的节奏毛边：不规整对白、长短段混排、动作里夹生活细节。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    revised = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1400,
        temperature=0.35,
        task_label=f"第{chapter_number}章审计反馈修订",
    )
    if not revised:
        return chapter_content
    return _normalize_revised_output(revised.strip(), chapter_number, original_title)
