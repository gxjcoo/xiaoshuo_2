"""向后兼容 shim：原 audit_pipeline 已拆分到 `audit/` 子包。

历史上有调用方写 `from audit_pipeline import audit_and_revise_until_pass`，
保留此模块作为转发层，避免外部脚本/旧 import 路径中断。新代码请直接：

    from audit import audit_and_revise_until_pass
    from audit.metrics import analyze_reference_similarity
    ...
"""

from audit import (  # noqa: F401
    _basic_style_metrics,
    compare_reference_and_generated,
    analyze_reference_similarity,
    evaluate_plot_fidelity_with_outline,
    evaluate_chapter_with_rules,
    revise_for_plot_fidelity,
    rewrite_for_expression_distance,
    anti_ai_rewrite_with_reference,
    revise_chapter_by_audit_feedback,
    audit_and_revise_until_pass,
)
from audit.metrics import (  # noqa: F401
    _clean_for_similarity,
    _char_ngrams_for_similarity,
    _sentence_similarity_ratio,
    _reference_similarity_thresholds,
    plot_fidelity_min_score as _plot_fidelity_min_score,
)
