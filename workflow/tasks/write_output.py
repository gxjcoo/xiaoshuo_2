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
        
        # 修复重复文本问题
        try:
            from entity_rewriter import fix_duplicate_text, detect_duplicate_text, remove_revision_notes, fix_sanchi_qingfeng_compound
            duplicates = detect_duplicate_text(final_content)
            if duplicates:
                print(f"  检测到 {len(duplicates)} 处重复文本，正在修复...")
                final_content = fix_duplicate_text(final_content)
            
            # 修复三尺青锋复合词错误
            final_content = fix_sanchi_qingfeng_compound(final_content)
            
            # 移除修订说明（AI生成时可能留下的编辑痕迹）
            original_length = len(final_content)
            final_content = remove_revision_notes(final_content)
            if len(final_content) < original_length:
                print(f"  已移除修订说明（减少 {original_length - len(final_content)} 字符）")
        except ImportError:
            # 如果无法导入，跳过文本修复
            pass
        
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
