"""
结构化类型定义 - 把结构骨架从文本变成真正的 AST
以及上下文知识库类型
"""

import json
from typing import Literal, List, Dict, Optional, Any
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
        self.emotional_beat = EmotionalBeat(emotional_beat) if emotional_beat and isinstance(emotional_beat, str) else emotional_beat
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


class AuditFeedbackItem:
    """可操作的审计反馈项 - 从模糊评分变成具体 diff"""
    def __init__(
        self,
        feedback_type: Literal["insert", "rewrite", "delete", "move"],
        dimension: str,  # 对应审计维度：continuity, plan_adherence 等
        severity: Literal["critical", "major", "minor", "suggestion"],
        reason: str,
        location: Optional[str] = None,  # "第 3 段后"、"第 10-15 行"
        target_text: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        self.feedback_type = feedback_type
        self.dimension = dimension
        self.severity = severity
        self.reason = reason
        self.location = location
        self.target_text = target_text
        self.suggestion = suggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.feedback_type,
            "dimension": self.dimension,
            "severity": self.severity,
            "reason": self.reason,
            "location": self.location,
            "target_text": self.target_text,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditFeedbackItem":
        return cls(
            feedback_type=data.get("type", "rewrite"),
            dimension=data.get("dimension", ""),
            severity=data.get("severity", "major"),
            reason=data.get("reason", ""),
            location=data.get("location"),
            target_text=data.get("target_text"),
            suggestion=data.get("suggestion"),
        )

    def to_human_readable(self) -> str:
        """转成人类可读的格式"""
        loc_str = f" @ {self.location}" if self.location else ""
        severity_icon = {
            "critical": "🔴",
            "major": "🟡",
            "minor": "🟢",
            "suggestion": "💡",
        }.get(self.severity, "•")

        lines = [f"{severity_icon} [{self.dimension}] {self.reason}{loc_str}"]
        if self.target_text:
            lines.append(f"  当前：{self.target_text}")
        if self.suggestion:
            lines.append(f"  建议：{self.suggestion}")
        return "\n".join(lines)


class AuditResult:
    """结构化审计结果"""
    def __init__(
        self,
        overall_score: float,
        dimension_scores: Dict[str, float],
        feedback_items: List[AuditFeedbackItem],
        should_revise: bool,
        plateau_detected: bool = False,
        best_score_in_history: Optional[float] = None,
    ):
        self.overall_score = overall_score
        self.dimension_scores = dimension_scores
        self.feedback_items = feedback_items
        self.should_revise = should_revise
        self.plateau_detected = plateau_detected
        self.best_score_in_history = best_score_in_history

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "feedback_items": [f.to_dict() for f in self.feedback_items],
            "should_revise": self.should_revise,
            "plateau_detected": self.plateau_detected,
            "best_score_in_history": self.best_score_in_history,
        }

    def get_critical_issues(self) -> List[AuditFeedbackItem]:
        return [f for f in self.feedback_items if f.severity == "critical"]

    def get_all_issues(self, min_severity: str = "suggestion") -> List[AuditFeedbackItem]:
        severity_order = ["critical", "major", "minor", "suggestion"]
        min_idx = severity_order.index(min_severity)
        return [
            f for f in self.feedback_items
            if severity_order.index(f.severity) <= min_idx
        ]


# =============================================================================
# 上下文知识库 - 核心改进 3
# =============================================================================

class CharacterState:
    """单个角色的状态"""
    def __init__(
        self,
        name: str,
        aliases: Optional[List[str]] = None,
        description: Optional[str] = None,
        current_goal: Optional[str] = None,
        current_emotion: Optional[str] = None,
        secrets_known: Optional[List[str]] = None,
        relationships: Optional[Dict[str, str]] = None,
        speaking_style: Optional[str] = None,
    ):
        self.name = name
        self.aliases = aliases or []
        self.description = description or ""
        self.current_goal = current_goal or ""
        self.current_emotion = current_emotion or "calm"
        self.secrets_known = secrets_known or []
        self.relationships = relationships or {}  # {other_name: relation_description}
        self.speaking_style = speaking_style or ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "current_goal": self.current_goal,
            "current_emotion": self.current_emotion,
            "secrets_known": self.secrets_known,
            "relationships": self.relationships,
            "speaking_style": self.speaking_style,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterState":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__annotations__})


class Conflict:
    """冲突记录"""
    def __init__(
        self,
        conflict_id: str,
        description: str,
        participants: List[str],
        status: Literal["open", "resolved", "dormant"] = "open",
        priority: int = 1,
    ):
        self.conflict_id = conflict_id
        self.description = description
        self.participants = participants
        self.status = status
        self.priority = priority

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "description": self.description,
            "participants": self.participants,
            "status": self.status,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conflict":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__annotations__})


class ItemInfo:
    """物品/能力信息"""
    def __init__(
        self,
        name: str,
        description: str,
        owner: Optional[str] = None,
        powers: Optional[List[str]] = None,
        restrictions: Optional[List[str]] = None,
    ):
        self.name = name
        self.description = description
        self.owner = owner
        self.powers = powers or []
        self.restrictions = restrictions or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "powers": self.powers,
            "restrictions": self.restrictions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItemInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__init__.__annotations__})


