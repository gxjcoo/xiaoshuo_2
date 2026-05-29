"""
更新上下文任务 - 更新故事上下文
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class UpdateContextTask(TaskNode):
    """更新故事上下文"""

    @property
    def id(self) -> str:
        return "update_context"

    @property
    def name(self) -> str:
        return "更新上下文"

    @property
    def deps(self) -> list:
        return ["write_output"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行上下文更新
        
        输入：
            - chapter_number: 当前章节号
            - final_content: 最终内容
            - strict_source_plot: 是否严格结构适配
            
        输出：
            - context_updated: 是否更新成功
        """
        from context_manager import update_story_context_after_chapter
        
        chapter_number = context.get("chapter_number")
        final_content = context.get("final_content")
        strict_source_plot = context.get("strict_source_plot", True)
        
        if not final_content:
            raise ValueError("没有内容可用于更新上下文")
        
        # 更新上下文
        update_story_context_after_chapter(
            chapter_number,
            final_content,
            strict_source_plot
        )
        
        print(f"  上下文已更新: chapter {chapter_number}")
        
        return {
            "context_updated": True
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "final_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "final_content"]

    def get_output_keys(self) -> list:
        return ["context_updated"]
