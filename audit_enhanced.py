"""
增强审计系统 - 核心改进 2
从模糊评分变成可操作的 diff 建议，增加 plateau 检测
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple

from structured_types import (
    AuditFeedbackItem,
    AuditResult,
)


class AuditHistory:
    """审计历史记录，用于检测 plateau"""
    def __init__(self, max_history: int = 5):
        self.scores: List[float] = []
        self.versions: List[str] = []  # 内容哈希或版本号
        self.max_history = max_history

    def add_score(self, score: float, content: str = ""):
        self.scores.append(score)
        if len(self.scores) > self.max_history:
            self.scores = self.scores[-self.max_history:]
            self.versions = self.versions[-self.max_history:]

    def is_plateau(self, threshold: float = 2.0, lookback: int = 3) -> bool:
        """
        检测分数是否进入平台期（连续几轮变化很小）
        """
        if len(self.scores) < lookback:
            return False
        recent = self.scores[-lookback:]
        max_change = max(recent) - min(recent)
        return max_change < threshold

    def get_best_score(self) -> Optional[float]:
        return max(self.scores) if self.scores else None


def extract_paragraphs(text: str) -> List[Tuple[int, str, int, int]]:
    """
    把文本拆成段落，同时记录位置信息
    返回：(段落索引, 段落内容, 起始行, 结束行)
    """
    lines = text.splitlines()
    paragraphs = []
    current_para = []
    start_line = 0

    for i, line in enumerate(lines):
        if not line.strip():
            if current_para:
                paragraphs.append((
                    len(paragraphs),
                    "\n".join(current_para),
                    start_line,
                    i - 1,
                ))
                current_para = []
                start_line = i + 1
        else:
            current_para.append(line)

    if current_para:
        paragraphs.append((
            len(paragraphs),
            "\n".join(current_para),
            start_line,
            len(lines) - 1,
        ))

    return paragraphs


def find_text_location(text: str, target: str, context_chars: int = 50) -> Optional[Dict[str, Any]]:
    """
    找到目标文本在全文中的大概位置
    """
    if not target or not text:
        return None

    # 简化匹配（去除空白）
    def simplify(s: str) -> str:
        return re.sub(r"\s+", "", s)

    target_simplified = simplify(target)
    if not target_simplified:
        return None

    # 先找精确匹配
    idx = text.find(target)
    if idx >= 0:
        return {
            "char_index": idx,
            "line_estimate": text[:idx].count("\n"),
            "context_before": text[max(0, idx - context_chars):idx],
            "context_after": text[idx:idx + len(target) + context_chars],
        }

    # 模糊匹配（找最长公共子串）
    # 这里简化处理，只返回找不到
    return None


def generate_feedback_for_dimension(
    dimension: str,
    score: float,
    threshold: float,
    generated_text: str,
    reference_text: Optional[str] = None,
    outline: Optional[Any] = None,
) -> List[AuditFeedbackItem]:
    """
    为单个审计维度生成具体的、可操作的反馈建议，而不是模糊的评分
    """
    items: List[AuditFeedbackItem] = []

    # 只有分数低于阈值才生成反馈
    if score >= threshold:
        return items

    # 段落分析
    paragraphs = extract_paragraphs(generated_text)

    if dimension == "continuity":
        # 连贯性问题的具体反馈
        if len(paragraphs) >= 3:
            # 检查段落间的过渡
            for i in range(1, min(4, len(paragraphs))):
                prev_text = paragraphs[i-1][1]
                curr_text = paragraphs[i][1]

                # 启发式：检查是否有明显的主题跳跃
                if len(prev_text.strip()) > 20 and len(curr_text.strip()) > 20:
                    # 这里可以用 LLM 来检查连贯性，但先用规则
                    if "突然" in curr_text and "忽然" not in prev_text and "紧接着" not in prev_text:
                        items.append(AuditFeedbackItem(
                            feedback_type="insert",
                            dimension="continuity",
                            severity="minor",
                            reason="段落过渡可能有点突兀，建议添加一句过渡",
                            location=f"第 {paragraphs[i][2] + 1} 行前",
                        ))

        # 默认反馈
        if not items:
            items.append(AuditFeedbackItem(
                feedback_type="rewrite",
                dimension="continuity",
                severity="major",
                reason="整体连贯性需要加强，确保事件有因有果",
                location="全文",
            ))

    elif dimension == "plan_adherence":
        # 章节意图达成问题
        items.append(AuditFeedbackItem(
            feedback_type="rewrite",
            dimension="plan_adherence",
            severity="major",
            reason="本章核心目标可能没有完全达成，请确保完成了结构骨架中的功能",
            location="全文",
        ))

    elif dimension == "character_consistency":
        # 角色一致性问题
        # 查找常见的 AI 写法问题
        ai_patterns = [
            r"心中一[震凛惊痛]",
            r"不禁[一]?[笑叹怒]",
            r"他明白|她明白",
        ]
        text_simplified = generated_text

        for pattern in ai_patterns:
            matches = list(re.finditer(pattern, text_simplified))
            for match in matches[:3]:  # 最多返回 3 个
                line_num = text_simplified[:match.start()].count("\n") + 1
                items.append(AuditFeedbackItem(
                    feedback_type="rewrite",
                    dimension="character_consistency",
                    severity="minor",
                    reason="这段表达方式有点模板化，建议换一种更自然的表达",
                    location=f"第 {line_num} 行附近",
                    target_text=match.group(0),
                ))

    elif dimension == "dialogue_distinctiveness":
        # 对话区分度问题
        items.append(AuditFeedbackItem(
            feedback_type="rewrite",
            dimension="dialogue_distinctiveness",
            severity="minor",
            reason="让角色说话更有个人特点，可以增加一些口头禅或独特的表达方式",
        ))

    elif dimension == "reference_fidelity":
        # 结构骨架贴合度问题
        items.append(AuditFeedbackItem(
            feedback_type="rewrite",
            dimension="reference_fidelity",
            severity="critical",
            reason="确保保留了参考章节的结构功能，不要颠倒关键节点的顺序",
            location="全文",
        ))

    elif dimension == "expression_distance":
        # 表达差异度问题（避免抄袭参考原文）
        items.append(AuditFeedbackItem(
            feedback_type="rewrite",
            dimension="expression_distance",
            severity="major",
            reason="建议换更多的表达方式，不要沿用参考原文的句式和用词",
        ))

    elif dimension == "hook_management":
        # 伏笔管理问题
        if paragraphs:
            last_para = paragraphs[-1][1]
            if "。" in last_para and len(last_para.strip().split("。")) <= 2:
                items.append(AuditFeedbackItem(
                    feedback_type="insert",
                    dimension="hook_management",
                    severity="suggestion",
                    reason="结尾可以加一个小钩子，为下一章留下一点悬念",
                    location=f"末尾（第 {paragraphs[-1][3] + 1} 行后）",
                ))

    elif dimension == "pacing":
        # 节奏控制问题
        avg_para_len = sum(len(p[1]) for p in paragraphs) / len(paragraphs) if paragraphs else 0
        if avg_para_len > 300:
            items.append(AuditFeedbackItem(
                feedback_type="rewrite",
                dimension="pacing",
                severity="minor",
                reason="段落有点长，建议拆成短段落，加快节奏",
            ))
        elif avg_para_len < 50 and len(paragraphs) > 20:
            items.append(AuditFeedbackItem(
                feedback_type="rewrite",
                dimension="pacing",
                severity="minor",
                reason="段落太碎了，建议适当合并一些",
            ))

    elif dimension == "writing_quality":
        # 写作质量问题
        items.append(AuditFeedbackItem(
            feedback_type="rewrite",
            dimension="writing_quality",
            severity="minor",
            reason="建议再润色一下文字，让它更自然、更流畅",
        ))

    return items


def run_enhanced_audit(
    generated_text: str,
    dimension_scores: Dict[str, float],
    pass_threshold: float = 85.0,
    dimension_thresholds: Optional[Dict[str, float]] = None,
    reference_text: Optional[str] = None,
    outline: Optional[Any] = None,
    history: Optional[AuditHistory] = None,
) -> AuditResult:
    """
    运行增强审计，返回结构化结果（包含可操作的反馈）
    """
    if dimension_thresholds is None:
        dimension_thresholds = {d: 70.0 for d in dimension_scores.keys()}

    overall_score = sum(dimension_scores.values()) / len(dimension_scores) if dimension_scores else 0.0

    # 生成具体的反馈项
    all_feedback: List[AuditFeedbackItem] = []
    for dim, score in dimension_scores.items():
        threshold = dimension_thresholds.get(dim, 70.0)
        feedback = generate_feedback_for_dimension(
            dim, score, threshold, generated_text, reference_text, outline
        )
        all_feedback.extend(feedback)

    # 检查是否应该继续修订
    should_revise = overall_score < pass_threshold and len(all_feedback) > 0

    # 检测 plateau
    plateau_detected = False
    best_score_in_history = None
    if history:
        plateau_detected = history.is_plateau()
        best_score_in_history = history.get_best_score()
        if plateau_detected:
            print(f"⚠ 检测到分数进入平台期（最近 {len(history.scores)} 轮变化很小）")

    return AuditResult(
        overall_score=overall_score,
        dimension_scores=dimension_scores,
        feedback_items=all_feedback,
        should_revise=should_revise,
        plateau_detected=plateau_detected,
        best_score_in_history=best_score_in_history,
    )


def build_revision_prompt(
    text_to_revise: str,
    audit_result: AuditResult,
    max_feedback_items: int = 5,
) -> str:
    """
    基于审计反馈构建修订提示词，不是模糊的「改得更好」，而是具体的「按这些建议改」
    """
    # 按严重程度排序，只取最重要的几个
    priority_order = ["critical", "major", "minor", "suggestion"]
    sorted_feedback = sorted(
        audit_result.feedback_items,
        key=lambda f: priority_order.index(f.severity),
    )[:max_feedback_items]

    if not sorted_feedback:
        return "（无具体修改建议）"

    # 构建人类可读的反馈列表
    feedback_lines = []
    for i, item in enumerate(sorted_feedback, 1):
        feedback_lines.append(f"{i}. {item.to_human_readable()}")

    prompt = f"""# 修订任务

