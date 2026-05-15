"""entity_rewriter 的纯逻辑测试。

只覆盖不调用 LLM 的函数：
- 格式归一（flatten / rich entry）
- 文本替换（按原名长度降序，避免子串误吞）
- 残留检测
- merge_entity_maps 的冲突规避（同新名 / 已存在原名）
- _split_into_chunks 的边界
"""

import pytest

from entity_rewriter import (
    flatten_entity_map,
    _normalize_value,
    apply_entity_rewrite,
    detect_original_entity_leaks,
    format_entity_leak_report,
    merge_entity_maps,
    _split_into_chunks,
    _empty_map,
    ENTITY_CATEGORIES,
)


# ----------------------------- 格式归一 -----------------------------


class TestFlatten:
    def test_normalize_value_from_str(self):
        assert _normalize_value("新名") == "新名"

    def test_normalize_value_from_rich_dict(self):
        assert _normalize_value({"new": "新名", "first_seen_chapter": 3}) == "新名"

    def test_normalize_value_other_returns_empty(self):
        assert _normalize_value(None) == ""
        assert _normalize_value(123) == ""

    def test_flatten_keeps_only_valid_pairs(self):
        rich = {
            "characters": {
                "宝寿": {"new": "玉竹", "first_seen_chapter": 1},
                "小熊": "雪熊",
                # 原名 == 新名 应被丢弃
                "无变": {"new": "无变"},
                # 空字符串应被丢弃
                "": "什么",
            },
            "places": {},
        }
        flat = flatten_entity_map(rich)
        assert flat["characters"] == {"宝寿": "玉竹", "小熊": "雪熊"}
        # 缺失的类目会补齐为空 dict
        for cat in ENTITY_CATEGORIES:
            assert cat in flat
            assert isinstance(flat[cat], dict)

    def test_flatten_none_returns_empty_map(self):
        flat = flatten_entity_map(None)
        for cat in ENTITY_CATEGORIES:
            assert flat[cat] == {}


# ----------------------------- 文本替换 -----------------------------


class TestApplyEntityRewrite:
    def test_basic_replace(self):
        m = {"characters": {"宝寿": "玉竹"}}
        assert apply_entity_rewrite("宝寿走过来", m) == "玉竹走过来"

    def test_long_name_replaced_before_short_substring(self):
        """关键回归点：'赵无恤' 必须在 '赵无' 之前替换，否则会被截断成 '<新>恤'。"""
        m = {"characters": {"赵无": "孙离", "赵无恤": "孙离恤"}}
        out = apply_entity_rewrite("赵无恤来了，赵无也来了", m)
        # '赵无恤' 必须先被整体替换，留下来的孤立 '赵无' 再换
        assert "赵无恤" not in out
        assert "孙离恤" in out
        assert "孙离" in out

    def test_empty_text_returns_as_is(self):
        assert apply_entity_rewrite("", {"characters": {"a": "b"}}) == ""

    def test_empty_map_returns_unchanged(self):
        assert apply_entity_rewrite("宝寿走过来", {}) == "宝寿走过来"
        assert apply_entity_rewrite("宝寿走过来", None) == "宝寿走过来"

    def test_skip_identical_pair(self):
        # 原名 == 新名 不应执行替换（避免无意义循环）
        m = {"characters": {"宝寿": "宝寿"}}
        assert apply_entity_rewrite("宝寿走过来", m) == "宝寿走过来"

    def test_works_with_rich_format(self):
        m = {"characters": {"宝寿": {"new": "玉竹", "first_seen_chapter": 1}}}
        assert apply_entity_rewrite("宝寿走过来", m) == "玉竹走过来"


# ----------------------------- 残留检测 -----------------------------


