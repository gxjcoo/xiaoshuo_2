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

        # 导入标题标准化函数
        from llm.titles import normalize_chapter_title

        # 构建输出内容 - 检查 final_content 是否已包含标题，避免重复
        final_content_stripped = final_content.strip()
        if final_content_stripped.startswith("# "):
            # final_content 已有标题（来自修订器），提取并标准化
            lines = final_content_stripped.split("\n")
            title_line = lines[0]  # "# 第二章 xxx"
            title_text = title_line.lstrip("# ").strip()  # "第二章 xxx"

            # 获取正文内容用于提取副标题
            body_lines = lines[1:]
            # 跳过标题后的空行
            while body_lines and not body_lines[0].strip():
                body_lines = body_lines[1:]
            body_content = "\n".join(body_lines)

            # 标准化标题格式（传入正文内容用于提取副标题）
            normalized_title = normalize_chapter_title(title_text, chapter_number, body_content)

            # 如果正文第一行与标题相同（不带#），移除重复的标题
            if body_lines and body_lines[0].strip() == title_text:
                print(f"  检测到正文中重复标题，已移除: {title_text}")
                body_lines = body_lines[1:]
                # 跳过重复标题后的空行
                while body_lines and not body_lines[0].strip():
                    body_lines = body_lines[1:]

            # 重组内容
            output_content = f"# {normalized_title}\n\n" + "\n".join(body_lines)
            print(f"  使用标准化标题: {normalized_title}")
        else:
            # final_content 无标题，添加 generated_title
            # 标准化 generated_title（传入正文内容用于提取副标题）
            normalized_title = normalize_chapter_title(generated_title, chapter_number, final_content_stripped)
            output_content = f"# {normalized_title}\n\n{final_content_stripped}"
            print(f"  使用生成标题: {normalized_title}")

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
