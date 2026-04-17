import json
import re

from config import ENABLE_ANTI_AI_REWRITE, ANTI_AI_MAX_ROUNDS, AUDIT_NEAR_PASS_DELTA
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

    prompt = (
        f"请对第 {chapter_number} 章做一次“保剧情、不改设定”的去模板化改写，以降低 AI 痕迹。\n"
        f"硬要求：\n"
        f"1) 不改变主事件、人物关系、世界设定、章节目标。\n"
        f"2) 主要修表达层：句长错落、减少说明文收束、减少工整排比。\n"
        f"3) 对话更口语化，允许打断、半句、停顿。\n"
        f"4) 增加动作/感官细节，减少抽象总结。\n"
        f"5) 必须优先修复【规则命中】中的问题，逐项消除。\n"
        f"6) 仅输出修订后的完整章节。\n\n"
        f"{findings_text}"
        f"【原文风格参考片段】\n{(reference_text or '')[:2500]}\n\n"
        f"【风格差异对比(JSON)】\n{json.dumps(style_compare, ensure_ascii=False, indent=2)}\n\n"
        f"【既有风格分析】\n{writing_style}\n\n"
        f"【本章意图规划】\n{chapter_plan_text if chapter_plan_text else '无'}\n\n"
        f"【领域圣经】\n{domain_text if domain_text else '无'}\n\n"
        f"【待改写章节】\n{chapter_content}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深网文改稿编辑。你的任务是保留剧情骨架，降低模板腔、说明腔和重复句式。"
                "参考原文语感进行局部重写，不要写成教科书。"
            ),
        },
        {"role": "user", "content": prompt},
    ]
    rewritten = call_deepseek_api(
        messages,
        model,
        max_tokens=len(chapter_content) + 1200,
        temperature=0.55,
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
        passed = bool(last_audit.get("pass", False)) and score >= pass_threshold and ai_trace_score >= ai_trace_hard_threshold
        print(
            f"规则审计得分: {score} (总阈值: {pass_threshold}) / ai_trace: {ai_trace_score} (硬阈值: {ai_trace_hard_threshold})，轮次: {round_idx}/{max_rounds}"
        )
        if passed:
            return {"passed": True, "content": current, "last_audit": last_audit}
        # 最后一轮仅差少量分数时，允许近阈值放行，避免长时间重跑后仍完全不落盘
        if (
            round_idx == max_rounds
            and score >= max(0, pass_threshold - AUDIT_NEAR_PASS_DELTA)
            and ai_trace_score >= ai_trace_hard_threshold
        ):
            print(
                f"规则审计近阈值放行: {score} (阈值 {pass_threshold}, 容差 {AUDIT_NEAR_PASS_DELTA})"
            )
            return {"passed": True, "content": current, "last_audit": last_audit}
        if round_idx == max_rounds:
            break

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
