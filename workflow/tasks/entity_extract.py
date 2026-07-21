"""
实体提取任务 — 五轮工业级抽取流程

1. 第一轮：逐章提取（只提取专有名词，不提取通用类别词）
2. 第二轮：全文滑窗 5000 字 / 步长 2000 字补抽，解决章节边界漏检
3. 两轮取并集，最大化召回
4. 第三轮：full_text 字符串匹配去幻觉（LLM 编造直接踢掉）
5. 第四轮：LLM 归一化 — 合并别名、再次过滤通用词、输出六分类 JSON

Prompt 设计原则：让 LLM 区分"专有名称"和"通用类别词"，从源头避免通用词混入。
判断标准：如果一个词可以指代任意同类事物（如'丹药'可以指任何丹药），则不提取；
如果一个词只指代某个特定事物（如'混沌珠'只指一颗特定的珠子），则提取。

每轮结果都落盘 runtime/entity_round_X.json，支持断点续跑。
"""

import json
import os
import re
from typing import Any, Dict, List, Set

from ..base import TaskNode
from .entity_common import (
    CATEGORIES,
    atomic_write_json,
    is_generic_entity,
    read_full_text,
)

WINDOW_SIZE = 5000
WINDOW_STEP = 2000

ROUND_FILES = {
    1: "entity_round_1_chapters.json",
    2: "entity_round_2_sliding.json",
    3: "entity_round_3_merged.json",
    4: "entity_round_4_no_hallucination.json",
    5: "entity_round_5_normalized.json",
}

PROGRESS_FILE = "entity_extract_progress.json"


def _load_set(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return set(data)
    if isinstance(data, dict):
        s: Set[str] = set()
        for v in data.values():
            if isinstance(v, list):
                s.update(v)
        return s
    return set()


def _union_sets(*args) -> Set[str]:
    out: Set[str] = set()
    for s in args:
        out.update(s)
    return out


def _extract_one_window(content: str) -> Set[str]:
    """单窗口 LLM 抽取，返回字符串集合（不分分类，最后统一归一化）"""
    from llm.client import call_deepseek_api
    from config import (
        ENTITY_EXTRACTION_MODEL,
        ENTITY_EXTRACTION_MAX_TOKENS,
        ENTITY_EXTRACTION_TEMPERATURE,
    )
    system = (
        "你是玄幻小说实体提取专家。严格只提取【专有名称】。\n\n"
        "【必须剔除的模式】（命中任意一条即不提取）：\n"
        "A. 通用称呼/官职/身份后缀：大人、国师、县令、捕头、掌柜、斩妖吏、师叔、长老、宗主、道长、道友、员外、千金、妖道\n"
        "   → 含这些后缀的词一律不提取（如'县令大人''大夏国师''红衣斩妖吏''墨归师叔''妖道秋风'）\n"
        "B. 描述性外观短语：含'黑袍''白衣''红衣''金衣''年轻''老者''青年''男子''女子'等外观词\n"
        "   → 如'黑袍男子''红衣斩妖吏''金衣斩妖吏'一律不提取\n"
        "C. 含'的'或'之'的短语：如'原天域掌域大人的千金''九宫令之离字令''火焰之术'一律不提取\n"
        "D. 通用类别词（可指代任意同类事物）：\n"
        "   人物类：少年、少女、青年、老者、男子、女子\n"
        "   地点类：官道、县城、衙门、村落、茶亭、道观、皇陵、边境\n"
        "   物品类：长剑、短刀、法剑、令牌、拂尘、拐杖、丹药、法宝\n"
        "   功法类：功法、神通、阵法、身法、道术、道诀、秘术、禁术、控火、御风\n"
        "   妖兽类：蛟龙、猛虎、大鱼、妖魔、小妖、妖兽、虾兵蟹将\n"
        "E. 地名+人名的混合体（如'吞阴山袁啸舟''惊雷剑柳明'）→ 只提取人名部分\n"
        "F. 人名+身份后缀的混合体（如'宝寿道长'）→ 提取完整专有名词\n\n"
        "【分类规则】\n"
        "- 同一实体只归入最合适的 1 个分类\n"
        "- 人名 → person，地名/宗门 → place，法宝/武器 → weapon，丹药 → medicine，功法/术法 → skill，妖兽/灵兽 → beast\n"
        "- 不确定时优先归入更具体的分类\n\n"
        "输出 6 类 JSON：person/place/weapon/medicine/skill/beast，值为字符串数组。禁止编造，只输出 JSON。"
    )
    user = (
        "从文本中提取所有专有玄幻实体名称。严格遵守剔除规则，不提取任何通用类别词、描述性短语或含'的'/'之'的短语。\n"
        "无则输出空数组。只输出 JSON。\n\n"
        f"文本：\n{content}"
    )
    try:
        result = call_deepseek_api(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            ENTITY_EXTRACTION_MODEL,
            max_tokens=ENTITY_EXTRACTION_MAX_TOKENS,
            temperature=ENTITY_EXTRACTION_TEMPERATURE,
            response_format={"type": "json_object"},
            task_label="实体提取-滑窗",
        )
        if not result or not result.strip():
            print(f"    [警告] LLM 返回空内容")
            return set()
        # 兼容 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）
        cleaned = result.strip()
        if cleaned.startswith("```"):
            # 去掉首行 ``` 或 ```json
            lines = cleaned.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"    [警告] JSON 解析失败: {e}; 返回内容前200字: {result[:200]!r}")
            return set()
        if isinstance(parsed, list):
            return {
                s.strip()
                for s in parsed
                if isinstance(s, str) and len(s.strip()) >= 2
            }
        if isinstance(parsed, dict):
            out: Set[str] = set()
            for v in parsed.values():
                if isinstance(v, list):
                    for s in v:
                        if isinstance(s, str) and len(s.strip()) >= 2:
                            out.add(s.strip())
            if not out:
                print(f"    [警告] LLM 返回结构正确但为空: {result[:200]!r}")
            return out
        print(f"    [警告] LLM 返回非预期结构: {type(parsed).__name__}, 内容: {result[:200]!r}")
        return set()
    except Exception as e:
        print(f"    [错误] LLM 调用失败: {type(e).__name__}: {e}")
        return set()


