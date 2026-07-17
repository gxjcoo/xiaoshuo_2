"""章节标题：AI 拟题与多种兜底。"""

import re

from config import CHAPTER_GENERATION_MODEL, TRUNCATE_TITLE_SNIPPET

from .client import call_deepseek_api

# 中文数字到阿拉伯数字的映射
_CHINESE_NUM_MAP = {
    '零': 0, '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000, '万': 10000,
    '两': 2
}


def _chinese_to_arabic(chinese_num: str) -> int:
    """将中文数字转换为阿拉伯数字"""
    if not chinese_num:
        return 0
    
    # 如果已经是阿拉伯数字，直接返回
    if chinese_num.isdigit():
        return int(chinese_num)
    
    result = 0
    temp = 0
    for char in chinese_num:
        if char in _CHINESE_NUM_MAP:
            val = _CHINESE_NUM_MAP[char]
            if val >= 10:  # 十、百、千、万
                if temp == 0:
                    temp = 1
                result += temp * val
                temp = 0
            else:
                temp = temp * 10 + val
        else:
            return 0  # 无法转换
    
    result += temp
    return result if result > 0 else 0


def normalize_chapter_title(title_text: str, chapter_number: int, chapter_content: str = "") -> str:
    """标准化章节标题格式为 `第{N}章 {标题}`
    
    Args:
        title_text: 原始标题文本（可能包含 # 或其他格式）
        chapter_number: 章节号（阿拉伯数字）
        chapter_content: 章节正文内容（用于提取副标题）
    
    Returns:
        标准化后的标题（不含 # 前缀）
    """
    if not isinstance(title_text, str):
        title_text = ""
    
    # 移除 # 前缀
    s = title_text.strip()
    s = re.sub(r"^#+\s*", "", s)

    subtitle = ""
    
    # 尝试提取已有的章节号和副标题
    # 匹配模式：第{数字}章{空格}{标题} 或 第{中文数字}章{空格}{标题}
    m = re.match(r"^第\s*([零〇一二三四五六七八九十百千万两\d]+)\s*章\s*(.*)$", s)
    if m:
        num_str = m.group(1)
        subtitle = m.group(2).strip()

    # 如果没有匹配到章节号格式，整个字符串都作为副标题
    if not subtitle:
        subtitle = s
    
    # 清洗副标题
    if subtitle:
        subtitle = _normalize_title_subtitle(subtitle, max_len=18)
    
    # 如果清洗后的副标题为空或"未命名"，尝试从章节内容提取
    if not subtitle or subtitle == "未命名":
        subtitle = _extract_subtitle_from_chapter_content(chapter_content, max_len=18)
    
    # 最后兜底：使用简单的序号标题
    if not subtitle:
        subtitle = f"章节{chapter_number}"
    
    return f"第{chapter_number}章 {subtitle}"


