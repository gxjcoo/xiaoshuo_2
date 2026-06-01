"""
风格分析任务 - 分析参考章节的写作风格
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class StyleAnalysisTask(TaskNode):
    """分析参考章节的写作风格"""

    @property
    def id(self) -> str:
        return "style_analysis"

    @property
    def name(self) -> str:
        return "风格分析"

    @property
    def deps(self) -> list:
        return ["split_novel"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行风格分析
        
        输入：
            - chapter_number: 当前章节号
            - reference_text: 参考文本
            - runtime_dir: 运行时目录
            
        输出：
            - writing_style: 风格分析结果
        """
        from llm.style_analysis import analyze_writing_style
        from config import RUNTIME_DIR
        
        chapter_number = context.get("chapter_number")
        reference_text = context.get("reference_text")
        runtime_dir = context.get("runtime_dir", RUNTIME_DIR)
        
        if not reference_text:
            # 尝试从文件加载
            chapters_dir = context.get("chapters_dir", "chapters")
            ref_file = os.path.join(chapters_dir, f"{chapter_number}.md")
            if os.path.exists(ref_file):
                with open(ref_file, "r", encoding="utf-8") as f:
                    reference_text = f.read()
        
        if not reference_text:
            raise ValueError("未提供参考文本")
        
        # 检查缓存
        cache_file = os.path.join(runtime_dir, f"ch{chapter_number:04d}_style.txt")
        if os.path.exists(cache_file):
            print(f"  使用缓存的风格分析: {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                writing_style = f.read()
        else:
            writing_style = analyze_writing_style(reference_text)
            
            # 缓存结果
            os.makedirs(runtime_dir, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(writing_style)
        
        # 验证风格分析非空
        if not writing_style or not writing_style.strip():
            raise ValueError(f"章节 {chapter_number} 风格分析为空，请重试")
        
        return {
            "writing_style": writing_style
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context

    def get_required_keys(self) -> list:
        return ["chapter_number"]

    def get_output_keys(self) -> list:
        return ["writing_style"]
