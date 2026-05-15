"""审计与修订子包。

按职责拆分自原 `audit_pipeline.py`（867 行单文件）：
- `metrics`：风格指标、参考相似度等纯计算（无 LLM 调用）
- `evaluators`：调用 LLM 做评分（章节多维评分、结构骨架贴合度）
- `revisers`：调用 LLM 做修订（结构纠偏、表达降重、去模板化、按反馈修订）
- `pipeline`：把上面三者编排成「审计 → 修订 → 再审计」闭环

对外保留与旧 `audit_pipeline` 同名的 API，旧 import 路径
`from audit_pipeline import audit_and_revise_until_pass` 通过同名 shim 继续工作。
"""

from .metrics import (
    _basic_style_metrics,
    compare_reference_and_generated,
    analyze_reference_similarity,
)
from .evaluators import (
    evaluate_plot_fidelity_with_outline,
    evaluate_chapter_with_rules,
)
from .revisers import (
    revise_for_plot_fidelity,
    rewrite_for_expression_distance,
    anti_ai_rewrite_with_reference,
    revise_chapter_by_audit_feedback,
)
from .pipeline import audit_and_revise_until_pass

__all__ = [
    "_basic_style_metrics",
    "compare_reference_and_generated",
    "analyze_reference_similarity",
    "evaluate_plot_fidelity_with_outline",
    "evaluate_chapter_with_rules",
    "revise_for_plot_fidelity",
    "rewrite_for_expression_distance",
    "anti_ai_rewrite_with_reference",
    "revise_chapter_by_audit_feedback",
    "audit_and_revise_until_pass",
]
