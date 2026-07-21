"""
实体校验任务 - LTP 兜底补漏 + 模式过滤 + LLM 别名聚类

1. 原文字符串验证去幻觉
2. LTP 全文扫描补漏
3. 模式规则过滤（通用后缀/描述性前缀/含"的""之"短语/通用类别词）
4. 频次统计
5. 跨类去重
6. LLM 别名聚类（合并同指别名）
7. 组装最终映射表

模式过滤规则见 entity_common.is_generic_entity，不依赖穷举黑名单。
"""

import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from ..base import TaskNode
from .entity_common import (
    CATEGORIES,
    CATEGORY_SUFFIX_HINTS,
    CROSS_CAT_PRIORITY,
    MAX_ENTITY_LEN,
    atomic_write_json,
    is_generic_entity,
    load_json_if_exists,
    read_full_text,
)


# 分类到 LTP NER tag 的映射
LTP_TAG_TO_CATEGORY = {
    "Nh": "person",  # 人名
    "Ns": "place",   # 地名
    "Ni": "place",   # 机构名（近似归地名，避免污染 person）
}


class EntityValidateTask(TaskNode):
    """LTP 全文校验 + 去幻觉 + 补漏 + LLM 别名聚类 + 归一化"""

    @property
    def id(self) -> str:
        return "entity_validate"

    @property
    def name(self) -> str:
        return "实体校验"

    @property
    def deps(self) -> list:
        return ["entity_extract"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from config import ENTITY_MAP_FILE, RUNTIME_DIR

        entity_raw = context.get("entity_raw", {})
        chapters_dir = context.get("chapters_dir", "chapters")
        novel_path = context.get("novel_path", "")

        if not entity_raw:
            cache_file = os.path.join(RUNTIME_DIR, "entity_extract_raw.json")
            entity_raw = load_json_if_exists(cache_file, default=None)
            if not entity_raw:
                raise ValueError("未找到 LLM 实体提取结果，请先执行 entity_extract")

        full_text = read_full_text(novel_path, chapters_dir)
        if not full_text:
            raise ValueError("无法读取原文内容")

        print("  [1/5] 原文校验 + LTP 补漏 ...")
        validated = self._validate_and_supplement(entity_raw, full_text)

        print("  [2/5] 描述性短语过滤 + 通用词过滤 + 频次统计 ...")
        counted = self._filter_and_count(validated, full_text)

        print("  [3/5] 跨类去重 ...")
        counted = self._dedupe_cross_category(counted)

        print("  [3.3/5] 基于后缀提示纠正分类 ...")
        counted = self._reclassify_by_suffix(counted)

        print("  [3.5/5] 前缀别名合并 ...")
        counted = self._merge_prefix_aliases(counted)

        # 保留旧行为的中间产物（未聚类）以便调试
        atomic_write_json(
            os.path.join(RUNTIME_DIR, "entity_map_precluster.json"),
            {cat: {k: v for k, v in items} for cat, items in counted.items()},
        )

        print("  [4/5] LLM 别名聚类 ...")
        clustered = self._cluster_aliases(counted)

        print("  [5/5] 组装最终映射表 ...")
        entity_map = self._to_entity_map(clustered)

        atomic_write_json(ENTITY_MAP_FILE, entity_map)

        total = sum(len(cat_data) for cat_data in entity_map.values())
        alias_total = sum(
            len(info.get("aliases", []))
            for cat in entity_map.values()
            for info in cat.values()
        )
        print(f"  实体校验完成：{total} 个主实体，{alias_total} 个别名")
        print(f"  映射表已保存至: {ENTITY_MAP_FILE}")
        print(f"  请编辑 {ENTITY_MAP_FILE} 中的 'replace' 字段填入替换名，然后运行主 pipeline")

        return {"entity_map": entity_map, "entity_map_path": ENTITY_MAP_FILE}

    # ---------- 第一层：校验 + LTP 补漏 ----------

    def _validate_and_supplement(
        self, entity_raw: Dict[str, List[str]], full_text: str
    ) -> Dict[str, Set[str]]:
        validated: Dict[str, Set[str]] = {cat: set() for cat in CATEGORIES}

        # LLM 实体：字面必须命中原文
        for cat in CATEGORIES:
            for entity in entity_raw.get(cat, []) or []:
                if isinstance(entity, str) and entity in full_text:
                    validated[cat].add(entity)
                elif isinstance(entity, str):
                    print(f"    [去幻觉] '{entity}' 未在原文中找到，已剔除")

        # LTP 按 tag 正确归类补漏
        ltp_by_cat = self._ltp_extract(full_text)
        for cat, ents in ltp_by_cat.items():
            already = set()
            for c in CATEGORIES:
                already |= validated[c]
            new = ents - already
            if new:
                print(f"    [LTP补漏-{cat}] +{len(new)} 个")
                validated[cat] |= new

        return validated

    def _ltp_extract(self, full_text: str) -> Dict[str, Set[str]]:
        """
        LTP NER 全文扫描（chunk 50 字 overlap 避免边界丢失）
        按 tag 归类到对应 category
        """
        by_cat: Dict[str, Set[str]] = {cat: set() for cat in CATEGORIES}
        try:
            from ltp import LTP
        except ImportError:
            print("    LTP 未安装，跳过 LTP 补漏（pip install ltp 可启用）")
            return by_cat

        try:
            ltp = LTP("LTP/small")
        except Exception as e:
            print(f"    LTP 加载失败: {e}，跳过 LTP 补漏")
            return by_cat

        chunk_size = 500
        overlap = 50
        step = chunk_size - overlap
        pos = 0
        n = len(full_text)

        while pos < n:
            chunk = full_text[pos:pos + chunk_size]
            if chunk.strip():
                try:
                    result = ltp.pipeline([chunk], tasks=["cws", "ner"])
                    ner = result.ner[0] if result.ner else []
                    # LTP v4+ ner 返回 [(tag, word, start, end), ...]
                    for item in ner:
                        tag, word = self._parse_ltp_item(item, chunk)
                        if not word or len(word) < 2:
                            continue
                        cat = LTP_TAG_TO_CATEGORY.get(tag)
                        if cat and word in full_text:
                            by_cat[cat].add(word)
                except Exception:
                    pass
            pos += step

        return by_cat

    @staticmethod
    def _parse_ltp_item(item, chunk: str) -> Tuple[str, str]:
        """兼容不同 LTP 版本的 ner 输出格式"""
        try:
            if len(item) == 4:
                tag, word, _s, _e = item
                return tag, word
            if len(item) == 3:
                # 旧格式 (tag, start, end)
                tag, s, e = item
                return tag, chunk[s:e + 1]
        except Exception:
            pass
        return "", ""

    # ---------- 第二层：频次统计 ----------

    def _filter_and_count(
        self, validated: Dict[str, Set[str]], full_text: str
    ) -> Dict[str, List[Tuple[str, int]]]:
        result: Dict[str, List[Tuple[str, int]]] = {}
        dropped_generic = 0
        for cat in CATEGORIES:
            max_len = MAX_ENTITY_LEN.get(cat, 10)
            items = []
            for entity in validated[cat]:
                # 长度过滤
                if len(entity) < 2 or len(entity) > max_len:
                    continue
                # 模式规则过滤（通用词/描述性短语）
                if is_generic_entity(entity):
                    dropped_generic += 1
                    continue
                # 频次统计
                count = full_text.count(entity)
                if count > 0:
                    items.append((entity, count))
            items.sort(key=lambda x: x[1], reverse=True)
            result[cat] = items
        if dropped_generic:
            print(f"    [模式过滤] 剔除 {dropped_generic} 个通用词/描述性短语")
        return result

    # ---------- 第二层半：跨类去重 ----------

    @staticmethod
    def _pick_category(entity: str, cats: List[str]) -> str:
        """
        从 entity 出现的多个类里挑一个：
        1) 若某类的后缀提示命中 → 用该类（如"惊雷剑"命中 weapon 后缀 → weapon）
        2) 否则用 CROSS_CAT_PRIORITY 排序（place > person > weapon > skill > medicine > beast）
        """
        # 后缀提示优先
        hint_matches = [
            c for c in cats
            if any(entity.endswith(suf) for suf in CATEGORY_SUFFIX_HINTS.get(c, ()))
        ]
        if len(hint_matches) == 1:
            return hint_matches[0]
        pool = hint_matches or cats
        return max(pool, key=lambda c: CROSS_CAT_PRIORITY.get(c, 0))

    def _dedupe_cross_category(
        self, counted: Dict[str, List[Tuple[str, int]]]
    ) -> Dict[str, List[Tuple[str, int]]]:
        """
        同一实体出现在多类时，按 _pick_category 保留一份，其余剔除。
        """
        # 收集每个实体出现的类
        entity_cats: Dict[str, List[str]] = {}
        for cat, items in counted.items():
            for name, _ in items:
                entity_cats.setdefault(name, []).append(cat)

        # 决定归属
        keep: Dict[str, str] = {}  # entity → 归属类
        moved = 0
        for name, cats in entity_cats.items():
            if len(cats) == 1:
                keep[name] = cats[0]
            else:
                chosen = self._pick_category(name, cats)
                keep[name] = chosen
                moved += len(cats) - 1
                print(f"    [跨类去重] '{name}' 出现在 {cats} → 保留 {chosen}")

        out: Dict[str, List[Tuple[str, int]]] = {c: [] for c in counted}
        for cat, items in counted.items():
            for name, cnt in items:
                if keep[name] == cat:
                    out[cat].append((name, cnt))
            out[cat].sort(key=lambda x: x[1], reverse=True)

        if moved:
            print(f"    共剔除 {moved} 条跨类重复")
        return out

    # ---------- 第三层：前缀别名合并（结构化） ----------

    def _reclassify_by_suffix(
        self, counted: Dict[str, List[Tuple[str, int]]]
    ) -> Dict[str, List[Tuple[str, int]]]:
        """
        基于 CATEGORY_SUFFIX_HINTS 纠正分类错误。
        如"纯阳丹"分到 weapon，"丹"是 medicine 的后缀 → 移到 medicine。
        只有当当前分类的后缀提示都不匹配、而其他分类的后缀提示明确匹配时才移动。
        """
        moved = 0
        # 收集所有实体（name, current_cat, count）
        entries: List[Tuple[str, str, int]] = []
        for cat, items in counted.items():
            for name, cnt in items:
                entries.append((name, cat, cnt))

        result: Dict[str, List[Tuple[str, int]]] = {c: [] for c in counted}
        for name, cur_cat, cnt in entries:
            # 当前类的后缀提示是否匹配
            cur_hints = CATEGORY_SUFFIX_HINTS.get(cur_cat, ())
            matches_cur = any(name.endswith(suf) for suf in cur_hints)
            if matches_cur:
                result[cur_cat].append((name, cnt))
                continue

            # 找其他类的后缀匹配
            other_matches = []
            for other_cat, hints in CATEGORY_SUFFIX_HINTS.items():
                if other_cat == cur_cat:
                    continue
                for suf in hints:
                    if name.endswith(suf):
                        other_matches.append((other_cat, len(suf)))
                        break

            if other_matches:
                # 选后缀最长的（匹配最精确）
                target_cat = max(other_matches, key=lambda x: x[1])[0]
                result[target_cat].append((name, cnt))
                moved += 1
                print(f"    [分类纠正] '{name}' {cur_cat} → {target_cat}")
            else:
                result[cur_cat].append((name, cnt))

        # 排序
        for cat in result:
            result[cat].sort(key=lambda x: x[1], reverse=True)

        if moved:
            print(f"    共纠正 {moved} 条分类")
        return result

    # 常见"扩展词"：一个专有实体的完整名 = 短名 + 扩展词
    # 例："大夏" + "国" = "大夏国"（同一势力）；"白羊县" + "衙" = "白羊县衙"（衙门属县）
    _PREFIX_EXPANSIONS = {
        # 地点/势力
        "place": (
            "国", "王朝", "朝廷", "帝国", "皇朝",
            "县", "州", "城", "镇", "村", "乡",
            "山", "河", "湖", "海", "岭", "峰",
            "宗", "阁", "观", "殿", "府", "堂", "门",
            "山脉", "皇宫", "皇陵", "县衙", "州府", "府衙",
            "境", "境内", "国境", "衙", "衙门",
        ),
        # 人物（道号/身份后缀，别名合并）
        "person": (
            "道人", "道长", "上人", "上仙", "真人", "老鬼", "老人",
        ),
        # 妖兽（种族/等级后缀）
        "beast": (
            "妖", "大妖", "妖兽", "族", "怪", "精", "神", "王",
        ),
        # 法宝（后缀变体较少）
        "weapon": ("剑", "刀",),
        # 功法
        "skill": ("术", "法", "诀", "阵", "阵法", "秘术", "秘法",),
        # 丹药
        "medicine": ("丹",),
    }

    def _merge_prefix_aliases(
        self, counted: Dict[str, List[Tuple[str, int]]]
    ) -> Dict[str, List[Tuple[str, int]]]:
        """
        同分类内，把"A 是 B 的严格前缀且 B = A + 扩展词"的 B 合并到 A。
        主名 = 较短者（更接近本名），count = 两者相加，别名先记在临时字段。
        LLM 聚类阶段再合并任意别名（如"宝寿道长"→"宝寿"这类无前缀关系）。
        """
        merged_count = 0
        result: Dict[str, List[Tuple[str, int]]] = {}
        for cat, items in counted.items():
            if not items or len(items) < 2:
                result[cat] = items
                continue

            expansions = self._PREFIX_EXPANSIONS.get(cat, ())
            if not expansions:
                result[cat] = items
                continue

            # 按名字长度升序，短名优先作为主名
            sorted_items = sorted(items, key=lambda x: (len(x[0]), -x[1]))
            counts = {name: cnt for name, cnt in items}
            # main_of[name] = 最终归属的主名
            main_of: Dict[str, str] = {name: name for name, _ in items}

            for main_name, _ in sorted_items:
                if main_of[main_name] != main_name:
                    continue  # 已被合并到其他主名
                for other_name, _ in items:
                    if other_name == main_name or main_of[other_name] != other_name:
                        continue
                    if not other_name.startswith(main_name):
                        continue
                    tail = other_name[len(main_name):]
                    if tail in expansions:
                        # other_name 归并到 main_name
                        main_of[other_name] = main_name
                        merged_count += 1
                        print(f"    [前缀合并-{cat}] '{other_name}' → '{main_name}'")

            # 累加频次
            grouped: Dict[str, int] = {}
            for name, cnt in items:
                main = main_of[name]
                grouped[main] = grouped.get(main, 0) + cnt

            result[cat] = sorted(
                grouped.items(), key=lambda x: x[1], reverse=True
            )

        if merged_count:
            print(f"    共合并 {merged_count} 条前缀别名")
        return result

    # ---------- 第四层：LLM 别名聚类 ----------

    def _cluster_aliases(
        self, counted: Dict[str, List[Tuple[str, int]]]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        对每个分类调 LLM 做别名聚类。
        - person 最重要（宝寿道长/白虹掌教/宝寿 → 同一人）
        - place/weapon 次之
        - medicine/skill/beast 通常无别名，跳过

        返回结构：{cat: {main_name: {"aliases": [...], "count": N}}}
        LLM 调用失败或字段不匹配时降级为不聚类。
        """
        need_cluster = {"person", "place", "weapon"}
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for cat, items in counted.items():
            if not items:
                out[cat] = {}
                continue
            if cat not in need_cluster or len(items) < 2:
                out[cat] = {
                    name: {"aliases": [], "count": cnt} for name, cnt in items
                }
                continue

            groups = self._llm_cluster(cat, items)
            if not groups:
                out[cat] = {
                    name: {"aliases": [], "count": cnt} for name, cnt in items
                }
                continue

            count_map = dict(items)
            merged: Dict[str, Dict[str, Any]] = {}
            covered: Set[str] = set()
            for group in groups:
                names = [n for n in group if n in count_map]
                if not names:
                    continue
                # 主名 = 频次最高
                main = max(names, key=lambda n: count_map[n])
                aliases = sorted(
                    [n for n in names if n != main],
                    key=lambda n: -count_map[n],
                )
                total = sum(count_map[n] for n in names)
                merged[main] = {"aliases": aliases, "count": total}
                covered.update(names)

            # 未参与任何 group 的实体单独成组
            for name, cnt in items:
                if name not in covered:
                    merged[name] = {"aliases": [], "count": cnt}

            # 按聚类后频次降序
            out[cat] = dict(
                sorted(merged.items(), key=lambda kv: kv[1]["count"], reverse=True)
            )
        return out

    @staticmethod
    def _llm_cluster(cat: str, items: List[Tuple[str, int]]) -> List[List[str]]:
        """
        请 LLM 输出同指别名分组。返回 [[name1, name2], ...]，
        每个内部子列表是同一实体的所有别称。
        失败时返回 []（调用方降级为不聚类）。
        """
        from llm.client import call_deepseek_api
        from config import (
            ENTITY_EXTRACTION_MODEL,
            ENTITY_EXTRACTION_TEMPERATURE,
        )

        # 名单太大时截断（按频次取前 200）
        names = [n for n, _ in items[:200]]
        if len(names) < 2:
            return []

        cat_label = {
            "person": "人物",
            "place": "地点/宗门/势力",
            "weapon": "法宝/武器",
        }.get(cat, cat)

        system = (
            f"你是玄幻小说实体归一化助手。给定一份同一部小说中出现的{cat_label}名单，"
            "找出指向同一实体的别名/道号/尊号/简称分组。"
            "不要跨实体合并；不要把不同实体强行归为一组；不要新增名单外的名字。"
            "只输出 JSON。"
        )
        user = (
            f"{cat_label}名单（来自同一部玄幻小说）：\n"
            + json.dumps(names, ensure_ascii=False)
            + "\n\n请找出同指分组。规则：\n"
            "1. 只把明显同指的合并（例如「宝寿道长」「白虹掌教」「宝寿」是同一人）；\n"
            "2. 名字完全无关的一律不合并；\n"
            "3. 每组至少 2 个名字，单独的实体不用输出；\n"
            "4. 输出 JSON 格式：{\"groups\": [[\"名1\", \"名2\"], [\"名3\", \"名4\", \"名5\"]]}\n"
            "只输出 JSON，无其他文字。"
        )

        try:
            result = call_deepseek_api(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                ENTITY_EXTRACTION_MODEL,
                max_tokens=4096,
                temperature=ENTITY_EXTRACTION_TEMPERATURE,
                response_format={"type": "json_object"},
                task_label=f"别名聚类-{cat}",
            )
            data = json.loads(result)
            groups = data.get("groups", [])
            if not isinstance(groups, list):
                return []
            clean: List[List[str]] = []
            name_set = set(names)
            for g in groups:
                if not isinstance(g, list):
                    continue
                names_in = [x for x in g if isinstance(x, str) and x in name_set]
                # 至少两个成员才算别名组
                if len(names_in) >= 2:
                    clean.append(names_in)
            return clean
        except Exception as e:
            print(f"    [别名聚类-{cat}] LLM 失败，降级为不聚类: {e}")
            return []

    # ---------- 第四层：组装最终 entity_map ----------

    @staticmethod
    def _to_entity_map(
        clustered: Dict[str, Dict[str, Dict[str, Any]]]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        entity_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for cat, cat_data in clustered.items():
            out: Dict[str, Dict[str, Any]] = {}
            for main, info in cat_data.items():
                out[main] = {
                    "aliases": list(info.get("aliases", [])),
                    "count": info.get("count", 0),
                    "replace": "",
                    # 替换阶段元数据：整词边界（默认 true）
                    "word_boundary": True,
                }
            entity_map[cat] = out
        return entity_map

    def get_required_keys(self) -> list:
        return []

    def get_output_keys(self) -> list:
        return ["entity_map", "entity_map_path"]
