"""LLM 驱动的修订器：四种针对不同失败模式的定向重写。

- `revise_for_plot_fidelity`：结构骨架偏离
- `rewrite_for_expression_distance`：与参考章表达过像
- `anti_ai_rewrite_with_reference`：AI 味重
- `revise_chapter_by_audit_feedback`：按审计反馈做最小修订（通用兜底）
"""

import json

from ai_handler import call_deepseek_api
from .metrics import _basic_style_metrics


def revise_for_plot_fidelity(
    reference_plot_outline,
    chapter_content,
    plot_report,
    chapter_number,
    chapter_plan_text="",
    model="deepseek-chat",
):
    """按结构骨架审计结果修正文稿，优先补齐缺失功能节点与纠正偏离。"""
    report_json = json.dumps(plot_report, ensure_ascii=False, indent=2)
    prompt = (
        f"请修订第 {chapter_number} 章，使其重新贴合结构功能骨架。\n"
        "硬要求：\n"
        "1) 补齐 missing_events，纠正 drift_issues，删除或弱化 wrong_added_facts。\n"
        "2) 不要照抄结构骨架或参考原文，要写成自然小说正文。\n"
        "3) 保持当前正文已有的表达与实体差异，不要为了贴合结构而改回参考章句式或实体体系。\n"
        "4) 只输出完整修订后章节。\n\n"
        f"【结构骨架】\n```json\n{reference_plot_outline}\n```\n\n"
        f"【剧情偏离报告】\n{report_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【当前正文】\n{chapter_content}"
    )
    messages = [
        {"role": "system", "content": "你是小说结构修订编辑，优先修正结构偏离，同时保持表达和实体体系与参考文拉开距离。"},
        {"role": "user", "content": prompt},
    ]
    revised = call_deepseek_api(messages, model, max_tokens=len(chapter_content) + 1600, temperature=0.42)
    if not revised:
        return chapter_content
    revised = revised.strip()
    if revised and not revised.startswith("# "):
        revised = f"# 第{chapter_number}章 修订稿\n\n{revised}"
    return revised


def rewrite_for_expression_distance(
    reference_text,
    chapter_content,
    similarity_report,
    chapter_number,
    chapter_plan_text="",
    model="deepseek-chat",
):
    """保留剧情事实，重写表达结构，专门处理与参考章过像的问题。"""
    report_json = json.dumps(similarity_report, ensure_ascii=False, indent=2)
    prompt = (
        f"请对第 {chapter_number} 章做一次“剧情不变、表达降重”的完整重写。\n"
        "目标：降低与参考章的连续字串、句式骨架、段落推进和开头/结尾相似度。\n\n"
        "硬要求：\n"
        "1) 保留当前正文里的主事件、人物动机、因果关系和结尾状态。\n"
        "2) 重排镜头入口、动作承接、对话切入顺序和段落节奏；同一事件换一种现场展开。\n"
        "3) 禁止连续 12 个字以上与参考章一致，尤其避开 matched_samples 中的表达。\n"
        "4) 不要新增改变剧情的关键事实，不要改人物关系结果。\n"
        "5) 只输出修订后的完整章节，标题格式仍为 `# 第N章 副题`。\n\n"
        f"【相似度报告】\n{report_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【参考章片段（只用于避开重复表达，不得仿句）】\n{(reference_text or '')[:1200]}\n\n"
        f"【待降重正文】\n{chapter_content}"
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
    )
    if not rewritten:
        return chapter_content
    rewritten = rewritten.strip()
    if rewritten and not rewritten.startswith("# "):
        rewritten = f"# 第{chapter_number}章 修订稿\n\n{rewritten}"
    return rewritten


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
        f"请对第 {chapter_number} 章做一次“保剧情、不改设定”的去模板化改写，以降低 AI 痕迹。\n"
        f"硬要求：\n"
        f"1) 不改变主事件、人物关系、世界设定、章节目标。\n"
        f"2) 主要修表达层：句长错落、减少说明文收束、减少工整排比。\n"
        f"3) 对话更口语化，允许打断、半句、停顿、抢话、说一半咽回去。\n"
        f"4) 增加动作/感官细节，减少抽象总结；允许略「糙」、略碎，不要润成光滑范文。\n"
        f"5) 刻意制造几处短段、一声一动的顿挫，少用「然而/因此/这一刻」类连接与收束。\n"
        f"6) 必须优先修复【规则命中】中的问题，逐项消除。\n"
        f"7) 仅输出修订后的完整章节。\n\n"
        f"{findings_text}"
        f"【参考文风格指标（只用于节奏差异判断，不得仿句）】\n{json.dumps(_basic_style_metrics(reference_text), ensure_ascii=False, indent=2)}\n\n"
        f"【风格差异对比(JSON)】\n{json.dumps(style_compare, ensure_ascii=False, indent=2)}\n\n"
        f"【既有风格分析（节选）】\n{style_snip if style_snip else '无'}\n\n"
        f"【本章意图规划】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【待改写章节】\n{chapter_content}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深网文改稿编辑：保留结构骨架，专门打掉模板腔、说明腔、排比与段尾万能升华。"
                "改完要像人在连载站点直接发章——允许碎、糙、打断，不要改成语文阅读题标准答案。"
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
    )
    if not rewritten:
        return chapter_content
    rewritten = rewritten.strip()
    if rewritten and not rewritten.startswith("# "):
        rewritten = f"# 第{chapter_number}章 修订稿\n\n{rewritten}"
    return rewritten


def revise_chapter_by_audit_feedback(
    chapter_content,
    chapter_number,
    writing_style,
    audit_result,
    chapter_plan_text="",
    author_intent_text="",
    current_focus_text="",
    focus_dimensions=None,
    model="deepseek-chat",
):
    """基于审计反馈做一次针对性修订。"""
    feedback_json = json.dumps(audit_result, ensure_ascii=False, indent=2)
    focus_dimensions = focus_dimensions or []
    focus_text = "、".join(str(x).strip() for x in focus_dimensions if str(x).strip()) or "issues 中最高优先级问题"
    prompt = (
        f"请根据审计结果修订第 {chapter_number} 章，仅修复问题，不改变核心剧情走向。\n"
        f"要求：\n"
        f"1) 本轮只优先修复这些维度：{focus_text}。\n"
        f"2) 保持原文风格与角色设定。\n"
        f"3) 除上述维度外，其他内容仅做最小改动，禁止大改剧情结构。\n"
        f"4) 输出完整修订后正文。\n\n"
        f"【审计结果】\n{feedback_json}\n\n"
        f"【风格分析】\n{writing_style}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【作者长期意图】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}\n\n"
        f"【当前正文】\n{chapter_content}"
    )
    messages = [
        {"role": "system", "content": "你是小说改稿编辑，按反馈精修但不改剧情主干。"},
        {"role": "user", "content": prompt},
    ]
    revised = call_deepseek_api(messages, model, max_tokens=len(chapter_content) + 1400, temperature=0.35)
    if not revised:
        return chapter_content
    revised = revised.strip()
    if revised and not revised.startswith("# "):
        revised = f"# 第{chapter_number}章 修订稿\n\n{revised}"
    return revised
