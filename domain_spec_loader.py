"""加载「领域圣经」(DDD) 与「章节规格」(SDD) 文本，供生成提示词使用。"""
import os

from config import (
    STORY_DOMAIN_DIR,
    CHAPTER_SPECS_DIR,
    MAX_DOMAIN_PROMPT_CHARS,
    MAX_CHAPTER_SPEC_CHARS,
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


def load_chapter_spec_text(chapter_number, specs_dir=None):
    """读取 chapter_specs/{章节号}.md；不存在则返回空串。"""
    base = specs_dir or CHAPTER_SPECS_DIR
    path = os.path.join(base, f"{chapter_number}.md")
    if not os.path.isfile(path):
        return ""

    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError as e:
        print(f"警告: 无法读取章节规格 {path}: {e}")
        return ""

    if len(text) > MAX_CHAPTER_SPEC_CHARS:
        text = text[:MAX_CHAPTER_SPEC_CHARS] + "\n\n…（章节规格已按长度截断）"
    return text
