"""
拆书结果注入任务 - 将 book_profile 合并到 story_context.json

功能：
- 将拆书生成的设定信息注入到故事上下文中
- 为后续章节处理提供世界观、人物、伏笔等基础信息
"""

import json
import os
from typing import Any, Dict

from ..base import TaskNode


class InjectProfileTask(TaskNode):
    """将拆书结果注入到故事上下文"""

    @property
    def id(self) -> str:
        return "inject_profile"

    @property
    def name(self) -> str:
        return "注入设定"

    @property
    def deps(self) -> list:
        return ["decompose_book"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行设定注入
        
        输入：
            - book_profile: 拆书生成的完整设定
            - book_profile_path: 设定文件路径（可选）
            
        输出：
            - profile_injected: 是否注入成功
            - context_file: 更新后的上下文文件路径
        """
        from context_manager import load_story_context, save_story_context
        
        book_profile = context.get("book_profile")
        
        # 如果没有直接传入，尝试从文件加载
        if not book_profile:
            profile_path = context.get("book_profile_path", "book_profile.json")
            if os.path.exists(profile_path):
                with open(profile_path, "r", encoding="utf-8") as f:
                    book_profile = json.load(f)
        
        if not book_profile:
            print("警告: 没有找到拆书结果，跳过注入")
            return {"profile_injected": False}
        
        # 加载现有上下文
        story_context = load_story_context()
        
        # 注入世界观设定
        if "world_setting" in book_profile:
            world_data = book_profile["world_setting"]
            if isinstance(world_data, dict):
                # 合并世界观信息
                if "description" in world_data:
                    story_context["world_setting"]["description"] = world_data["description"]
                if "key_elements" in world_data:
                    # 合并关键元素，去重
                    existing_elements = set(story_context["world_setting"].get("key_elements", []))
                    new_elements = set(world_data["key_elements"])
                    story_context["world_setting"]["key_elements"] = list(existing_elements | new_elements)
                # 保留额外的世界观细节
                story_context["world_setting"]["detailed"] = world_data
        
        # 注入主角信息
        if "protagonist" in book_profile:
            protagonist_data = book_profile["protagonist"]
            if isinstance(protagonist_data, dict):
                if "name" in protagonist_data:
                    story_context["protagonist_info"]["name"] = protagonist_data["name"]
                if "description" in protagonist_data:
                    story_context["protagonist_info"]["description"] = protagonist_data["description"]
                # 保留完整的主角档案
                story_context["protagonist_info"]["profile"] = protagonist_data
        
        # 注入金手指设定
        if "golden_finger" in book_profile:
            story_context["golden_finger"] = book_profile["golden_finger"]
        
        # 注入力量体系
        if "power_system" in book_profile:
            story_context["power_system"] = book_profile["power_system"]
        
        # 注入核心冲突
        if "core_conflict" in book_profile:
            story_context["core_conflict"] = book_profile["core_conflict"]
        
        # 注入主要对手
        if "antagonists" in book_profile:
            story_context["antagonists"] = book_profile["antagonists"]
        
        # 注入伏笔系统
        if "foreshadowing" in book_profile:
            # 将伏笔添加到 pending_hooks 中
            existing_hooks = set(h.get("id", "") for h in story_context.get("pending_hooks", []))
            for hook in book_profile["foreshadowing"]:
                hook_id = hook.get("id", hook.get("content", "")[:20])
                if hook_id not in existing_hooks:
                    story_context.setdefault("pending_hooks", []).append({
                        "id": hook_id,
                        "content": hook.get("content", ""),
                        "chapter_introduced": 0,  # 标记为原始伏笔
                        "status": "open"
                    })
        
        # 注入分卷规划
        if "volume_plan" in book_profile:
            story_context["volume_plan"] = book_profile["volume_plan"]
        
        # 注入写作风格指南
        if "writing_style_guide" in book_profile:
            story_context["writing_style_guide"] = book_profile["writing_style_guide"]
        
        # 保存更新后的上下文
        save_story_context()
        
        print(f"  拆书结果已注入到故事上下文")
        print(f"    - 世界观: {'✓' if 'world_setting' in book_profile else '✗'}")
        print(f"    - 主角档案: {'✓' if 'protagonist' in book_profile else '✗'}")
        print(f"    - 力量体系: {'✓' if 'power_system' in book_profile else '✗'}")
        print(f"    - 金手指: {'✓' if 'golden_finger' in book_profile else '✗'}")
        print(f"    - 核心冲突: {'✓' if 'core_conflict' in book_profile else '✗'}")
        print(f"    - 主要对手: {'✓' if 'antagonists' in book_profile else '✗'}")
        print(f"    - 伏笔系统: {'✓' if 'foreshadowing' in book_profile else '✗'}")
        print(f"    - 分卷规划: {'✓' if 'volume_plan' in book_profile else '✗'}")
        print(f"    - 写作风格: {'✓' if 'writing_style_guide' in book_profile else '✗'}")
        
        return {
            "profile_injected": True,
            "context_file": "story_context.json"
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        # 需要 book_profile 或 book_profile_path
        return "book_profile" in context or "book_profile_path" in context

    def get_required_keys(self) -> list:
        return ["book_profile"]

    def get_output_keys(self) -> list:
        return ["profile_injected", "context_file"]