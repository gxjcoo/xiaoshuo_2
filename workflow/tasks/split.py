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
            - novel_path: 小说文件路径（可选）
            - output_dir: 输出目录
            
        输出：
            - chapters: 章节文件列表
            - chapter_count: 章节数量
        """
        novel_path = context.get("novel_path")
        output_dir = context.get("chapters_dir", "chapters")
        
        # 如果指定了小说文件，则执行切章
        if novel_path:
            if not os.path.exists(novel_path):
                raise FileNotFoundError(f"小说文件不存在: {novel_path}")
            
            # 调用现有的切章逻辑
            from split_novel import split_novel_to_chapters
            
            split_novel_to_chapters(novel_path, output_dir)
        else:
            # 如果没有指定小说文件，假设章节文件已存在于输入目录
            print(f"未指定小说文件路径，跳过切章步骤，使用现有章节文件")
        
        # 获取切章后的文件列表
        # 优先查找 chapters 目录（split_novel.py 默认输出目录）
        search_dirs = [output_dir, "chapters", context.get("input_dir", "chapters")]
        chapters = []
        found_dir = None
        
        for dir_path in search_dirs:
            if dir_path and os.path.exists(dir_path):
                found_chapters = sorted([
                    f for f in os.listdir(dir_path)
                    if f.endswith('.md') and f[0].isdigit()
                ])
                if found_chapters:
                    chapters = found_chapters
                    found_dir = dir_path
                    break
        
        if chapters:
            output_dir = found_dir
            print(f"找到 {len(chapters)} 个章节文件: {output_dir}")
        else:
            print(f"未找到任何章节文件")
        
        return {
            "chapters": chapters,
            "chapter_count": len(chapters),
            "chapters_dir": output_dir
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        # novel_path 是可选的，如果没有则跳过切章
        return True

    def get_required_keys(self) -> list:
        # novel_path 是可选的
        return []

    def get_output_keys(self) -> list:
        return ["chapters", "chapter_count", "chapters_dir"]
