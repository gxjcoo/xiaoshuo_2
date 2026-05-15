"""章节标题：AI 拟题与多种兜底。"""

import re

from config import CHAPTER_GENERATION_MODEL

from .client import call_deepseek_api


def _normalize_title_subtitle(text, max_len=18):
    """清洗副标题文本，避免过长或包含不适合作为标题的符号。"""
    if not isinstance(text, str):
        return ""
    s = text.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^第\s*\d+\s*[章节回]\s*", "", s)
    s = s.replace("：", " ").replace(":", " ")
    s = re.sub(r"[`*_~\[\]\(\){}<>|\\\/]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .。!！?？,，;；-—")
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def _fallback_subtitle_from_content(chapter_content):
    """AI 取题失败时，用正文首句兜底生成副标题。"""
    if not isinstance(chapter_content, str):
        return "未命名"
    lines = [ln.strip() for ln in chapter_content.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return "未命名"
    first = lines[0]
    first = re.split(r"[。！？!?；;]", first)[0]
    first = _normalize_title_subtitle(first, max_len=16)
    return first or "未命名"


def _fallback_subtitle_from_reference(reference_chapter_text, chapter_number):
    """从参考原文章节首行提取副标题作为兜底。"""
    if not isinstance(reference_chapter_text, str) or not reference_chapter_text.strip():
        return ""
    lines = [ln.strip() for ln in reference_chapter_text.splitlines() if ln.strip()]
    if not lines:
        return ""

    first_line = lines[0]
    m = re.match(
        r"^#?\s*第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回]\s*(.*)$",
        first_line,
    )
    if m:
        subtitle = _normalize_title_subtitle(m.group(1), max_len=18)
        if subtitle:
            return subtitle

    search_pool = " ".join(lines[:5])
    m2 = re.search(
        r"第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回]\s*(?:[:：]\s*|\s+)([^\n\r]{1,30})",
        search_pool,
    )
    if m2:
        subtitle = _normalize_title_subtitle(m2.group(1), max_len=18)
        if subtitle:
            return subtitle
    return ""


def title_from_existing_heading(chapter_number, heading_text="", chapter_content="", reference_chapter_text=""):
    """优先复用正文生成阶段已有标题；没有可用标题时使用本地兜底，不发起 LLM 请求。"""
    subtitle = _normalize_title_subtitle(heading_text, max_len=18)
    if not subtitle:
        subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
    if not subtitle:
        subtitle = _fallback_subtitle_from_content(chapter_content)
    return f"第{chapter_number}章 {subtitle or '未命名'}"


def generate_title_from_chapter_content(chapter_number, chapter_content, reference_chapter_text=""):
    """根据章节正文生成更贴合内容的副标题。"""
    snippet = (chapter_content or "")[:2600]
    if not snippet.strip():
        ref_subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
        return f"第{chapter_number}章 {ref_subtitle or '未命名'}"

    prompt = (
        f"请基于以下小说正文内容，为第{chapter_number}章拟一个中文章节副标题。\n"
        "要求：\n"
        "1) 只输出副标题文本，不要输出“第X章”、井号、引号、解释。\n"
        "2) 8-16个汉字为宜，尽量具体，贴合本章核心冲突/转折。\n"
        "3) 不要使用“故事继续/新的开始/风云再起”等空泛套话。\n\n"
        f"正文片段：\n{snippet}"
    )
    messages = [
        {"role": "system", "content": "你是网络小说编辑，擅长根据章节内容拟标题，要求具体、有记忆点。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CHAPTER_GENERATION_MODEL,
        max_tokens=80,
        temperature=0.4,
        task_label=f"第{chapter_number}章标题生成",
    )
    subtitle = _normalize_title_subtitle(raw or "", max_len=18)
    if not subtitle:
        subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
    if not subtitle:
        subtitle = _fallback_subtitle_from_content(chapter_content)
    return f"第{chapter_number}章 {subtitle}"