def _normalize_title_subtitle(text, max_len=18):
    """清洗副标题文本，避免过长或包含不适合作为标题的符号。"""
    if not isinstance(text, str):
        return ""
    s = text.strip()
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回]\s*", "", s)
    # 保留常用标点，只移除影响标题的特殊符号
    s = s.replace("：", " ").replace(":", " ")
    s = re.sub(r"[`*_~\[\]\(\){}<>|\\\/]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 放宽末尾标点限制，只移除明显不适合标题的
    s = s.strip(" .。!！?？,，;；-—\n\r\t")
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s






def _extract_subtitle_from_chapter_content(chapter_content, max_len=18):
    """从章节正文中尝试提取合适的副标题。"""
    if not isinstance(chapter_content, str) or not chapter_content.strip():
        return ""
    
    lines = [ln.strip() for ln in chapter_content.splitlines() if ln.strip()]
    if not lines:
        return ""
    
    # 策略1：从前几行中找有意义的句子片段
    candidate_lines = lines[:10]
    for line in candidate_lines:
        # 跳过太短或太长的行
        if len(line) < 4 or len(line) > 80:
            continue
        # 尝试提取有名词和动词的句子片段
        if any(c in line for c in ['说', '道', '问', '想', '看', '听', '走', '来', '去', '是']):
            # 取前半句
            for split_char in ['。', '！', '？', '，', '；', '…']:
                if split_char in line:
                    candidate = line.split(split_char)[0].strip()
                    if 4 <= len(candidate) <= max_len:
                        return _normalize_title_subtitle(candidate, max_len)
            if 4 <= len(line) <= max_len:
                return _normalize_title_subtitle(line, max_len)
    
    # 策略2：找包含关键动作的短句
    for line in candidate_lines:
        if 6 <= len(line) <= max_len + 10:
            # 检查是否有足够的汉字
            chinese_chars = sum(1 for c in line if '\u4e00' <= c <= '\u9fff')
            if chinese_chars >= 4:
                return _normalize_title_subtitle(line, max_len)
    
    return ""


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
    
    # 如果原始标题不行，尝试从章节正文提取
    if not subtitle or subtitle == "未命名":
        subtitle = _extract_subtitle_from_chapter_content(chapter_content, max_len=18)
    
    # 还是不行的话，从参考原文提取
    if not subtitle or subtitle == "未命名":
        subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
    
    # 最后兜底：使用简单的序号标题
    if not subtitle:
        subtitle = f"章节{chapter_number}"
    
    return f"第{chapter_number}章 {subtitle}"


def generate_title_from_chapter_content(chapter_number, chapter_content, reference_chapter_text=""):
    """根据章节正文生成更贴合内容的副标题。"""
    snippet = (chapter_content or "")[:TRUNCATE_TITLE_SNIPPET]
    if not snippet.strip():
        ref_subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
        if not ref_subtitle:
            ref_subtitle = _extract_subtitle_from_chapter_content(chapter_content, max_len=18)
        if not ref_subtitle:
            ref_subtitle = f"章节{chapter_number}"
        return f"第{chapter_number}章 {ref_subtitle}"

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
        max_tokens=512,
        temperature=0.4,
        task_label=f"第{chapter_number}章标题生成",
    )
    subtitle = _normalize_title_subtitle(raw or "", max_len=18)
    if not subtitle:
        subtitle = _fallback_subtitle_from_reference(reference_chapter_text, chapter_number)
    if not subtitle:
        subtitle = _extract_subtitle_from_chapter_content(chapter_content, max_len=18)
    if not subtitle:
        subtitle = f"章节{chapter_number}"
    return f"第{chapter_number}章 {subtitle}"


def generate_short_title(chapter_content: str, style_description: str = "", max_len: int = 9) -> str:
    """根据章节正文生成短标题（不超过 max_len 个字）。

    Args:
        chapter_content: 章节正文内容
        style_description: 可选的风格描述，用于指导标题风格
        max_len: 标题最大字数，默认为 9（小于 10）

    Returns:
        生成的短标题字符串
    """
    snippet = (chapter_content or "")[:TRUNCATE_TITLE_SNIPPET]
    if not snippet.strip():
        return "未命名"

    style_hint = ""
    if style_description:
        style_hint = f"\n风格参考：{style_description[:500]}"

    prompt = (
        f"请基于以下小说正文内容，为本章拟一个简短的中文标题。\n"
        "要求：\n"
        f"1) 标题不超过{max_len}个汉字，尽量简洁有力。\n"
        "2) 只输出标题文本，不要输出任何解释、引号或标点。\n"
        "3) 标题要具体、有记忆点，能概括本章核心冲突或转折。\n"
        "4) 不要使用\"故事继续/新的开始/风云再起\"等空泛套话。\n"
        "5) 语言风格要贴近网络小说的口语化、节奏感强的特点。\n"
        f"{style_hint}\n\n"
        f"正文片段：\n{snippet}"
    )
    messages = [
        {"role": "system", "content": "你是网络小说编辑，擅长根据章节内容拟短标题，要求简洁、具体、有吸引力。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        CHAPTER_GENERATION_MODEL,
        max_tokens=4096,
        temperature=0.5,
        task_label="短标题生成",
    )
    title = (raw or "").strip()
    # 清洗：移除可能的前缀如"第X章"或多余标点/引号
    title = re.sub(r"^第\s*[零〇一二三四五六七八九十百千万两\d]+\s*[章节回]\s*", "", title)
    title = title.strip('""''「」『』【】《》〈〉()（）·…—-—')
    # 去掉书名号（如果整个标题被包住）
    if title.startswith("《") and title.endswith("》"):
        title = title[1:-1]
    # 截断到最大长度
    if len(title) > max_len:
        title = title[:max_len].rstrip()
    return title or "未命名"
