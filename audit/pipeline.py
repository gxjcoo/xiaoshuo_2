"""审计-修订闭环：单章按规则循环审计，达标才返回成功。

编排 `metrics` / `evaluators` / `revisers` 三个子模块，并加入：
- 实体泄漏检测与硬替换
- Plateau 检测（连续 3 轮变化 < 2 时回退到历史最佳版本）
- 双向衔接校验（开头 ↔ 上一章结尾、结尾 → 下一章预览）
- 多种针对性修订策略选择（结构偏离 / 表达过像 / AI 味 / 通用反馈）
"""

from concurrent.futures import ThreadPoolExecutor

from audit_enhanced import AuditHistory
from ai_trace_rules import _dice_similarity, _normalize_chinese

from config import (
    ENABLE_ANTI_AI_REWRITE,
    ANTI_AI_REWRITE_ONLY_WHEN_BELOW_THRESHOLD,
    ANTI_AI_MAX_ROUNDS,
    AUDIT_PARALLEL_EVALUATORS,
    AUDIT_SKIP_LLM_CONTINUITY_ON_GUARD_FAIL,
    AUDIT_NEAR_PASS_DELTA,
    CHAPTER_GENERATION_MODEL,
    CONTEXT_ANALYSIS_MODEL,
)

from .metrics import (
    analyze_reference_similarity,
    compare_reference_and_generated,
    plot_fidelity_min_score,
)
from .evaluators import (
    evaluate_chapter_with_rules,
    evaluate_plot_fidelity_with_outline,
    evaluate_next_anchor_continuity,
)
from .revisers import (
    revise_for_plot_fidelity,
    rewrite_for_expression_distance,
    anti_ai_rewrite_with_reference,
    revise_chapter_by_audit_feedback,
)


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


def _has_any(text, terms):
    return any(term in text for term in terms)


def _append_audit_issue(last_audit, issue, suggestion):
    issues = last_audit.get("issues", []) or []
    suggestions = last_audit.get("suggestions", []) or []
    issues.append(issue)
    suggestions.append(suggestion)
    last_audit["issues"] = issues
    last_audit["suggestions"] = suggestions


def _evaluate_rule_and_plot(
    current,
    chapter_number,
    rules,
    recent_chapter_texts,
    chapter_plan_text,
    current_focus_text,
    analysis_model,
    reference_plot_outline,
    plot_min_score,
):
    """并行执行两个互不依赖的 LLM 审计，减少单轮网络等待。"""
    if not AUDIT_PARALLEL_EVALUATORS or not reference_plot_outline:
        last_audit = evaluate_chapter_with_rules(
            current,
            chapter_number,
            rules,
            recent_chapter_texts=recent_chapter_texts,
            chapter_plan_text=chapter_plan_text,
            current_focus_text=current_focus_text,
            model=analysis_model,
        )
        plot_report = evaluate_plot_fidelity_with_outline(
            reference_plot_outline,
            current,
            chapter_number,
            model=analysis_model,
            min_score=plot_min_score,
        )
        return last_audit, plot_report

    with ThreadPoolExecutor(max_workers=2) as pool:
        rule_future = pool.submit(
            evaluate_chapter_with_rules,
            current,
            chapter_number,
            rules,
            recent_chapter_texts=recent_chapter_texts,
            chapter_plan_text=chapter_plan_text,
            current_focus_text=current_focus_text,
            model=analysis_model,
        )
        plot_future = pool.submit(
            evaluate_plot_fidelity_with_outline,
            reference_plot_outline,
            current,
            chapter_number,
            model=analysis_model,
            min_score=plot_min_score,
        )
        return rule_future.result(), plot_future.result()


