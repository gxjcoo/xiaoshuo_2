"""
实体改写映射 - 同结构改编的核心降重层

设计要点：
1. **项目级全局映射**（runtime/global_entity_map.json）带元数据：
   {"characters": {"原名": {"new": "新名", "first_seen_chapter": 3}}}
   确保同一原名跨章永远映射到同一新名，并可反查来源章节。
2. **章节级缓存**（runtime/chapter-XXXX.entity_map.json）保留扁平映射：
   {"characters": {"原名": "新名"}}，便于人读和排查。
3. **格式互通**：apply_entity_rewrite / detect_original_entity_leaks 同时
   接受扁平格式与带元数据格式，内部统一归一为扁平表。
4. **分段扫描**：长章按段落分块送进 LLM，避免后半实体被截断。
5. **硬清洗**：apply_entity_rewrite 按原名长度降序替换，避免短名子串误吞长名；
   detect_original_entity_leaks 输出残留明细，供审计/修订提示用。
"""

import datetime as _dt
import json
import os
from typing import Dict, List, Optional, Union

from config import RUNTIME_DIR, CONTEXT_ANALYSIS_MODEL
from ai_handler import call_deepseek_api

ENTITY_CACHE_SUFFIX = "entity_map.json"
GLOBAL_ENTITY_MAP_FILE = "global_entity_map.json"
ENTITY_CATEGORIES = ("characters", "places", "events", "objects_animals")

# 章节级映射值类型：str（扁平格式）
# 全局映射值类型：dict（带元数据）或 str（向后兼容旧格式）
EntityMapFlat = Dict[str, Dict[str, str]]
EntityMapRich = Dict[str, Dict[str, Union[str, dict]]]


# =================== 格式转换 ===================

def _normalize_value(v) -> str:
    """从全局表的条目值中提取 new name（兼容扁平 str 和 rich dict）。"""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return str(v.get("new", ""))
    return ""


