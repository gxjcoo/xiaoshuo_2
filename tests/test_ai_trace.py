"""ai_trace_rules 与 ai_trace_enhanced 的确定性逻辑测试。

不调用 LLM，纯函数行为验证：
- 基础数学辅助：CV、dice 相似度、normalize、char ngrams
- analyze_ai_trace 端到端：构造典型模板化文本，验证能命中规则
- ai_trace_enhanced.dialogue_ratio：dialogue 修复后的回归点（之前元组恒真）
"""

import pytest

from ai_trace_rules import (
    _split_sentences,
    _split_paragraphs,
    _normalize_chinese,
    _char_ngrams,
    _dice_similarity,
    _coefficient_of_variation,
    _same_prefix_streak,
    _count_transition_words,
    _dialogue_voice_similarity,
    analyze_ai_trace,
)
from ai_trace_enhanced import (
    WritingStatistics,
    detect_ai_trace_statistical,
    enhanced_ai_trace_analysis,
)


# =========================== 基础数学辅助 ===========================


class TestNumericHelpers:
    def test_coefficient_of_variation_empty(self):
        assert _coefficient_of_variation([]) == 0.0

    def test_coefficient_of_variation_zero_mean(self):
        assert _coefficient_of_variation([0, 0, 0]) == 0.0

    def test_coefficient_of_variation_uniform_is_zero(self):
        assert _coefficient_of_variation([5, 5, 5, 5]) == 0.0

    def test_coefficient_of_variation_varied(self):
        cv = _coefficient_of_variation([1, 10, 100])
        assert cv > 0.5  # 差异很大 → CV 较高

    def test_same_prefix_streak_basic(self):
        sentences = ["他走过去", "他说了什么", "他离开了", "她笑了"]
        # 连续 3 句以 "他" 开头
        assert _same_prefix_streak(sentences, prefix_len=1) >= 3

    def test_same_prefix_streak_no_match(self):
        sentences = ["他走", "她笑", "我看", "你来"]
        assert _same_prefix_streak(sentences, prefix_len=1) == 1


class TestStringHelpers:
    def test_normalize_strips_punctuation_and_whitespace(self):
        result = _normalize_chinese("他 说：“你好！”\n她。")
        assert "“" not in result
        assert "”" not in result
        assert "！" not in result
        assert " " not in result
        assert "\n" not in result
        assert result == "他说你好她"

    def test_normalize_handles_none(self):
        assert _normalize_chinese(None) == ""

    def test_char_ngrams_short_text_empty(self):
        # 短于 n 的归一化结果应返回空列表
        assert _char_ngrams("短文", n=6) == []

    def test_char_ngrams_correct_length(self):
        text = "他突然站起来对她说别走她头也不回地走了远去了"
        ngrams = _char_ngrams(text, n=6)
        assert all(len(g) == 6 for g in ngrams)
        assert len(ngrams) > 0


class TestDiceSimilarity:
    def test_identical_is_one(self):
        assert _dice_similarity("hello world", "hello world") == 1.0

    def test_empty_returns_zero(self):
        assert _dice_similarity("", "abc") == 0.0
        assert _dice_similarity("abc", "") == 0.0

    def test_too_short_returns_zero(self):
        # 不同的单字符（避开 a == b 提前返回 1.0 的分支）
        assert _dice_similarity("a", "b") == 0.0

    def test_no_overlap(self):
        assert _dice_similarity("abcdef", "uvwxyz") == 0.0

    def test_partial_overlap(self):
        ratio = _dice_similarity("hello world", "world peace")
        assert 0.0 < ratio < 1.0


# =========================== 转折词 + 段落切分 ===========================


class TestTransitionsAndSplitting:
    def test_split_sentences_basic(self):
        text = "他走过去。她笑了！可是没说话？"
        sents = _split_sentences(text)
        assert len(sents) == 3

    def test_split_sentences_ignores_empty(self):
        text = "。。。他走了。"
        sents = _split_sentences(text)
        assert sents == ["他走了"]

    def test_split_paragraphs_double_newline(self):
        text = "段一\n\n段二\n\n段三"
        paras = _split_paragraphs(text)
        assert paras == ["段一", "段二", "段三"]

    def test_count_transition_words(self):
        text = "然而他笑了。不过她没回应。然而事情没完。"
        total, counts = _count_transition_words(text)
        assert total >= 3
        assert counts.get("然而", 0) >= 2
        assert counts.get("不过", 0) >= 1


# =========================== 对话同腔 ===========================


