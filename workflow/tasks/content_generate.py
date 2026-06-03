"""
正文生成任务 - 生成章节正文内容
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class ContentGenerateTask(TaskNode):
    """生成章节正文内容"""

    @property
    def id(self) -> str:
        return "content_generate"

    @property
    def name(self) -> str:
        return "正文生成"

    @property
    def deps(self) -> list:
        return ["chapter_plan"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行正文生成
        
        输入：
            - chapter_number: 当前章节号
            - chapter_intent: 章节意图
            - outline: 结构化骨架
            - writing_style: 风格分析
            - entity_map: 实体映射
            - target_length: 目标字数
            
        输出：
            - generated_content: 生成的正文内容
            - generated_title: 生成的标题
        """
        from ai_handler import generate_chapter_content
        from config import RUNTIME_DIR, STRICT_SOURCE_PLOT
        from context_manager import load_story_context
        
        chapter_number = context.get("chapter_number")
        chapter_intent = context.get("chapter_intent")
        outline = context.get("outline")
        writing_style = context.get("writing_style")
        entity_map = context.get("entity_map")
        entity_rewrite_enabled = context.get("entity_rewrite_enabled", True)
        target_length = context.get("target_length", 3000)
        runtime_dir = context.get("runtime_dir", RUNTIME_DIR)
        
        if not chapter_intent:
            # 尝试从缓存文件加载
            intent_file = os.path.join(runtime_dir, f"ch{chapter_number:04d}_intent.md")
            if os.path.exists(intent_file):
                with open(intent_file, "r", encoding="utf-8") as f:
                    chapter_intent = f.read()
        
        if not chapter_intent:
            raise ValueError("章节意图未生成")
        
        # 加载故事上下文
        current_context = load_story_context()
        
        # 获取上一章内容
        previous_chapter_content = None
        chapters_dir = context.get("chapters_dir", "chapters")
        if chapter_number > 1:
            prev_file = os.path.join(chapters_dir, f"{chapter_number - 1}.md")
            if os.path.exists(prev_file):
                with open(prev_file, "r", encoding="utf-8") as f:
                    previous_chapter_content = f.read()
        
        # 获取参考文本
        reference_chapter_text = context.get("reference_text", "")
        if not reference_chapter_text:
            ref_file = os.path.join(chapters_dir, f"{chapter_number}.md")
            if os.path.exists(ref_file):
                with open(ref_file, "r", encoding="utf-8") as f:
                    reference_chapter_text = f.read()
        
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
        
        # 生成正文
        result = generate_chapter_content(
            current_context=current_context,
            writing_style=writing_style or "",
            target_length=target_length,
            previous_chapter_content=previous_chapter_content,
            target_chapter_number=chapter_number,
            chapter_plan_text=chapter_intent,
            reference_chapter_text=reference_chapter_text,
            reference_plot_outline=reference_plot_outline,
            strict_source_plot=STRICT_SOURCE_PLOT,
            entity_rewrite=entity_rewrite_enabled,
            entity_map=entity_map
        )
        
        if isinstance(result, tuple):
            generated_content, generated_title = result
        else:
            generated_content = result
            # 从内容中提取标题
            if generated_content and generated_content.strip().startswith("# "):
                lines = generated_content.strip().splitlines()
                generated_title = lines[0].lstrip("# ").strip()
                # 移除标题行和紧随的空行
                body_lines = lines[1:]
                while body_lines and not body_lines[0].strip():
                    body_lines = body_lines[1:]
                generated_content = "\n".join(body_lines)
            else:
                generated_title = f"第{chapter_number}章"
        
        # 验证生成内容非空
        if not generated_content or not generated_content.strip():
            raise ValueError(f"章节 {chapter_number} 正文生成为空，请重试")
        
        return {
            "generated_content": generated_content,
            "generated_title": generated_title
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        required = ["chapter_number", "chapter_intent"]
        return all(key in context for key in required)

    def get_required_keys(self) -> list:
        return ["chapter_number", "chapter_intent"]

    def get_output_keys(self) -> list:
        return ["generated_content", "generated_title"]