def flatten_entity_map(entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> EntityMapFlat:
    """将任意格式映射归一为扁平 {"cat": {"原名": "新名"}}。"""
    if not isinstance(entity_map, dict):
        return _empty_map()
    out: EntityMapFlat = {}
    for cat in ENTITY_CATEGORIES:
        out[cat] = {}
        raw = entity_map.get(cat, {}) or {}
        if not isinstance(raw, dict):
            continue
        for old, v in raw.items():
            new = _normalize_value(v)
            if old and new and old != new:
                out[cat][old] = new
    return out


def _to_rich_entry(new_name: str, chapter_number: int) -> dict:
    return {
        "new": new_name,
        "first_seen_chapter": chapter_number,
    }


# =================== 路径与 IO ===================

def _entity_map_path(chapter_number: int) -> str:
    return os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.{ENTITY_CACHE_SUFFIX}")


def _global_entity_map_path() -> str:
    return os.path.join(RUNTIME_DIR, GLOBAL_ENTITY_MAP_FILE)


def _empty_map() -> EntityMapFlat:
    return {cat: {} for cat in ENTITY_CATEGORIES}


def _ensure_categories(m: dict) -> dict:
    if not isinstance(m, dict):
        return _empty_map()
    for cat in ENTITY_CATEGORIES:
        if not isinstance(m.get(cat), dict):
            m[cat] = {}
    return m


def load_cached_entity_map(chapter_number: int) -> Optional[EntityMapFlat]:
    path = _entity_map_path(chapter_number)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return flatten_entity_map(json.load(f))
    except Exception:
        return None


def save_entity_map(chapter_number: int, entity_map: EntityMapFlat) -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(_entity_map_path(chapter_number), "w", encoding="utf-8") as f:
        json.dump(flatten_entity_map(entity_map), f, ensure_ascii=False, indent=2)


def load_global_entity_map() -> EntityMapRich:
    """加载项目级全局实体映射（带元数据格式；兼容读取旧扁平格式）。"""
    path = _global_entity_map_path()
    if not os.path.isfile(path):
        return _empty_map()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = _ensure_categories(json.load(f))
        # 向后兼容：旧扁平格式自动升级为 rich 格式（first_seen_chapter=-1 表示未知）
        for cat in ENTITY_CATEGORIES:
            for old, v in list(raw.get(cat, {}).items()):
                if isinstance(v, str):
                    raw[cat][old] = {"new": v, "first_seen_chapter": -1}
        return raw
    except Exception:
        return _empty_map()


def save_global_entity_map(entity_map: EntityMapRich) -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(_global_entity_map_path(), "w", encoding="utf-8") as f:
        json.dump(_ensure_categories(entity_map), f, ensure_ascii=False, indent=2)


def merge_entity_maps(
    base: Union[EntityMapFlat, EntityMapRich],
    incoming: Union[EntityMapFlat, EntityMapRich],
    chapter_number: int = -1,
) -> Union[EntityMapFlat, EntityMapRich]:
    """以 base 为权威：base 中已有的原名保留原映射；incoming 中新增的才合入。
    同时阻止 incoming 中新名与 base 中现有新名冲突（撞名时丢弃 incoming 的该条）。

    chapter_number: 传入时对新合入条目打上 first_seen_chapter 标记（仅当 base
    是 rich 格式时有效）。-1 表示未知。
    """
    base = _ensure_categories(json.loads(json.dumps(base or {})))
    if not isinstance(incoming, dict):
        return base
    # 判断 base 是否 rich 格式（第一个非空值是 dict）
    base_is_rich = False
    for cat in ENTITY_CATEGORIES:
        for v in (base.get(cat, {}) or {}).values():
            base_is_rich = isinstance(v, dict)
            break
        if base_is_rich:
            break
    existing_new_names = set()
    for cat in ENTITY_CATEGORIES:
        for v in (base.get(cat, {}) or {}).values():
            existing_new_names.add(_normalize_value(v))
    for cat in ENTITY_CATEGORIES:
        new_pairs = incoming.get(cat, {}) or {}
        if not isinstance(new_pairs, dict):
            continue
        for old, v in new_pairs.items():
            if not isinstance(old, str):
                continue
            new_name = _normalize_value(v)
            old = old.strip()
            new_name = new_name.strip()
            if not old or not new_name or old == new_name:
                continue
            if old in base[cat]:
                continue
            if new_name in existing_new_names:
                continue
            if base_is_rich:
                # 如果 incoming 本身是 rich 且带 first_seen_chapter 就沿用
                if isinstance(v, dict) and v.get("first_seen_chapter", -1) > 0:
                    base[cat][old] = v
                else:
                    base[cat][old] = _to_rich_entry(new_name, chapter_number)
            else:
                base[cat][old] = new_name
            existing_new_names.add(new_name)
    return base


# =================== 实体扫描 ===================

def _split_into_chunks(text: str, max_chars: int = 4500) -> List[str]:
    """按段落把长文切成不超过 max_chars 的若干块。"""
    if not text:
        return []
    paragraphs = [p for p in text.split("\n") if p.strip()]
    chunks: List[str] = []
    buf: List[str] = []
    cur = 0
    for p in paragraphs:
        if cur + len(p) + 1 > max_chars and buf:
            chunks.append("\n".join(buf))
            buf = [p]
            cur = len(p)
        else:
            buf.append(p)
            cur += len(p) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks or [text[:max_chars]]


def _scan_chunk_for_entities(
    chunk: str,
    chapter_number: int,
    existing_map: EntityMapFlat,
    chunk_idx: int,
    chunk_total: int,
) -> EntityMapFlat:
    existing_json = json.dumps(flatten_entity_map(existing_map), ensure_ascii=False)
    prompt = (
        f"请扫描第 {chapter_number} 章参考原文【片段 {chunk_idx}/{chunk_total}】中出现的全部实体名，"
        "为每个**尚未在已有映射中**的实体生成一个风格一致但不同的新名字。\n\n"
        "硬规则：\n"
        "1) 必须穷尽扫描本片段：所有出场角色（含一笔带过的配角）、所有地名、所有有名号的事件、"
        "所有有名号的物件/动物都要列出，不得遗漏。\n"
        "2) 同类实体保持命名风格一致：角色名用同长度、同姓氏风格替换；地名保持同类型后缀（城/镇/山/河等）；"
        "事件保持同类型后缀（之乱/之变/之约 等）。\n"
        "3) 新名不得与原文任一实体名相同；不得与【已有映射】中任一新名相同。\n"
        "4) 不要编造文中不存在的实体；只输出本片段中真实出现过的原名。\n"
        "5) 主角名必须替换；姓氏与名字若可独立出现请分别列出（如 '赵无恤' 与 '赵' 都列）。\n"
        "6) 称谓性别名（小道士、那年轻人、他）等代称不算实体，不要列出。\n\n"
        f"【已有映射（请避免冲突，不要为已存在的原名再生成新名）】\n{existing_json}\n\n"
        "输出 JSON（字段必须完整，没有就给空对象）：\n"
        "{\n"
        '  "characters": {"原名": "新名"},\n'
        '  "places": {"原名": "新名"},\n'
        '  "events": {"原名": "新名"},\n'
        '  "objects_animals": {"原名": "新名"}\n'
        "}\n\n"
        f"【参考原文片段】\n{chunk}"
    )
    messages = [
        {"role": "system", "content": "你是小说命名专家，只输出合法 JSON。扫描必须穷尽，宁多勿漏。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=2000,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    if not raw:
        return _empty_map()
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _empty_map()
        return flatten_entity_map(parsed)
    except Exception:
        return _empty_map()


def extract_entity_map_from_reference(
    reference_text: str,
    chapter_number: int,
    existing_map: Optional[Union[EntityMapFlat, EntityMapRich]] = None,
) -> EntityMapFlat:
    """从参考章扫描实体名，结合 existing_map（通常是全局映射）增量产出本章映射。

    返回的是【本章】扫描出的映射（含已有映射里命中的部分），不会原地修改 existing_map。
    """
    if not reference_text or not reference_text.strip():
        return _empty_map()

    base = flatten_entity_map(existing_map)
    chunks = _split_into_chunks(reference_text, max_chars=4500)
    print(f"  实体扫描：第 {chapter_number} 章共 {len(chunks)} 个片段")

    merged = json.loads(json.dumps(base))
    for idx, chunk in enumerate(chunks, start=1):
        delta = _scan_chunk_for_entities(chunk, chapter_number, merged, idx, len(chunks))
        merged = merge_entity_maps(merged, delta)

    # 只返回参考原文中实际出现过的实体
    result = _empty_map()
    for cat in ENTITY_CATEGORIES:
        for old, new in merged.get(cat, {}).items():
            new_name = _normalize_value(new)
            if old and old in reference_text and old != new_name:
                result[cat][old] = new_name
    return result


# =================== 文本改写 ===================

def _flatten_replacements(entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> Dict[str, str]:
    """从任意格式映射提取扁平替换对。"""
    pairs: Dict[str, str] = {}
    if not isinstance(entity_map, dict):
        return pairs
    for cat in ENTITY_CATEGORIES:
        m = entity_map.get(cat, {}) or {}
        if not isinstance(m, dict):
            continue
        for old, v in m.items():
            if not isinstance(old, str):
                continue
            new = _normalize_value(v)
            old = old.strip()
            new = new.strip()
            if not old or not new or old == new:
                continue
            pairs[old] = new
    return pairs


def apply_entity_rewrite(text: str, entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> str:
    """对文本中已知实体名做全局硬替换。按原名长度降序，避免 '赵无' 先替换吃掉 '赵无恤'。"""
    if not text or not entity_map:
        return text
    pairs = _flatten_replacements(entity_map)
    if not pairs:
        return text
    result = text
    for old in sorted(pairs.keys(), key=len, reverse=True):
        new = pairs[old]
        if old and old in result:
            result = result.replace(old, new)
    return result


def detect_original_entity_leaks(
    text: str,
    entity_map: Union[EntityMapFlat, EntityMapRich, None],
) -> List[Dict]:
    """检测文本中残留的原实体名。返回 [{entity, category, count, expected}, ...]"""
    if not text or not entity_map:
        return []
    leaks: List[Dict] = []
    for cat in ENTITY_CATEGORIES:
        for old, v in (entity_map.get(cat, {}) or {}).items():
            if not isinstance(old, str):
                continue
            new = _normalize_value(v)
            if not old or old == new:
                continue
            count = text.count(old)
            if count > 0:
                leaks.append({
                    "entity": old,
                    "category": cat,
                    "count": count,
                    "expected": new,
                })
    return leaks


def format_entity_leak_report(leaks: List[Dict]) -> str:
    if not leaks:
        return "无原实体残留"
    lines = [f"检测到 {len(leaks)} 个原实体残留："]
    for leak in leaks:
        lines.append(
            f"  - {leak['entity']}（{leak['category']}）残留 {leak['count']} 次，应改为 {leak['expected']}"
        )
    return "\n".join(lines)


def format_entity_map_for_prompt(entity_map: Union[EntityMapFlat, EntityMapRich, None], max_per_category: int = 0) -> str:
    """把实体映射格式化成提示词块。max_per_category=0 表示不截断（默认列全部）。"""
    if not entity_map:
        return ""
    flat = flatten_entity_map(entity_map)
    label = {
        "characters": "角色名",
        "places": "地名",
        "events": "事件名",
        "objects_animals": "物件/动物名",
    }
    sections: List[str] = []
    for cat in ENTITY_CATEGORIES:
        pairs = flat.get(cat, {}) or {}
        if not pairs:
            continue
        items = list(pairs.items())
        if max_per_category and max_per_category > 0:
            items = items[:max_per_category]
        rendered = "、".join(f"{old}→{new}" for old, new in items)
        sections.append(f"- {label.get(cat, cat)}：{rendered}")
    return "\n".join(sections)


# =================== 预览与反查 ===================

def format_global_map_for_preview(global_map: Union[EntityMapFlat, EntityMapRich, None]) -> str:
    """格式化全局映射表，按类别和来源章节排列，供终端预览。"""
    if not global_map:
        return "（全局实体映射为空）"
    label = {
        "characters": "角色",
        "places": "地名",
        "events": "事件",
        "objects_animals": "物件/动物",
    }
    lines: List[str] = ["=== 全局实体映射 ==="]
    total = 0
    for cat in ENTITY_CATEGORIES:
        entries = (global_map.get(cat, {}) or {})
        if not entries:
            continue
        lines.append(f"\n[{label.get(cat, cat)}] ({len(entries)} 条)")
        for old, v in entries.items():
            if isinstance(v, dict):
                new = v.get("new", "?")
                ch = v.get("first_seen_chapter", "?")
                lines.append(f"  {old} → {new}  (首见: 第{ch}章)")
            else:
                lines.append(f"  {old} → {v}  (首见: 未知)")
            total += 1
    lines.append(f"\n共 {total} 条映射")
    return "\n".join(lines)
