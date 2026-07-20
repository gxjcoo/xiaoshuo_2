"""从参考章抽取文本版结构功能骨架（JSON 字符串）。"""

import json

from config import CONTEXT_ANALYSIS_MODEL

from .client import call_deepseek_api
from .prompts import _reference_prose_snippet

# 大纲必需字段
_OUTLINE_REQUIRED_FIELDS = {"chapter_goal", "scene_beats", "ending_state", "characters_present"}


def _validate_outline(data: dict, chapter_number: int) -> bool:
    """校验大纲 JSON 是否包含必需字段。"""
    missing = _OUTLINE_REQUIRED_FIELDS - set(data.keys())
    if missing:
        print(f"警告：第{chapter_number}章大纲缺少字段: {missing}", flush=True)
        return False
    return True


def extract_plot_outline_from_reference(reference_chapter_text, chapter_number, strict_source_plot=True):
    """从参考章抽取结构骨架，供生成阶段使用，避免直接贴原文导致高相似。"""
    if not isinstance(reference_chapter_text, str) or not reference_chapter_text.strip():
        return ""

    ref_text = _reference_prose_snippet(reference_chapter_text, max_chars=6200)
    prompt = (
        f"请把第 {chapter_number} 章参考原文抽取成「结构功能骨架」，输出 JSON。\n"
        "目标：后续作者会基于骨架做同结构改编，不会看到原文全文。\n"
        "必须保留事件功能、冲突功能、因果位置和结尾功能，但不要复写原文句子。\n\n"
        "JSON 字段：\n"
        "{\n"
        '  "chapter_goal": string,\n'
        '  "scene_beats": [string],\n'
        '  "character_motives": [string],\n'
        '  "characters_present": [string],\n'
        '  "must_keep_facts": [string],\n'
        '  "causal_chain": [string],\n'
        '  "ending_state": string,\n'
        '  "do_not_change": [string]\n'
        "}\n\n"
        "规则：\n"
        "- scene_beats 按原文事件顺序列 5-10 条，每条只写事实，不写原文修辞。\n"
        "- characters_present 列出本章实际出场的所有有名有姓的角色（含门派/势力名），不要遗漏。\n"
        "- must_keep_facts 只放改变结构功能会出错的信息点，避免把可改名的人名/地名当成硬约束。\n"
        "- 不要摘抄连续 12 个字以上的原文表达。\n"
        "- 不要输出正文、标题、修辞点评或 Markdown。\n"
        f"- 当前模式：{'严格结构适配' if strict_source_plot else '结构主干适配'}。\n\n"
        f"【参考原文】\n{ref_text}"
    )
    messages = [
        {"role": "system", "content": "你是小说结构拆解编辑，只抽取叙事功能、事件功能和因果位置，不复写原文句子。输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=1600,
        temperature=0.1,
        response_format={"type": "json_object"},
        task_label=f"第{chapter_number}章结构骨架抽取",
    )
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return raw.strip()
        _validate_outline(parsed, chapter_number)
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告：大纲 JSON 解析失败，返回原始文本: {e}", flush=True)
        return raw.strip()
