"""
实体替换任务 — 基于 ahocorasick-rs 的多模式一次性替换

选型（2026-07）：ahocorasick-rs 1.0+，Rust aho-corasick crate 后端，pip 直装 wheel。
比 flashtext（2020 停更、无 span API）活跃且更强：
- `find_matches_as_indexes(text, overlapping=False)` 返回 (pattern_id, start, end)
- MatchKind.LeftmostLongest 保证长匹配优先
- 单次扫描 + 按原文位置拼接 → 天然免疫链式污染 / 循环互换
- span 位置天然可用于 dry-run 预览

设计要点：
1. 自动子串保护：entity_map 中所有实体（含未填 replace 的）都注册进自动机，
   未填 replace 的实体注册 self→self，保证 map 内实体互相之间不会被子串误伤。
2. 保留自研预检 + 报告：硬冲突（多主实体撞同一 target）→ error；
   target 撞名、零命中 → warning；落盘 runtime/entity_replace_report.json。
3. 别名共享主名 target。
"""

import json
import os
import shutil
from typing import Any, Dict, List, Tuple

from ahocorasick_rs import AhoCorasick, MatchKind

from ..base import TaskNode
from .entity_common import atomic_write_json, list_chapter_files, read_full_text


PROTECT_MARK = "__protect__"


class ReplacementPlan:
    """单条替换规则的声明式表示"""

    __slots__ = ("original", "target", "category", "is_alias_of")

    def __init__(self, original: str, target: str, category: str, is_alias_of: str = ""):
        self.original = original
        self.target = target
        self.category = category
        self.is_alias_of = is_alias_of  # 主名 / PROTECT_MARK / ""