def _normalize_by_llm(all_entities: List[str]) -> Dict[str, List[str]]:
    """最后一轮 LLM 归一化：六分类 + 别名合并 + 通用词过滤"""
    from llm.client import call_deepseek_api
    from config import (
        ENTITY_EXTRACTION_MODEL,
        ENTITY_EXTRACTION_MAX_TOKENS,
        ENTITY_EXTRACTION_TEMPERATURE,
    )
    system = (
        "你是玄幻小说实体归一化专家。给定实体列表，执行：\n"
        "1. 合并同指别名（如玉恒/玉恒长老/玉恒老鬼 → 只保留主名玉恒；秋风/秋风妖道/妖道秋风 → 只保留秋风）\n"
        "2. 剔除命中以下模式的实体：\n"
        "   A. 通用称呼/官职/身份后缀：大人、国师、县令、捕头、掌柜、斩妖吏、师叔、长老、宗主、道长、道友、员外、千金、妖道\n"
        "   B. 描述性外观短语：含'黑袍''白衣''红衣''金衣''年轻''老者''青年''男子''女子'等外观词\n"
        "   C. 含'的'或'之'的短语\n"
        "   D. 通用类别词：少年、少女、青年、老者、男子、女子、官道、县城、衙门、村落、茶亭、道观、皇陵、边境、"
        "长剑、短刀、法剑、令牌、拂尘、拐杖、丹药、法宝、功法、神通、阵法、身法、道术、道诀、秘术、禁术、控火、御风、"
        "蛟龙、猛虎、大鱼、妖魔、小妖、妖兽、虾兵蟹将\n"
        "3. 修正分类错误：人名归 person，地名/宗门归 place，法宝/武器归 weapon，丹药归 medicine，功法归 skill，妖兽归 beast\n"
        "4. 同一实体只归入最合适的 1 个分类，不要重复\n"
        "5. 输出 6 类：person/place/weapon/medicine/skill/beast\n"
        "严格只输出 JSON，键必须是以上 6 个，值是字符串数组。不要输出解释，不要编造。"
    )
    user = (
        "实体列表：\n"
        + json.dumps(all_entities, ensure_ascii=False)
        + "\n\n请剔除通用类别词和描述性短语，只保留专有名称。"
        "输出 JSON，键为 person/place/weapon/medicine/skill/beast，值为字符串数组。"
    )
    try:
        result = call_deepseek_api(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            ENTITY_EXTRACTION_MODEL,
            max_tokens=ENTITY_EXTRACTION_MAX_TOKENS,
            temperature=ENTITY_EXTRACTION_TEMPERATURE,
            response_format={"type": "json_object"},
            task_label="实体归一化",
        )
        if not result or not result.strip():
            print(f"    [归一化警告] LLM 返回空内容，走兜底逻辑")
            return {cat: (all_entities if cat == "person" else []) for cat in CATEGORIES}
        # 兼容 markdown 代码块包裹
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"    [归一化警告] JSON 解析失败: {e}")
            print(f"    [归一化警告] 返回内容前 500 字: {result[:500]!r}")
            return {cat: (all_entities if cat == "person" else []) for cat in CATEGORIES}
        out: Dict[str, List[str]] = {cat: [] for cat in CATEGORIES}
        for cat in CATEGORIES:
            items = parsed.get(cat, []) or []
            out[cat] = sorted({
                s.strip()
                for s in items
                if isinstance(s, str) and len(s.strip()) >= 2
                and not is_generic_entity(s.strip())  # 兜底：LLM 归一化后再过滤一遍通用词
            })
        return out
    except Exception as e:
        # 失败兜底：全部放 person ，后续 validate 再修正
        print(f"    [归一化错误] LLM 调用失败: {type(e).__name__}: {e}")
        return {cat: (all_entities if cat == "person" else []) for cat in CATEGORIES}


