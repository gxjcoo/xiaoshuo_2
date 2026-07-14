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
        
        # 强制检查：必须先执行拆书，获取世界观、人物关系、核心设定
        self._check_book_profile_exists()
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
        
        # 加载拆书设定（必须：生成时强制依赖这些设定，不能冲突）
        book_profile = self._load_book_profile()

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
            entity_map=entity_map,
            book_profile=book_profile,
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
    
    def _check_book_profile_exists(self):
        """强制检查：必须先完成 split_novel、decompose_book、inject_profile 三个前置任务
        
        检查顺序和产物：
        1. split_novel → chapters/*.md（章节文件）
        2. decompose_book → book_profile.json（拆书设定）
        3. inject_profile → story_context.json 包含拆书结果（已注入的统一上下文）
        
        任何一个产物缺失，立即报错终止。
        """
        from config import RUNTIME_DIR
        import json
        
        errors = []
        
        # ── 1. 检查 split_novel 产物：chapters 目录下有 .md 文件 ──
        chapters_dir = "chapters"
        if not os.path.isdir(chapters_dir):
            errors.append("  ✗ split_novel：未找到 chapters/ 目录，请先执行切章任务")
        else:
            chapter_files = [f for f in os.listdir(chapters_dir) if f.endswith('.md') and f[0].isdigit()]
            if not chapter_files:
                errors.append("  ✗ split_novel：chapters/ 目录下无章节文件，请先执行切章任务")
        
        # ── 2. 检查 decompose_book 产物：book_profile.json ──
        book_profile_path = "book_profile.json"
        if not os.path.exists(book_profile_path):
            errors.append("  ✗ decompose_book：未找到 book_profile.json，请先执行拆书任务")
        else:
            try:
                with open(book_profile_path, "r", encoding="utf-8") as f:
                    bp = json.load(f)
                if not isinstance(bp, dict) or not bp:
                    errors.append("  ✗ decompose_book：book_profile.json 内容为空或格式错误")
            except Exception as e:
                errors.append(f"  ✗ decompose_book：book_profile.json 解析失败: {e}")
        
        # ── 3. 检查 inject_profile 产物：story_context.json 包含拆书结果 ──
        story_context_path = os.path.join(RUNTIME_DIR, "story_context.json") if RUNTIME_DIR else "story_context.json"
        if not os.path.exists(story_context_path):
            story_context_path = "story_context.json"
        
        inject_ok = False
        if os.path.exists(story_context_path):
            try:
                with open(story_context_path, "r", encoding="utf-8") as f:
                    ctx = json.load(f)
                # inject_profile 注入的核心字段（注意：protagonist 存为 protagonist_info）
                required_keys = ["world_setting", "protagonist_info", "core_conflict"]
                present_keys = [k for k in required_keys if k in ctx]
                if len(present_keys) == len(required_keys):
                    inject_ok = True
                else:
                    missing = set(required_keys) - set(present_keys)
                    errors.append(f"  ✗ inject_profile：story_context.json 缺少已注入的字段: {', '.join(missing)}")
            except Exception as e:
                errors.append(f"  ✗ inject_profile：story_context.json 解析失败: {e}")
        else:
            errors.append("  ✗ inject_profile：未找到 story_context.json，请先执行设定注入任务")
        
        # ── 汇总：任何一项失败都终止 ──
        if errors:
            raise RuntimeError(
                "\n" + "=" * 60 + "\n"
                "错误：写书前置条件未满足！\n\n"
                "必须先完成以下三个任务，产物文件齐全后才能生成正文：\n\n"
                "  1. split_novel  → chapters/*.md\n"
                "  2. decompose_book → book_profile.json\n"
                "  3. inject_profile → story_context.json（含拆书结果）\n\n"
                "当前检查结果：\n"
                + "\n".join(errors) + "\n\n"
                "请按顺序执行：\n"
                "  python -m workflow.cli run --novel <小说文件路径> --start 1 --end <章节数>\n"
                + "=" * 60
            )
    
    def _load_book_profile(self) -> dict:
        """加载拆书设定，用于约束章节生成内容，防止与世界观、人物、核心设定冲突
        
        加载策略：
        优先从 story_context.json 读取（inject_profile 注入后的统一上下文），
        因为 inject_profile 会对拆书结果做格式规范化和合并。
        如果 story_context.json 中没有相关字段，才回退到 book_profile.json。
        """
        import json
        from config import RUNTIME_DIR
        
        # ── 优先：从 story_context.json 读取（inject_profile 注入后的版本）──
        story_context_path = os.path.join(RUNTIME_DIR, "story_context.json") if RUNTIME_DIR else "story_context.json"
        if not os.path.exists(story_context_path):
            story_context_path = "story_context.json"
        
        if os.path.exists(story_context_path):
            try:
                with open(story_context_path, "r", encoding="utf-8") as f:
                    ctx = json.load(f)
                # 提取拆书相关字段
                profile_keys = [
                    "world_setting", "protagonist", "core_conflict", "power_system",
                    "golden_finger", "antagonists", "foreshadowing", "volume_plan",
                    "writing_style_guide"
                ]
                profile = {}
                for key in profile_keys:
                    if key in ctx:
                        profile[key] = ctx[key]
                if profile:
                    return profile
            except Exception as e:
                print(f"  警告：从 story_context.json 加载拆书设定失败: {e}")
        
        # ── 回退：从 book_profile.json 读取原始拆书结果 ──
        book_profile_path = "book_profile.json"
        if os.path.exists(book_profile_path):
            try:
                with open(book_profile_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"  警告：加载 book_profile.json 失败: {e}")
        
        return {}
