from pathlib import Path
import sys

import app
import audit.pipeline as audit_pipeline
from audit.pipeline import _next_anchor_conflict_issues
from chapter_processor import get_chapter_start_end, preload_chapter_anchors


def test_preload_chapter_anchors_includes_adjacent_next_chapter(tmp_path):
    input_dir = Path(tmp_path)
    (input_dir / "1.md").write_text("第001章\n\n第一章开头\n\n第一章结尾", encoding="utf-8")
    (input_dir / "2.md").write_text(
        "第002章\n\n妖道哪里走！\n\n少女喊声从身后传来。\n\n原来是老家伙，而不是他。",
        encoding="utf-8",
    )

    anchors = preload_chapter_anchors(str(input_dir), 1, 1)

    assert 1 in anchors
    assert 2 in anchors
    assert "原来是老家伙" in anchors[2]["start"]


def test_chapter_anchor_default_keeps_reveal_lines():
    chapter = "\n".join(
        [
            "第002章",
            "",
            "妖道哪里走！",
            "少女之声传来。",
            "主角一怔。",
            "他回头。",
            "远处有人追来。",
            "老者满脸邪气。",
            "手执骷髅拐杖。",
            "婴儿已经死了。",
            "少女口中的妖道，原来是这个老家伙，而不是他。",
        ]
    )

    start, _ = get_chapter_start_end(chapter)

    assert "而不是他" in start


def test_next_anchor_detects_wrong_capture_hook():
    next_start = (
        "妖道哪里走！\n"
        "少女之声传来。\n"
        "道兄，为何不助我斩杀妖道？\n"
        "然后便见身后有一个满脸邪气的老者追来。\n"
        "少女口中的妖道，原来是这个老家伙，而不是他。"
    )
    generated_end = "街角忽然冲出几个捕快，将他团团围住，喝道：妖道哪里走！"

    issues = _next_anchor_conflict_issues(generated_end, next_start)

    assert issues
    assert any("另有其人" in issue for issue, _ in issues)


def test_audit_double_empty_does_not_pass(monkeypatch):
    monkeypatch.setattr(
        audit_pipeline,
        "evaluate_chapter_with_rules",
        lambda *args, **kwargs: {"total_score": 0, "pass": False, "issues": ["empty"], "suggestions": []},
    )
    monkeypatch.setattr(
        audit_pipeline,
        "evaluate_plot_fidelity_with_outline",
        lambda *args, **kwargs: {"score": 0, "pass": False, "issues": ["empty"], "suggestions": []},
    )
    monkeypatch.setattr(audit_pipeline, "revise_for_plot_fidelity", lambda *args, **kwargs: args[1])

    result = audit_pipeline.audit_and_revise_until_pass(
        "# 第1章 测试\n\n正文",
        1,
        "",
        {"pass_threshold": 68, "ai_trace_hard_threshold": 50, "max_revise_rounds": 1},
        reference_plot_outline="{}",
    )

    assert result["passed"] is False
    assert any("audit_empty" in issue for issue in result["last_audit"]["issues"])


def test_plateau_does_not_pass_when_continuity_fails(monkeypatch):
    monkeypatch.setattr(
        audit_pipeline,
        "evaluate_chapter_with_rules",
        lambda *args, **kwargs: {"total_score": 87, "pass": True, "dimension_scores": {"ai_trace": 82}, "issues": [], "suggestions": []},
    )
    monkeypatch.setattr(
        audit_pipeline,
        "evaluate_plot_fidelity_with_outline",
        lambda *args, **kwargs: {"score": 95, "pass": True, "issues": [], "suggestions": []},
    )
    monkeypatch.setattr(
        audit_pipeline,
        "evaluate_next_anchor_continuity",
        lambda *args, **kwargs: {"score": 95, "pass": True, "issues": [], "suggestions": []},
    )
    monkeypatch.setattr(audit_pipeline, "anti_ai_rewrite_with_reference", lambda *args, **kwargs: args[1])
    monkeypatch.setattr(audit_pipeline, "revise_chapter_by_audit_feedback", lambda *args, **kwargs: args[0])

    result = audit_pipeline.audit_and_revise_until_pass(
        "# 第1章 测试\n\n他关上门，夜色安静下来。",
        1,
        "",
        {"pass_threshold": 68, "ai_trace_hard_threshold": 50, "max_revise_rounds": 2},
        reference_text="参考正文",
        reference_plot_outline="{}",
        next_chapter_start="妖道追了上来。",
    )

    assert result["passed"] is False
    assert any("下一章开头存在追逐" in issue for issue in result["last_audit"]["issues"])


def test_app_stops_after_failed_chapter_by_default(monkeypatch):
    calls = []

    monkeypatch.setattr(sys, "argv", ["app.py", "--no_entity_rewrite", "--start_chapter", "1", "--end_chapter", "2"])
    monkeypatch.setattr(app, "load_story_context", lambda: {"last_generated_chapter": 0})
    monkeypatch.setattr(app, "preload_chapter_anchors", lambda *args, **kwargs: {})

    def fake_process_chapter(chapter_num, *args, **kwargs):
        calls.append(chapter_num)
        return False

    monkeypatch.setattr(app, "process_chapter", fake_process_chapter)

    app.main()

    assert calls == [1]


def test_entity_prescan_includes_next_chapter(tmp_path, monkeypatch):
    (tmp_path / "1.md").write_text("第001章\n\n宝寿走进山门。", encoding="utf-8")
    (tmp_path / "2.md").write_text("第002章\n\n少女追着妖道而来。", encoding="utf-8")

    scanned = []

    monkeypatch.setattr("entity_rewriter.load_global_entity_map", lambda: {"characters": {}, "places": {}, "events": {}, "objects_animals": {}})
    monkeypatch.setattr("entity_rewriter.load_cached_entity_map", lambda chapter: None)
    monkeypatch.setattr("entity_rewriter.save_global_entity_map", lambda entity_map: None)
    monkeypatch.setattr("entity_rewriter.save_entity_map", lambda chapter, entity_map: None)

    def fake_extract(reference_text, chapter_number, existing_map=None):
        scanned.append(chapter_number)
        return {"characters": {f"原名{chapter_number}": f"新名{chapter_number}"}, "places": {}, "events": {}, "objects_animals": {}}

    monkeypatch.setattr("entity_rewriter.extract_entity_map_from_reference", fake_extract)

    app.pre_scan_entities_for_range(str(tmp_path), 1, 1)

    assert scanned == [1, 2]
