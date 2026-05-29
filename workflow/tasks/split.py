"""
切章任务 - 将小说文本分割为章节
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class SplitNovelTask(TaskNode):
    """将小说文本切分为独立章节文件"""

    @property
    def id(self) -> str:
        return "split_novel"

    @property
    def name(self) -> str:
        return "切章"

    @property
    def deps(self) -> list:
        return []

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行切章操作
        
        输入：
            - novel_path: 小说文件路径
            - output_dir: 输出目录
            
        输出：
            - chapters: 章节文件列表
            - chapter_count: 章节数量
        """
        novel_path = context.get("novel_path")
        output_dir = context.get("chapters_dir", "chapters")
        
        if not novel_path:
            raise ValueError("未指定小说文件路径 (novel_path)")
        
        if not os.path.exists(novel_path):
            raise FileNotFoundError(f"小说文件不存在: {novel_path}")
        
        # 调用现有的切章逻辑
        from split_novel import split_novel
        
        chapters = split_novel(novel_path, output_dir)
        
        return {
            "chapters": chapters,
            "chapter_count": len(chapters),
            "chapters_dir": output_dir
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "novel_path" in context

    def get_required_keys(self) -> list:
        return ["novel_path"]

    def get_output_keys(self) -> list:
        return ["chapters", "chapter_count", "chapters_dir"]
