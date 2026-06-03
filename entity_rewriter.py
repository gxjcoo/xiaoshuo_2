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
import re
from typing import Dict, List, Optional, Union

from config import RUNTIME_DIR, CONTEXT_ANALYSIS_MODEL
from ai_handler import call_deepseek_api

ENTITY_CACHE_SUFFIX = "entity_map.json"
GLOBAL_ENTITY_MAP_FILE = "global_entity_map.json"
ENTITY_CATEGORIES = ("characters", "places", "events", "objects_animals")

# 常用字黑名单：这些字/词绝不能作为实体名被替换，否则会破坏正常文本
# 单字黑名单覆盖最常见的中文虚词、量词、方位词、身体部位等
_ENTITY_BLACKLIST_SINGLE = frozenset([
    "头", "口", "手", "脚", "眼", "心", "脸", "身", "嘴", "耳", "鼻", "眉", "发",
    "人", "大", "小", "上", "下", "左", "右", "前", "后", "里", "外", "中", "内",
    "天", "地", "山", "水", "风", "火", "石", "木", "草", "花", "树", "云", "雨",
    "金", "银", "铁", "铜", "玉", "珠", "刀", "剑", "门", "路", "桥", "车", "船",
    "家", "房", "屋", "城", "村", "镇", "县", "州", "府", "国", "殿", "楼", "阁",
    "老", "新", "男", "女", "长", "少", "公", "母", "好", "坏", "黑", "白", "红",
    "走", "来", "去", "看", "听", "说", "吃", "喝", "坐", "站", "跑", "飞", "打",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万",
    "你", "我", "他", "她", "它", "谁", "这", "那", "什么", "怎么", "哪",
    "的", "了", "着", "过", "地", "得", "把", "被", "让", "给", "对", "向", "从",
    "和", "与", "及", "或", "但", "而", "就", "也", "都", "还", "又", "再", "才",
    "很", "太", "最", "更", "越", "挺", "真", "假", "会", "能", "要", "想", "该",
])

# 多字黑名单：常见的短词也不应作为实体名
_ENTITY_BLACKLIST_MULTI = frozenset([
    "这个", "那个", "什么", "怎么", "哪里", "这里", "那里", "自己", "别人",
    "大家", "咱们", "我们", "你们", "他们", "她们", "它们",
    "一个", "两个", "几个", "所有", "每个", "某些",
    "可以", "应该", "能够", "需要", "必须", "已经", "正在", "将要",
    "不是", "没有", "还是", "就是", "只是", "都是", "也是",
    "因为", "所以", "如果", "虽然", "但是", "不过", "然而", "而且",
    "然后", "接着", "于是", "因此", "所以", "总之",
    "突然", "忽然", "居然", "竟然", "果然", "当然", "自然",
    "起来", "出来", "过来", "回来", "下来", "上来",
    "地方", "时候", "东西", "事情", "样子", "名字", "声音",
])

def _is_entity_blacklisted(name: str) -> bool:
    """检查实体名是否在黑名单中（不应被替换的常用字/词）。"""
    name = name.strip()
    if not name:
        return True
    if len(name) == 1 and name in _ENTITY_BLACKLIST_SINGLE:
        return True
    if name in _ENTITY_BLACKLIST_MULTI:
        return True
    # 2字以下且不含特定姓氏/称号特征的，谨慎处理
    # 但不完全禁止2字名（如"张三"是合法实体名）
    return False

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
    existing_old_names = set()  # 新增：收集所有类别的原名
    for cat in ENTITY_CATEGORIES:
        for old, v in (base.get(cat, {}) or {}).items():
            existing_new_names.add(_normalize_value(v))
            if isinstance(old, str):
                existing_old_names.add(old.strip())
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
            if _is_entity_blacklisted(old):
                continue
            if old in base[cat]:
                continue
            if old in existing_old_names:  # 新增：检查跨类别原名冲突
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
        task_label=f"第{chapter_number}章实体扫描 {chunk_idx}/{chunk_total}",
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

