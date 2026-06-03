#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量删除 global_entity_map.json 中的问题映射。

删除类别：
1. 黑名单映射（2个）
2. 通用词映射（62个）
3. 循环映射（2个）
4. 同一实体不同类别的冲突映射（选择保留一个）
"""

import json
import os
import sys

MAP_FILE = os.path.join(os.path.dirname(__file__), '..', 'runtime', 'global_entity_map.json')

# 黑名单映射：必须删除
BLACKLIST_DELETES = {
    ('objects_animals', '菜'),
    ('objects_animals', '酒'),
}

# 通用词映射：必须删除
GENERIC_DELETES = {
    ('characters', '小熊'),
    ('characters', '少女'),
    ('characters', '捕头'),
    ('characters', '公差'),
    ('characters', '大人'),
    ('characters', '师姐'),
    ('characters', '师尊'),
    ('characters', '丫鬟'),
    ('characters', '车夫'),
    ('characters', '樵夫'),
    ('characters', '和尚'),
    ('characters', '年轻人'),
    ('characters', '老夫'),
    ('characters', '贫道'),
    ('characters', '老丈'),
    ('characters', '闺女'),
    ('characters', '牛车'),
    ('characters', '少爷'),
    ('characters', '道士'),
    ('characters', '青年'),
    ('characters', '国师'),
    ('characters', '师叔'),
    ('characters', '陛下'),
    ('characters', '师父'),
    ('characters', '工匠'),
    ('characters', '老爷'),
    ('characters', '弟子'),
    ('places', '京城'),
    ('places', '官道'),
    ('places', '山上'),
    ('places', '山门'),
    ('places', '村落'),
    ('places', '家乡'),
    ('places', '大门'),
    ('places', '后山'),
    ('events', '吃人'),
    ('events', '事发'),
    ('events', '自嘲'),
    ('events', '拂袖'),
    ('events', '驱邪'),
    ('events', '共识'),
    ('events', '变故'),
    ('events', '诛杀'),
    ('events', '反扑'),
    ('events', '报仇'),
    ('events', '看家'),
    ('events', '撞见'),
    ('events', '关押'),
    ('events', '清洗'),
    ('events', '筛查'),
    ('events', '炖汤'),
    ('events', '干活'),
    ('events', '清点'),
    ('events', '悟道'),
    ('events', '炼器'),
    ('events', '送死'),
    ('objects_animals', '小熊'),
    ('objects_animals', '头发'),
    ('objects_animals', '包裹'),
    ('objects_animals', '饭菜'),
    ('objects_animals', '马车'),
    ('objects_animals', '斗法'),
}

# 循环映射：删除一个保留一个
# "师尊"<->"师父"：删除 characters 师尊 和 characters 师父（已在通用词中）
# "功绩"<->"功勋"：删除 objects_animals 中的功勋
CIRCULAR_DELETES = {
    ('objects_animals', '功勋'),
}

# 冲突映射：同一实体在不同类别中有不同 new_name，删除冲突的那个
# "宝寿道长": characters->青云道人(保留), objects->清虚道长(删除)
# "小熊": characters->玄熊(已在通用词中删除), objects->墨熊(已在通用词中删除)
# "赤玄蛟龙": characters->赤炎蛟龙(保留), objects->玄炎蛟龙(删除)
# "大夏王朝": characters->炎夏王朝(保留), places->大周王朝(删除)
# "红衣斩妖吏": characters->赤衣诛魔使(保留), objects->赤袍诛魔使(删除)
# "小熊仔": characters->幼熊(保留), objects->玄熊崽(删除)
# "猎杀榜": events->诛妖榜(保留), objects->诛魔令(删除)
# "炼气大成": events->聚气大成(保留), objects->聚气境大成(删除)
# "白光": events->祖师神念(保留), objects->神异白光(删除)
CONFLICT_DELETES = {
    ('objects_animals', '宝寿道长'),
    ('objects_animals', '赤玄蛟龙'),
    ('places', '大夏王朝'),
    ('objects_animals', '红衣斩妖吏'),
    ('objects_animals', '小熊仔'),
    ('objects_animals', '猎杀榜'),
    ('objects_animals', '炼气大成'),
    ('objects_animals', '白光'),
}

# 合并所有要删除的映射
ALL_DELETES = BLACKLIST_DELETES | GENERIC_DELETES | CIRCULAR_DELETES | CONFLICT_DELETES

def main():
    filepath = os.path.abspath(MAP_FILE)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    deleted = []
    not_found = []
    
    for category, old_name in ALL_DELETES:
        if category in data and old_name in data[category]:
            info = data[category][old_name]
            deleted.append({
                'category': category,
                'old': old_name,
                'new': info.get('new', ''),
                'chapter': info.get('first_seen_chapter', -1)
            })
            del data[category][old_name]
        else:
            not_found.append((category, old_name))
    
    # 保存修改后的文件
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 打印结果
    print(f"成功删除 {len(deleted)} 个问题映射")
    print(f"未找到 {len(not_found)} 个映射")
    
    if deleted:
        print("\n已删除的映射:")
        print("-" * 60)
        for item in sorted(deleted, key=lambda x: (x['category'], x['old'])):
            print(f"  [{item['category']}] \"{item['old']}\" -> \"{item['new']}\" (章节{item['chapter']})")
    
    if not_found:
        print("\n未找到的映射（可能已被删除）:")
        for cat, old in not_found:
            print(f"  [{cat}] \"{old}\"")
    
    # 统计剩余映射
    total_remaining = sum(len(entries) for entries in data.values())
    print(f"\n剩余映射总数: {total_remaining}")
    for cat, entries in data.items():
        print(f"  {cat}: {len(entries)} 个")

if __name__ == '__main__':
    main()
