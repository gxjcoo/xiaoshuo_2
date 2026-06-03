#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面检查 global_entity_map.json 中的问题映射。

检查项目：
1. 黑名单中的字符仍有映射
2. 通用词/常用词不应作为实体名
3. 循环映射（A→B 同时 B→A）
4. 同一实体在不同类别中有不同的 new_name
5. 其他可疑映射
"""

import json
import sys
import os

# 黑名单（与 entity_rewriter.py 一致）
BLACKLIST_SINGLE = frozenset([
    "头", "口", "手", "脚", "眼", "心", "脸", "身", "嘴", "耳", "鼻", "眉", "发",
    "人", "大", "小", "上", "下", "左", "右", "前", "后", "里", "外", "中", "内",
    "天", "地", "山", "水", "风", "火", "石", "木", "草", "花", "树", "云", "雨",
    "金", "银", "铁", "铜", "玉", "珠", "刀", "剑", "门", "路", "桥", "车", "船",
    "家", "房", "屋", "城", "村", "镇", "县", "州", "府", "国", "殿", "楼", "阁",
    "老", "新", "男", "女", "长", "少", "公", "母", "好", "坏", "黑", "白", "红",
    "走", "来", "去", "看", "听", "说", "吃", "喝", "坐", "站", "跑", "飞", "打",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "百", "千", "万",
    "你", "我", "他", "她", "它", "谁", "这", "那", "什么", "怎么", "哪",
    "的", "了", "着", "过", "地", "得", "把", "被", "让", "给", "对", "向", "从",
    "和", "与", "及", "或", "但", "而", "就", "也", "都", "还", "又", "再", "才",
    "很", "太", "最", "更", "越", "挺", "真", "假", "会", "能", "要", "想", "该",
    "菜", "酒",
])

# 通用词列表（不应作为实体名的常见词）
GENERIC_WORDS = {
    # 称谓/身份
    "少女", "丫鬟", "车夫", "樵夫", "捕头", "公差", "大人", "师姐", "师尊",
    "师父", "和尚", "年轻人", "老夫", "贫道", "老丈", "闺女", "少爷", "道士",
    "青年", "国师", "师叔", "陛下", "工匠", "老爷", "弟子", "小子",
    # 常见物品
    "头发", "包裹", "饭菜", "牛车", "马车",
    # 常见地点词
    "官道", "山上", "山门", "京城", "家乡", "大门", "村落", "后山",
    # 常见动作/状态
    "吃人", "事发", "自嘲", "拂袖", "驱邪", "共识", "变故", "诛杀", "反扑",
    "报仇", "看家", "撞见", "关押", "清洗", "筛查", "炖汤", "干活", "清点",
    "悟道", "炼器", "送死", "斗法",
    # 其他
    "小熊",
}

def check_entity_map(filepath):
    """全面检查实体映射表。"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    issues = {
        'blacklisted': [],      # 黑名单中的映射
        'generic': [],          # 通用词映射
        'circular': [],         # 循环映射
        'duplicate_key': [],    # 同一 key 在不同类别
        'duplicate_new': [],    # 同一 key 有不同 new_name
    }
    
    # 收集所有映射
    all_mappings = {}  # key -> [(category, new_name, first_seen_chapter)]
    
    for category, entries in data.items():
        for old_name, info in entries.items():
            new_name = info.get('new', '')
            chapter = info.get('first_seen_chapter', -1)
            
            # 1. 检查黑名单
            if old_name in BLACKLIST_SINGLE:
                issues['blacklisted'].append({
                    'category': category,
                    'old': old_name,
                    'new': new_name,
                    'chapter': chapter,
                    'reason': '单字在黑名单中'
                })
            
            # 2. 检查通用词
            if old_name in GENERIC_WORDS:
                issues['generic'].append({
                    'category': category,
                    'old': old_name,
                    'new': new_name,
                    'chapter': chapter,
                    'reason': '通用词不应作为实体名'
                })
            
            # 收集映射
            if old_name not in all_mappings:
                all_mappings[old_name] = []
            all_mappings[old_name].append((category, new_name, chapter))
    
    # 3. 检查循环映射
    # 构建 old->new 映射
    old_to_new = {}
    for category, entries in data.items():
        for old_name, info in entries.items():
            new_name = info.get('new', '')
            if old_name and new_name:
                old_to_new[old_name] = new_name
    
    seen_pairs = set()
    for old_name, new_name in old_to_new.items():
        pair_key = tuple(sorted([old_name, new_name]))
        if pair_key in seen_pairs:
            continue
        if new_name in old_to_new and old_to_new[new_name] == old_name:
            issues['circular'].append({
                'old_a': old_name,
                'new_a': new_name,
                'old_b': new_name,
                'new_b': old_name,
                'reason': 'A<->B 循环映射'
            })
            seen_pairs.add(pair_key)
    
    # 4. 检查同一 key 在不同类别中有不同 new_name
    for old_name, mappings in all_mappings.items():
        if len(mappings) > 1:
            new_names = set(m[1] for m in mappings)
            if len(new_names) > 1:
                issues['duplicate_new'].append({
                    'old': old_name,
                    'mappings': [(m[0], m[1], m[2]) for m in mappings],
                    'reason': f'同一实体有 {len(new_names)} 个不同的 new_name'
                })
    
    return issues

