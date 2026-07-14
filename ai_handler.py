"""向后兼容入口：实现已拆分到 `llm/` 子包。

外部脚本可继续 `from ai_handler import call_deepseek_api`；
新代码建议 `from llm import call_deepseek_api` 或 `from llm.client import call_deepseek_api`。
"""

from llm import (  # noqa: F401
    call_deepseek_api,
    _brief_style_for_generation,
    _reference_prose_snippet,
    _entity_rewrite_block,
    _entity_rewrite_system_addon,
    _slim_context_for_generation,
    _chapter_completion_max_tokens,
    extract_plot_outline_from_reference,
    _normalize_title_subtitle,
    _fallback_subtitle_from_reference,
    generate_title_from_chapter_content,
    generate_short_title,
    analyze_writing_style,
    plan_chapter_with_ai,
    analyze_hooks_and_volume_update,
    generate_chapter_content,
    analyze_context_with_ai,
)

__all__ = [
    "call_deepseek_api",
    "_brief_style_for_generation",
    "_reference_prose_snippet",
    "_entity_rewrite_block",
    "_entity_rewrite_system_addon",
    "_slim_context_for_generation",
    "_chapter_completion_max_tokens",
    "extract_plot_outline_from_reference",
    "_normalize_title_subtitle",
    "_fallback_subtitle_from_reference",
    "generate_title_from_chapter_content",
    "generate_short_title",
    "analyze_writing_style",
    "plan_chapter_with_ai",
    "analyze_hooks_and_volume_update",
    "generate_chapter_content",
    "analyze_context_with_ai",
]
