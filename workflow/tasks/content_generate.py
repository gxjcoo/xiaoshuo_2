"""
正文生成任务 - 生成章节正文内容
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class ContentGenerateTask(TaskNode):
    """生成章节正文内容"""

    @property
    def id(self) -> str:
        return "content_generate"

    @property
    def name(self) -> str:
        return "正文生成"

    @property
    def deps(self) -> list:
        return ["chapter_plan"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行正文生成
        
        输入：
            - chapter_number: 当前章节号
            - chapter_intent: 章节意图
            - outline: 结构化骨架
            - writing_style: 风格分析
            - entity_map: 实体映射
            - target_length: 目标字数
            
        输出：
            - generated_content: 生成的正文内容
            - generated_title: 生成的标题
        """
        from ai_handler import generate_chapter_content
        
        chapter_number = context.get("chapter_number")
        chapter_intent = context.get("chapter_intent")
        outline = context.get("outline")
        writing_style = context.get("writing_style")
        entity_map = context.get("entity_map")
        target_length = context.get("target_length", 3000)
        
        if not chapter_intent:
            raise ValueError("章节意图未生成")
        
        # 生成正文
        result = generate_chapter_content(
            chapter_number,
            chapter_intent,
            outline,
            writing_style,
            entity_map,
            target_length
        )
        
        if isinstance(result, tuple):
            generated_content, generated_title = result
        else:
            generated_content = result
            generated_title = f"第{chapter_number}章"
        
        return {
            "generated_content": generated_content,
            "generated_title": generated_title
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        required = ["chapter_number", "chapter_intent"]
        return all(key in context for key in required)

    def get_required_keys(self) -> list:
        return ["chapter_number", "chapter_intent"]

    def get_output_keys(self) -> list:
        return ["generated_content", "generated_title"]
