"""
实体命名建议任务 - 使用 LLM 自动为 entity_map.json 中每个实体建议替换名

设计要点：
1. 读取 entity_map.json，收集所有 replace 为空的主实体
2. 一次性发送给 LLM（保证不重名、风格统一）
3. 按分类批处理（避免单次输出过长）
4. 只填写空的 replace 字段，不覆盖用户已填写的
5. 原子写回 entity_map.json
6. 可通过 --overwrite 强制覆盖所有 replace（包括已填写的）
"""

import json
import os
from typing import Any, Dict, List

from ..base import TaskNode
from .entity_common import atomic_write_json


CATEGORY_STYLE_HINTS = {
    "person": "玄幻风格人名/道号，2-4 字，保留原名风格（如是道号则起道号，是常人名则起常人名）",
    "place": "玄幻风格地名/宗门/势力名，2-5 字，保留原名结构（山/宗/域/县 等后缀）",
    "weapon": "玄幻风格法宝/武器名，2-5 字，保留原名器物类型（剑/珠/幡/令 等后缀）",
    "medicine": "玄幻风格丹药/宝物名，2-4 字，保留原名后缀（丹/膏/散 等）",
    "skill": "玄幻风格功法/秘术名，2-6 字，保留原名后缀（术/法/诀/阵 等）",
    "beast": "玄幻风格妖兽/灵兽名，2-4 字，保留原名类别（龙/蛟/龟/蛇 等）",
}


class SuggestReplacementsTask(TaskNode):
    """使用 LLM 为 entity_map.json 中每个实体建议替换名"""

    @property
    def id(self) -> str:
        return "suggest_replacements"

    @property
    def name(self) -> str:
        return "实体命名建议"

    @property
    def deps(self) -> list:
        # 允许运行时覆盖（用于独立命令场景，不依赖 entity_validate）
        if hasattr(self, "_deps_override") and self._deps_override is not None:
            return self._deps_override
        return ["entity_validate"]

    @deps.setter
    def deps(self, value: list):
        self._deps_override = value

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from config import ENTITY_MAP_FILE

        overwrite = bool(context.get("suggest_overwrite", False))

        if not os.path.exists(ENTITY_MAP_FILE):
            raise FileNotFoundError(f"实体映射文件不存在: {ENTITY_MAP_FILE}")

        with open(ENTITY_MAP_FILE, "r", encoding="utf-8") as f:
            entity_map = json.load(f)

        # 收集需要建议的实体（按分类分组）
        pending: Dict[str, List[str]] = {}
        skipped_filled = 0
        for cat, cat_data in entity_map.items():
            if not isinstance(cat_data, dict):
                continue
            names = []
            for main_name, info in cat_data.items():
                if not isinstance(info, dict):
                    continue
                current = str(info.get("replace", "")).strip()
                if current and not overwrite:
                    skipped_filled += 1
                    continue
                names.append(main_name)
            if names:
                pending[cat] = names

        total_pending = sum(len(v) for v in pending.values())
        if total_pending == 0:
            print(f"  所有实体的 replace 字段都已填写，无需建议")
            print(f"  （使用 --overwrite 可强制覆盖）")
            return {"suggestions_added": 0, "entity_map_path": ENTITY_MAP_FILE}

        print(f"  需要建议命名的实体：{total_pending} 个（跳过已填写的 {skipped_filled} 个）")

        # 收集所有已存在的 target（防止重名）
        existing_targets = set()
        for cat_data in entity_map.values():
            if not isinstance(cat_data, dict):
                continue
            for info in cat_data.values():
                if isinstance(info, dict):
                    t = str(info.get("replace", "")).strip()
                    if t:
                        existing_targets.add(t)

        # 按分类分批调用 LLM
        total_added = 0
        for cat, names in pending.items():
            suggestions = self._llm_suggest(cat, names, existing_targets)
            if not suggestions:
                print(f"    [{cat}] LLM 建议失败，跳过")
                continue
            # 写回 entity_map
            for name, target in suggestions.items():
                if name in entity_map.get(cat, {}) and target:
                    entity_map[cat][name]["replace"] = target
                    existing_targets.add(target)
                    total_added += 1
            print(f"    [{cat}] 已建议 {len(suggestions)}/{len(names)} 个")

        atomic_write_json(ENTITY_MAP_FILE, entity_map)
        print(f"  完成，共添加 {total_added} 条命名建议")
        print(f"  请检查并按需调整 {ENTITY_MAP_FILE} 中的 'replace' 字段")

        return {
            "suggestions_added": total_added,
            "entity_map_path": ENTITY_MAP_FILE,
        }

    @staticmethod
    def _llm_suggest(cat: str, names: List[str], existing_targets: set) -> Dict[str, str]:
        """
        请 LLM 为一批实体建议替换名。
        返回 {original: target}，失败返回 {}。
        """
        from llm.client import call_deepseek_api
        from config import ENTITY_EXTRACTION_MODEL, ENTITY_EXTRACTION_TEMPERATURE

        style = CATEGORY_STYLE_HINTS.get(cat, "玄幻风格名字，2-5 字")
        cat_label = {
            "person": "人物名/道号",
            "place": "地点/宗门/势力名",
            "weapon": "法宝/武器名",
            "medicine": "丹药/宝物名",
            "skill": "功法/秘术名",
            "beast": "妖兽/灵兽名",
        }.get(cat, cat)

        system = (
            f"你是玄幻小说命名专家。为给定的{cat_label}列表，每个原名生成一个新名字。\n"
            f"要求：\n"
            f"1. 风格：{style}\n"
            f"2. 新名字与原名字面完全不同（不要仅改一个字），但风格相近\n"
            f"3. 一批内的新名字彼此不重复\n"
            f"4. 新名字必须完全不出现在提供的\"禁用名单\"中\n"
            f"5. 只输出 JSON，键为原名，值为新名字"
        )
        user_data = {
            "原名列表": names,
            "禁用名单（不能使用这些名字）": sorted(existing_targets)[:200] if existing_targets else [],
        }
        user = (
            "请为以下实体生成替换名：\n"
            + json.dumps(user_data, ensure_ascii=False, indent=2)
            + f'\n\n输出 JSON 格式：{{"原名1": "新名1", "原名2": "新名2", ...}}\n'
            "只输出 JSON，无其他文字。"
        )

        try:
            result = call_deepseek_api(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                ENTITY_EXTRACTION_MODEL,
                max_tokens=8192,
                temperature=max(ENTITY_EXTRACTION_TEMPERATURE, 0.4),  # 命名需要多样性，温度略高
                response_format={"type": "json_object"},
                task_label=f"命名建议-{cat}",
            )
            if not result or not result.strip():
                print(f"    [{cat}] LLM 返回空")
                return {}
            cleaned = result.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = lines[1:] if lines[0].startswith("```") else lines
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return {}
            # 清洗：只保留 name in names 的键，target 非空且不等于原名
            clean: Dict[str, str] = {}
            name_set = set(names)
            for k, v in data.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    continue
                k = k.strip()
                v = v.strip()
                if k not in name_set:
                    continue
                if not v or v == k:
                    continue
                if v in existing_targets:
                    continue  # 避免与其他实体重名
                clean[k] = v
                existing_targets.add(v)  # 本批内也不能重复
            return clean
        except Exception as e:
            print(f"    [{cat}] LLM 命名失败: {type(e).__name__}: {e}")
            return {}

    def get_required_keys(self) -> list:
        return []

    def get_output_keys(self) -> list:
        return ["suggestions_added", "entity_map_path"]
