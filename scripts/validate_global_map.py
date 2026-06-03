#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用正向验证规则扫描全局实体映射，找出不合规的条目。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from entity_rewriter import (
    load_global_entity_map, validate_entity, flatten_entity_map, ENTITY_CATEGORIES
)

def main():
    global_map = load_global_entity_map()
    flat = flatten_entity_map(global_map)
    
    invalid = []
    valid_count = 0
    
    for cat in ENTITY_CATEGORIES:
        entries = global_map.get(cat, {}) or {}
        for old, v in entries.items():
            if isinstance(v, dict):
                new_name = v.get("new", "?")
                chapter = v.get("first_seen_chapter", "?")
            else:
                new_name = v
                chapter = "?"
            
            if validate_entity(old, cat):
                valid_count += 1
            else:
                invalid.append((old, new_name, cat, chapter))
    
    print(f"=== 全局实体映射验证报告 ===")
    print(f"合法条目: {valid_count}")
    print(f"不合规条目: {len(invalid)}")
    
    if invalid:
        print(f"\n不合规条目列表:")
        by_cat = {}
        for old, new, cat, ch in invalid:
            by_cat.setdefault(cat, []).append((old, new, ch))
        
        for cat in ENTITY_CATEGORIES:
            items = by_cat.get(cat, [])
            if not items:
                continue
            label = {"characters": "角色", "places": "地名", "events": "事件", "objects_animals": "物件/动物"}
            print(f"\n[{label.get(cat, cat)}] ({len(items)} 条)")
            for old, new, ch in items:
                print(f"  {old} → {new}  (首见: 第{ch}章)")

if __name__ == '__main__':
    main()
