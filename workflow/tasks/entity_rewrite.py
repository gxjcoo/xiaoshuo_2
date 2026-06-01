"""
实体改写任务 - 提取和应用实体映射
"""

import os
from typing import Any, Dict

from ..base import TaskNode


class EntityRewriteTask(TaskNode):
    """提取实体映射并准备改写规则"""

    @property
    def id(self) -> str:
        return "entity_rewrite"

    @property
    def name(self) -> str:
        return "实体改写"

    @property
    def deps(self) -> list:
        return ["split_novel"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行实体映射提取
        
        输入：
            - chapter_number: 当前章节号
            - reference_text: 参考文本
            - entity_rewrite_enabled: 是否启用实体改写
            
        输出：
            - entity_map: 实体映射字典
            - entity_rewrite_enabled: 是否启用
        """
        from entity_rewriter import (
            extract_entity_map_from_reference,
            load_cached_entity_map,
            save_entity_map,
            load_global_entity_map,
            save_global_entity_map,
            merge_entity_maps,
            flatten_entity_map
        )
        from config import RUNTIME_DIR
        
        chapter_number = context.get("chapter_number")
        reference_text = context.get("reference_text")
        entity_rewrite_enabled = context.get("entity_rewrite_enabled", True)
        runtime_dir = context.get("runtime_dir", RUNTIME_DIR)
        
        if not entity_rewrite_enabled:
            return {
                "entity_map": None,
                "entity_rewrite_enabled": False
            }
        
        if not reference_text:
            # 尝试从文件加载
            chapters_dir = context.get("chapters_dir", "chapters")
            ref_file = os.path.join(chapters_dir, f"{chapter_number}.md")
            if os.path.exists(ref_file):
                with open(ref_file, "r", encoding="utf-8") as f:
                    reference_text = f.read()
        
        if not reference_text:
            return {
                "entity_map": None,
                "entity_rewrite_enabled": False
            }
        
        # 检查缓存
        cached_map = load_cached_entity_map(chapter_number)
        if cached_map:
            print(f"  使用缓存的实体映射: chapter {chapter_number}")
            entity_map = cached_map
        else:
            # 加载全局映射作为基准，确保跨章节一致性
            global_map = load_global_entity_map()
            # 提取实体映射，传入全局映射以保持一致性
            entity_map = extract_entity_map_from_reference(reference_text, chapter_number, global_map)
            
            if entity_map:
                # 保存章节映射
                save_entity_map(chapter_number, entity_map)
                
                # 合并到全局映射
                merged = merge_entity_maps(global_map, entity_map, chapter_number)
                save_global_entity_map(merged)
        
        # 获取全局实体映射，确保跨章节一致性
        global_entity_map = load_global_entity_map()
        flat_map = flatten_entity_map(global_entity_map) if global_entity_map else None
        
        return {
            "entity_map": flat_map,  # 返回扁平化格式，与 _entity_rewrite_block 兼容
            "entity_map_flat": flat_map,
            "entity_rewrite_enabled": True
        }

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context

    def get_required_keys(self) -> list:
        return ["chapter_number"]

    def get_output_keys(self) -> list:
        return ["entity_map", "entity_map_flat", "entity_rewrite_enabled"]
