#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用更新后的黑名单重新检查 global_entity_map.json。
"""

import json
import os
import sys

# 从 entity_rewriter.py 导入黑名单
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from entity_rewriter import _ENTITY_BLACKLIST_SINGLE, _ENTITY_BLACKLIST_MULTI, _is_entity_blacklisted

MAP_FILE = os.path.join(os.path.dirname(__file__), '..', 'runtime', 'global_entity_map.json')

def main():
    filepath = os.path.abspath(MAP_FILE)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    issues = []
    for category, entries in data.items():
        for old_name, info in entries.items():
            new_name = info.get('new', '')
            chapter = info.get('first_seen_chapter', -1)
            if _is_entity_blacklisted(old_name):
                issues.append({
                    'category': category,
                    'old': old_name,
                    'new': new_name,
                    'chapter': chapter
                })
    
    if issues:
        print(f"发现 {len(issues)} 个仍在黑名单中的映射:")
        print("-" * 60)
        for item in sorted(issues, key=lambda x: (x['category'], x['old'])):
            print(f"  [{item['category']}] \"{item['old']}\" -> \"{item['new']}\" (章节{item['chapter']})")
        
        # 自动删除
        print(f"\n正在删除 {len(issues)} 个映射...")
        for item in issues:
            del data[item['category']][item['old']]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print("删除完成！")
    else:
        print("映射表中没有黑名单中的词，全部干净！")
    
    # 统计
    total = sum(len(entries) for entries in data.values())
    print(f"\n剩余映射总数: {total}")
    for cat, entries in data.items():
        print(f"  {cat}: {len(entries)} 个")

if __name__ == '__main__':
    main()
