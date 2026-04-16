"""加载领域圣经文本与意图文档，供生成提示词使用。"""
import os

from config import (
    STORY_DOMAIN_DIR,
    MAX_DOMAIN_PROMPT_CHARS,
    AUTHOR_INTENT_FILE,
    CURRENT_FOCUS_FILE,
    MAX_AUTHOR_INTENT_CHARS,
    MAX_CURRENT_FOCUS_CHARS,
)


def load_story_domain_text(domain_dir=None):
    """读取 story_domain 下所有 .md（排除 _ 前缀），按文件名排序拼接。"""
    base = domain_dir or STORY_DOMAIN_DIR
    if not os.path.isdir(base):
        return ""

    names = sorted(
        f
        for f in os.listdir(base)
        if f.endswith(".md") and not f.startswith("_")
    )
    parts = []
    for name in names:
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read().strip()
        except OSError as e:
            print(f"警告: 无法读取领域文件 {path}: {e}")
            continue
        if text:
            parts.append(f"## 文件: {name}\n{text}")

    if not parts:
        return ""

    full = "\n\n".join(parts)
    if len(full) > MAX_DOMAIN_PROMPT_CHARS:
        full = full[:MAX_DOMAIN_PROMPT_CHARS] + "\n\n…（领域文本已按长度截断）"
    return full


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


def load_author_intent_text(path=None):
    """读取作者长期意图文档 author_intent.md。"""
    target = path or AUTHOR_INTENT_FILE
    return _load_optional_text_file(target, MAX_AUTHOR_INTENT_CHARS, "author_intent")


def load_current_focus_text(path=None):
    """读取近 1-3 章焦点文档 current_focus.md。"""
    target = path or CURRENT_FOCUS_FILE
    return _load_optional_text_file(target, MAX_CURRENT_FOCUS_CHARS, "current_focus")
