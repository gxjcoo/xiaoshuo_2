"""本章意图规划（短文本）。"""

import json

from config import CHAPTER_GENERATION_MODEL

from .client import call_deepseek_api
from .prompts import _reference_prose_snippet


def plan_chapter_with_ai(
    current_context,
    target_chapter_number,
    previous_chapter_content=None,
    next_chapter_preview="",
    author_intent_text="",
    current_focus_text="",
    reference_chapter_text="",
    strict_source_plot=False,
):
    """生成本章意图规划（短文本），用于约束正文生成焦点。"""
    context_json = json.dumps(current_context, ensure_ascii=False, indent=2)
    previous_tail = (previous_chapter_content or "")[-1200:]
    next_head = (next_chapter_preview or "")[:1600]
    ref_snip = ""
    strict_head = ""
    if strict_source_plot and (reference_chapter_text or "").strip():
        ref_snip = _reference_prose_snippet(reference_chapter_text, max_chars=4200)
        strict_head = (
            "【模式：严格结构适配，表达与实体去同构】\n"
            "本章意图必须能从「本章参考原文节选」中推导：只拆解已有场景功能、冲突功能与信息点，写成可执行改编点；"
            "不得新增参考原文里不存在的关键结构功能、不得改因果位置与结局功能。"
            "不要摘抄原文句子，不要把原文段落节奏写成计划。\n"
            "若与【作者长期意图】【近期焦点】或 JSON 上下文冲突，一律以参考原文为准，其余仅作语气参考。\n\n"
            f"【本章参考原文节选（意图规划唯一情节依据）】\n```\n{ref_snip}\n```\n\n"
        )
    prompt = (
        f"{strict_head}"
        f"【章节号】你正在为第 {target_chapter_number} 章列写作意图；不得把对象误写成第 {target_chapter_number + 1} 章。\n\n"
        f"你是小说章节规划师。请为第 {target_chapter_number} 章输出一份简洁可执行的写作意图。\n\n"
        f"输出要求：\n"
        f"1) 只输出纯文本，不要 Markdown 表格。\n"
        f"2) 控制在 8 条以内，每条一句话。\n"
        f"3) 至少包含：主线推进、角色变化、关键冲突、伏笔/回收点。\n"
        f"4) 不得与既有设定冲突，不得新增未铺垫的大设定。\n"
        f"5) 用自然语言短句列出即可，不要写成正文片段或带编号的小标题目录。\n\n"
        f"【当前上下文】\n{context_json}\n\n"
        f"【上一章结尾（衔接用，可选）】\n{previous_tail if previous_tail else '无'}\n\n"
        f"【下一章开头（本章结尾硬约束，可选）】\n{next_head if next_head else '无'}\n\n"
        f"【作者长期意图（可选）】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点（可选）】\n{current_focus_text if current_focus_text else '无'}\n"
    )
    system_msg = "你擅长把「同结构改编」任务拆成可执行写作点：只拆解参考里的结构功能，不发明新主线，也不复刻原文表达和实体体系。"
    if strict_source_plot and ref_snip:
        system_msg += " 当前为严格结构适配：意图必须与参考原文场次功能一一对应，不得添加参考中不存在的关键功能，但表达结构和实体体系要为后续改编留出距离。"
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]
    plan_text = call_deepseek_api(messages, CHAPTER_GENERATION_MODEL, max_tokens=800, temperature=0.3)
    if not plan_text:
        return ""
    return plan_text.strip()