def _next_anchor_conflict_issues(gen_end, next_chapter_start):
    """确定性识别本章结尾与下一章开头的硬冲突。"""
    if not next_chapter_start:
        return []
    issues = []
    next_start = next_chapter_start.strip()
    generated_tail = gen_end.strip()

    chase_terms = ("追", "追杀", "追来", "追赶", "逃", "拦路")
    if _has_any(next_start, chase_terms) and not _has_any(generated_tail, chase_terms):
        issues.append((
            "[continuity] 下一章开头存在追逐/追杀/逃避类动作，但本章结尾没有铺垫对应压力。",
            "重写本章结尾，让钩子落在下一章开头已经确定的追逐对象、冲突来源和行动方向上。",
        ))

    reveal_terms = ("而不是", "原来是", "不是他", "不是她", "并非")
    evil_other_terms = ("老者", "老家伙", "妖道", "邪气", "骷髅", "婴儿")
    mistaken_capture_terms = ("捕快", "官差", "衙役", "巡捕", "差役", "拿人", "缉拿")
    restrain_terms = ("堵", "围", "拦", "抓", "拿", "锁", "押", "缉", "擒")
    if (
        _has_any(next_start, reveal_terms)
        and _has_any(next_start, evil_other_terms)
        and _has_any(generated_tail, mistaken_capture_terms)
        and _has_any(generated_tail, restrain_terms)
    ):
        issues.append((
            "[continuity] 下一章开头揭示被追/被喊的对象另有其人，但本章结尾写成主角被捕快或官差明确围捕。",
            "重写本章结尾：只铺垫真正的追杀者或旁侧冲突，不要把主角写成已被明确定罪、抓捕或围堵的对象。",
        ))

    if "为何不助我" in next_start and _has_any(generated_tail, mistaken_capture_terms):
        issues.append((
            "[continuity] 下一章开头把主角放在可被求助的旁观/介入位置，但本章结尾把他放进官差围捕场。",
            "让本章结尾保留主角可回头介入的空间，避免用捕快堵门、官差拿人等结局功能覆盖下一章开场。",
        ))
    return issues


