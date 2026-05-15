"""伏笔与分卷摘要抽取。"""

import json

from config import CONTEXT_ANALYSIS_MODEL, VOLUME_CHAPTER_SIZE

from .client import call_deepseek_api


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
