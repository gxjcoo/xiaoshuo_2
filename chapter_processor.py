import os
import json
from typing import Tuple, Dict, Any

# 新增模块导入
from outline_extractor import extract_structured_outline_from_reference
from structured_types import ChapterOutline
from entity_rewriter import (
    extract_entity_map_from_reference,
    load_cached_entity_map,
    save_entity_map,
    apply_entity_rewrite,
    detect_original_entity_leaks,
    format_entity_leak_report,
)

# 从其他模块导入所需函数和常量
from config import (
    RUNTIME_DIR,
    STORY_DOMAIN_DIR,
    AUTO_UPDATE_DOMAIN_KNOWLEDGE,
    AUDIT_RULES_FILE,
    AUDIT_MAX_REVISE_ROUNDS,
    MAX_RUNTIME_CHAPTER_ARTIFACTS,
    MAX_RUNTIME_INTENT_CHARS,
    MAX_RUNTIME_CONTEXT_SNAPSHOT_BYTES,
    MAX_DOMAIN_STRICT_CHARS,
    MAX_AUTHOR_STRICT_CHARS,
    MAX_FOCUS_STRICT_CHARS,
)
from context_manager import get_current_context, update_story_context_after_chapter
from ai_handler import (
    analyze_writing_style,
    plan_chapter_with_ai,
    generate_chapter_content,
    extract_plot_outline_from_reference,
)
from audit_pipeline import audit_and_revise_until_pass
from knowledge_sync import extract_domain_updates
from domain_spec_loader import (
    load_story_domain_text,
    load_author_intent_text,
    load_current_focus_text,
)

REFERENCE_STUB_TEMPLATE = """# 第{chapter}章 参考稿占位

请在本文件中写入第 {chapter} 章的**参考原文**（或用作文风范本的文字），建议不少于 500 字，保存后重新运行程序。

本段为程序自动生成的占位说明，替换为正文前请勿期待生成质量。
"""

# 用于判断用户是否仍使用自动占位（未写入真实参考正文）
STUB_SENTINEL = "程序自动生成的占位说明"


def reference_still_placeholder(content, chapter_number):
    """若仍是自动生成的占位稿，或几乎为空，则视为未就绪。"""
    if content is None:
        return True
    s = content.strip()
    if not s:
        return True
    if STUB_SENTINEL in s:
        return True
    if s == REFERENCE_STUB_TEMPLATE.format(chapter=chapter_number).strip():
        return True
    return False


def ensure_input_chapter_ready(chapter_number, input_dir, input_filepath):
    """若输入目录或参考 .md 不存在，则自动创建；新建占位文件后返回 False（本回合不调用 API）。"""
    try:
        if not os.path.isdir(input_dir):
            os.makedirs(input_dir, exist_ok=True)
            print(f"提示: 已自动创建输入目录: {os.path.abspath(input_dir)}")
    except OSError as e:
        print(f"错误: 无法创建输入目录 {input_dir}: {e}")
        return False

    if os.path.isfile(input_filepath):
        return True

    try:
        with open(input_filepath, "w", encoding="utf-8") as f:
            f.write(REFERENCE_STUB_TEMPLATE.format(chapter=chapter_number))
        print(f"提示: 未找到参考文件，已自动生成占位: {os.path.abspath(input_filepath)}")
        print("      本次不会调用 API。请用编辑器打开该文件，把占位说明整段换成你的参考正文（建议≥500字），保存后再运行同一命令。")
    except OSError as e:
        print(f"错误: 无法创建参考文件 {input_filepath}: {e}")
    return False


