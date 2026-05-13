import json
import re

from config import (
    ENABLE_ANTI_AI_REWRITE,
    ANTI_AI_MAX_ROUNDS,
    AUDIT_NEAR_PASS_DELTA,
    REFERENCE_SIMILARITY_NGRAM_OVERLAP,
    REFERENCE_SIMILARITY_SENTENCE_REUSE,
    REFERENCE_SIMILARITY_OVERLAP_COUNT,
    PLOT_FIDELITY_MIN_SCORE,
)
from config import CHAPTER_GENERATION_MODEL, CONTEXT_ANALYSIS_MODEL
from ai_handler import call_deepseek_api
from ai_trace_rules import analyze_ai_trace


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


def _plot_fidelity_min_score(rules=None):
    if isinstance(rules, dict):
        try:
            return int(rules.get("plot_fidelity_min_score", PLOT_FIDELITY_MIN_SCORE))
        except Exception:
            return PLOT_FIDELITY_MIN_SCORE
    return PLOT_FIDELITY_MIN_SCORE


def evaluate_plot_fidelity_with_outline(
    reference_plot_outline,
    chapter_content,
    chapter_number,
    model="deepseek-chat",
    min_score=80,
):
    """检查生成稿是否偏离结构骨架。"""
    if not reference_plot_outline:
        return {"score": 100, "pass": True, "issues": [], "suggestions": []}
    prompt = (
        f"请检查第 {chapter_number} 章生成稿是否忠实覆盖结构功能骨架，输出 JSON。\n"
        "字段必须为：\n"
        "{\n"
        '  "score": number,\n'
        '  "pass": bool,\n'
        '  "missing_events": [string],\n'
        '  "drift_issues": [string],\n'
        '  "wrong_added_facts": [string],\n'
        '  "suggestions": [string]\n'
        "}\n\n"
        "评分规则：\n"
        "- 100：结构功能、因果位置、人物功能、结尾功能完整一致。\n"
        "- 80-99：有轻微遗漏或弱化，但不改变主线结构结果。\n"
        "- 60-79：缺少关键功能节点、因果位置变弱或结尾功能有偏差。\n"
        "- 0-59：改变主线结构、反转关键因果、替换结局功能或新增破坏结构的大事件。\n"
        f"- pass 仅当 score >= {min_score} 且无关键剧情反转时为 true。\n\n"
        f"【结构功能骨架】\n```json\n{reference_plot_outline}\n```\n\n"
        f"【生成稿】\n{chapter_content[:10000]}"
    )
    messages = [
        {"role": "system", "content": "你是严格的结构一致性审计器，只检查结构骨架覆盖，不评价文采。输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        model,
        max_tokens=1100,
        temperature=0.05,
        response_format={"type": "json_object"},
    )
    if not raw:
        return {"score": 0, "pass": False, "issues": ["结构骨架审计失败"], "suggestions": []}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("plot fidelity output is not object")
        score = int(parsed.get("score", 0))
        missing = parsed.get("missing_events", [])
        drift = parsed.get("drift_issues", [])
        added = parsed.get("wrong_added_facts", [])
        suggestions = parsed.get("suggestions", [])
        issues = []
        for vals in (missing, drift, added):
            if isinstance(vals, list):
                issues.extend(str(v) for v in vals if str(v).strip())
        passed = bool(parsed.get("pass", False)) and score >= min_score
        return {
            "score": score,
            "pass": passed,
            "missing_events": missing if isinstance(missing, list) else [],
            "drift_issues": drift if isinstance(drift, list) else [],
            "wrong_added_facts": added if isinstance(added, list) else [],
            "issues": issues,
            "suggestions": suggestions if isinstance(suggestions, list) else [],
        }
    except Exception:
        return {"score": 0, "pass": False, "issues": ["结构骨架审计 JSON 解析失败"], "suggestions": []}


def revise_for_plot_fidelity(
    reference_plot_outline,
    chapter_content,
    plot_report,
    chapter_number,
    chapter_plan_text="",
    domain_text="",
    model="deepseek-chat",
):
    """按结构骨架审计结果修正文稿，优先补齐缺失功能节点与纠正偏离。"""
    report_json = json.dumps(plot_report, ensure_ascii=False, indent=2)
    prompt = (
        f"请修订第 {chapter_number} 章，使其重新贴合结构功能骨架。\n"
        "硬要求：\n"
        "1) 补齐 missing_events，纠正 drift_issues，删除或弱化 wrong_added_facts。\n"
        "2) 不要照抄结构骨架或参考原文，要写成自然小说正文。\n"
        "3) 保持当前正文已有的表达与实体差异，不要为了贴合结构而改回参考章句式或实体体系。\n"
        "4) 只输出完整修订后章节。\n\n"
        f"【结构骨架】\n```json\n{reference_plot_outline}\n```\n\n"
        f"【剧情偏离报告】\n{report_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【领域圣经】\n{domain_text if domain_text else '无'}\n\n"
        f"【当前正文】\n{chapter_content}"
    )
    messages = [
        {"role": "system", "content": "你是小说结构修订编辑，优先修正结构偏离，同时保持表达和实体体系与参考文拉开距离。"},
        {"role": "user", "content": prompt},
    ]
    revised = call_deepseek_api(messages, model, max_tokens=len(chapter_content) + 1600, temperature=0.42)
    if not revised:
        return chapter_content
    revised = revised.strip()
    if revised and not revised.startswith("# "):
        revised = f"# 第{chapter_number}章 修订稿\n\n{revised}"
    return revised


def rewrite_for_expression_distance(
    reference_text,
    chapter_content,
    similarity_report,
    chapter_number,
    chapter_plan_text="",
    domain_text="",
    model="deepseek-chat",
):
    """保留剧情事实，重写表达结构，专门处理与参考章过像的问题。"""
    report_json = json.dumps(similarity_report, ensure_ascii=False, indent=2)
    prompt = (
        f"请对第 {chapter_number} 章做一次“剧情不变、表达降重”的完整重写。\n"
        "目标：降低与参考章的连续字串、句式骨架、段落推进和开头/结尾相似度。\n\n"
        "硬要求：\n"
        "1) 保留当前正文里的主事件、人物动机、因果关系和结尾状态。\n"
        "2) 重排镜头入口、动作承接、对话切入顺序和段落节奏；同一事件换一种现场展开。\n"
        "3) 禁止连续 12 个字以上与参考章一致，尤其避开 matched_samples 中的表达。\n"
        "4) 不要新增改变剧情的关键事实，不要改人物关系结果。\n"
        "5) 只输出修订后的完整章节，标题格式仍为 `# 第N章 副题`。\n\n"
        f"【相似度报告】\n{report_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【领域圣经】\n{domain_text if domain_text else '无'}\n\n"
        f"【参考章片段（只用于避开重复表达，不得仿句）】\n{(reference_text or '')[:1200]}\n\n"
        f"【待降重正文】\n{chapter_content}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是小说降重改稿编辑。你的任务不是润色得更像参考文，"
                "而是在剧情不变的前提下主动拉开表达距离，避免句式和段落同构。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    rewritten = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1600,
        temperature=0.58,
    )
    if not rewritten:
        return chapter_content
    rewritten = rewritten.strip()
    if rewritten and not rewritten.startswith("# "):
        rewritten = f"# 第{chapter_number}章 修订稿\n\n{rewritten}"
    return rewritten


def anti_ai_rewrite_with_reference(
    reference_text,
    chapter_content,
    style_compare,
    chapter_number,
    writing_style,
    chapter_plan_text="",
    domain_text="",
    ai_trace_findings=None,
    model="deepseek-chat",
):
    """参考原文风格和差异，执行定向去模板化重写。"""
    findings_text = ""
    if ai_trace_findings:
        lines = []
        for item in ai_trace_findings[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- [{item.get('rule', 'unknown')}] {item.get('description', '')}；修复建议：{item.get('suggestion', '')}"
            )
        if lines:
            findings_text = "【规则命中（必须优先修复）】\n" + "\n".join(lines) + "\n\n"

    style_snip = (writing_style or "").strip()
    if len(style_snip) > 1400:
        style_snip = style_snip[:1400] + "\n…（风格分析已截断）"

    prompt = (
        f"请对第 {chapter_number} 章做一次“保剧情、不改设定”的去模板化改写，以降低 AI 痕迹。\n"
        f"硬要求：\n"
        f"1) 不改变主事件、人物关系、世界设定、章节目标。\n"
        f"2) 主要修表达层：句长错落、减少说明文收束、减少工整排比。\n"
        f"3) 对话更口语化，允许打断、半句、停顿、抢话、说一半咽回去。\n"
        f"4) 增加动作/感官细节，减少抽象总结；允许略「糙」、略碎，不要润成光滑范文。\n"
        f"5) 刻意制造几处短段、一声一动的顿挫，少用「然而/因此/这一刻」类连接与收束。\n"
        f"6) 必须优先修复【规则命中】中的问题，逐项消除。\n"
        f"7) 仅输出修订后的完整章节。\n\n"
        f"{findings_text}"
        f"【参考文风格指标（只用于节奏差异判断，不得仿句）】\n{json.dumps(_basic_style_metrics(reference_text), ensure_ascii=False, indent=2)}\n\n"
        f"【风格差异对比(JSON)】\n{json.dumps(style_compare, ensure_ascii=False, indent=2)}\n\n"
        f"【既有风格分析（节选）】\n{style_snip if style_snip else '无'}\n\n"
        f"【本章意图规划】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【领域圣经】\n{(domain_text or '')[:1800] if domain_text else '无'}\n\n"
        f"【待改写章节】\n{chapter_content}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深网文改稿编辑：保留结构骨架，专门打掉模板腔、说明腔、排比与段尾万能升华。"
                "改完要像人在连载站点直接发章——允许碎、糙、打断，不要改成语文阅读题标准答案。"
                "参考原文片段只借语感与节奏，不要全文仿句式堆砌。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    rewritten = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1200,
        temperature=0.62,
    )
    if not rewritten:
        return chapter_content
    rewritten = rewritten.strip()
    if rewritten and not rewritten.startswith("# "):
        rewritten = f"# 第{chapter_number}章 修订稿\n\n{rewritten}"
    return rewritten


def evaluate_chapter_with_rules(
    chapter_content,
    chapter_number,
    rules,
    recent_chapter_texts=None,
    chapter_plan_text="",
    domain_text="",
    author_intent_text="",
    current_focus_text="",
    model="deepseek-chat",
):
    """按 audit_rules 评估章节，返回结构化评分结果。"""
    if not chapter_content:
        return {"total_score": 0, "pass": False, "issues": ["内容为空"], "suggestions": []}

    rules_json = json.dumps(rules, ensure_ascii=False, indent=2)
    prompt = (
        f"请作为小说审计器，严格依据规则对第 {chapter_number} 章评分，输出 JSON。\n"
        f"评分范围 0-100，必须包含字段：\n"
        f'{{"total_score": number, "pass": bool, "dimension_scores": {{"id": number}}, "issues": [string], "suggestions": [string]}}\n'
        f"规则如下：\n{rules_json}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【领域圣经】\n{domain_text if domain_text else '无'}\n\n"
        f"【作者长期意图】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}\n\n"
        f"【正文】\n{chapter_content[:9000]}"
    )
    messages = [
        {"role": "system", "content": "你是严格的小说审计评分器，输出必须是合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        model,
        max_tokens=1200,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    if not raw:
        return {"total_score": 0, "pass": False, "issues": ["审计失败"], "suggestions": []}

    def _extract_balanced_json(text):
        if not text:
            return ""
        start = text.find("{")
        if start < 0:
            return ""
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return ""

    def _parse_json_relaxed(text):
        candidates = []
        t = (text or "").strip()
        if t:
            candidates.append(t)
        fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", t, flags=re.IGNORECASE)
        for block in fenced:
            b = block.strip()
            if b:
                candidates.append(b)
        balanced = _extract_balanced_json(t)
        if balanced:
            candidates.append(balanced)

        for cand in candidates:
            try:
                parsed_obj = json.loads(cand)
                if isinstance(parsed_obj, dict):
                    return parsed_obj
            except Exception:
                continue
        return None

    try:
        parsed = _parse_json_relaxed(raw)
        if not isinstance(parsed, dict):
            raise ValueError("审计输出非 JSON 对象")
        result = {
            "total_score": int(parsed.get("total_score", 0)),
            "pass": bool(parsed.get("pass", False)),
            "dimension_scores": parsed.get("dimension_scores", {}),
            "issues": parsed.get("issues", []),
            "suggestions": parsed.get("suggestions", []),
            "ai_trace_rule_issues": [],
        }
        # 叠加确定性 ai_trace 规则分析，避免只靠模型主观判断
        deterministic = analyze_ai_trace(chapter_content, recent_chapter_texts=recent_chapter_texts or [])
        penalty = int(deterministic.get("score_penalty", 0))
        rule_issues = deterministic.get("issues", []) if isinstance(deterministic.get("issues", []), list) else []
        result["ai_trace_rule_issues"] = rule_issues
        if penalty > 0:
            # 确定性扣分与模型分叠加易把「已通过」的章节压穿阈值；对总分与 ai_trace 分别封顶
            cap_total = int(rules.get("deterministic_penalty_cap_total", 12))
            cap_ai = int(rules.get("deterministic_penalty_cap_ai_trace", 10))
            cap_total = max(0, cap_total)
            cap_ai = max(0, cap_ai)
            applied_total = min(penalty, cap_total)
            applied_ai = min(penalty, cap_ai)
            result["total_score"] = max(0, int(result.get("total_score", 0)) - applied_total)
            dims = result.get("dimension_scores", {})
            if not isinstance(dims, dict):
                dims = {}
            ai_trace_raw = dims.get("ai_trace", 0)
            try:
                ai_trace_score = int(ai_trace_raw)
            except Exception:
                ai_trace_score = 0
            dims["ai_trace"] = max(0, ai_trace_score - applied_ai)
            result["dimension_scores"] = dims

            extra_issue_lines = [
                f"[{item.get('rule', 'ai_trace')}] {item.get('description', '')}"
                for item in rule_issues if isinstance(item, dict)
            ]
            extra_suggestion_lines = [
                item.get("suggestion", "")
                for item in rule_issues if isinstance(item, dict) and item.get("suggestion")
            ]
            result["issues"] = (result.get("issues", []) or []) + extra_issue_lines
            result["suggestions"] = (result.get("suggestions", []) or []) + extra_suggestion_lines

        # 仅统计明确标为 severe 的命中；勿用 severity==warning（当前软规则也用它，会误伤）
        severe_hits = len([i for i in rule_issues if isinstance(i, dict) and i.get("severity") == "severe"])
        structural_hard_rules = {"事件密度不足", "解释段超限", "角色声纹同构"}
        structural_hard_hits = [
            i for i in rule_issues
            if isinstance(i, dict) and i.get("rule") in structural_hard_rules
        ]
        result["structural_hard_hits"] = len(structural_hard_hits)
        if severe_hits >= 3 or structural_hard_hits:
            result["pass"] = False
        if "pass" not in parsed:
            result["pass"] = int(result.get("total_score", 0)) >= int(rules.get("pass_threshold", 85))
        return result
    except Exception as e:
        preview = (raw or "").replace("\n", "\\n")
        if len(preview) > 400:
            preview = preview[:400] + "...(truncated)"
        print(f"警告：审计结果解析失败: {e}; raw_preview={preview}")
        return {"total_score": 0, "pass": False, "issues": ["审计结果解析失败"], "suggestions": []}


def revise_chapter_by_audit_feedback(
    chapter_content,
    chapter_number,
    writing_style,
    audit_result,
    chapter_plan_text="",
    domain_text="",
    author_intent_text="",
    current_focus_text="",
    focus_dimensions=None,
    model="deepseek-chat",
):
    """基于审计反馈做一次针对性修订。"""
    feedback_json = json.dumps(audit_result, ensure_ascii=False, indent=2)
    focus_dimensions = focus_dimensions or []
    focus_text = "、".join(str(x).strip() for x in focus_dimensions if str(x).strip()) or "issues 中最高优先级问题"
    prompt = (
        f"请根据审计结果修订第 {chapter_number} 章，仅修复问题，不改变核心剧情走向。\n"
        f"要求：\n"
        f"1) 本轮只优先修复这些维度：{focus_text}。\n"
        f"2) 保持原文风格与角色设定。\n"
        f"3) 除上述维度外，其他内容仅做最小改动，禁止大改剧情结构。\n"
        f"4) 输出完整修订后正文。\n\n"
        f"【审计结果】\n{feedback_json}\n\n"
        f"【风格分析】\n{writing_style}\n\n"
        f"【本章意图】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【领域圣经】\n{domain_text if domain_text else '无'}\n\n"
        f"【作者长期意图】\n{author_intent_text if author_intent_text else '无'}\n\n"
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}\n\n"
        f"【当前正文】\n{chapter_content}"
    )
    messages = [
        {"role": "system", "content": "你是小说改稿编辑，按反馈精修但不改剧情主干。"},
        {"role": "user", "content": prompt},
    ]
    revised = call_deepseek_api(messages, model, max_tokens=len(chapter_content) + 1400, temperature=0.35)
    if not revised:
        return chapter_content
    revised = revised.strip()
    if revised and not revised.startswith("# "):
        revised = f"# 第{chapter_number}章 修订稿\n\n{revised}"
    return revised


def audit_and_revise_until_pass(
    chapter_content,
    chapter_number,
    writing_style,
    rules,
    recent_chapter_texts=None,
    reference_text="",
    reference_plot_outline="",
    chapter_plan_text="",
    domain_text="",
    author_intent_text="",
    current_focus_text="",
    generation_model=CHAPTER_GENERATION_MODEL,
    analysis_model=CONTEXT_ANALYSIS_MODEL,
):
    """按规则循环审计修订，达标才返回成功。"""
    if not chapter_content:
        return {"passed": False, "content": chapter_content, "last_audit": {"total_score": 0}}

    pass_threshold = int(rules.get("pass_threshold", 85))
    ai_trace_hard_threshold = int(rules.get("ai_trace_hard_threshold", 80))
    max_rounds = int(rules.get("max_revise_rounds", ANTI_AI_MAX_ROUNDS))
    max_rounds = max(1, max_rounds)
    current = chapter_content
    last_audit = {"total_score": 0, "pass": False, "issues": ["未审计"]}
    similarity_rewrite_used = False
    plot_min_score = _plot_fidelity_min_score(rules)

    def _pick_focus_dimensions(dimension_scores):
        if not isinstance(dimension_scores, dict) or not dimension_scores:
            return []
        normalized = []
        for dim_id, dim_score in dimension_scores.items():
            try:
                normalized.append((str(dim_id), int(dim_score)))
            except Exception:
                continue
        normalized.sort(key=lambda x: x[1])
        return [dim for dim, _ in normalized[:2]]

    for round_idx in range(max_rounds + 1):
        last_audit = evaluate_chapter_with_rules(
            current,
            chapter_number,
            rules,
            recent_chapter_texts=recent_chapter_texts,
            chapter_plan_text=chapter_plan_text,
            domain_text=domain_text,
            author_intent_text=author_intent_text,
            current_focus_text=current_focus_text,
            model=analysis_model,
        )
        score = int(last_audit.get("total_score", 0))
        try:
            ai_trace_score = int((last_audit.get("dimension_scores", {}) or {}).get("ai_trace", 0))
        except Exception:
            ai_trace_score = 0
        similarity_report = (
            analyze_reference_similarity(reference_text, current, rules=rules)
            if reference_text
            else {"too_similar": False, "ngram_overlap": 0.0, "sentence_reuse": 0.0}
        )
        plot_report = evaluate_plot_fidelity_with_outline(
            reference_plot_outline,
            current,
            chapter_number,
            model=analysis_model,
            min_score=plot_min_score,
        )
        similarity_ok = not bool(similarity_report.get("too_similar", False))
        plot_ok = bool(plot_report.get("pass", True))
        passed = (
            bool(last_audit.get("pass", False))
            and score >= pass_threshold
            and ai_trace_score >= ai_trace_hard_threshold
            and similarity_ok
            and plot_ok
        )
        print(
            f"规则审计得分: {score} (总阈值: {pass_threshold}) / ai_trace: {ai_trace_score} (硬阈值: {ai_trace_hard_threshold})，轮次: {round_idx}/{max_rounds}"
        )
        if reference_text:
            print(
                "参考相似度: "
                f"ngram_overlap={similarity_report.get('ngram_overlap', 0)} / "
                f"sentence_reuse={similarity_report.get('sentence_reuse', 0)} / "
                f"overlap_count={similarity_report.get('overlap_count', 0)} / "
                f"{'过高' if not similarity_ok else '通过'}"
            )
        if reference_plot_outline:
            print(
                f"结构骨架贴合: {plot_report.get('score', 0)} "
                f"(阈值: {plot_min_score}) / {'偏离' if not plot_ok else '通过'}"
            )
        last_audit["reference_similarity"] = similarity_report
        last_audit["plot_fidelity"] = plot_report
        if passed:
            return {"passed": True, "content": current, "last_audit": last_audit}
        # 最后一轮仅差少量分数时，允许近阈值放行，避免长时间重跑后仍完全不落盘
        if (
            round_idx == max_rounds
            and score >= max(0, pass_threshold - AUDIT_NEAR_PASS_DELTA)
            and ai_trace_score >= ai_trace_hard_threshold
            and similarity_ok
            and plot_ok
        ):
            print(
                f"规则审计近阈值放行: {score} (阈值 {pass_threshold}, 容差 {AUDIT_NEAR_PASS_DELTA})"
            )
            return {"passed": True, "content": current, "last_audit": last_audit}
        if round_idx == max_rounds:
            break

        if reference_plot_outline and not plot_ok:
            issues = plot_report.get("issues", []) or []
            suggestions = plot_report.get("suggestions", []) or []
            last_audit["issues"] = (last_audit.get("issues", []) or []) + [
                f"[plot_fidelity] {item}" for item in issues
            ]
            last_audit["suggestions"] = (last_audit.get("suggestions", []) or []) + [
                f"[plot_fidelity] {item}" for item in suggestions
            ]
            current = revise_for_plot_fidelity(
                reference_plot_outline,
                current,
                plot_report,
                chapter_number,
                chapter_plan_text=chapter_plan_text,
                domain_text=domain_text,
                model=generation_model,
            )
            print("结构骨架贴合未达标，已执行一次结构纠偏修订。")
            continue

        if reference_text and not similarity_ok and not similarity_rewrite_used:
            current = rewrite_for_expression_distance(
                reference_text,
                current,
                similarity_report,
                chapter_number,
                chapter_plan_text=chapter_plan_text,
                domain_text=domain_text,
                model=generation_model,
            )
            similarity_rewrite_used = True
            print("参考相似度过高，已执行一次剧情不变的表达降重重写。")
            continue

        # 将去 AI 味作为 ai_trace 维度的专属修订策略并入唯一审计循环
        if ENABLE_ANTI_AI_REWRITE:
            if ai_trace_score < ai_trace_hard_threshold and reference_text:
                style_compare = compare_reference_and_generated(reference_text, current)
                current = anti_ai_rewrite_with_reference(
                    reference_text,
                    current,
                    style_compare,
                    chapter_number,
                    writing_style,
                    chapter_plan_text=chapter_plan_text,
                    domain_text=domain_text,
                    ai_trace_findings=last_audit.get("ai_trace_rule_issues", []),
                    model=generation_model,
                )
                print(
                    f"ai_trace 硬阈值未达标（{ai_trace_score} < {ai_trace_hard_threshold}），已执行一次参考文去模板化修订。"
                )
            elif reference_text and not passed:
                # 在总评未过但 ai_trace 达标时，保留一次轻量去模板化优化（避免误导为“未达标”）
                style_compare = compare_reference_and_generated(reference_text, current)
                current = anti_ai_rewrite_with_reference(
                    reference_text,
                    current,
                    style_compare,
                    chapter_number,
                    writing_style,
                    chapter_plan_text=chapter_plan_text,
                    domain_text=domain_text,
                    ai_trace_findings=last_audit.get("ai_trace_rule_issues", []),
                    model=generation_model,
                )
                print("ai_trace 已达硬阈值，但总评未通过，已执行一次轻量去模板化优化。")

        current = revise_chapter_by_audit_feedback(
            current,
            chapter_number,
            writing_style,
            last_audit,
            chapter_plan_text=chapter_plan_text,
            domain_text=domain_text,
            author_intent_text=author_intent_text,
            current_focus_text=current_focus_text,
            focus_dimensions=_pick_focus_dimensions(last_audit.get("dimension_scores", {})),
            model=generation_model,
        )
    return {"passed": False, "content": current, "last_audit": last_audit}