class TestDialogueVoiceSimilarity:
    def test_few_dialogues_returns_zero(self):
        text = '他说：“好的。”\n她说：“嗯。”'
        ratio, _ = _dialogue_voice_similarity(text)
        assert ratio == 0.0

    def test_uniform_endings_detected(self):
        # 6 句对话全部以 "走了" 收尾 → 应被判同腔
        dialogues = ['"我走了"'] * 6
        text = "\n".join(dialogues)
        ratio, markers = _dialogue_voice_similarity(text)
        assert ratio >= 0.5
        assert markers


# =========================== analyze_ai_trace 端到端 ===========================


class TestAnalyzeAITrace:
    def test_empty_text_no_issues(self):
        result = analyze_ai_trace("", recent_chapter_texts=[])
        assert result["score_penalty"] == 0
        assert result["issues"] == []

    def test_uniform_sentence_length_triggers_rule(self):
        # 7 句长度几乎相同（cv 远低于 0.22）→ 应命中"句长同质化"
        uniform = "。".join(["他走过去" for _ in range(7)]) + "。"
        result = analyze_ai_trace(uniform, recent_chapter_texts=[])
        rule_names = [i.get("rule") for i in result["issues"]]
        assert "句长同质化" in rule_names
        assert result["score_penalty"] > 0

    def test_transition_overflow_triggers_rule(self):
        # 大量转折词 → 转折词过密
        text = ("然而这是一个故事。" * 8) + ("不过又出现了变化。" * 8)
        result = analyze_ai_trace(text, recent_chapter_texts=[])
        rule_names = [i.get("rule") for i in result["issues"]]
        assert "转折词过密" in rule_names

    def test_summary_tail_triggers_rule(self):
        # 多段段尾命中 SUMMARY_TAIL_PATTERNS
        text = (
            "一些细节描述这里是过渡内容，他终于明白。\n\n"
            "另一段动作描写文字铺垫情绪，他总之明白。\n\n"
            "第三段更多描述与铺陈，他终于明白。\n\n"
            "第四段补充细节，他终于明白。"
        )
        result = analyze_ai_trace(text, recent_chapter_texts=[])
        rule_names = [i.get("rule") for i in result["issues"]]
        assert "段尾总结腔" in rule_names

    def test_score_penalty_is_capped(self):
        # 即使触发多条规则，score_penalty 也应被封顶（实现里 min(55, ...)）
        bad_text = (
            ("然而他终于明白。" * 20)
            + ("不过她总之显然。" * 20)
        )
        result = analyze_ai_trace(bad_text, recent_chapter_texts=[])
        assert result["score_penalty"] <= 55


# =========================== ai_trace_enhanced：dialogue_ratio bug 回归 ===========================


class TestDialogueRatioBugRegression:
    """旧代码里 `('\"', l)` 是非空元组，恒真，导致 dialogue_ratio 始终 = 1.0。
    修复后必须能区分有引号 / 无引号的行。"""

    def test_no_dialogue_returns_low_ratio(self):
        # 纯叙述文本，零引号 → 比例应远低于 1.0
        text = "他走过去\n她笑了\n外面下雨\n月亮升起来"
        ws = WritingStatistics(text)
        assert ws.dialogue_ratio() < 0.5

    def test_all_dialogue_returns_high_ratio(self):
        text = '他说：“你好。”\n她答：“嗯。”\n他又问：“走吗？”'
        ws = WritingStatistics(text)
        assert ws.dialogue_ratio() > 0.5

    def test_mixed_returns_intermediate(self):
        text = (
            "他走过去\n"
            '她说：“别走。”\n'
            "外面下雨\n"
            '他答：“没事。”\n'
            "夜更深了"
        )
        ws = WritingStatistics(text)
        ratio = ws.dialogue_ratio()
        assert 0.2 < ratio < 0.8

    def test_empty_text_returns_zero(self):
        ws = WritingStatistics("")
        assert ws.dialogue_ratio() == 0


# =========================== 增强检测最小烟雾测试 ===========================


class TestEnhancedAITraceSmoke:
    def test_detect_statistical_returns_tuple(self):
        text = "这是一段文字" * 30
        score, details = detect_ai_trace_statistical(text)
        assert 0 <= score <= 100
        assert "sentence_cv" in details
        assert "paragraph_cv" in details
        assert "dialogue_ratio" in details

    def test_enhanced_analysis_combined_score_in_range(self):
        text = "他走过去\n她笑了\n外面下雨\n夜风渐起" * 20
        out = enhanced_ai_trace_analysis(text)
        assert 0 <= out["combined_score"] <= 100
        assert "rule_score" in out
        assert "statistical_score" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