# 通用称谓后缀集合（不限于特定题材，覆盖常见中文称谓）
# 设计原则：包含 1-3 字的常见称谓后缀，支持古风/现代/武侠/仙侠等多题材
_TITLE_SUFFIXES: List[str] = [
    # 道教/仙侠类
    "道长", "道人", "真人", "道友", "道兄", "仙子", "仙姑", "仙长",
    # 武侠/江湖类
    "大侠", "女侠", "侠客", "侠士", "前辈", "老前辈",
    # 门派/师徒类
    "长老", "老祖", "掌门", "宗主", "门主", "教主",
    "师兄", "师姐", "师弟", "师妹", "师父", "师尊", "恩师", "师叔", "师伯",
    # 官职/权贵类
    "大人", "老爷", "老夫人", "夫人", "公子", "少爷", "小姐", "姑娘",
    "王爷", "皇子", "公主", "太子",
    # 民间/职业类
    "员外", "乡绅", "掌柜", "老板", "东家", "老板娘",
    "捕头", "都头", "班头", "总管", "管家",
    "大夫", "郎中", "先生",
    # 称呼类
    "兄弟", "兄台", "贤弟", "贤妹", "仁兄", "贤侄",
    "老丈", "老者", "老翁", "老婆婆",
    # 现代类
    "同志", "老师", "教授", "医生", "律师",
]


def _extract_name_parts(name: str) -> tuple:
    """提取角色名的核心部分和称谓后缀。
    
    策略：从后向前匹配已知后缀，返回 (核心, 后缀)。
    如果无法识别后缀，返回 (完整名称, "")。
    
    例如：
        '宝寿道长' → ('宝寿', '道长')
        '青云道人' → ('青云', '道人')
        '郑大人'   → ('郑', '大人')
        '小熊'     → ('小熊', '')
    """
    for suffix in _TITLE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return (name[:-len(suffix)], suffix)
    return (name, "")


def _generate_name_variants(old_name: str, new_name: str) -> Dict[str, str]:
    """为角色名生成称谓后缀变体的替换对（保持后缀一致性）。
    
    核心逻辑：
    1. 提取原名的核心+后缀（如 "宝寿道长" → 核心="宝寿", 后缀="道长"）
    2. 提取新名的核心+后缀（如 "青云道人" → 核心="青云", 后缀="道人"）
    3. 对于每个可能的变体后缀，生成：新核心 + 变体后缀
    
    例如：old='宝寿道长', new='青云道人'
    - 宝寿道人 → 青云道人（保持"道人"后缀）
    - 宝寿真人 → 青云真人（保持"真人"后缀）
    - 宝寿道友 → 青云道友（保持"道友"后缀）
    - 宝寿道兄 → 青云道兄（保持"道兄"后缀）
    """
    variants: Dict[str, str] = {}
    
    # 提取原名的核心和后缀
    old_core, old_suffix = _extract_name_parts(old_name)
    if not old_core:
        return variants
    
    # 提取新名的核心
    new_core, _ = _extract_name_parts(new_name)
    if not new_core:
        new_core = new_name
    
    # 如果原名没有后缀，无法生成变体
    if not old_suffix:
        return variants
    
    # 为所有可能的后缀生成变体（排除原名自身）
    for suffix in _TITLE_SUFFIXES:
        if suffix == old_suffix:
            continue  # 跳过原名自身后缀
        
        variant_old = old_core + suffix
        variant_new = new_core + suffix
        
        # 只有变体与原名不同时才添加
        if variant_old != old_name:
            variants[variant_old] = variant_new
    
    return variants


def _flatten_replacements(entity_map: Union[EntityMapFlat, EntityMapRich, None]) -> Dict[str, str]:
    """从任意格式映射提取扁平替换对（含变体扩展）。"""
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
            
            # 对 characters 类别生成称谓后缀变体
            if cat == "characters":
                variants = _generate_name_variants(old, new)
                for variant_old, variant_new in variants.items():
                    # 只添加原映射中没有明确覆盖的变体
                    if variant_old not in pairs:
                        pairs[variant_old] = variant_new
    
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
    """检测文本中残留的原实体名（含称谓后缀变体）。
    
    返回 [{entity, category, count, expected}, ...]
    对于 characters 类别，除了检测原名，还检测其称谓后缀变体。
    """
    if not text or not entity_map:
        return []
    leaks: List[Dict] = []
    seen_entities: set = set()  # 避免重复报告
    
    for cat in ENTITY_CATEGORIES:
        for old, v in (entity_map.get(cat, {}) or {}).items():
            if not isinstance(old, str):
                continue
            new = _normalize_value(v)
            if not old or old == new:
                continue
            
            # 检测原名
            count = text.count(old)
            if count > 0 and old not in seen_entities:
                leaks.append({
                    "entity": old,
                    "category": cat,
                    "count": count,
                    "expected": new,
                })
                seen_entities.add(old)
            
            # 对 characters 类别，检测称谓后缀变体
            if cat == "characters":
                old_core, old_suffix = _extract_name_parts(old)
                if old_core and old_suffix:
                    new_core, _ = _extract_name_parts(new)
                    if not new_core:
                        new_core = new
                    
                    for suffix in _TITLE_SUFFIXES:
                        if suffix == old_suffix:
                            continue
                        
                        variant_name = old_core + suffix
                        if variant_name != old and variant_name not in seen_entities:
                            count = text.count(variant_name)
                            if count > 0:
                                expected_variant = new_core + suffix
                                leaks.append({
                                    "entity": variant_name,
                                    "category": cat,
                                    "count": count,
                                    "expected": expected_variant,
                                    "is_variant": True,
                                    "original_entity": old,
                                })
                                seen_entities.add(variant_name)
    
    return leaks


