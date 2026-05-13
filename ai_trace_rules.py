import math
import re
from collections import Counter

# 新增增强AI痕迹检测
try:
    from ai_trace_enhanced import enhanced_ai_trace_analysis
    ENHANCED_TRACE_AVAILABLE = True
except ImportError:
    ENHANCED_TRACE_AVAILABLE = False


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

COGNITIVE_MARKERS = [
    "觉得", "认为", "意识到", "明白", "知道", "分析", "判断", "盘算", "思考", "推测", "估计",
    "回忆", "琢磨", "理解", "推断", "复盘", "意味着", "所以", "因此",
]

EVENT_MARKERS = [
    "突然", "猛地", "冲", "砸", "打", "杀", "跪", "喊", "吼", "扑", "炸", "裂", "断", "死",
    "受伤", "战书", "系统", "任务", "解锁", "出现", "进攻", "偷袭", "逃", "追",
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


def _event_density_issue(text, window_chars=650):
    text = text or ""
    if len(text) < window_chars:
        return None
    windows = [text[i:i + window_chars] for i in range(0, len(text), window_chars)]
    low_event_windows = 0
    for w in windows:
        marker_hits = sum(w.count(m) for m in EVENT_MARKERS)
        quote_hits = len(re.findall(r"[“\"].+?[”\"]", w))
        if marker_hits + quote_hits < 3:
            low_event_windows += 1
    if low_event_windows >= max(2, len(windows) // 2):
        return {
            "rule": "事件密度不足",
            "severity": "warning",
            "description": f"{low_event_windows}/{len(windows)} 个文本窗口缺少有效事件推进，存在解释替代剧情的问题。",
            "suggestion": "每 500-700 字至少落一处不可逆变化（冲突升级、关系变化、代价落地、任务状态跃迁）。",
            "span_hint": "整章推进结构",
        }, 12
    return None


def _exposition_overflow_issue(paragraphs):
    if not paragraphs or len(paragraphs) < 4:
        return None
    streak = 0
    max_streak = 0
    for p in paragraphs:
        cog_hits = sum(p.count(m) for m in COGNITIVE_MARKERS)
        quote_hits = len(re.findall(r"[“\"].+?[”\"]", p))
        action_hits = sum(p.count(m) for m in EVENT_MARKERS)
        # 解释段：认知词高，动作和对话低
        is_exposition = cog_hits >= 2 and quote_hits == 0 and action_hits <= 1
        if is_exposition:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    if max_streak >= 3:
        return {
            "rule": "解释段超限",
            "severity": "warning",
            "description": f"检测到连续 {max_streak} 段解释/判断型段落，叙事有“复盘腔”倾向。",
            "suggestion": "连续两段解释后必须插入动作对抗、意外反馈或人物交锋，禁止长段纯判断推进。",
            "span_hint": "中段叙事",
        }, 10
    return None


def _extract_dialogue_records(text):
    records = []
    # 通用说话人识别：仅从对话左侧近邻文本中抽取“2-6字中文词 + 说/喊/问/道”等模式
    speaker_patterns = [
        re.compile(r"([\u4e00-\u9fff]{2,6})(?:低声|高声|冷声|沉声|轻声)?(?:说|道|问|喊|吼|应道|嘀咕|回道|答道)$"),
        re.compile(r"(?:对面|旁边|身后)?(?:的)?([\u4e00-\u9fff]{2,6})(?:低声|高声|冷声|沉声|轻声)?(?:说|道|问|喊|吼|应道|嘀咕|回道|答道)$"),
    ]
    for m in re.finditer(r"[“\"]([^”\"]{2,100})[”\"]", text or ""):
        line = m.group(1).strip()
        left = (text[max(0, m.start() - 40):m.start()] or "")
        speaker = "unknown"
        left_tail = re.sub(r"[\s\n\r，。！？!?：:、；;（）()【】\[\]《》\-…,.]+", "", left)
        for pattern in speaker_patterns:
            match = pattern.search(left_tail)
            if match:
                speaker = match.group(1)
                break
        records.append((speaker, line))
    return records


def _voiceprint_gap_issue(text):
    records = _extract_dialogue_records(text)
    if len(records) < 6:
        return None
    by_speaker = {}
    for speaker, line in records:
        by_speaker.setdefault(speaker, []).append(line)
    meaningful = {k: v for k, v in by_speaker.items() if k != "unknown" and len(v) >= 2}
    if len(meaningful) < 2:
        return {
            "rule": "角色声纹不足",
            "severity": "warning",
            "description": "可识别说话人不足 2 组，角色对话声线区分度弱。",
            "suggestion": "至少给两名核心角色固定口癖/句长偏好/语气差异，避免同一书面腔。",
            "span_hint": "对话层",
        }, 5

    def features(lines):
        joined = " ".join(lines)
        short = sum(1 for x in lines if len(x) <= 10) / max(1, len(lines))
        modal = sum(joined.count(x) for x in ("啊", "呢", "吧", "哎", "嘛", "诶"))
        qmark = joined.count("？") + joined.count("?")
        return short, modal / max(1, len(joined)), qmark / max(1, len(lines))

    speakers = list(meaningful.keys())[:3]
    feats = [features(meaningful[s]) for s in speakers]
    # 若两名角色特征过于接近，判同腔
    too_close_pairs = 0
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            dist = sum(abs(feats[i][k] - feats[j][k]) for k in range(3))
            if dist < 0.18:
                too_close_pairs += 1
    if too_close_pairs >= 1:
        return {
            "rule": "角色声纹同构",
            "severity": "warning",
            "description": f"主要角色对话风格距离过近（近似对数: {too_close_pairs}），存在同一作者声线。",
            "suggestion": "为角色建立固定说话策略：一人短句打断，一人完整陈述，一人口头禅/反问偏好。",
            "span_hint": "角色台词",
        }, 10
    return None


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

    # 6.5) 结构硬约束：事件密度
    density_res = _event_density_issue(text)
    if density_res:
        item, penalty = density_res
        score_penalty += penalty
        issues.append(item)

    # 6.6) 结构硬约束：解释上限
    exposition_res = _exposition_overflow_issue(paragraphs)
    if exposition_res:
        item, penalty = exposition_res
        score_penalty += penalty
        issues.append(item)

    # 6.7) 结构硬约束：角色声纹差异
    voiceprint_res = _voiceprint_gap_issue(text)
    if voiceprint_res:
        item, penalty = voiceprint_res
        score_penalty += penalty
        issues.append(item)

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

    # 新增：增强AI痕迹检测（统计分布分析）
    if ENHANCED_TRACE_AVAILABLE:
        try:
            enhanced_analysis = enhanced_ai_trace_analysis(text)
            enhanced_score = enhanced_analysis.get("combined_score", 0)
            if enhanced_score >= 60:  # 高分才加惩罚
                penalty = int(enhanced_score * 0.1)  # 最多加10分
                score_penalty += penalty
                issues.append({
                    "rule": "统计特征AI化",
                    "severity": "warning" if enhanced_score >= 80 else "info",
                    "description": f"统计特征检测到较强AI痕迹（得分={enhanced_score:.1f}/100）。",
                    "suggestion": "增加句子/段落长度变化，减少标准化情绪表达。",
                    "span_hint": "全文风格",
                })
        except Exception as e:
            # 增强检测失败不影响主流程
            pass

    return {
        "score_penalty": min(55, score_penalty),
        "issues": issues,
    }
