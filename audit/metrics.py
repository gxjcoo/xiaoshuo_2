"""纯计算的审计辅助：风格指标、参考相似度、阈值解析。

本模块不调用 LLM，所有函数确定性，可独立写单元测试。
"""

import re

from config import (
    REFERENCE_SIMILARITY_NGRAM_OVERLAP,
    REFERENCE_SIMILARITY_SENTENCE_REUSE,
    REFERENCE_SIMILARITY_OVERLAP_COUNT,
    PLOT_FIDELITY_MIN_SCORE,
)


def _basic_style_metrics(text):
    """提取轻量风格指标，用于参考文与生成文差异对比。"""
    if not text:
        return {
            "avg_sentence_len": 0.0,
            "dialogue_ratio": 0.0,
            "short_paragraph_ratio": 0.0,
            "ellipsis_count": 0,
            "rhetorical_count": 0,
        }
    sentences = [s for s in re.split(r"[。！？!?]", text) if s.strip()]
    avg_sentence_len = (sum(len(s.strip()) for s in sentences) / len(sentences)) if sentences else 0.0
    lines = [ln for ln in text.splitlines() if ln.strip()]
    dialogue_lines = [ln for ln in lines if ("“" in ln and "”" in ln) or ('"' in ln)]
    short_lines = [ln for ln in lines if len(ln.strip()) <= 16]
    return {
        "avg_sentence_len": round(avg_sentence_len, 2),
        "dialogue_ratio": round((len(dialogue_lines) / len(lines)) if lines else 0.0, 3),
        "short_paragraph_ratio": round((len(short_lines) / len(lines)) if lines else 0.0, 3),
        "ellipsis_count": text.count("……"),
        "rhetorical_count": text.count("？") + text.count("?"),
    }


def compare_reference_and_generated(reference_text, generated_text):
    """对比原文与生成文的风格指标差异。"""
    ref = _basic_style_metrics(reference_text)
    gen = _basic_style_metrics(generated_text)
    delta = {
        "sentence_len_delta": round(gen["avg_sentence_len"] - ref["avg_sentence_len"], 2),
        "dialogue_ratio_delta": round(gen["dialogue_ratio"] - ref["dialogue_ratio"], 3),
        "short_paragraph_ratio_delta": round(gen["short_paragraph_ratio"] - ref["short_paragraph_ratio"], 3),
        "ellipsis_delta": gen["ellipsis_count"] - ref["ellipsis_count"],
        "rhetorical_delta": gen["rhetorical_count"] - ref["rhetorical_count"],
    }
    return {"reference": ref, "generated": gen, "delta": delta}


def _clean_for_similarity(text):
    if not isinstance(text, str):
        return ""
    text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。！？、；：“”‘’（）《》【】\[\]{}…,.!?;:\"'()<>-]", "", text)
    return text


def _char_ngrams_for_similarity(text, n=12):
    cleaned = _clean_for_similarity(text)
    if len(cleaned) < n:
        return set()
    return {cleaned[i:i + n] for i in range(0, len(cleaned) - n + 1)}


def _sentence_similarity_ratio(reference_text, generated_text):
    ref_sentences = [
        _clean_for_similarity(s)
        for s in re.split(r"[。！？!?；;]\s*", reference_text or "")
        if len(_clean_for_similarity(s)) >= 12
    ]
    gen_clean = _clean_for_similarity(generated_text)
    if not ref_sentences or not gen_clean:
        return 0.0
    hits = 0
    for sentence in ref_sentences:
        probe = sentence[:28] if len(sentence) > 28 else sentence
        if len(probe) >= 12 and probe in gen_clean:
            hits += 1
    return round(hits / max(1, len(ref_sentences)), 3)


def _reference_similarity_thresholds(rules=None):
    cfg = (rules or {}).get("reference_similarity", {}) if isinstance(rules, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "ngram_overlap_threshold": float(
            cfg.get("ngram_overlap_threshold", REFERENCE_SIMILARITY_NGRAM_OVERLAP)
        ),
        "sentence_reuse_threshold": float(
            cfg.get("sentence_reuse_threshold", REFERENCE_SIMILARITY_SENTENCE_REUSE)
        ),
        "overlap_count_threshold": int(
            cfg.get("overlap_count_threshold", REFERENCE_SIMILARITY_OVERLAP_COUNT)
        ),
    }


def analyze_reference_similarity(reference_text, generated_text, rules=None):
    """检测生成稿与参考章的表达相似度，重点抓连续字串和句子片段复用。"""
    ref_ngrams = _char_ngrams_for_similarity(reference_text, n=12)
    gen_ngrams = _char_ngrams_for_similarity(generated_text, n=12)
    if not ref_ngrams or not gen_ngrams:
        return {
            "ngram_overlap": 0.0,
            "sentence_reuse": 0.0,
            "too_similar": False,
            "matched_samples": [],
        }
    overlap = ref_ngrams & gen_ngrams
    ngram_overlap = round(len(overlap) / max(1, min(len(ref_ngrams), len(gen_ngrams))), 3)
    sentence_reuse = _sentence_similarity_ratio(reference_text, generated_text)
    samples = sorted(overlap, key=len, reverse=True)[:12]
    thresholds = _reference_similarity_thresholds(rules)
    too_similar = (
        ngram_overlap >= thresholds["ngram_overlap_threshold"]
        or sentence_reuse >= thresholds["sentence_reuse_threshold"]
        or len(overlap) >= thresholds["overlap_count_threshold"]
    )
    return {
        "ngram_overlap": ngram_overlap,
        "sentence_reuse": sentence_reuse,
        "overlap_count": len(overlap),
        "thresholds": thresholds,
        "too_similar": too_similar,
        "matched_samples": samples,
    }


def plot_fidelity_min_score(rules=None):
    """从规则中读取结构骨架贴合度阈值，缺失或异常时回退到默认值。"""
    if isinstance(rules, dict):
        try:
            return int(rules.get("plot_fidelity_min_score", PLOT_FIDELITY_MIN_SCORE))
        except Exception:
            return PLOT_FIDELITY_MIN_SCORE
    return PLOT_FIDELITY_MIN_SCORE


_plot_fidelity_min_score = plot_fidelity_min_score
