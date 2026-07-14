"""LLM 调用与章节生成子包（由 `ai_handler.py` 薄层转发）。

模块划分：
- `client`：OpenAI 兼容 / 豆包 Ark、重试、元推理过滤
- `prompts`：风格备忘、参考片段、实体禁令、生成侧上下文瘦身
- `titles`：章节副标题与兜底
- `outline_extract`：从参考章抽取文本版结构骨架 JSON
- `style_analysis`：文风分析
- `chapter_plan`：本章意图规划
- `hooks`：伏笔与分卷摘要抽取
- `chapter_generate`：正文生成
- `context_analysis`：上下文 JSON 更新
"""

from .client import call_deepseek_api
from .prompts import (
    _brief_style_for_generation,
    _reference_prose_snippet,
    _entity_rewrite_block,
    _entity_rewrite_system_addon,
    _slim_context_for_generation,
    _chapter_completion_max_tokens,
)
from .outline_extract import extract_plot_outline_from_reference
from .titles import (
    _normalize_title_subtitle,
    _fallback_subtitle_from_reference,
    generate_title_from_chapter_content,
    generate_short_title,
)
from .style_analysis import analyze_writing_style
from .chapter_plan import plan_chapter_with_ai
from .hooks import analyze_hooks_and_volume_update
from .chapter_generate import generate_chapter_content
from .context_analysis import analyze_context_with_ai

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
