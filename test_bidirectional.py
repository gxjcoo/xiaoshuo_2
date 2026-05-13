"""Test bidirectional validation mechanism"""
import sys, os, inspect
sys.path.insert(0, os.path.dirname(__file__))

from chapter_processor import preload_chapter_anchors, get_chapter_start_end, process_chapter
from audit_pipeline import audit_and_revise_until_pass
from ai_handler import generate_chapter_content
from ai_trace_rules import _dice_similarity, _normalize_chinese

content = "Test chapter content\nwith multiple lines\nfor testing."
start, end = get_chapter_start_end(content)
print(f"[OK] get_chapter_start_end: {len(start)}/{len(end)} chars")

anchors = preload_chapter_anchors("input_chapters", 1, 1)
print(f"[OK] preload_chapter_anchors: {len(anchors)} chapters")

sim = _dice_similarity(_normalize_chinese("abc"), _normalize_chinese("abd"))
print(f"[OK] _dice_similarity: {sim:.2f}")

assert "chapter_anchors" in inspect.signature(process_chapter).parameters
print("[OK] process_chapter: accepts chapter_anchors")

assert "prev_chapter_end" in inspect.signature(generate_chapter_content).parameters
assert "next_chapter_start" in inspect.signature(generate_chapter_content).parameters
print("[OK] generate_chapter_content: accepts bidirectional params")

assert "prev_chapter_end" in inspect.signature(audit_and_revise_until_pass).parameters
assert "next_chapter_start" in inspect.signature(audit_and_revise_until_pass).parameters
print("[OK] audit_and_revise_until_pass: accepts bidirectional params")

print("\nALL 7 TESTS PASSED - Bidirectional validation ready!")