def print_report(issues):
    """打印检查报告。"""
    print("=" * 70)
    print("  实体映射表全面检查报告")
    print("=" * 70)
    
    total_issues = sum(len(v) for v in issues.values())
    
    # 1. 黑名单问题
    print(f"\n[1] 黑名单中的映射 ({len(issues['blacklisted'])} 个)")
    print("-" * 50)
    if issues['blacklisted']:
        for item in issues['blacklisted']:
            print(f"  [{item['category']}] \"{item['old']}\" -> \"{item['new']}\" (章节{item['chapter']})")
    else:
        print("  无问题")
    
    # 2. 通用词问题
    print(f"\n[2] 通用词映射 ({len(issues['generic'])} 个)")
    print("-" * 50)
    if issues['generic']:
        for item in issues['generic']:
            print(f"  [{item['category']}] \"{item['old']}\" -> \"{item['new']}\" (章节{item['chapter']})")
    else:
        print("  无问题")
    
    # 3. 循环映射
    print(f"\n[3] 循环映射 ({len(issues['circular'])} 个)")
    print("-" * 50)
    if issues['circular']:
        for item in issues['circular']:
            print(f"  \"{item['old_a']}\" <-> \"{item['new_a']}\" (互相映射)")
    else:
        print("  无问题")
    
    # 4. 同一 key 不同 new_name
    print(f"\n[4] 同一实体在不同类别中有不同映射 ({len(issues['duplicate_new'])} 个)")
    print("-" * 50)
    if issues['duplicate_new']:
        for item in issues['duplicate_new']:
            print(f"  \"{item['old']}\":")
            for cat, new, ch in item['mappings']:
                print(f"    [{cat}] -> \"{new}\" (章节{ch})")
    else:
        print("  无问题")
    
    # 汇总
    print("\n" + "=" * 70)
    print(f"  总计发现 {total_issues} 个问题")
    print("=" * 70)
    
    # 生成建议删除列表
    print("\n[建议删除的映射]")
    print("-" * 50)
    
    to_delete = set()
    
    for item in issues['blacklisted']:
        to_delete.add((item['category'], item['old']))
    
    for item in issues['generic']:
        to_delete.add((item['category'], item['old']))
    
    for item in issues['circular']:
        # 循环映射，删除较短的那个（通常是通用词）
        to_delete.add(('characters', item['old_a']))
        to_delete.add(('characters', item['old_b']))
    
    for cat, old in sorted(to_delete):
        print(f"  [{cat}] \"{old}\"")
    
    return to_delete

if __name__ == '__main__':
    filepath = os.path.join(os.path.dirname(__file__), '..', 'runtime', 'global_entity_map.json')
    filepath = os.path.abspath(filepath)
    
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        sys.exit(1)
    
    issues = check_entity_map(filepath)
    to_delete = print_report(issues)
    
    # 保存到文件
    report_path = os.path.join(os.path.dirname(__file__), 'entity_map_check_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        print_report(issues)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        f.write(output)
    
    print(f"\n报告已保存到: {report_path}")