def audit_and_revise_until_pass(
    chapter_content,
    chapter_number,
    writing_style,
    rules,
    recent_chapter_texts=None,
    reference_text="",
    reference_plot_outline="",
    chapter_plan_text="",
    current_focus_text="",
    generation_model=CHAPTER_GENERATION_MODEL,
    analysis_model=CONTEXT_ANALYSIS_MODEL,
    prev_chapter_end="",
    next_chapter_start="",
    entity_rewrite=False,
    entity_map=None,
):
    """按规则循环审计修订，达标才返回成功。
    含 Plateau 检测（回退到历史最佳版本）。
    """
    if not chapter_content:
        return {"passed": False, "content": chapter_content, "last_audit": {"total_score": 0}}

    pass_threshold = int(rules.get("pass_threshold", 68))
    ai_trace_hard_threshold = int(rules.get("ai_trace_hard_threshold", 50))
    max_rounds = int(rules.get("max_revise_rounds", ANTI_AI_MAX_ROUNDS))
    max_rounds = max(1, max_rounds)
    current = chapter_content
    last_audit = {"total_score": 0, "pass": False, "issues": ["未审计"]}
    similarity_rewrite_used = False
    plot_min_score = plot_fidelity_min_score(rules)

    audit_history = AuditHistory(max_history=5)
    best_version = {
        "score": 0,
        "content": chapter_content,
        "audit": last_audit,
    }
    anti_ai_rewrite_used = False

    for round_idx in range(max_rounds + 1):
        plateau_detected = False
        # 入轮先做一次实体硬清洗，确保上一轮任何修订都没把原名引回来
        if entity_rewrite and entity_map:
            from entity_rewriter import apply_entity_rewrite as _apply_rewrite
            current = _apply_rewrite(current, entity_map)
        last_audit, plot_report = _evaluate_rule_and_plot(
            current,
            chapter_number,
            rules,
            recent_chapter_texts,
            chapter_plan_text,
            current_focus_text,
            analysis_model,
            reference_plot_outline,
            plot_min_score,
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
        similarity_ok = not bool(similarity_report.get("too_similar", False))
        plot_ok = bool(plot_report.get("pass", True))
        # 审计 API 双空时不能正式放行：结构/衔接风险不可被“空响应”覆盖。
        both_api_empty = (score == 0 and plot_report.get("score", 0) == 0)
        if both_api_empty:
            last_audit["pass"] = False
            last_audit["total_score"] = 0
            last_audit["issues"] = (last_audit.get("issues", []) or []) + [
                "[audit_empty] 规则审计与结构贴合审计均返回空响应，本轮不得正式落盘。"
            ]
            last_audit["suggestions"] = (last_audit.get("suggestions", []) or []) + [
                "请重试审计或检查模型/API 状态；必要时先人工检查当前稿件后再重新运行。"
            ]
            print("  审计+结构贴合 API 双空，本轮不允许正式放行。")
        elif score == 0 and plot_report.get("score", 0) > 0:
            score = int(plot_report.get("score", 0))
            last_audit["pass"] = True
            last_audit["total_score"] = score
            print(f"  审计器空响应，用结构贴合度({score})兜底")
        if ai_trace_score == 0:
            ai_trace_score = 80
        # 用修正后的分数做 Plateau 检测
        audit_history.add_score(score, current)
        if score > best_version["score"]:
            best_version = {"score": score, "content": current, "audit": last_audit}
        if audit_history.is_plateau(threshold=2.0, lookback=3):
            plateau_detected = True
            print(f"  Plateau: 连续3轮分数变化<2，当前={score} 历史最佳={best_version['score']}")
            if best_version["score"] >= pass_threshold:
                print("  历史最佳分数已达标，但仍需通过实体/相似度/结构/双向衔接硬门槛")
        passed = (
            bool(last_audit.get("pass", False))
            and score >= pass_threshold
            and ai_trace_score >= ai_trace_hard_threshold
            and similarity_ok
            and plot_ok
        )
        print(
            f"规则审计得分: {score} (总阈值: {pass_threshold}) / "
            f"ai_trace: {ai_trace_score} (硬阈值: {ai_trace_hard_threshold})，轮次: {round_idx}/{max_rounds}"
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

        # --- 实体泄漏检测：先硬替换，再扣分（修订 prompt 会拿到残留明细） ---
        if entity_rewrite and entity_map:
            from entity_rewriter import (
                detect_original_entity_leaks,
                format_entity_leak_report,
                apply_entity_rewrite,
            )
            leaks_before = detect_original_entity_leaks(current, entity_map)
            if leaks_before:
                print(f"  实体泄漏(替换前): {len(leaks_before)} 个原名残留")
                # 先做一次硬替换，让本轮审计在干净文本上做判断
                current = apply_entity_rewrite(current, entity_map)
                leaks_after = detect_original_entity_leaks(current, entity_map)
                last_audit["entity_leaks"] = leaks_before
                last_audit["entity_leaks_remaining"] = leaks_after
                if leaks_after:
                    # 硬替换之后仍残留（子串歧义等），按残留扣分并把详情塞进 issues
                    leak_penalty = min(20, sum(l["count"] for l in leaks_after) * 3)
                    score = max(0, score - leak_penalty)
                    print(
                        f"  硬替换后仍残留 {len(leaks_after)} 项，扣 {leak_penalty} 分：\n"
                        + format_entity_leak_report(leaks_after)
                    )
                    issues = last_audit.get("issues", []) or []
                    for leak in leaks_after:
                        issues.append(
                            f"[entity_leak] '{leak['entity']}' 残留 {leak['count']} 次，必须改为 '{leak['expected']}'"
                        )
                    last_audit["issues"] = issues
                    # 标志位让修订环节强制修补
                    last_audit["needs_entity_fix"] = True
                else:
                    print("  硬替换完成，已无原名残留。")

        # --- 双向衔接校验 ---
        hook_matched = True
        if prev_chapter_end or next_chapter_start:
            # 内联提取开头/结尾，避免循环导入
            gen_lines = [l.rstrip() for l in current.splitlines() if l.strip()]
            gen_start = "\n".join(gen_lines[:5]) if gen_lines else ""
            gen_end = "\n".join(gen_lines[-5:]) if gen_lines else ""
            hook_matched = True
            if prev_chapter_end:
                overlap = _dice_similarity(_normalize_chinese(gen_start), _normalize_chinese(prev_chapter_end))
                if overlap < 0.15:
                    hook_matched = False
                    print(f"  双向衔接: 本章开头与上一章结尾衔接偏弱 (dice={overlap:.2f})")
            if next_chapter_start:
                continuity_issues = _next_anchor_conflict_issues(gen_end, next_chapter_start)
                if continuity_issues:
                    hook_matched = False
                    for issue, suggestion in continuity_issues:
                        print(f"  双向衔接: {issue}")
                        _append_audit_issue(last_audit, issue, suggestion)
                if continuity_issues and AUDIT_SKIP_LLM_CONTINUITY_ON_GUARD_FAIL:
                    last_audit["next_anchor_continuity"] = {
                        "score": 0,
                        "pass": False,
                        "issues": [issue for issue, _ in continuity_issues],
                        "suggestions": [suggestion for _, suggestion in continuity_issues],
                        "skipped_llm": True,
                    }
                    print("  双向衔接: 确定性守卫已命中，跳过 LLM 衔接复审以节省时间。")
                else:
                    continuity_report = evaluate_next_anchor_continuity(
                        gen_end,
                        next_chapter_start,
                        chapter_number,
                        model=analysis_model,
                    )
                    last_audit["next_anchor_continuity"] = continuity_report
                    if not continuity_report.get("pass", True):
                        hook_matched = False
                        report_score = continuity_report.get("score", 0)
                        print(f"  双向衔接结构化审计未通过: score={report_score}")
                        for issue in continuity_report.get("issues", []) or []:
                            _append_audit_issue(
                                last_audit,
                                f"[continuity] {issue}",
                                "按下一章开头重写本章结尾，确保对象、事件、主角位置和误会指向一致。",
                            )

        if passed and not hook_matched:
            print("  双向衔接未通过，本轮不计为通过")
            passed = False

        if passed:
            return {"passed": True, "content": current, "last_audit": last_audit}
        if plateau_detected and round_idx >= max_rounds:
            print("  Plateau: 已到最后一轮且硬门槛未通过，结束审计")
            break
        # 最后一轮仅差少量分数时，允许近阈值放行，避免长时间重跑后仍完全不落盘
        if (
            round_idx == max_rounds
            and not both_api_empty
            and score >= max(0, pass_threshold - AUDIT_NEAR_PASS_DELTA)
            and ai_trace_score >= ai_trace_hard_threshold
            and similarity_ok
            and plot_ok
            and hook_matched
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
                model=generation_model,
            )
            similarity_rewrite_used = True
            print("参考相似度过高，已执行一次剧情不变的表达降重重写。")
            continue

        # 将去 AI 味作为 ai_trace 维度的专属修订策略并入唯一审计循环
        if ENABLE_ANTI_AI_REWRITE:
            ai_trace_findings = last_audit.get("ai_trace_rule_issues", []) or []
            zhuque_sensitive_rules = {
                "镜头指令词过密",
                "短句阶梯铺陈",
                "角色标签说明过密",
                "口癖刷屏",
                "句长同质化",
                "段落等长",
                "段尾总结腔",
                "圆场解释腔过密",
            }
            needs_trace_rewrite = any(
                isinstance(item, dict) and item.get("rule") in zhuque_sensitive_rules
                for item in ai_trace_findings
            )
            if reference_text and not anti_ai_rewrite_used and (ai_trace_score < ai_trace_hard_threshold or needs_trace_rewrite):
                style_compare = compare_reference_and_generated(reference_text, current)
                current = anti_ai_rewrite_with_reference(
                    reference_text,
                    current,
                    style_compare,
                    chapter_number,
                    writing_style,
                    chapter_plan_text=chapter_plan_text,
                    ai_trace_findings=ai_trace_findings,
                    model=generation_model,
                )
                anti_ai_rewrite_used = True
                if ai_trace_score < ai_trace_hard_threshold:
                    print(
                        f"ai_trace 硬阈值未达标（{ai_trace_score} < {ai_trace_hard_threshold}），已执行一次参考文去模板化修订。"
                    )
                else:
                    print("命中朱雀高风险 AI 形态，已执行一次针对性去模板化修订。")
                continue
            elif reference_text and not passed:
                # 在总评未过但 ai_trace 达标时，保留一次轻量去模板化优化（避免误导为"未达标"）
                if ANTI_AI_REWRITE_ONLY_WHEN_BELOW_THRESHOLD:
                    print("ai_trace 已达硬阈值，跳过去模板化修订，直接按审计反馈定向修订。")
                else:
                    style_compare = compare_reference_and_generated(reference_text, current)
                    current = anti_ai_rewrite_with_reference(
                        reference_text,
                        current,
                        style_compare,
                        chapter_number,
                        writing_style,
                        chapter_plan_text=chapter_plan_text,
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
            current_focus_text=current_focus_text,
            focus_dimensions=_pick_focus_dimensions(last_audit.get("dimension_scores", {})),
            model=generation_model,
        )
    # 最终兜底: 审计 API 持续空响应时返回失败，不正式落盘。
    if best_version["score"] == 0 and len(audit_history.scores) >= 2:
        last_audit = best_version["audit"]
        last_audit["pass"] = False
        last_audit["issues"] = (last_audit.get("issues", []) or []) + [
            "[audit_empty] 审计 API 持续空响应，已拒绝正式落盘。"
        ]
        print("审计 API 持续空响应，拒绝正式落盘。")
        return {"passed": False, "content": best_version["content"], "last_audit": last_audit}
    return {"passed": False, "content": current, "last_audit": last_audit}