def read_chapter_file(filepath):
    """读取章节文件内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"错误：未找到文件 {filepath}")
        return None
    except Exception as e:
        print(f"读取文件 {filepath} 时出错: {e}")
        return None


def get_chapter_start_end(chapter_content: str, lines_count: int = 5) -> Tuple[str, str]:
    """
    获取章节的开头和结尾（默认各5行）
    返回：(开头文本, 结尾文本)
    """
    if not chapter_content:
        return "", ""
    lines = [line.rstrip() for line in chapter_content.splitlines() if line.strip()]
    if not lines:
        return "", ""
    start = "\n".join(lines[:min(lines_count, len(lines))])
    end = "\n".join(lines[-min(lines_count, len(lines)):])
    return start, end


def preload_chapter_anchors(input_dir: str, start_chapter: int, end_chapter: int) -> Dict[int, Dict[str, str]]:
    """
    预加载所有章节的首尾锚点，用于双向衔接校验
    返回：{章节号: {"start": 开头文本, "end": 结尾文本}}
    """
    anchors = {}
    print(f"正在预加载章节 {start_chapter} 到 {end_chapter} 的首尾锚点...")
    for ch in range(start_chapter, end_chapter + 1):
        filepath = os.path.join(input_dir, f"{ch}.md")
        if not os.path.isfile(filepath):
            continue
        content = read_chapter_file(filepath)
        if not content:
            continue
        start, end = get_chapter_start_end(content)
        anchors[ch] = {
            "start": start,
            "end": end,
        }
    print(f"已预加载 {len(anchors)} 个章节的首尾锚点")
    return anchors

def write_chapter_file(filepath, content):
    """将内容写入章节文件"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"章节已写入: {filepath}")
    except Exception as e:
        print(f"写入文件 {filepath} 时出错: {e}")


def load_recent_output_chapters(output_dir, chapter_number, window=5):
    """读取最近 window 章已生成正文，用于跨章重复/同构检测。"""
    texts = []
    start = max(1, chapter_number - window)
    for ch in range(start, chapter_number):
        p = os.path.join(output_dir, f"{ch}.md")
        if not os.path.isfile(p):
            continue
        content = read_chapter_file(p)
        if content and content.strip():
            texts.append(content)
    return texts


def _runtime_path(chapter_number, suffix):
    return os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.{suffix}")


def _read_runtime_text(chapter_number, suffix):
    path = _runtime_path(chapter_number, suffix)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _write_runtime_text(chapter_number, suffix, text):
    if not text:
        return
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(_runtime_path(chapter_number, suffix), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"警告：写入 runtime 文本工件失败 ({suffix}): {e}")


