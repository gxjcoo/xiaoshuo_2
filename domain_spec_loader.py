"""加载意图文档，供生成提示词使用。"""
import os

from config import (
    AUTHOR_INTENT_FILE,
    CURRENT_FOCUS_FILE,
    MAX_AUTHOR_INTENT_CHARS,
    MAX_CURRENT_FOCUS_CHARS,
)


def _load_optional_text_file(path, max_chars, label):
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError as e:
        print(f"警告: 无法读取 {label} 文件 {path}: {e}")
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n…（{label} 已按长度截断）"
    return text


def load_author_intent_text(path=None, max_chars=None):
    """读取作者长期意图文档 author_intent.md。max_chars 默认 MAX_AUTHOR_INTENT_CHARS。"""
    target = path or AUTHOR_INTENT_FILE
    cap = int(max_chars) if max_chars is not None else MAX_AUTHOR_INTENT_CHARS
    return _load_optional_text_file(target, max(200, cap), "author_intent")


def load_current_focus_text(path=None, max_chars=None):
    """读取近 1-3 章焦点文档 current_focus.md。max_chars 默认 MAX_CURRENT_FOCUS_CHARS。"""
    target = path or CURRENT_FOCUS_FILE
    cap = int(max_chars) if max_chars is not None else MAX_CURRENT_FOCUS_CHARS
    return _load_optional_text_file(target, max(200, cap), "current_focus")