class EntityExtractTask(TaskNode):
    """四轮工业级实体提取：逐章 → 滑窗 → 去幻觉 → LLM 归一化"""

    @property
    def id(self) -> str:
        return "entity_extract"

    @property
    def name(self) -> str:
        return "实体提取"

    @property
    def deps(self) -> list:
        return ["split_novel"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        from config import RUNTIME_DIR

        chapters_dir = context.get("chapters_dir", "chapters")
        novel_path = context.get("novel_path", "")

        full_text = read_full_text(novel_path, chapters_dir)
        if not full_text:
            raise ValueError("无法读取原文内容")

        os.makedirs(RUNTIME_DIR, exist_ok=True)
        progress_path = os.path.join(RUNTIME_DIR, PROGRESS_FILE)
        progress = {}
        if os.path.exists(progress_path):
            progress = json.load(open(progress_path, encoding="utf-8"))

        # ========== 第一轮：逐章提取 ==========
        round1_path = os.path.join(RUNTIME_DIR, ROUND_FILES[1])
        if progress.get("round1_done") and os.path.exists(round1_path):
            round1 = _load_set(round1_path)
            print(f"  [轮次 1/5] 逐章提取 已完成，{len(round1)} 个实体")
        else:
            chapter_files = sorted(
                [f for f in os.listdir(chapters_dir) if f.endswith(".md") and f[0].isdigit()],
                key=lambda x: int(re.search(r"(\d+)", x).group(1)) if re.search(r"(\d+)", x) else 0
            )
            processed1 = set(progress.get("round1_processed", []))
            round1 = _load_set(round1_path)
            print(f"  [轮次 1/5] 逐章提取，共 {len(chapter_files)} 章，"
                  f"已完成 {len(processed1)} 章")

            for i, f in enumerate(chapter_files):
                if f in processed1:
                    continue
                with open(os.path.join(chapters_dir, f), "r", encoding="utf-8") as fh:
                    content = fh.read()
                if len(content) > WINDOW_SIZE:
                    content = content[:WINDOW_SIZE]
                ents = _extract_one_window(content)
                round1.update(ents)
                processed1.add(f)
                atomic_write_json(round1_path, sorted(round1))
                progress["round1_processed"] = sorted(processed1)
                atomic_write_json(progress_path, progress)
                if (i + 1) % 10 == 0:
                    print(f"    已处理 {i + 1}/{len(chapter_files)} 章，共 {len(round1)} 实体")

            progress["round1_done"] = True
            atomic_write_json(progress_path, progress)
            print(f"  [轮次 1/5] 逐章提取完成，{len(round1)} 个实体")

        # ========== 第二轮：滑窗补抽 ==========
        round2_path = os.path.join(RUNTIME_DIR, ROUND_FILES[2])
        if progress.get("round2_done") and os.path.exists(round2_path):
            round2 = _load_set(round2_path)
            print(f"  [轮次 2/5] 滑窗补抽 已完成，{len(round2)} 个实体")
        else:
            n_windows = (len(full_text) - WINDOW_SIZE + WINDOW_STEP - 1) // WINDOW_STEP + 1
            processed2 = progress.get("round2_processed", 0)
            round2 = _load_set(round2_path)
            print(f"  [轮次 2/5] 滑窗补抽，共 {n_windows} 窗口，"
                  f"已完成 {processed2} 窗口")

            pos = 0
            idx = 0
            while pos < len(full_text):
                if idx < processed2:
                    pos += WINDOW_STEP
                    idx += 1
                    continue
                window = full_text[pos:pos + WINDOW_SIZE]
                ents = _extract_one_window(window)
                round2.update(ents)
                processed2 = idx + 1
                atomic_write_json(round2_path, sorted(round2))
                progress["round2_processed"] = processed2
                atomic_write_json(progress_path, progress)
                if (idx + 1) % 20 == 0:
                    print(f"    已处理 {idx + 1}/{n_windows} 窗口，共 {len(round2)} 实体")
                pos += WINDOW_STEP
                idx += 1

            progress["round2_done"] = True
            atomic_write_json(progress_path, progress)
            print(f"  [轮次 2/5] 滑窗补抽完成，{len(round2)} 个实体")

        # ========== 第三轮：合并 + 字符串去幻觉 ==========
        round3_path = os.path.join(RUNTIME_DIR, ROUND_FILES[3])
        round4_path = os.path.join(RUNTIME_DIR, ROUND_FILES[4])
        if progress.get("round4_done") and os.path.exists(round4_path):
            round4 = _load_set(round4_path)
            print(f"  [轮次 4/5] 去幻觉 已完成，{len(round4)} 个实体")
        else:
            merged = _union_sets(round1, round2)
            atomic_write_json(round3_path, sorted(merged))
            progress["round3_done"] = True
            atomic_write_json(progress_path, progress)
            print(f"  [轮次 3/5] 合并完成，总 {len(merged)} 个实体")

            # 字符串去幻觉
            no_hallucination = {e for e in merged if e in full_text}
            atomic_write_json(round4_path, sorted(no_hallucination))
            progress["round4_done"] = True
            atomic_write_json(progress_path, progress)
            print(f"  [轮次 4/5] 去幻觉完成，{len(no_hallucination)} 个实体 "
                  f"(剔除 {len(merged) - len(no_hallucination)})")
            round4 = no_hallucination

        # ========== 第五轮：LLM 归一化 + 六分类 ==========
        round5_path = os.path.join(RUNTIME_DIR, ROUND_FILES[5])
        if progress.get("round5_done") and os.path.exists(round5_path):
            with open(round5_path, "r", encoding="utf-8") as f:
                final = json.load(f)
            total = sum(len(v) for v in final.values())
            print(f"  [轮次 5/5] LLM 归一化 已完成，最终 {total} 个实体")
        else:
            print(f"  [轮次 5/5] LLM 归一化中...")
            all_entities = sorted(round4)
            final = _normalize_by_llm(all_entities)
            atomic_write_json(round5_path, final)
            progress["round5_done"] = True
            atomic_write_json(progress_path, progress)
            total = sum(len(v) for v in final.values())
            print(f"  [轮次 5/5] LLM 归一化完成，最终 {total} 个实体")

        # 输出和原接口完全兼容，下游 entity_validate 无感知
        entity_raw = {cat: final.get(cat, []) for cat in CATEGORIES}
        output_path = os.path.join(RUNTIME_DIR, "entity_extract_raw.json")
        atomic_write_json(output_path, entity_raw)

        return {"entity_raw": entity_raw, "entity_raw_path": output_path}

    def get_required_keys(self) -> list:
        return []

    def get_output_keys(self) -> list:
        return ["entity_raw", "entity_raw_path"]