def load_cached_outline(chapter_number):
    path = _runtime_path(chapter_number, "outline.json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        if isinstance(parsed, dict) and "raw_outline" in parsed:
            return str(parsed.get("raw_outline") or "").strip()
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except Exception:
        return ""


def write_runtime_outline(chapter_number, reference_plot_outline):
    """单独落盘结构骨架，便于生成失败时也能排查抽取质量。"""
    if not reference_plot_outline:
        return
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        outline_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.outline.json")
        try:
            parsed = json.loads(reference_plot_outline)
        except Exception:
            parsed = {"raw_outline": reference_plot_outline}
        with open(outline_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告：写入结构骨架 runtime 工件失败: {e}")


def write_runtime_artifacts(
    chapter_number,
    chapter_plan_text,
    current_context,
    trace_data,
    reference_plot_outline="",
    writing_style="",
):
    """写入 runtime 工件，便于排查“为什么这样写”。"""
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        intent_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.intent.md")
        context_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.context.json")
        trace_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.trace.json")
        outline_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.outline.json")

        intent_text = (chapter_plan_text or "")
        if len(intent_text) > MAX_RUNTIME_INTENT_CHARS:
            intent_text = intent_text[:MAX_RUNTIME_INTENT_CHARS] + "\n\n…（intent 已截断）"
        with open(intent_path, "w", encoding="utf-8") as f:
            f.write(intent_text)
        if writing_style:
            _write_runtime_text(chapter_number, "style.md", writing_style)

        # context 快照降载：超限时只保留高价值字段
        snapshot = current_context
        snapshot_bytes = len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))
        if snapshot_bytes > MAX_RUNTIME_CONTEXT_SNAPSHOT_BYTES:
            snapshot = {
                "last_generated_chapter": current_context.get("last_generated_chapter", 0),
                "recent_plot_summary": current_context.get("recent_plot_summary", ""),
                "recent_chapter_summaries": current_context.get("recent_chapter_summaries", [])[-6:],
                "pending_hooks": current_context.get("pending_hooks", [])[-12:],
                "volume_summaries": current_context.get("volume_summaries", [])[-3:],
                "core_characters": current_context.get("core_characters", [])[-20:],
                "core_items": current_context.get("core_items", [])[-20:],
            }
        with open(context_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)
        if reference_plot_outline:
            try:
                parsed_outline = json.loads(reference_plot_outline)
            except Exception:
                parsed_outline = {"raw_outline": reference_plot_outline}
            with open(outline_path, "w", encoding="utf-8") as f:
                json.dump(parsed_outline, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告：写入 runtime 工件失败: {e}")


def cleanup_runtime_artifacts():
    """仅保留最近 N 章 runtime 工件，避免 runtime 目录无限增长。"""
    try:
        if not os.path.isdir(RUNTIME_DIR):
            return
        files = []
        for name in os.listdir(RUNTIME_DIR):
            if not name.startswith("chapter-"):
                continue
            if not (
                name.endswith(".intent.md")
                or name.endswith(".context.json")
                or name.endswith(".trace.json")
                or name.endswith(".outline.json")
                or name.endswith(".style.md")
            ):
                continue
            prefix = name.split(".", 1)[0]  # chapter-0001
            try:
                chapter_num = int(prefix.split("-")[1])
            except Exception:
                continue
            files.append((chapter_num, name))

        if not files:
            return
        keep_from = max(1, max(ch for ch, _ in files) - MAX_RUNTIME_CHAPTER_ARTIFACTS + 1)
        for chapter_num, name in files:
            if chapter_num < keep_from:
                try:
                    os.remove(os.path.join(RUNTIME_DIR, name))
                except OSError:
                    pass
    except Exception as e:
        print(f"警告：清理 runtime 工件失败: {e}")


def load_audit_rules():
    """加载审计规则，缺失或异常时回退默认规则。"""
    default_rules = {
        "pass_threshold": 85,
        "deterministic_penalty_cap_total": 12,
        "deterministic_penalty_cap_ai_trace": 10,
        "ai_trace_hard_threshold": 80,
        "max_revise_rounds": AUDIT_MAX_REVISE_ROUNDS,
        "dimensions": [
            {"id": "continuity", "name": "连贯性", "weight": 0.3, "requirements": ["剧情衔接自然", "设定不冲突"]},
            {"id": "pacing", "name": "节奏", "weight": 0.2, "requirements": ["本章有推进", "节奏不过慢"]},
            {"id": "ai_trace", "name": "AI痕迹", "weight": 0.3, "requirements": ["减少模板句式", "减少总结腔"]},
            {"id": "voice", "name": "文风", "weight": 0.2, "requirements": ["风格一致", "对话有区分"]},
        ],
    }
    if not os.path.isfile(AUDIT_RULES_FILE):
        return default_rules
    try:
        with open(AUDIT_RULES_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return default_rules
        loaded.setdefault("pass_threshold", default_rules["pass_threshold"])
        loaded.setdefault("deterministic_penalty_cap_total", 12)
        loaded.setdefault("deterministic_penalty_cap_ai_trace", 10)
        loaded.setdefault("ai_trace_hard_threshold", default_rules["ai_trace_hard_threshold"])
        loaded.setdefault("max_revise_rounds", default_rules["max_revise_rounds"])
        loaded.setdefault("dimensions", default_rules["dimensions"])
        return loaded
    except Exception as e:
        print(f"警告：加载审计规则失败，回退默认规则: {e}")
        return default_rules


def build_audit_requirements_for_writing(audit_rules, top_k=6, strict_imitation=False):
    """将审计规则转为写作前约束，提升首稿命中率。

    strict_imitation: 仅取权重最高的少量维度、每条只保留首条要求，减轻提示「清单感」以降低 AI 腔。
    """
    dimensions = audit_rules.get("dimensions", [])
    if not isinstance(dimensions, list) or not dimensions:
        return ""
    if strict_imitation:
        top_k = min(top_k, 3)
    ranked = sorted(
        [d for d in dimensions if isinstance(d, dict)],
        key=lambda d: float(d.get("weight", 0)),
        reverse=True,
    )[:max(1, top_k)]
    lines = []
    for dim in ranked:
        name = dim.get("name") or dim.get("id", "未命名维度")
        reqs = dim.get("requirements", [])
        if not isinstance(reqs, list) or not reqs:
            continue
        if strict_imitation:
            req_text = str(reqs[0]).strip() if reqs else ""
        else:
            req_text = "；".join(str(r).strip() for r in reqs if str(r).strip())
        if req_text:
            lines.append(f"- {name}：{req_text}")
    return "\n".join(lines)


def _append_unique_lines(path, title, lines):
    """将增量行追加到文件末尾，做简单去重。"""
    if not lines:
        return
    existing = ""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = ""
    to_add = [ln for ln in lines if ln and ln not in existing]
    if not to_add:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {title}\n")
            for ln in to_add:
                f.write(f"- {ln}\n")
    except Exception as e:
        print(f"警告：写入领域增量失败 {path}: {e}")


def auto_update_domain_knowledge(chapter_number, chapter_content, current_context):
    """自动更新 story_domain 增量。"""
    updates = extract_domain_updates(chapter_content, current_context)
    _append_unique_lines(
        os.path.join(STORY_DOMAIN_DIR, "01-glossary.md"),
        f"自动增量（来源：第{chapter_number}章）",
        updates.get("glossary", []),
    )
    _append_unique_lines(
        os.path.join(STORY_DOMAIN_DIR, "02-world.md"),
        f"自动增量（来源：第{chapter_number}章）",
        updates.get("world", []),
    )
    _append_unique_lines(
        os.path.join(STORY_DOMAIN_DIR, "03-characters.md"),
        f"自动增量（来源：第{chapter_number}章）",
        updates.get("characters", []),
    )
    _append_unique_lines(
        os.path.join(STORY_DOMAIN_DIR, "04-voice.md"),
        f"自动增量（来源：第{chapter_number}章）",
        updates.get("voice", []),
    )

def _load_reference_chapter_from_input(input_dir, chapter_number):
    """读取 input 目录中指定章参考正文；占位或缺失时返回 None。"""
    path = os.path.join(input_dir, f"{chapter_number}.md")
    if not os.path.isfile(path):
        return None
    content = read_chapter_file(path)
    if not content or reference_still_placeholder(content, chapter_number):
        return None
    return content


def process_chapter(
    chapter_number,
    input_dir,
    output_dir,
    length,
    strict_source_plot=True,
    force_reanalyze=False,
    analyze_only=False,
    chapter_anchors=None,
    entity_rewrite=False,
):
    """同结构改编单章：对照 input/{n}.md 生成 output/{n}.md（保留结构功能，实体表达可改）。

    strict_source_plot: True（默认）时衔接 input 原作上一章、规划/生成锁定结构骨架、
    不把生成稿反写进 story_context / 不写 story_domain 自动增量。False 时为实验模式。

    chapter_anchors: 预加载的所有章节首尾锚点 {ch: {"start": "...", "end": "..."}}
        用于双向校验，确保本开头衔接上一章结尾、本结尾衔接下一章开头。
    """
    # 提取双向锚点：上一章结尾 + 下一章开头
    prev_chapter_end = ""
    next_chapter_start = ""
    if isinstance(chapter_anchors, dict):
        prev = chapter_anchors.get(chapter_number - 1)
        if prev and isinstance(prev, dict):
            prev_chapter_end = prev.get("end", "")
        next_ch = chapter_anchors.get(chapter_number + 1)
        if next_ch and isinstance(next_ch, dict):
            next_chapter_start = next_ch.get("start", "")
    if prev_chapter_end:
        print(f"已加载上一章结尾锚点 (第 {chapter_number - 1} 章)，用于双向衔接校验")
    if next_chapter_start:
        print(f"已加载下一章开头锚点 (第 {chapter_number + 1} 章)，用于双向衔接校验")

    print(f"\n--- 处理章节 {chapter_number}（同结构改编） ---")
    input_filepath = os.path.join(input_dir, f"{chapter_number}.md")
    output_filepath = os.path.join(output_dir, f"{chapter_number}.md")

    if not ensure_input_chapter_ready(chapter_number, input_dir, input_filepath):
        return False

    # 1. 读取 input 参考章（风格锚点 + 情节真值；非「另写一章」的自由创作）
    print(f"读取原始章节: {input_filepath}")
    original_content = read_chapter_file(input_filepath)
    if not original_content:
        if not os.path.isfile(input_filepath):
            print(
                f"错误：未找到参考章节文件: {input_filepath}\n"
                f"      该目录下需要有与章节号同名的 .md（如 1.md），供风格分析与剧情参照。"
            )
        else:
            print(f"错误：参考文件为空或无法读取 {input_filepath}，跳过此章节。")
        return False # 表示处理失败

    if reference_still_placeholder(original_content, chapter_number):
        print(
            f"提示: 参考文件仍是占位内容，尚未替换为真实正文: {os.path.abspath(input_filepath)}\n"
            "      请删除占位段落，粘贴/写入至少数百字的参考章节后再运行；出现本提示时不会调用 API。"
        )
        return False

    reference_plot_outline = ""
    structured_outline = None  # 新增：结构化骨架
    if not force_reanalyze:
        reference_plot_outline = load_cached_outline(chapter_number)
        if reference_plot_outline:
            print(f"已复用缓存结构骨架: {_runtime_path(chapter_number, 'outline.json')}")
            # 尝试加载结构化骨架（如果存在）
            try:
                structured_path = _runtime_path(chapter_number, "structured_outline.json")
                if os.path.isfile(structured_path):
                    with open(structured_path, "r", encoding="utf-8") as f:
                        structured_data = json.load(f)
                        structured_outline = ChapterOutline.from_dict(structured_data)
                        print(f"已复用结构化骨架，包含 {len(structured_outline.scenes)} 个场景节点")
            except Exception as e:
                print(f"读取结构化骨架缓存失败: {e}")
    if not reference_plot_outline or not structured_outline:
        # 提取传统骨架（原有逻辑）
        reference_plot_outline = extract_plot_outline_from_reference(
            original_content,
            chapter_number,
            strict_source_plot=strict_source_plot,
        )
        if reference_plot_outline:
            print("已从参考章抽取结构骨架，正文生成将基于骨架改编以降低相似度。")
            write_runtime_outline(chapter_number, reference_plot_outline)
        # 新增：提取结构化骨架
        structured_outline = extract_structured_outline_from_reference(
            original_content,
            chapter_number,
            strict_source_plot=strict_source_plot,
        )
        if structured_outline:
            # 保存结构化骨架
            try:
                os.makedirs(RUNTIME_DIR, exist_ok=True)
                structured_path = _runtime_path(chapter_number, "structured_outline.json")
                with open(structured_path, "w", encoding="utf-8") as f:
                    json.dump(structured_outline.to_dict(), f, ensure_ascii=False, indent=2)
                print(f"已保存结构化骨架到: {structured_path}")
            except Exception as e:
                print(f"保存结构化骨架失败: {e}")
    if not reference_plot_outline:
        print("警告：结构骨架抽取失败，正文生成将使用极短参考结构兜底。")
    if not structured_outline:
        print("提示：结构化骨架抽取失败，将继续使用原有流程。")

    previous_chapter_content = None
    next_chapter_preview = _load_reference_chapter_from_input(input_dir, chapter_number + 1) or ""
    if next_chapter_preview:
        print(f"已加载下一章开头作为结尾连续性约束: {os.path.join(input_dir, f'{chapter_number + 1}.md')}")
    if chapter_number > 1:
        if strict_source_plot:
            prev_ref = _load_reference_chapter_from_input(input_dir, chapter_number - 1)
            if prev_ref:
                previous_chapter_content = prev_ref
                print(
                    f"同结构改编衔接：使用 input 原作上一章 {os.path.join(input_dir, f'{chapter_number - 1}.md')}"
                )
            else:
                print(
                    f"警告：未找到可用 input 原作上一章 {chapter_number - 1}.md，"
                    f"将回退为 output 已生成稿衔接（可能与参考原作不一致，建议补全 input）。"
                )
        if previous_chapter_content is None:
            prev_output_filepath = os.path.join(output_dir, f"{chapter_number - 1}.md")
            if os.path.exists(prev_output_filepath):
                print(f"读取上一章 output 衔接: {prev_output_filepath}")
                previous_chapter_content = read_chapter_file(prev_output_filepath)
            else:
                print(f"警告：未找到上一章 output {prev_output_filepath}，无衔接片段。")

    # 2. 分析写作风格 (基于原始章节)
    writing_style = "" if force_reanalyze else _read_runtime_text(chapter_number, "style.md")
    if writing_style:
        print(f"已复用缓存风格分析: {_runtime_path(chapter_number, 'style.md')}")
    else:
        writing_style = analyze_writing_style(original_content)
        if writing_style:
            _write_runtime_text(chapter_number, "style.md", writing_style)
    if not writing_style:
        print("错误：无法分析写作风格，使用默认风格 '幽默吐槽'。")
        writing_style = "幽默吐槽" # 提供一个回退
    else:
        print(f"分析得到的风格: {writing_style}")

    # 3. 获取当前上下文
    current_context = get_current_context()
    if strict_source_plot and int(current_context.get("last_generated_chapter", 0) or 0) >= chapter_number:
        current_context = json.loads(json.dumps(current_context, ensure_ascii=False))
        current_context["last_generated_chapter"] = chapter_number - 1
        current_context["recent_plot_summary"] = ""
        summaries = current_context.get("recent_chapter_summaries", [])
        if isinstance(summaries, list):
            current_context["recent_chapter_summaries"] = [
                item for item in summaries
                if not isinstance(item, dict) or int(item.get("chapter", 0) or 0) < chapter_number
            ]
        print("严格结构适配：重跑当前/已生成章节时，已忽略该章及之后的生成态摘要。")
    audit_rules = load_audit_rules()
    audit_requirements_text = build_audit_requirements_for_writing(
        audit_rules, strict_imitation=strict_source_plot
    )

    if strict_source_plot:
        domain_text = load_story_domain_text(max_chars=MAX_DOMAIN_STRICT_CHARS)
        author_intent_text = load_author_intent_text(max_chars=MAX_AUTHOR_STRICT_CHARS)
        current_focus_text = load_current_focus_text(max_chars=MAX_FOCUS_STRICT_CHARS)
    else:
        domain_text = load_story_domain_text()
        author_intent_text = load_author_intent_text()
        current_focus_text = load_current_focus_text()
    if domain_text:
        print("已加载领域圣经 (story_domain/*.md) 并注入生成提示。")
    if author_intent_text:
        print("已加载作者长期意图: author_intent.md")
    if current_focus_text:
        print("已加载近期焦点: current_focus.md")

    # 4. 先做本章意图规划，再生成正文
    chapter_plan_text = "" if force_reanalyze else _read_runtime_text(chapter_number, "intent.md")
    if chapter_plan_text:
        print(f"已复用缓存章节意图: {_runtime_path(chapter_number, 'intent.md')}")
    else:
        chapter_plan_text = plan_chapter_with_ai(
            current_context,
            chapter_number,
            previous_chapter_content=previous_chapter_content,
            next_chapter_preview=next_chapter_preview,
            author_intent_text=author_intent_text,
            current_focus_text=current_focus_text,
            reference_chapter_text=original_content,
            strict_source_plot=strict_source_plot,
        )
        if chapter_plan_text:
            _write_runtime_text(chapter_number, "intent.md", chapter_plan_text)
    if chapter_plan_text:
        print("本章意图规划完成，将用于约束正文生成焦点。")
    else:
        print("警告：本章意图规划失败，将按原有路径直接生成正文。")

    if analyze_only:
        print(
            f"分析模式完成：已准备第 {chapter_number} 章的风格分析、结构骨架与章节意图；"
            "未生成正文、未执行审计、未更新故事上下文。"
        )
        return True

    # --- 实体改写：扫描参考章 → 生成映射 → 替换骨架中的实体名 ---
    entity_map = {}
    if entity_rewrite:
        entity_map = load_cached_entity_map(chapter_number)
        if not entity_map or force_reanalyze:
            entity_map = extract_entity_map_from_reference(original_content, chapter_number)
            if entity_map:
                save_entity_map(chapter_number, entity_map)
                print(f"已生成实体改写映射: {len(entity_map.get('characters', {}))} 角色, "
                      f"{len(entity_map.get('places', {}))} 地点, "
                      f"{len(entity_map.get('events', {}))} 事件, "
                      f"{len(entity_map.get('objects_animals', {}))} 物件")
        if entity_map and reference_plot_outline:
            reference_plot_outline = apply_entity_rewrite(reference_plot_outline, entity_map)
            print("已将实体映射应用到结构骨架")

    new_chapter_content = generate_chapter_content(
        current_context,
        writing_style,
        length,
        previous_chapter_content,
        next_chapter_preview,
        target_chapter_number=chapter_number,
        domain_text=domain_text,
        chapter_plan_text=chapter_plan_text,
        author_intent_text=author_intent_text,
        current_focus_text=current_focus_text,
        audit_requirements_text=audit_requirements_text,
        reference_chapter_text=original_content,
        reference_plot_outline=reference_plot_outline,
        strict_source_plot=strict_source_plot,
        prev_chapter_end=prev_chapter_end,
        next_chapter_start=next_chapter_start,
        entity_rewrite=entity_rewrite,
        entity_map=entity_map,
    )
    if not new_chapter_content:
        print(f"错误：未能生成章节 {chapter_number} 的内容，跳过此章节。")
        return False # 表示处理失败

    # 5. 按规则审计并循环修订（含 ai_trace 专属去模板化策略），达标才允许落盘
    recent_chapter_texts = load_recent_output_chapters(output_dir, chapter_number, window=5)
    audit_gate_result = audit_and_revise_until_pass(
        new_chapter_content,
        chapter_number,
        writing_style,
        audit_rules,
        recent_chapter_texts=recent_chapter_texts,
        reference_text=original_content,
        reference_plot_outline=reference_plot_outline,
        chapter_plan_text=chapter_plan_text,
        domain_text=domain_text,
        author_intent_text=author_intent_text,
        current_focus_text=current_focus_text,
        prev_chapter_end=prev_chapter_end,
        next_chapter_start=next_chapter_start,
        entity_rewrite=entity_rewrite,
        entity_map=entity_map,
    )
    if not audit_gate_result.get("passed", False):
        score = audit_gate_result.get("last_audit", {}).get("total_score", 0)
        threshold = audit_rules.get("pass_threshold", 85)
        print(f"章节 {chapter_number} 审计未达标（{score} < {threshold}），本次不落盘。")
        return False

    # 写出 runtime 工件（intent/context/trace）
    write_runtime_artifacts(
        chapter_number,
        chapter_plan_text,
        current_context,
        {
            "chapter": chapter_number,
            "strict_source_plot": bool(strict_source_plot),
            "has_domain_text": bool(domain_text),
            "has_author_intent": bool(author_intent_text),
            "has_current_focus": bool(current_focus_text),
            "audit_score": audit_gate_result.get("last_audit", {}).get("total_score", 0),
            "audit_passed": bool(audit_gate_result.get("passed", False)),
            "has_reference_plot_outline": bool(reference_plot_outline),
            "reference_file": input_filepath,
            "output_file": output_filepath,
        },
        reference_plot_outline=reference_plot_outline,
        writing_style=writing_style,
    )
    cleanup_runtime_artifacts()

    # 7. 写入新章节文件
    write_chapter_file(output_filepath, new_chapter_content)

    # 8. 更新并保存故事上下文（内部会完成 AI 上下文分析）
    # 即使 AI 分析失败，也仍会更新章节号与章节结尾摘要
    update_story_context_after_chapter(
        chapter_number,
        new_chapter_content,
        strict_source_plot=strict_source_plot,
    )

    # 9. 自动同步 story_domain 增量
    if AUTO_UPDATE_DOMAIN_KNOWLEDGE and not strict_source_plot:
        latest_context = get_current_context()
        auto_update_domain_knowledge(chapter_number, new_chapter_content, latest_context)
    elif AUTO_UPDATE_DOMAIN_KNOWLEDGE and strict_source_plot:
        print("严格跟原作：跳过 story_domain 自动增量。")

    print(f"章节 {chapter_number} 处理完成。")
    return True # 表示处理成功
