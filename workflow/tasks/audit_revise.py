"""
审计修订任务 - 审计和修订生成内容
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class AuditReviseTask(TaskNode):
    """审计和修订生成的章节内容"""

    @property
    def id(self) -> str:
        return "audit_revise"

    @property
    def name(self) -> str:
        return "审计修订"

    @property
    def deps(self) -> list:
        return ["content_generate"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行审计修订
        
        输入：
            - chapter_number: 当前章节号
            - generated_content: 生成内容
            - reference_text: 参考文本
            - outline: 结构化骨架
            - entity_map: 实体映射
            
        输出：
            - final_content: 最终内容
            - audit_report: 审计报告
        """
        from audit_pipeline import audit_and_revise_until_pass
        
        chapter_number = context.get("chapter_number")
        generated_content = context.get("generated_content")
        reference_text = context.get("reference_text")
        outline = context.get("outline")
        entity_map = context.get("entity_map")
        entity_rewrite_enabled = context.get("entity_rewrite_enabled", True)
        
        if not generated_content:
            raise ValueError("未生成内容")
        
        # 执行审计修订
        final_content, audit_report = audit_and_revise_until_pass(
            chapter_number,
            generated_content,
            reference_text,
            outline,
            entity_map if entity_rewrite_enabled else None
        )
        
        return {
            "final_content": final_content,
            "audit_report": audit_report
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "generated_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "generated_content"]

    def get_output_keys(self) -> list:
        return ["final_content", "audit_report"]