class EntityReplaceTask(TaskNode):
    """ahocorasick-rs 多模式一次性替换 + Dry-run + 冲突检测"""

    @property
    def id(self) -> str:
        return "entity_replace"

    @property
    def name(self) -> str:
        return "实体替换"

    @property
    def deps(self) -> list:
        return ["entity_extract"]

    def can_skip(self, context: Dict[str, Any]) -> bool:
        from config import ENTITY_MAP_FILE

        if not os.path.exists(ENTITY_MAP_FILE):
            return True
        try:
            with open(ENTITY_MAP_FILE, "r", encoding="utf-8") as f:
                entity_map = json.load(f)
            for cat_data in entity_map.values():
                if not isinstance(cat_data, dict):
                    continue
                for info in cat_data.values():
                    if isinstance(info, dict) and str(info.get("replace", "")).strip():
                        return False
            return True
        except Exception:
            return True

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from config import ENTITY_MAP_FILE, RUNTIME_DIR

        novel_path = context.get("novel_path", "")
        original_chapters_dir = context.get("chapters_dir", "chapters")
        dry_run = bool(context.get("entity_replace_dry_run", False))

        if not os.path.exists(ENTITY_MAP_FILE):
            raise FileNotFoundError(f"实体映射文件不存在: {ENTITY_MAP_FILE}")

        with open(ENTITY_MAP_FILE, "r", encoding="utf-8") as f:
            entity_map = json.load(f)

        plans = self._build_plans(entity_map)
        if not plans:
            print("  映射表中没有需要替换的实体，跳过替换")
            return {
                "replaced_novel_path": novel_path,
                "chapters_dir": original_chapters_dir,
                "replace_count": 0,
            }

        full_text = read_full_text(novel_path, original_chapters_dir)
        if not full_text:
            raise ValueError("无法读取原文内容")

        report = self._prevalidate(plans, full_text)
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        report_path = os.path.join(RUNTIME_DIR, "entity_replace_report.json")
        atomic_write_json(report_path, report)

        if report["errors"]:
            print("  ❌ 检测到硬冲突，替换已中止：")
            for err in report["errors"]:
                print(f"    - {err}")
            print(f"  完整报告：{report_path}")
            raise ValueError("实体替换冲突，见上方报告；修正 entity_map.json 后重试")

        for w in report["warnings"]:
            print(f"  ⚠️  {w}")
        print(f"  Dry-run 预估：{report['total_hits']} 处命中，"
              f"{sum(1 for p in report['plans'] if not p['protect_only'])} 条替换规则，"
              f"{len(report['zero_hit'])} 条零命中")

        if dry_run:
            print(f"  Dry-run 模式，未写出。报告：{report_path}")
            return {
                "replaced_novel_path": novel_path,
                "chapters_dir": original_chapters_dir,
                "replace_count": 0,
                "entity_replace_report_path": report_path,
                "dry_run": True,
            }

        replaced_text, actual_count = self._apply(full_text, plans)

        replaced_novel_path = self._write_replaced_file(novel_path, replaced_text)
        replaced_chapters_dir = "chapters_replaced"
        self._re_split(replaced_novel_path, replaced_chapters_dir)

        print(f"  实体替换完成，实际替换 {actual_count} 处")
        print(f"  替换后文件: {replaced_novel_path}")
        print(f"  替换后章节目录: {replaced_chapters_dir}")
        print(f"  替换报告：{report_path}")

        return {
            "replaced_novel_path": replaced_novel_path,
            "chapters_dir": replaced_chapters_dir,
            "chapters": list_chapter_files(replaced_chapters_dir),
            "replace_count": actual_count,
            "entity_replace_report_path": report_path,
        }

    # ---------- Plan 构建 ----------

    @staticmethod
    def _build_plans(entity_map: Dict) -> List[ReplacementPlan]:
        """
        - 有 replace 字段 → 真替换 plan（主名 + 别名共享 target）
        - 未填 replace 且 word_boundary=True → 保护型 plan（self→self）
        """
        plans: List[ReplacementPlan] = []
        for cat, cat_data in entity_map.items():
            if not isinstance(cat_data, dict):
                continue
            for main_name, info in cat_data.items():
                if not isinstance(info, dict):
                    continue
                target = str(info.get("replace", "")).strip()
                wb = bool(info.get("word_boundary", True))
                aliases = [
                    a.strip() for a in info.get("aliases", []) or []
                    if isinstance(a, str) and a.strip()
                ]

                if target and target != main_name:
                    plans.append(ReplacementPlan(main_name, target, cat))
                    for alias in aliases:
                        if alias != target:
                            plans.append(ReplacementPlan(alias, target, cat, main_name))
                elif wb:
                    plans.append(ReplacementPlan(main_name, main_name, cat, PROTECT_MARK))
                    for alias in aliases:
                        plans.append(ReplacementPlan(alias, alias, cat, PROTECT_MARK))
        return plans

    # ---------- 预检 ----------

    @staticmethod
    def _prevalidate(plans: List[ReplacementPlan], full_text: str) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        zero_hit: List[str] = []
        per_plan: List[Dict[str, Any]] = []

        total_hits = 0
        for p in plans:
            hits = full_text.count(p.original)
            is_protect = (p.is_alias_of == PROTECT_MARK)
            if not is_protect:
                total_hits += hits
            per_plan.append({
                "original": p.original,
                "target": p.target,
                "category": p.category,
                "is_alias_of": p.is_alias_of,
                "hits": hits,
                "protect_only": is_protect,
            })
            if hits == 0 and not is_protect:
                zero_hit.append(p.original)

        if zero_hit:
            warnings.append(
                f"{len(zero_hit)} 个实体在原文中零命中，示例：{zero_hit[:5]}"
            )

        # 不同主实体撞同一 target → 硬错误
        target_to_mains: Dict[str, List[str]] = {}
        for p in plans:
            if p.is_alias_of:
                continue
            target_to_mains.setdefault(p.target, []).append(p.original)
        for target, mains in target_to_mains.items():
            if len(mains) > 1:
                errors.append(
                    f"target '{target}' 被多个不同主实体使用: {mains}（会造成合并冲突）"
                )

        # target 已在原文且未被保护 → 告警
        protected = {p.original for p in plans if p.is_alias_of == PROTECT_MARK}
        for p in plans:
            if p.is_alias_of:
                continue
            if p.target and p.target != p.original and p.target in full_text \
                    and p.target not in protected:
                warnings.append(
                    f"target '{p.target}' 已在原文出现（{full_text.count(p.target)} 次），"
                    f"改名后会与原有出现合并；如需保留，请把它加进 entity_map（replace 留空即可自动保护）"
                )

        return {
            "total_hits": total_hits,
            "plans": per_plan,
            "zero_hit": zero_hit,
            "warnings": warnings,
            "errors": errors,
        }

    # ---------- 核心：ahocorasick-rs 一次性替换 ----------

    @staticmethod
    def _apply(text: str, plans: List[ReplacementPlan]) -> Tuple[str, int]:
        """
        LeftmostLongest + 非重叠 → 长匹配优先且区间不交叠。
        单次扫描拿 (idx, start, end)，按原文位置拼接输出：
        - 天然免疫链式污染 (A→B, C→A)：替换后的文本不会再被扫描
        - 天然支持循环互换 (A↔B)：两次匹配基于同一份原文位置
        """
        if not plans:
            return text, 0

        patterns = [p.original for p in plans]
        targets = [p.target for p in plans]

        ac = AhoCorasick(patterns, matchkind=MatchKind.LeftmostLongest)
        matches = ac.find_matches_as_indexes(text, overlapping=False)

        if not matches:
            return text, 0

        matches.sort(key=lambda m: m[1])

        parts: List[str] = []
        pos = 0
        actual = 0
        for pat_idx, start, end in matches:
            if start > pos:
                parts.append(text[pos:start])
            tgt = targets[pat_idx]
            parts.append(tgt)
            if tgt != text[start:end]:
                actual += 1
            pos = end
        if pos < len(text):
            parts.append(text[pos:])

        return "".join(parts), actual

    # ---------- I/O ----------

    @staticmethod
    def _write_replaced_file(original_path: str, replaced_text: str) -> str:
        if original_path:
            base, ext = os.path.splitext(original_path)
            replaced_path = f"{base}_replaced{ext or '.txt'}"
        else:
            replaced_path = "novel_replaced.txt"
        with open(replaced_path, "w", encoding="utf-8") as f:
            f.write(replaced_text)
        return replaced_path

    @staticmethod
    def _re_split(novel_path: str, output_dir: str) -> None:
        from split_novel import split_novel_to_chapters

        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        split_novel_to_chapters(novel_path, output_dir)

    def get_required_keys(self) -> list:
        return []

    def get_output_keys(self) -> list:
        return [
            "replaced_novel_path",
            "chapters_dir",
            "chapters",
            "replace_count",
            "entity_replace_report_path",
        ]
