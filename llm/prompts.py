"""提示词拼装辅助：风格备忘、参考片段、实体禁令、生成侧上下文瘦身。"""

import re


def _brief_style_for_generation(writing_style, max_chars=1100):
    """风格分析往往带 Markdown 条目，直接全文注入易诱发「分析腔/清单体」正文。"""
    if not isinstance(writing_style, str) or not writing_style.strip():
        return "（风格备忘缺失：保持口语、松紧交替，少用抽象收束句。）"
    s = writing_style.strip()
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 24].rstrip() + "\n…(备忘已截断；禁止模仿其中小标题、编号与排比结构。)"


def _reference_prose_snippet(text, max_chars=2600):
    """截取参考原文供对齐语感；避免只喂分析报告导致写法「像写论文」。"""
    if not isinstance(text, str) or not text.strip():
        return ""
    s = text.strip()
    if len(s) <= max_chars:
        return s
    head = s[: max_chars - 320]
    tail = s[-280:]
    return f"{head.rstrip()}\n\n…(参考原文中部已省略)…\n\n{tail.lstrip()}"


def _entity_rewrite_block(enabled: bool, entity_map) -> str:
    """生成实体改写禁令块。列出**全部**映射，避免 LLM 只看到部分而沿用其他原名。"""
    if not enabled or not entity_map or not isinstance(entity_map, dict):
        return ""
    label = {
        "characters": "角色名",
        "places": "地名",
        "events": "事件名",
        "objects_animals": "物件/动物名",
    }
    lines = ["【实体改写禁令（硬约束，违反直接判不合格；下表为本书全局统一新名）】"]
    has_any = False
    for cat in ("characters", "places", "events", "objects_animals"):
        mapping = entity_map.get(cat, {}) if isinstance(entity_map, dict) else {}
        if not mapping:
            continue
        has_any = True
        items = [f"{old}→{new}" for old, new in mapping.items()]
        lines.append(f"- {label[cat]}（共 {len(items)} 条，必须用新名）：")
        chunk_size = 8
        for i in range(0, len(items), chunk_size):
            lines.append("    " + "、".join(items[i:i + chunk_size]))
    if not has_any:
        return ""
    lines.append("- 上述任何【原名】不得出现在正文（含对话、内心独白、叙述、地名、招式、动物名等任何位置）。")
    lines.append("- 与原名同字的常用词若非实体（如'宝'是普通字而非'宝寿'里的角色字）可保留；但凡作为人名/地名/物件名连用即视为违规。")
    lines.append("- 代称（他/她/它/那人/那道士）不受此限。")
    lines.append("- 出现任意一处原名都会触发硬替换并扣分，影响落盘。\n")
    return "\n".join(lines) + "\n"


def _entity_rewrite_system_addon(enabled: bool, entity_map) -> str:
    """system 消息追加的实体硬禁令摘要，提高 LLM 的注意权重。"""
    if not enabled or not entity_map or not isinstance(entity_map, dict):
        return ""
    chars = entity_map.get("characters", {}) or {}
    places = entity_map.get("places", {}) or {}
    char_items = list(chars.items())[:6]
    place_items = list(places.items())[:4]
    parts = []
    if char_items:
        parts.append("角色改名：" + "、".join(f"{o}→{n}" for o, n in char_items))
    if place_items:
        parts.append("地名改名：" + "、".join(f"{o}→{n}" for o, n in place_items))
    if not parts:
        return ""
    return (
        " 本任务启用实体全局改写：参考资料里可能仍有原名，但正文必须用新名。"
        + "；".join(parts)
        + "（完整映射见用户消息中的实体改写禁令块）。任何原名出现都会被判为硬错误。"
    )


def _slim_context_for_generation(current_context, writing_chapter_number=None):
    """生成侧瘦身：完整 JSON 易诱发按 pending_hooks/设定清单扩写。

    writing_chapter_number: 本次正在生成的章节号；用于消解 last_generated_chapter 被误读为「下一章」。
    """
    if not isinstance(current_context, dict):
        return {}
    pi = current_context.get("protagonist_info") or {}
    ws = current_context.get("world_setting") or {}
    slim_pi = {}
    if isinstance(pi, dict):
        slim_pi = {
            "name": pi.get("name"),
            "description": (pi.get("description") or "")[:220],
            "status_summary": (pi.get("status_summary") or "")[:300],
        }
        items = pi.get("key_items_abilities")
        if isinstance(items, list):
            slim_pi["key_items_abilities"] = [str(x)[:90] for x in items[:5]]
        rel = pi.get("key_relationships")
        if isinstance(rel, dict):
            keys = list(rel.keys())[:6]
            slim_pi["key_relationships"] = {k: str(rel[k])[:110] for k in keys}
    slim_ws = {}
    if isinstance(ws, dict):
        slim_ws = {
            "description": (ws.get("description") or "")[:220],
            "location": (ws.get("location") or "")[:220],
        }
        el = ws.get("key_elements")
        if isinstance(el, list):
            slim_ws["key_elements"] = [str(x)[:100] for x in el[:6]]
    hooks = current_context.get("pending_hooks") or []
    if isinstance(hooks, list):
        hooks = [str(h)[:120] for h in hooks[-8:]]
    else:
        hooks = []
    out = {
        "last_generated_chapter": current_context.get("last_generated_chapter", 0),
        "protagonist_info": slim_pi,
        "world_setting": slim_ws,
        "recent_plot_summary": (current_context.get("recent_plot_summary") or "")[:450],
        "pending_hooks": hooks,
    }
    if writing_chapter_number is not None:
        out["本次须输出的章节号"] = int(writing_chapter_number)
        out["_说明"] = (
            "last_generated_chapter 仅表示 story_context.json 里上次落盘更新过的章节号，"
            "重跑同一章时可能与「本次须输出的章节号」相同；标题与正文中的章号必须与「本次须输出的章节号」一致，禁止自增成下一章。"
        )
    return out


def _chapter_completion_max_tokens(target_length):
    """中文正文约 1.5–2 token/字；target_length 为期望字数时不可把 max_tokens 当字数用。"""
    try:
        n = int(target_length)
    except Exception:
        n = 3000
    return max(2048, int(n * 2.2) + 512)
