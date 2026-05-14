"""
实体改写映射 - 同结构改编的核心降重层
扫描参考章中的角色、地点、事件、物件名，生成映射表，后续所有流程使用新名
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple

from config import RUNTIME_DIR, CONTEXT_ANALYSIS_MODEL
from ai_handler import call_deepseek_api

ENTITY_CACHE_SUFFIX = "entity_map.json"


def _entity_map_path(chapter_number: int) -> str:
    return os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.{ENTITY_CACHE_SUFFIX}")


def load_cached_entity_map(chapter_number: int) -> Optional[Dict[str, Dict[str, str]]]:
    """加载缓存的实体映射"""
    path = _entity_map_path(chapter_number)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_entity_map(chapter_number: int, entity_map: Dict[str, Dict[str, str]]):
    """保存实体映射到 runtime"""
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(_entity_map_path(chapter_number), "w", encoding="utf-8") as f:
        json.dump(entity_map, f, ensure_ascii=False, indent=2)


def extract_entity_map_from_reference(
    reference_text: str,
    chapter_number: int,
    existing_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Dict[str, str]]:
    """
    从参考章自动扫描实体名，调用 LLM 生成新名映射
    返回: {"characters": {"原名": "新名"}, "places": {...}, "events": {...}, "objects_animals": {...}}
    """
    if not reference_text or not reference_text.strip():
        return {"characters": {}, "places": {}, "events": {}, "objects_animals": {}}

    existing_hint = ""
    if existing_map:
        existing_hint = (
            "\n已有映射（新实体名不要和已有映射冲突）：\n" + json.dumps(existing_map, ensure_ascii=False)
        )

    prompt = (
        f"请扫描第 {chapter_number} 章参考原文中的核心实体名，为每个实体生成一个风格一致但不同的新名字。\n\n"
        "规则：\n"
        "1. 同类实体保持命名风格一致（如都是先秦风格、都带官职感等）\n"
        "2. 新名不得和原文任何一个实体名相同\n"
        "3. 角色名用同长度、同姓氏风格替换；地名保持同类型后缀（城/镇/山/河）\n"
        "4. 只提取文中出现的真实实体，不要编造文中不存在的实体\n"
        "5. 主角名必须替换\n"
        f"{existing_hint}\n"
        "输出 JSON：\n"
        "{\n"
        '  "characters": {"原名": "新名"},\n'
        '  "places": {"原名": "新名"},\n'
        '  "events": {"原名": "新名"},\n'
        '  "objects_animals": {"原名": "新名"}\n'
        "}\n\n"
        f"参考原文：\n{reference_text[:5000]}"
    )

    messages = [
        {"role": "system", "content": "你是小说命名专家，为实体生成风格一致的新名字。只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]

    print(f"正在为第 {chapter_number} 章生成实体改写映射...")
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=2000,
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    if not raw:
        print("警告: 实体映射生成失败，返回空映射")
        return {"characters": {}, "places": {}, "events": {}, "objects_animals": {}}

    try:
        entity_map = json.loads(raw)
        if not isinstance(entity_map, dict):
            raise ValueError("not dict")
        # 确保四个分类都存在
        for key in ["characters", "places", "events", "objects_animals"]:
            entity_map.setdefault(key, {})
        return entity_map
    except Exception as e:
        print(f"解析实体映射失败: {e}")
        return {"characters": {}, "places": {}, "events": {}, "objects_animals": {}}


def apply_entity_rewrite(text: str, entity_map: Dict[str, Dict[str, str]]) -> str:
    """
    对文本中的已知实体名进行全局替换
    按实体名长度降序替换，避免短名先替换导致长名部分被替换
    """
    if not text or not entity_map:
        return text

    # 展平所有映射
    all_replacements: Dict[str, str] = {}
    for category in ["characters", "places", "events", "objects_animals"]:
        all_replacements.update(entity_map.get(category, {}))

    if not all_replacements:
        return text

    # 按原名长度降序排序，避免 "赵无" 先替换导致 "赵无恤" 无法完整替换
    sorted_keys = sorted(all_replacements.keys(), key=len, reverse=True)
    result = text
    for old_name in sorted_keys:
        new_name = all_replacements[old_name]
        result = result.replace(old_name, new_name)

    return result


def detect_original_entity_leaks(
    text: str,
    entity_map: Dict[str, Dict[str, str]],
) -> List[Dict]:
    """
    检测文本中残留的原实体名
    返回: [{"entity": "赵无恤", "category": "characters", "count": 3}, ...]
    """
    leaks = []
    for category in ["characters", "places", "events", "objects_animals"]:
        for old_name, new_name in entity_map.get(category, {}).items():
            count = text.count(old_name)
            if count > 0:
                leaks.append({
                    "entity": old_name,
                    "category": category,
                    "count": count,
                    "expected": new_name,
                })
    return leaks


def format_entity_leak_report(leaks: List[Dict]) -> str:
    """格式化实体残留报告"""
    if not leaks:
        return "无原实体残留"
    lines = [f"检测到 {len(leaks)} 个原实体残留："]
    for leak in leaks:
        lines.append(f"  - {leak['entity']}（{leak['category']}）残留 {leak['count']} 次，应为 {leak['expected']}")
    return "\n".join(lines)
