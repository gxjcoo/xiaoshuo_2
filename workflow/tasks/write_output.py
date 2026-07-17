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
            - entity_map: 实体映射（可选）
            - entity_rewrite_enabled: 是否启用实体改写

        输出：
            - output_path: 输出文件路径
        """
        chapter_number = context.get("chapter_number")
        final_content = context.get("final_content")
        generated_title = context.get("generated_title", f"第{chapter_number}章")
        output_dir = context.get("output_dir", "output_chapters")
        entity_map = context.get("entity_map")
        entity_rewrite_enabled = context.get("entity_rewrite_enabled", True)

        if not final_content:
            raise ValueError("没有内容可写入")

        # 写盘前实体改写：强制把任何残留原名替换为新名
        if entity_rewrite_enabled and entity_map:
            from entity_rewriter import apply_entity_rewrite, detect_original_entity_leaks, format_entity_leak_report
            leaks = detect_original_entity_leaks(final_content, entity_map)
            if leaks:
                print(f"  写盘前发现 {len(leaks)} 个原名残留，执行硬替换：")
                print(format_entity_leak_report(leaks))
                final_content = apply_entity_rewrite(final_content, entity_map)
                leaks_after = detect_original_entity_leaks(final_content, entity_map)
                if leaks_after:
                    print(f"  警告：硬替换后仍残留 {len(leaks_after)} 项")
                else:
                    print("  硬替换完成，已无原名残留。")
        
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
