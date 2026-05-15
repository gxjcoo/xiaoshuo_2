"""
结构化结构骨架提取 - 独立模块
"""

import json
from typing import Optional, Dict, Any

from config import (
    CONTEXT_ANALYSIS_MODEL,
    CONTEXT_ANALYSIS_TEMPERATURE,
)
from structured_types import (
    ChapterOutline,
    SceneNode,
)
from ai_handler import call_deepseek_api, _reference_prose_snippet


def extract_structured_outline_from_reference(
    reference_chapter_text,
    chapter_number,
    strict_source_plot=True,
) -> Optional[ChapterOutline]:
    """
    从参考章抽取结构化的结构骨架（AST）
    """
    if not isinstance(reference_chapter_text, str) or not reference_chapter_text.strip():
        print("警告：参考文本为空")
        return None

    ref_text = _reference_prose_snippet(reference_chapter_text, max_chars=6200)

    prompt = (
        f"请把第 {chapter_number} 章参考原文拆解成「结构化叙事骨架」，输出 JSON。\n\n"
        "目标：后续会基于这个骨架做同结构改编，改编时会保留功能，替换实体和表达。\n\n"
        "JSON 字段：\n"
        "{\n"
        '  "chapter_goal": string（本章核心目标）,\n'
        '  "core_conflict": string（本章核心冲突）,\n'
        '  "resolution": string（冲突如何解决）,\n'
        '  "hook_for_next": string（可选，为下一章留的钩子）,\n'
        '  "must_keep_facts": [string]（必须保留的核心事实）,\n'
        '  "causal_chain": [string]（因果链条，按顺序列关键事件）,\n'
        '  "ending_state": string（可选，本章结束时的状态）,\n'
        '  "scenes": [\n'
        '    {\n'
        '      "node_type": "scene" | "dialogue" | "action" | "transition" | "climax" | "resolution",\n'
        '      "purpose": string（这个场景/节拍的功能是什么）,\n'
        '      "location": string（可选，发生地点）,\n'
        '      "characters": [string]（涉及角色）,\n'
        '      "content_summary": string（内容摘要，不要抄原文句子）,\n'
        '      "emotional_beat": "tension" | "humor" | "sadness" | "excitement" | "calm" | "surprise" | "fear" | "anger",\n'
        '      "is_optional": boolean（这个节拍是否可选）\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "规则：\n"
        "- scenes 列出 5-15 个节点，每个节点代表一个叙事节拍\n"
        "- 不要摘抄原文句子，只写功能和摘要\n"
        f"- 当前模式：{'严格结构适配' if strict_source_plot else '结构主干适配'}\n\n"
        f"参考原文：\n{ref_text}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是专业的小说结构拆解师。你只输出合法的 JSON，不输出任何 Markdown、解释或自然语言。"
                "你会把小说拆解成有功能的叙事节点，而不是摘抄原文。"
            )
        },
        {"role": "user", "content": prompt},
    ]

    print(f"正在提取第 {chapter_number} 章的结构化骨架...")
    raw = call_deepseek_api(
        messages,
        CONTEXT_ANALYSIS_MODEL,
        max_tokens=2000,
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    if not raw:
        print("警告：API 返回为空")
        return None

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            print("警告：API 返回的不是字典")
            return None

        scenes = []
        for i, scene_dict in enumerate(parsed.get("scenes", [])):
            scene_dict["original_beat_idx"] = i
            scene = SceneNode.from_dict(scene_dict)
            scenes.append(scene)

        outline = ChapterOutline(
            chapter_goal=parsed.get("chapter_goal", ""),
            scenes=scenes,
            core_conflict=parsed.get("core_conflict", ""),
            resolution=parsed.get("resolution", ""),
            hook_for_next=parsed.get("hook_for_next"),
            must_keep_facts=parsed.get("must_keep_facts", []),
            causal_chain=parsed.get("causal_chain", []),
            ending_state=parsed.get("ending_state"),
            source_chapter=chapter_number,
        )

        issues = outline.validate()
        if issues:
            print(f"警告：骨架验证发现问题：{issues}")
        else:
            print(f"成功：提取到 {len(scenes)} 个场景节点")

        return outline

    except Exception as e:
        print(f"解析结构化骨架失败：{e}")
        return None
