"""章节处理器 - 提供审计规则加载等基础功能"""

import os
import json

from config import (
    AUDIT_RULES_FILE,
    AUDIT_MAX_REVISE_ROUNDS,
)


# 审计规则默认值。当 audit_rules.json 不存在或损坏时使用。
_DEFAULT_AUDIT_RULES = {
    "pass_threshold": 68,
    "deterministic_penalty_cap_total": 12,
    "deterministic_penalty_cap_ai_trace": 10,
    "ai_trace_hard_threshold": 50,
    "hard_fail_threshold": 40,
    "max_revise_rounds": AUDIT_MAX_REVISE_ROUNDS,
    "dimensions": [
        {"id": "continuity", "name": "连贯性", "weight": 0.3, "requirements": ["剧情衔接自然", "设定不冲突"]},
        {"id": "pacing", "name": "节奏", "weight": 0.2, "requirements": ["本章有推进", "节奏不过慢"]},
        {"id": "ai_trace", "name": "AI痕迹", "weight": 0.3, "requirements": ["减少模板句式", "减少总结腔"]},
        {"id": "voice", "name": "文风", "weight": 0.2, "requirements": ["风格一致", "对话有区分"]},
    ],
}


def load_audit_rules():
    """加载审计规则，缺失或异常时回退默认规则。"""
    if not os.path.isfile(AUDIT_RULES_FILE):
        return dict(_DEFAULT_AUDIT_RULES)
    try:
        with open(AUDIT_RULES_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return dict(_DEFAULT_AUDIT_RULES)
        for key, default_value in _DEFAULT_AUDIT_RULES.items():
            loaded.setdefault(key, default_value)
        return loaded
    except Exception as e:
        print(f"警告：加载审计规则失败，回退默认规则: {e}")
        return dict(_DEFAULT_AUDIT_RULES)
