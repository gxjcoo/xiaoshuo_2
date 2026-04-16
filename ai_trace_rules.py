import math
import re
from collections import Counter


SUMMARY_TAIL_PATTERNS = [
    r"这一刻",
    r"总之",
    r"显然",
    r"不禁",
    r"他明白",
    r"她明白",
    r"终于明白",
]

TRANSITION_WORDS = [
    "然而",
    "不过",
    "与此同时",
    "另一方面",
    "尽管如此",
    "话虽如此",
    "但值得注意的是",
    "然后",
    "接着",
]


def _split_sentences(text):
    parts = re.split(r"[。！？!?]", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _split_paragraphs(text):
    parts = re.split(r"\n\s*\n", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _normalize_chinese(text):
    return re.sub(r"[\s\n\r，。！？!?；：、“”\"'（）()【】\[\]《》\-…,.]", "", text or "")


def _char_ngrams(text, n=6):
    src = _normalize_chinese(text)
    if len(src) < n:
        return []
    return [src[i:i + n] for i in range(len(src) - n + 1)]


def _boundary_sentence(text, boundary):
    sentences = _split_sentences(text or "")
    if not sentences:
        return ""
    return sentences[0] if boundary == "opening" else sentences[-1]


def _dice_similarity(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0
    a_bi = Counter(a[i:i + 2] for i in range(len(a) - 1))
    b_bi = Counter(b[i:i + 2] for i in range(len(b) - 1))
    overlap = sum(min(v, b_bi.get(k, 0)) for k, v in a_bi.items())
    total = sum(a_bi.values()) + sum(b_bi.values())
    return (2 * overlap / total) if total else 0.0


def _coefficient_of_variation(values):
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean


def _count_transition_words(text):
    counts = {}
    total = 0
    for w in TRANSITION_WORDS:
        c = len(re.findall(re.escape(w), text))
        if c > 0:
            counts[w] = c
            total += c
    return total, counts


def _same_prefix_streak(sentences, prefix_len=2):
    max_streak = 1
    streak = 1
    for i in range(1, len(sentences)):
        a = sentences[i - 1][:prefix_len]
        b = sentences[i][:prefix_len]
        if a and b and a == b:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1
    return max_streak


def _dialogue_voice_similarity(text):
    # 抽取引号内对话，按标点切分后比较尾词同质化
    lines = re.findall(r"[“\"]([^”\"]{2,80})[”\"]", text or "")
    if len(lines) < 4:
        return 0.0, []
    endings = []
    for ln in lines:
        chunks = re.split(r"[，。！？!?、\s]", ln.strip())
        chunks = [c for c in chunks if c]
        if chunks:
            endings.append(chunks[-1][-2:])
    if len(endings) < 4:
        return 0.0, []
    cnt = Counter(endings)
    top, top_n = cnt.most_common(1)[0]
    ratio = top_n / len(endings)
    return ratio, [top]


def analyze_ai_trace(text, recent_chapter_texts=None):
    text = text or ""
    issues = []
    score_penalty = 0
    recent_chapter_texts = recent_chapter_texts or []

    sentences = _split_sentences(text)
    paragraphs = _split_paragraphs(text)

    # 1) 句长同质化
    if len(sentences) >= 6:
        lens = [len(s) for s in sentences]
        cv = _coefficient_of_variation(lens)
        if cv < 0.22:
            score_penalty += 16
            issues.append({
                "rule": "句长同质化",
                "severity": "warning",
                "description": f"句长变异系数偏低（cv={cv:.3f}），整体节奏过于工整。",
                "suggestion": "改写部分句子，拉开长短句差异，避免连续同节奏陈述。",
                "span_hint": "全章句式节奏",
            })

    # 2) 段落等长
    if len(paragraphs) >= 4:
        para_lens = [len(p) for p in paragraphs]
        para_cv = _coefficient_of_variation(para_lens)
        if para_cv < 0.20:
            score_penalty += 10
            issues.append({
                "rule": "段落等长",
                "severity": "warning",
                "description": f"段落长度变异系数偏低（cv={para_cv:.3f}），段落形态模板化。",
                "suggestion": "重组段落：关键动作短段、解释信息并段，避免齐刷刷等长段。",
                "span_hint": "段落结构",
            })

    # 3) 转折词密度
    trans_total, trans_counts = _count_transition_words(text)
    density = trans_total / max(1, len(text) / 1000)
    if density > 3.2:
        score_penalty += 12
        detail = "、".join(f"{k}x{v}" for k, v in sorted(trans_counts.items(), key=lambda x: -x[1])[:4])
        issues.append({
            "rule": "转折词过密",
            "severity": "warning",
            "description": f"转折连接词密度偏高（{density:.2f}/千字），集中在：{detail}。",
            "suggestion": "用动作切换、场景切换替代连接词衔接，减少“然而/然后/不过”依赖。",
            "span_hint": "连接词分布",
        })

    # 4) 段尾总结腔
    summary_hits = 0
    for p in paragraphs:
        tail = p[-16:] if len(p) > 16 else p
        if any(re.search(pattern, tail) for pattern in SUMMARY_TAIL_PATTERNS):
            summary_hits += 1
    if summary_hits >= 3:
        score_penalty += 10
        issues.append({
            "rule": "段尾总结腔",
            "severity": "warning",
            "description": f"检测到 {summary_hits} 处段尾总结式收束，叙述者痕迹偏重。",
            "suggestion": "删除抽象结论句，改为动作/反应落板，让读者自行判断。",
            "span_hint": "段尾句",
        })

    # 5) 列表句式（同前缀连发）
    if len(sentences) >= 6:
        streak = _same_prefix_streak(sentences, prefix_len=2)
        if streak >= 3:
            score_penalty += 8
            issues.append({
                "rule": "列表句式",
                "severity": "warning",
                "description": f"连续 {streak} 句以相似前缀起句，存在列表化表达倾向。",
                "suggestion": "打散起句方式，切换主语/动作入口，避免排比堆叠。",
                "span_hint": "连续起句",
            })

    # 6) 对话同腔
    voice_ratio, markers = _dialogue_voice_similarity(text)
    if voice_ratio >= 0.55:
        score_penalty += 8
        issues.append({
            "rule": "角色同腔",
            "severity": "warning",
            "description": f"对话尾词同质化明显（占比 {voice_ratio:.2f}，样本尾词：{','.join(markers)}）。",
            "suggestion": "给至少一名角色改成短句/口语/打断式表达，拉开说话习惯差异。",
            "span_hint": "对话句",
        })

    # 7) 跨章短语重复（近 3-5 章）
    valid_recent = [t for t in recent_chapter_texts if isinstance(t, str) and t.strip()]
    if len(valid_recent) >= 2 and len(text) >= 400:
        current_ngrams = _char_ngrams(text, n=6)
        if current_ngrams:
            current_counts = Counter(current_ngrams)
            repeated_here = {k for k, v in current_counts.items() if v >= 2}
            recent_joined = "\n".join(valid_recent)
            repeated_cross = [g for g in repeated_here if g and g in _normalize_chinese(recent_joined)]
            if len(repeated_cross) >= 6:
                score_penalty += 10
                sample = "、".join(repeated_cross[:5])
                issues.append({
                    "rule": "跨章重复",
                    "severity": "warning",
                    "description": f"检测到跨章重复短语 {len(repeated_cross)} 处（示例：{sample}）。",
                    "suggestion": "替换重复动作模板和常用短语，改写同义表达并重排句序。",
                    "span_hint": "跨章措辞",
                })

    # 8) 开头/结尾同构（近 3-5 章）
    if len(valid_recent) >= 2:
        current_open = _normalize_chinese(_boundary_sentence(text, "opening"))
        current_end = _normalize_chinese(_boundary_sentence(text, "ending"))
        if current_open and current_end:
            prev_opens = [_normalize_chinese(_boundary_sentence(t, "opening")) for t in valid_recent[-3:]]
            prev_ends = [_normalize_chinese(_boundary_sentence(t, "ending")) for t in valid_recent[-3:]]
            open_sims = [_dice_similarity(current_open, p) for p in prev_opens if p]
            end_sims = [_dice_similarity(current_end, p) for p in prev_ends if p]

            if open_sims and max(open_sims) >= 0.72:
                score_penalty += 8
                issues.append({
                    "rule": "开头同构",
                    "severity": "warning",
                    "description": f"本章开头与近章开头相似度过高（max={max(open_sims):.2f}）。",
                    "suggestion": "换开篇入口：从动作、冲突后果或异常信息切入，避免重复抬镜句。",
                    "span_hint": "首句/首段",
                })
            if end_sims and max(end_sims) >= 0.72:
                score_penalty += 8
                issues.append({
                    "rule": "结尾同构",
                    "severity": "warning",
                    "description": f"本章结尾与近章结尾相似度过高（max={max(end_sims):.2f}）。",
                    "suggestion": "换落板方式：用决断/代价/新变量收尾，避免重复解释式结尾。",
                    "span_hint": "尾句/尾段",
                })

    return {
        "score_penalty": min(55, score_penalty),
        "issues": issues,
    }