## 当前文本
```
{text_to_revise[:4000]}
```

## 具体修改建议
{chr(10)}{chr(10).join(feedback_lines)}

## 修订要求
1. 只修改有问题的地方，不要大范围重写
2. 保持原文的风格和结构
3. 优先处理 critical 和 major 级别的问题
4. 修改后仍然要保持完整的章节结构
"""
    return prompt


def format_audit_summary(audit_result: AuditResult) -> str:
    """格式化审计摘要，方便阅读"""
    lines = [
        f"# 审计结果",
        f"",
        f"总分数: {audit_result.overall_score:.1f}",
        f"",
        f"## 维度分数",
    ]

    for dim, score in sorted(audit_result.dimension_scores.items()):
        indicator = "[OK]" if score >= 70 else "[WARN]" if score >= 50 else "[FAIL]"
        lines.append(f"{indicator} {dim}: {score:.1f}")

    if audit_result.feedback_items:
        lines.extend([
            "",
            "## 具体反馈",
        ])
        for item in audit_result.feedback_items[:10]:
            lines.append(f"- {item.to_human_readable()}")
        if len(audit_result.feedback_items) > 10:
            lines.append(f"... (还有 {len(audit_result.feedback_items) - 10} 项)")

    if audit_result.plateau_detected:
        lines.extend([
            "",
            "[WARN] 注意：检测到分数进入平台期，建议停止修订或人工干预",
        ])

    if audit_result.best_score_in_history is not None and audit_result.best_score_in_history > audit_result.overall_score:
        lines.extend([
            "",
            f"[INFO] 历史最高分: {audit_result.best_score_in_history:.1f}（建议回退到该版本）",
        ])

    return "\n".join(lines)