class TestDetectLeaks:
    def test_no_leak_when_text_already_rewritten(self):
        m = {"characters": {"宝寿": "玉竹"}}
        leaks = detect_original_entity_leaks("玉竹走过来", m)
        assert leaks == []

    def test_detect_count_and_expected(self):
        m = {"characters": {"宝寿": "玉竹"}, "places": {"青云山": "白鹿岭"}}
        leaks = detect_original_entity_leaks("宝寿在青云山，宝寿又走了。", m)
        # 期望两条残留：宝寿 x2、青云山 x1
        as_dict = {l["entity"]: l for l in leaks}
        assert as_dict["宝寿"]["count"] == 2
        assert as_dict["宝寿"]["expected"] == "玉竹"
        assert as_dict["宝寿"]["category"] == "characters"
        assert as_dict["青云山"]["count"] == 1
        assert as_dict["青云山"]["category"] == "places"

    def test_skip_identical_old_new(self):
        m = {"characters": {"小熊": "小熊"}}
        # old == new 不应被当成残留（否则永远修不完）
        assert detect_original_entity_leaks("小熊很可爱", m) == []

    def test_format_leak_report_empty(self):
        assert "无原实体残留" in format_entity_leak_report([])

    def test_format_leak_report_has_count(self):
        leaks = [{"entity": "宝寿", "category": "characters", "count": 2, "expected": "玉竹"}]
        report = format_entity_leak_report(leaks)
        assert "宝寿" in report
        assert "2" in report
        assert "玉竹" in report


# ----------------------------- 映射合并 -----------------------------


class TestMergeEntityMaps:
    def test_incoming_new_entries_are_added(self):
        base = _empty_map()
        incoming = {"characters": {"宝寿": "玉竹"}}
        merged = merge_entity_maps(base, incoming, chapter_number=1)
        assert merged["characters"]["宝寿"] == "玉竹"

    def test_base_existing_old_is_protected(self):
        """base 已有的原名永不被 incoming 覆盖（保证跨章一致）。"""
        base = {"characters": {"宝寿": "玉竹"}}
        incoming = {"characters": {"宝寿": "另一个新名"}}
        merged = merge_entity_maps(base, incoming)
        assert merged["characters"]["宝寿"] == "玉竹"

    def test_incoming_new_name_collision_is_rejected(self):
        """incoming 新名若与 base 已有新名撞车，整条丢弃，避免两个原名映射到同一新名。"""
        base = {"characters": {"宝寿": "玉竹"}}
        incoming = {"characters": {"另一人": "玉竹"}}
        merged = merge_entity_maps(base, incoming)
        assert "另一人" not in merged["characters"]

    def test_rich_format_chapter_metadata(self):
        """合入 rich 格式 base 时应带上 first_seen_chapter。"""
        base = {"characters": {"宝寿": {"new": "玉竹", "first_seen_chapter": 1}}}
        incoming = {"characters": {"小熊": "雪熊"}}
        merged = merge_entity_maps(base, incoming, chapter_number=5)
        entry = merged["characters"]["小熊"]
        assert isinstance(entry, dict)
        assert entry["new"] == "雪熊"
        assert entry["first_seen_chapter"] == 5

    def test_does_not_mutate_base(self):
        base = {"characters": {"宝寿": "玉竹"}}
        before = dict(base["characters"])
        merge_entity_maps(base, {"characters": {"小熊": "雪熊"}})
        # base 原地不应被改动
        assert base["characters"] == before


# ----------------------------- 分段 -----------------------------


class TestSplitChunks:
    def test_short_text_single_chunk(self):
        chunks = _split_into_chunks("一段短文。", max_chars=4500)
        assert len(chunks) == 1
        assert "一段短文" in chunks[0]

    def test_empty_returns_empty_list(self):
        assert _split_into_chunks("", max_chars=4500) == []

    def test_each_chunk_under_limit(self):
        paragraphs = [f"段落{i}" * 60 for i in range(40)]
        text = "\n".join(paragraphs)
        chunks = _split_into_chunks(text, max_chars=400)
        assert len(chunks) >= 2
        # 每块都不超过 max_chars 的两倍（容忍单段超长不分裂）
        for c in chunks:
            assert len(c) <= max(400, len(paragraphs[0])) * 1.5

    def test_keeps_all_content(self):
        text = "\n".join(["第" + str(i) for i in range(50)])
        chunks = _split_into_chunks(text, max_chars=30)
        rejoined = "\n".join(chunks)
        # 每个原段落都应该出现在某个块里
        for i in range(50):
            assert f"第{i}" in rejoined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
