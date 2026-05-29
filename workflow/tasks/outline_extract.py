"""
骨架抽取任务 - 提取参考章节的结构化骨架
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class OutlineExtractTask(TaskNode):
    """提取参考章节的结构化叙事骨架"""

    @property
    def id(self) -> str:
        return "outline_extract"

    @property
    def name(self) -> str:
        return "骨架抽取"

    @property
    def deps(self) -> list:
        return ["split_novel"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行骨架抽取
        
        输入：
            - chapter_number: 当前章节号
            - reference_text: 参考文本
            - strict_source_plot: 是否严格结构适配
            
        输出：
            - outline: 结构化骨架 (ChapterOutline)
        """
        from outline_extractor import extract_structured_outline_from_reference
        from config import RUNTIME_DIR
        
        chapter_number = context.get("chapter_number")
        reference_text = context.get("reference_text")
        strict_source_plot = context.get("strict_source_plot", True)
        
        if not reference_text:
            # 尝试从文件加载
            chapters_dir = context.get("chapters_dir", "input_chapters")
            ref_file = os.path.join(chapters_dir, f"{chapter_number}.md")
            if os.path.exists(ref_file):
                with open(ref_file, "r", encoding="utf-8") as f:
                    reference_text = f.read()
        
        if not reference_text:
            raise ValueError("未提供参考文本")
        
        # 检查缓存
        runtime_dir = context.get("runtime_dir", RUNTIME_DIR)
        cache_file = os.path.join(runtime_dir, f"ch{chapter_number:04d}_outline.json")
        
        if os.path.exists(cache_file):
            print(f"  使用缓存的骨架: {cache_file}")
            import json
            from structured_types import ChapterOutline
            with open(cache_file, "r", encoding="utf-8") as f:
                outline_dict = json.load(f)
            outline = ChapterOutline.from_dict(outline_dict)
        else:
            outline = extract_structured_outline_from_reference(
                reference_text,
                chapter_number,
                strict_source_plot
            )
            
            # 缓存结果
            if outline:
                os.makedirs(runtime_dir, exist_ok=True)
                import json
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        return {
            "outline": outline
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context

    def get_required_keys(self) -> list:
        return ["chapter_number"]

    def get_output_keys(self) -> list:
        return ["outline"]