def format_entity_leak_report(leaks: List[Dict]) -> str:
    if not leaks:
        return "无原实体残留"
    lines = [f"检测到 {len(leaks)} 个原实体残留："]
    for leak in leaks:
        variant_info = ""
        if leak.get("is_variant"):
            variant_info = f" [变体，原名: {leak.get('original_entity', '?')}]"
        lines.append(
            f"  - {leak['entity']}（{leak['category']}）残留 {leak['count']} 次，应改为 {leak['expected']}{variant_info}"
        )
    return "\n".join(lines)


def detect_duplicate_text(text: str, min_repeat_length: int = 2, max_repeat_length: int = 10) -> List[Dict]:
    """检测文本中的重复字符或短语（如"乾坤乾坤乾坤"）。
    
    返回重复模式列表：[{"pattern": "乾坤", "count": 3, "position": 10}, ...]
    """
    if not text or len(text) < min_repeat_length * 2:
        return []
    
    duplicates = []
    
    # 检测长度为 min_repeat_length 到 max_repeat_length 的重复模式
    for length in range(min_repeat_length, max_repeat_length + 1):
        i = 0
        while i <= len(text) - length * 2:
            pattern = text[i:i + length]
            # 跳过纯标点或空白
            if not pattern.strip() or all(c in '，。！？、；：""''（）【】《》 \t\n' for c in pattern):
                i += 1
                continue
            
            # 计算连续重复次数
            count = 1
            j = i + length
            while j <= len(text) - length and text[j:j + length] == pattern:
                count += 1
                j += length
            
            # 如果重复2次以上，记录
            if count >= 2:
                duplicates.append({
                    "pattern": pattern,
                    "count": count,
                    "position": i,
                    "full_match": pattern * count,
                })
                i = j  # 跳过已检测的重复
            else:
                i += 1
    
    # 合并重叠的检测结果（优先保留更长的模式）
    if not duplicates:
        return []
    
    # 按位置排序
    duplicates.sort(key=lambda x: x["position"])
    
    # 去重：如果两个模式有重叠，保留更长的
    merged = []
    for dup in duplicates:
        if not merged:
            merged.append(dup)
        else:
            last = merged[-1]
            # 检查是否重叠
            if dup["position"] < last["position"] + len(last["full_match"]):
                # 重叠，保留更长的
                if len(dup["full_match"]) > len(last["full_match"]):
                    merged[-1] = dup
            else:
                merged.append(dup)
    
    return merged


def fix_duplicate_text(text: str) -> str:
    """修复文本中的重复字符或短语（如"乾坤乾坤乾坤" → "天地灵气"）。
    
    常见重复模式修复映射：
    - "乾坤乾坤乾坤" → "天地灵气"（或其他合理替换）
    - "精华精华精华" → "精华"
    - "黑衣黑衣" → "黑衣"
    """
    if not text:
        return text
    
    # 定义重复模式修复映射
    duplicate_fixes = {
        # 三字重复
        "乾坤乾坤乾坤": "天地灵气",
        "精华精华精华": "精华",
        "黑衣黑衣黑衣": "黑衣",
        "白衣白衣白衣": "白衣",
        "青锋青锋青锋": "青锋",
        "灵气灵气灵气": "灵气",
        "剑气剑气剑气": "剑气",
        "道法道法道法": "道法",
        # 双字重复（可能更多）
        "乾坤乾坤": "天地",
        "精华精华": "精华",
        "黑衣黑衣": "黑衣",
        "白衣白衣": "白衣",
        "青锋青锋": "青锋",
        "灵气灵气": "灵气",
        "剑气剑气": "剑气",
        "道法道法": "道法",
        # 其他常见重复
        "天地天地灵气": "天地灵气",
        "天地天地": "天地",
    }
    
    result = text
    # 按长度降序替换，避免短模式误匹配
    for old, new in sorted(duplicate_fixes.items(), key=lambda x: len(x[0]), reverse=True):
        if old in result:
            result = result.replace(old, new)
    
    return result


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
