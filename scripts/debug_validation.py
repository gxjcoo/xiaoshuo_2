#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试验证逻辑。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from entity_rewriter import validate_entity, _is_valid_character, _is_valid_treasure

# 测试失败的用例
test_cases = [
    ("宝寿道长", "characters"),
    ("万年灵芝", "objects_animals"),
]

for name, category in test_cases:
    print(f"\n=== 测试: \"{name}\" ({category}) ===")
    if category == "characters":
        print(f"  _is_valid_character: {_is_valid_character(name)}")
    elif category == "objects_animals":
        print(f"  _is_valid_treasure: {_is_valid_treasure(name)}")
    print(f"  validate_entity: {validate_entity(name, category)}")
