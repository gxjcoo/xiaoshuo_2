"""章节结构骨架的结构化类型定义（真正接入主链路的部分）。

只保留 outline_extractor / chapter_processor 实际在用的 SceneNode 与 ChapterOutline。
"""

import json
from typing import List, Dict, Optional, Any
from enum import Enum


class NodeType(str, Enum):
    SCENE = "scene"
    DIALOGUE = "dialogue"
    ACTION = "action"
    TRANSITION = "transition"
    CLIMAX = "climax"
    RESOLUTION = "resolution"


class EmotionalBeat(str, Enum):
    TENSION = "tension"
    HUMOR = "humor"
    SADNESS = "sadness"
    EXCITEMENT = "excitement"
    CALM = "calm"
    SURPRISE = "surprise"
    FEAR = "fear"
    ANGER = "anger"


class SceneNode:
    """单个场景/节拍节点"""

    def __init__(
        self,
        node_type: NodeType,
        purpose: str,
        location: Optional[str] = None,
        characters: Optional[List[str]] = None,
        content_summary: Optional[str] = None,
        emotional_beat: Optional[EmotionalBeat] = None,
        is_optional: bool = False,
        original_beat_idx: Optional[int] = None,
    ):
        self.node_type = NodeType(node_type) if isinstance(node_type, str) else node_type
        self.purpose = purpose
        self.location = location
        self.characters = characters or []
        self.content_summary = content_summary
        self.emotional_beat = (
            EmotionalBeat(emotional_beat)
            if emotional_beat and isinstance(emotional_beat, str)
            else emotional_beat
        )
        self.is_optional = is_optional
        self.original_beat_idx = original_beat_idx

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": self.node_type.value if isinstance(self.node_type, Enum) else self.node_type,
            "purpose": self.purpose,
            "location": self.location,
            "characters": self.characters,
            "content_summary": self.content_summary,
            "emotional_beat": self.emotional_beat.value if isinstance(self.emotional_beat, Enum) else self.emotional_beat,
            "is_optional": self.is_optional,
            "original_beat_idx": self.original_beat_idx,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneNode":
        return cls(
            node_type=data.get("node_type"),
            purpose=data.get("purpose", ""),
            location=data.get("location"),
            characters=data.get("characters", []),
            content_summary=data.get("content_summary"),
            emotional_beat=data.get("emotional_beat"),
            is_optional=data.get("is_optional", False),
            original_beat_idx=data.get("original_beat_idx"),
        )


class ChapterOutline:
    """章节结构大纲 - 真正的 AST"""

    def __init__(
        self,
        chapter_goal: str,
        scenes: List[SceneNode],
        core_conflict: str,
        resolution: str,
        hook_for_next: Optional[str] = None,
        must_keep_facts: Optional[List[str]] = None,
        causal_chain: Optional[List[str]] = None,
        ending_state: Optional[str] = None,
        source_chapter: Optional[int] = None,
    ):
        self.chapter_goal = chapter_goal
        self.scenes = scenes
        self.core_conflict = core_conflict
        self.resolution = resolution
        self.hook_for_next = hook_for_next
        self.must_keep_facts = must_keep_facts or []
        self.causal_chain = causal_chain or []
        self.ending_state = ending_state
        self.source_chapter = source_chapter

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_goal": self.chapter_goal,
            "scenes": [s.to_dict() for s in self.scenes],
            "core_conflict": self.core_conflict,
            "resolution": self.resolution,
            "hook_for_next": self.hook_for_next,
            "must_keep_facts": self.must_keep_facts,
            "causal_chain": self.causal_chain,
            "ending_state": self.ending_state,
            "source_chapter": self.source_chapter,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterOutline":
        scenes = [SceneNode.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            chapter_goal=data.get("chapter_goal", ""),
            scenes=scenes,
            core_conflict=data.get("core_conflict", ""),
            resolution=data.get("resolution", ""),
            hook_for_next=data.get("hook_for_next"),
            must_keep_facts=data.get("must_keep_facts", []),
            causal_chain=data.get("causal_chain", []),
            ending_state=data.get("ending_state"),
            source_chapter=data.get("source_chapter"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "ChapterOutline":
        data = json.loads(json_str)
        return cls.from_dict(data)

    def validate(self) -> List[str]:
        """验证大纲完整性，返回问题列表"""
        issues = []
        if not self.chapter_goal:
            issues.append("缺少 chapter_goal")
        if not self.scenes:
            issues.append("缺少 scenes")
        if len(self.scenes) < 3:
            issues.append(f"scenes 太少（只有 {len(self.scenes)} 个，建议 5-15 个）")
        if not self.core_conflict:
            issues.append("缺少 core_conflict")
        if not self.resolution:
            issues.append("缺少 resolution")
        return issues
