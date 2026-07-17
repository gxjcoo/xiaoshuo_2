"""
章节规划任务 - 规划章节意图和写作要点
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class ChapterPlanTask(TaskNode):
    """规划章节意图和写作要点"""

    @property
    def id(self) -> str:
        return "chapter_plan"

    @property
    def name(self) -> str:
        return "意图规划"

    @property
    def deps(self) -> list:
        # 允许运行时覆盖（用于动态添加 entity_rewrite 等可选依赖）
        override = getattr(self, '_deps_override', None)
        if override is not None:
            return override
        # 如果 inject_profile 存在，则依赖它
        # 这样可以支持有拆书和无拆书两种模式
        # entity_rewrite 是可选依赖，在 DAG 构建时根据 enable_entity_rewrite 决定是否添加
        base_deps = ["style_analysis", "outline_extract"]
        # inject_profile 是可选依赖，在 DAG 构建时动态添加
        return base_deps

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行章节规划
        
        输入：
            - chapter_number: 当前章节号
            - reference_text: 参考文本
            - outline: 结构化骨架
            - writing_style: 风格分析
            - entity_map: 实体映射
            
        输出：
            - chapter_intent: 章节意图文档
        """
        from ai_handler import plan_chapter_with_ai
        from config import RUNTIME_DIR, STRICT_SOURCE_PLOT
        from context_manager import load_story_context
        
        chapter_number = context.get("chapter_number")
        reference_text = context.get("reference_text")
        outline = context.get("outline")
        writing_style = context.get("writing_style")
        entity_map = context.get("entity_map")
        runtime_dir = context.get("runtime_dir", RUNTIME_DIR)
        
        # 检查缓存
        intent_file = os.path.join(runtime_dir, f"ch{chapter_number:04d}_intent.md")
        if os.path.exists(intent_file):
            print(f"  使用缓存的章节意图: {intent_file}")
            with open(intent_file, "r", encoding="utf-8") as f:
                chapter_intent = f.read()
        else:
            # 加载故事上下文
            current_context = load_story_context()
            
            # 获取上一章内容（用于衔接）
            previous_chapter_content = None
            chapters_dir = context.get("chapters_dir", "chapters")
            if chapter_number > 1:
                prev_file = os.path.join(chapters_dir, f"{chapter_number - 1}.md")
                if os.path.exists(prev_file):
                    with open(prev_file, "r", encoding="utf-8") as f:
                        previous_chapter_content = f.read()
            
            # 调用 AI 规划（参数顺序：context, chapter_number, prev_content, ...）
            chapter_intent = plan_chapter_with_ai(
                current_context,
                chapter_number,
                previous_chapter_content=previous_chapter_content,
                reference_chapter_text=reference_text or "",
                strict_source_plot=STRICT_SOURCE_PLOT
            )
            
            # 缓存结果
            if chapter_intent:
                os.makedirs(runtime_dir, exist_ok=True)
                with open(intent_file, "w", encoding="utf-8") as f:
                    f.write(chapter_intent)
        
        # 验证意图非空
        if not chapter_intent or not chapter_intent.strip():
            raise ValueError(f"章节 {chapter_number} 意图生成为空，请重试")
        
        return {
            "chapter_intent": chapter_intent
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        required = ["chapter_number", "outline"]
        return all(key in context for key in required)

    def get_required_keys(self) -> list:
        return ["chapter_number", "outline"]

    def get_output_keys(self) -> list:
        return ["chapter_intent"]
