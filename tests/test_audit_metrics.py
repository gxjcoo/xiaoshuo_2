"""audit.metrics 纯计算测试（不调用 LLM）。"""

import pytest

from audit.metrics import (
    _basic_style_metrics,
    compare_reference_and_generated,
    _clean_for_similarity,
    _char_ngrams_for_similarity,
    _sentence_similarity_ratio,
    _reference_similarity_thresholds,
    analyze_reference_similarity,
    plot_fidelity_min_score,
)


class TestBasicStyleMetrics:
    def test_empty_text_returns_zeros(self):
        m = _basic_style_metrics("")
        assert m["avg_sentence_len"] == 0.0
        assert m["dialogue_ratio"] == 0.0
        assert m["ellipsis_count"] == 0
        assert m["rhetorical_count"] == 0

    def test_counts_ellipsis_and_question(self):
        text = "他说了什么？她没回答……他又问？"
        m = _basic_style_metrics(text)
        assert m["ellipsis_count"] == 1
        # 中文 ？ + 半角 ? 都计入
        assert m["rhetorical_count"] >= 2

    def test_dialogue_ratio_chinese_quotes(self):
        text = "他说：“你好。”\n她笑了笑。\n他又说：“再见。”"
        m = _basic_style_metrics(text)
        # 3 行里有 2 行带中文引号 → 占比应大于 0.5
        assert m["dialogue_ratio"] > 0.5


class TestCompareReferenceAndGenerated:
    def test_delta_keys_present(self):
        out = compare_reference_and_generated("参考文。", "生成文！")
        assert "reference" in out
        assert "generated" in out
        assert "delta" in out
        for key in (
            "sentence_len_delta",
            "dialogue_ratio_delta",
            "short_paragraph_ratio_delta",
            "ellipsis_delta",
            "rhetorical_delta",
        ):
            assert key in out["delta"]


class TestCleanForSimilarity:
    def test_strips_punctuation_and_whitespace(self):
        cleaned = _clean_for_similarity("他 说：“你好！”\n她笑。")
        # 标点和空白都应被去掉
        assert "“" not in cleaned
        assert "”" not in cleaned
        assert "：" not in cleaned
        assert "！" not in cleaned
        assert " " not in cleaned
        assert "\n" not in cleaned
        assert "他说你好她笑" == cleaned

    def test_strips_markdown_headings(self):
        cleaned = _clean_for_similarity("# 第一章 标题\n正文")
        assert "第一章" not in cleaned
        assert "正文" in cleaned

    def test_non_string_returns_empty(self):
        assert _clean_for_similarity(None) == ""
        assert _clean_for_similarity(123) == ""


class TestCharNgrams:
    def test_returns_empty_set_when_too_short(self):
        ngrams = _char_ngrams_for_similarity("短文", n=12)
        assert ngrams == set()

    def test_overlap_when_long_enough(self):
        text = "他突然站起来对她说别走她头也不回地走了远去了的背影看不清"
        ngrams = _char_ngrams_for_similarity(text, n=12)
        assert len(ngrams) > 0
        # 每个 n-gram 长度恒为 12
        assert all(len(g) == 12 for g in ngrams)


class TestSentenceSimilarityRatio:
    def test_zero_when_no_overlap(self):
        ref = "他突然站起来对她说别走她头也不回地走了远去了背影。" * 2
        gen = "完全无关的文本：今天天气很好我去爬山遇到一只狐狸跑很快。"
        ratio = _sentence_similarity_ratio(ref, gen)
        assert ratio == 0.0

    def test_high_when_sentences_reused(self):
        sentence = "他突然站起来对她说别走她头也不回地走了远去了背影。"
        ref = sentence * 3
        gen = sentence + "其他完全无关的文字。"
        ratio = _sentence_similarity_ratio(ref, gen)
        assert ratio > 0


class TestReferenceSimilarityThresholds:
    def test_uses_rules_overrides(self):
        rules = {
            "reference_similarity": {
                "ngram_overlap_threshold": 0.5,
                "sentence_reuse_threshold": 0.9,
                "overlap_count_threshold": 999,
            }
        }
        thr = _reference_similarity_thresholds(rules)
        assert thr["ngram_overlap_threshold"] == 0.5
        assert thr["sentence_reuse_threshold"] == 0.9
        assert thr["overlap_count_threshold"] == 999

    def test_falls_back_to_defaults_for_invalid(self):
        thr = _reference_similarity_thresholds({})
        assert thr["ngram_overlap_threshold"] > 0
        assert thr["overlap_count_threshold"] >= 1

        thr2 = _reference_similarity_thresholds(None)
        assert thr2 == thr


class TestAnalyzeReferenceSimilarity:
    def test_short_texts_not_too_similar(self):
        out = analyze_reference_similarity("短", "短")
        assert out["too_similar"] is False
        assert out["ngram_overlap"] == 0.0

    def test_identical_long_text_is_too_similar(self):
        text = ("他突然站起来对她说别走她头也不回地走了远去了背影看不清"
                "夜风很凉他攥紧拳头知道再说什么也没用门外脚步声越走越远") * 4
        out = analyze_reference_similarity(text, text)
        assert out["too_similar"] is True
        assert out["ngram_overlap"] > 0.5
        assert isinstance(out["matched_samples"], list)

    def test_completely_different_text_is_ok(self):
        ref = "他突然站起来对她说别走她头也不回地走了远去了背影看不清夜风很凉"
        gen = "今天天气很好阳光很灿烂适合出门散步看看花草树木呼吸新鲜空气"
        out = analyze_reference_similarity(ref, gen)
        assert out["too_similar"] is False

    def test_custom_threshold_in_rules_applies(self):
        text = ("他突然站起来对她说别走她头也不回地走了远去了背影看不清"
                "夜风很凉他攥紧拳头知道再说什么也没用门外脚步声越走越远") * 4
        # 阈值用 > 1 / 比实际计数大，确保完全等同文本也不再判定 too_similar
        rules = {
            "reference_similarity": {
                "ngram_overlap_threshold": 1.01,
                "sentence_reuse_threshold": 1.01,
                "overlap_count_threshold": 10 ** 9,
            }
        }
        out = analyze_reference_similarity(text, text, rules=rules)
        assert out["too_similar"] is False


class TestPlotFidelityMinScore:
    def test_reads_from_rules(self):
        assert plot_fidelity_min_score({"plot_fidelity_min_score": 77}) == 77

    def test_fallback_when_missing(self):
        # 没传 rules 或没这个 key 时应回到 config 默认（int）
        assert isinstance(plot_fidelity_min_score({}), int)
        assert isinstance(plot_fidelity_min_score(None), int)

    def test_invalid_value_falls_back(self):
        # 字符串无法转 int → 应回退而不是抛
        result = plot_fidelity_min_score({"plot_fidelity_min_score": "not-a-number"})
        assert isinstance(result, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
