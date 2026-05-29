"""
写入输出任务 - 将最终内容写入文件
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class WriteOutputTask(TaskNode):
    """将最终内容写入输出文件"""

    @property
    def id(self) -> str:
        return "write_output"

    @property
    def name(self) -> str:
        return "写入输出"

    @property
    def deps(self) -> list:
        return ["audit_revise"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行写入操作
        
        输入：
            - chapter_number: 当前章节号
            - final_content: 最终内容
            - generated_title: 章节标题
            - output_dir: 输出目录
            
        输出：
            - output_path: 输出文件路径
        """
        chapter_number = context.get("chapter_number")
        final_content = context.get("final_content")
        generated_title = context.get("generated_title", f"第{chapter_number}章")
        output_dir = context.get("output_dir", "output_chapters")
        
        if not final_content:
            raise ValueError("没有内容可写入")
        
        # 构建输出内容
        output_content = f"# {generated_title}\n\n{final_content}"
        
        # 写入文件
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{chapter_number}.md")
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_content)
        
        print(f"  已写入: {output_path}")
        
        return {
            "output_path": output_path
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "final_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "final_content"]

    def get_output_keys(self) -> list:
        return ["output_path"]
