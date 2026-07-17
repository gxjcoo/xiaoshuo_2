"""LLM 驱动的评估器：章节多维评分 + 结构骨架贴合度评分。

这里只负责「评分」，不负责「修订」；修订相关请见 `audit.revisers`。
"""

import json
import re

from ai_handler import call_deepseek_api
from ai_trace_rules import analyze_ai_trace
from config import TRUNCATE_EVALUATOR_RULES, TRUNCATE_EVALUATOR_FIDELITY


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
        f"【生成稿】\n{chapter_content[:TRUNCATE_EVALUATOR_FIDELITY]}"
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
        task_label=f"第{chapter_number}章结构贴合审计",
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
    except Exception as e:
        print(f"警告：结构骨架审计失败: {e}", flush=True)
        return {"score": 0, "pass": False, "issues": ["结构骨架审计 JSON 解析失败"], "suggestions": []}


def evaluate_next_anchor_continuity(
    generated_tail,
    next_chapter_start,
    chapter_number,
    model="deepseek-chat",
):
    """用结构化 JSON 检查本章结尾是否能接入下一章开头。"""
    if not next_chapter_start:
        return {"score": 100, "pass": True, "issues": [], "suggestions": []}
    prompt = (
        f"请检查第 {chapter_number} 章结尾是否能自然接入第 {chapter_number + 1} 章开头，输出 JSON。\n"
        "只判断衔接逻辑，不评价文笔。重点抽取：下一章开头的呼喊/追逐对象、冲突对象、主角所处位置、是否存在误会指向。\n\n"
        "字段必须为：\n"
        "{\n"
        '  "score": number,\n'
        '  "pass": bool,\n'
        '  "next_anchor": {"protagonist_position": string, "conflict_target": string, "speaker_intent": string},\n'
        '  "tail_state": {"protagonist_position": string, "conflict_target": string, "hook_direction": string},\n'
        '  "issues": [string],\n'
        '  "suggestions": [string]\n'
        "}\n\n"
        "评分规则：\n"
        "- 90-100：对象、事件、时间线、主角位置都可自然接上。\n"
        "- 70-89：略有信息缺口，但不改变下一章开头含义。\n"
        "- 40-69：钩子方向偏弱或对象含混，需要修订。\n"
        "- 0-39：本章结尾与下一章开头矛盾，例如下一章说被追对象另有其人，本章却写成主角被明确抓捕/定罪。\n"
        "pass 仅当 score>=75 且无硬冲突时为 true。\n\n"
        f"【本章结尾】\n{generated_tail}\n\n"
        f"【下一章开头】\n{next_chapter_start}"
    )
    messages = [
        {"role": "system", "content": "你是连载小说跨章衔接审稿器，只输出合法 JSON。"},
        {"role": "user", "content": prompt},
    ]
    raw = call_deepseek_api(
        messages,
        model,
        max_tokens=900,
        temperature=0.05,
        response_format={"type": "json_object"},
        task_label=f"第{chapter_number}章跨章衔接审计",
    )
    if not raw:
        return {
            "score": 0,
            "pass": False,
            "issues": ["跨章衔接结构化审计失败：API 返回为空"],
            "suggestions": ["重试审计，或人工检查本章结尾与下一章开头的对象、事件、主角位置是否一致。"],
        }
    parsed = _parse_json_relaxed(raw)
    if not isinstance(parsed, dict):
        return {
            "score": 0,
            "pass": False,
            "issues": ["跨章衔接结构化审计 JSON 解析失败"],
            "suggestions": ["重试审计，或人工检查本章结尾与下一章开头。"],
        }
    try:
        score = int(parsed.get("score", 0))
    except Exception:
        score = 0
    issues = parsed.get("issues", [])
    suggestions = parsed.get("suggestions", [])
    return {
        "score": score,
        "pass": bool(parsed.get("pass", False)) and score >= 75,
        "next_anchor": parsed.get("next_anchor", {}) if isinstance(parsed.get("next_anchor", {}), dict) else {},
        "tail_state": parsed.get("tail_state", {}) if isinstance(parsed.get("tail_state", {}), dict) else {},
        "issues": issues if isinstance(issues, list) else [],
        "suggestions": suggestions if isinstance(suggestions, list) else [],
    }


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


def evaluate_chapter_with_rules(
    chapter_content,
    chapter_number,
    rules,
    recent_chapter_texts=None,
    chapter_plan_text="",
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
        f"【近期焦点】\n{current_focus_text if current_focus_text else '无'}\n\n"
        f"【正文】\n{chapter_content[:TRUNCATE_EVALUATOR_RULES]}"
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
        task_label=f"第{chapter_number}章规则审计",
    )
    if not raw:
        return {"total_score": 0, "pass": False, "issues": ["审计失败"], "suggestions": []}

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
