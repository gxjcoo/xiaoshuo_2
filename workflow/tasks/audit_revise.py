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

        输出：
            - final_content: 最终内容
            - audit_report: 审计报告
        """
        from audit_pipeline import audit_and_revise_until_pass
        from chapter_processor import load_audit_rules
        from config import RUNTIME_DIR, STRICT_SOURCE_PLOT

        chapter_number = context.get("chapter_number")
        generated_content = context.get("generated_content")
        writing_style = context.get("writing_style", "")
        reference_text = context.get("reference_text", "")
        outline = context.get("outline")
        chapter_intent = context.get("chapter_intent", "")
        runtime_dir = context.get("runtime_dir", RUNTIME_DIR)

        if not generated_content:
            raise ValueError("未生成内容")

        # 加载审计规则
        rules = load_audit_rules()

        # 获取参考文本
        chapters_dir = context.get("chapters_dir", "chapters")
        if not reference_text:
            ref_file = os.path.join(chapters_dir, f"{chapter_number}.md")
            if os.path.exists(ref_file):
                with open(ref_file, "r", encoding="utf-8") as f:
                    reference_text = f.read()

        # 将 outline 转为字符串
        reference_plot_outline = ""
        if outline:
            if hasattr(outline, "to_dict"):
                import json
                reference_plot_outline = json.dumps(outline.to_dict(), ensure_ascii=False, indent=2)
            elif isinstance(outline, dict):
                import json
                reference_plot_outline = json.dumps(outline, ensure_ascii=False, indent=2)
            else:
                reference_plot_outline = str(outline)

        # 获取上一章结尾
        prev_chapter_end = ""
        if chapter_number > 1:
            prev_file = os.path.join(chapters_dir, f"{chapter_number - 1}.md")
            if os.path.exists(prev_file):
                with open(prev_file, "r", encoding="utf-8") as f:
                    prev_content = f.read()
                    prev_chapter_end = prev_content[-1200:] if prev_content else ""

        # 执行审计修订
        result = audit_and_revise_until_pass(
            chapter_content=generated_content,
            chapter_number=chapter_number,
            writing_style=writing_style,
            rules=rules,
            reference_text=reference_text,
            reference_plot_outline=reference_plot_outline,
            chapter_plan_text=chapter_intent,
            prev_chapter_end=prev_chapter_end,
        )

        # 处理返回值
        if isinstance(result, dict):
            final_content = result.get("content", generated_content)
            audit_report = result.get("last_audit", {})
        elif isinstance(result, tuple):
            final_content, audit_report = result
        else:
            final_content = result
            audit_report = {}

        return {
            "final_content": final_content,
            "audit_report": audit_report,
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "generated_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "generated_content"]

    def get_output_keys(self) -> list:
        return ["final_content", "audit_report"]