class StoryKnowledgeBase:
    """
    结构化故事知识库，替代简单的 JSON 摘要
    """
    def __init__(
        self,
        world_rules: Optional[Dict[str, str]] = None,
        characters: Optional[Dict[str, CharacterState]] = None,
        active_conflicts: Optional[List[Conflict]] = None,
        resolved_conflicts: Optional[List[Conflict]] = None,
        key_items: Optional[Dict[str, ItemInfo]] = None,
        recent_summaries: Optional[List[str]] = None,
        pending_hooks: Optional[List[str]] = None,
    ):
        self.world_rules = world_rules or {}
        self.characters = characters or {}
        self.active_conflicts = active_conflicts or []
        self.resolved_conflicts = resolved_conflicts or []
        self.key_items = key_items or {}
        self.recent_summaries = recent_summaries or []
        self.pending_hooks = pending_hooks or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_rules": self.world_rules,
            "characters": {k: v.to_dict() for k, v in self.characters.items()},
            "active_conflicts": [c.to_dict() for c in self.active_conflicts],
            "resolved_conflicts": [c.to_dict() for c in self.resolved_conflicts],
            "key_items": {k: v.to_dict() for k, v in self.key_items.items()},
            "recent_summaries": self.recent_summaries,
            "pending_hooks": self.pending_hooks,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryKnowledgeBase":
        return cls(
            world_rules=data.get("world_rules", {}),
            characters={
                k: CharacterState.from_dict(v)
                for k, v in data.get("characters", {}).items()
            },
            active_conflicts=[
                Conflict.from_dict(c) for c in data.get("active_conflicts", [])
            ],
            resolved_conflicts=[
                Conflict.from_dict(c) for c in data.get("resolved_conflicts", [])
            ],
            key_items={
                k: ItemInfo.from_dict(v)
                for k, v in data.get("key_items", {}).items()
            },
            recent_summaries=data.get("recent_summaries", []),
            pending_hooks=data.get("pending_hooks", []),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_context_prompt(self, max_chars: int = 3000) -> str:
        """把知识库转成适合放入提示词的文本"""
        lines = ["# 故事知识库"]

        # 角色信息（只放核心信息）
        if self.characters:
            lines.append("\n## 角色")
            for char in self.characters.values():
                lines.append(f"- {char.name}: {char.description[:100]}")
                if char.current_goal:
                    lines.append(f"  目标: {char.current_goal}")
                if char.relationships:
                    rels = ", ".join([f"{k}: {v}" for k, v in list(char.relationships.items())[:3]])
                    lines.append(f"  关系: {rels}")

        # 活跃冲突
        if self.active_conflicts:
            lines.append("\n## 活跃冲突")
            for conflict in self.active_conflicts[:5]:
                lines.append(f"- {conflict.description}")

        # 关键物品
        if self.key_items:
            lines.append("\n## 关键物品")
            for item in list(self.key_items.values())[:5]:
                lines.append(f"- {item.name}: {item.description[:80]}")

        # 近期摘要
        if self.recent_summaries:
            lines.append("\n## 近期情节")
            for summary in self.recent_summaries[-3:]:
                lines.append(f"- {summary[:150]}")

        # 未回收的钩子
        if self.pending_hooks:
            lines.append("\n## 未回收伏笔")
            for hook in self.pending_hooks[-5:]:
                lines.append(f"- {hook}")

        result = "\n".join(lines)
        # 截断
        if len(result) > max_chars:
            result = result[:max_chars] + "\n...（知识库已截断）"
        return result

    def get_character(self, name: str) -> Optional[CharacterState]:
        """获取角色，支持别名匹配"""
        if name in self.characters:
            return self.characters[name]
        # 尝试别名匹配
        name_lower = name.lower()
        for char in self.characters.values():
            if name_lower in [a.lower() for a in char.aliases] or name_lower == char.name.lower():
                return char
        return None

    def add_character(self, char: CharacterState):
        self.characters[char.name] = char

    def add_conflict(self, conflict: Conflict):
        self.active_conflicts.append(conflict)

    def resolve_conflict(self, conflict_id: str):
        for i, c in enumerate(self.active_conflicts):
            if c.conflict_id == conflict_id:
                c.status = "resolved"
                self.resolved_conflicts.append(self.active_conflicts.pop(i))
                return

    def add_recent_summary(self, summary: str, max_summaries: int = 10):
        self.recent_summaries.append(summary)
        if len(self.recent_summaries) > max_summaries:
            self.recent_summaries = self.recent_summaries[-max_summaries:]

    def add_hook(self, hook: str, max_hooks: int = 20):
        self.pending_hooks.append(hook)
        if len(self.pending_hooks) > max_hooks:
            self.pending_hooks = self.pending_hooks[-max_hooks:]

    def resolve_hook(self, hook_substring: str):
        """回收包含某子串的钩子"""
        self.pending_hooks = [
            h for h in self.pending_hooks if hook_substring.lower() not in h.lower()
        ]
