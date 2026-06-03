#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用正向验证规则清理全局实体映射中的不合规条目。"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from entity_rewriter import (
    load_global_entity_map, save_global_entity_map, validate_entity, 
    flatten_entity_map, ENTITY_CATEGORIES
)

def main():
    global_map = load_global_entity_map()
    
    deleted = []
    kept = []
    
    for cat in ENTITY_CATEGORIES:
        entries = global_map.get(cat, {}) or {}
        to_delete = []
        
        for old, v in entries.items():
            if isinstance(v, dict):
                new_name = v.get("new", "?")
                chapter = v.get("first_seen_chapter", "?")
            else:
                new_name = v
                chapter = "?"
            
            if validate_entity(old, cat):
                kept.append((old, new_name, cat, chapter))
            else:
                deleted.append((old, new_name, cat, chapter))
                to_delete.append(old)
        
        for old in to_delete:
            del entries[old]
    
    print(f"=== 清理结果 ===")
    print(f"保留: {len(kept)} 条")
    print(f"删除: {len(deleted)} 条")
    
    if deleted:
        by_cat = {}
        for old, new, cat, ch in deleted:
            by_cat.setdefault(cat, []).append((old, new, ch))
        
        for cat in ENTITY_CATEGORIES:
            items = by_cat.get(cat, [])
            if not items:
                continue
            label = {"characters": "角色", "places": "地名", "events": "事件", "objects_animals": "物件/动物"}
            print(f"\n[{label.get(cat, cat)}] 删除 {len(items)} 条:")
            for old, new, ch in items:
                print(f"  {old} → {new}  (首见: 第{ch}章)")
    
    # 保存清理后的映射
    save_global_entity_map(global_map)
    print(f"\n已保存清理后的全局映射到 global_entity_map.json")

if __name__ == '__main__':
    main()
