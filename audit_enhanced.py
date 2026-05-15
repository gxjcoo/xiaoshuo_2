"""审计辅助：分数历史 + Plateau 检测。

历史背景：本模块原本还包含 `run_enhanced_audit` / `build_revision_prompt` /
`generate_feedback_for_dimension` 等「结构化 diff 反馈」实现，但实际从未接入
主流程，且产出的 feedback_items 多数是占位文本。为了消除「文档承诺 ≠ 实际行为」，
已在收尾时一并移除，只保留主链路真正在用的 `AuditHistory`。
"""

from typing import List, Optional


class AuditHistory:
    """审计历史记录，用于检测分数 plateau（连续几轮变化很小）。"""

    def __init__(self, max_history: int = 5):
        self.scores: List[float] = []
        self.versions: List[str] = []  # 预留：当前未用，原计划存内容哈希
        self.max_history = max_history

    def add_score(self, score: float, content: str = "") -> None:
        self.scores.append(score)
        if len(self.scores) > self.max_history:
            self.scores = self.scores[-self.max_history:]
            self.versions = self.versions[-self.max_history:]

    def is_plateau(self, threshold: float = 2.0, lookback: int = 3) -> bool:
        if len(self.scores) < lookback:
            return False
        recent = self.scores[-lookback:]
        return (max(recent) - min(recent)) < threshold

    def get_best_score(self) -> Optional[float]:
        return max(self.scores) if self.scores else None
