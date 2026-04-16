import os
import json

# 从其他模块导入所需函数和常量
from config import (
    CHAPTER_SPECS_DIR,
    RUNTIME_DIR,
    MAX_RUNTIME_CHAPTER_ARTIFACTS,
    MAX_RUNTIME_INTENT_CHARS,
    MAX_RUNTIME_CONTEXT_SNAPSHOT_BYTES,
)
from context_manager import get_current_context, update_story_context_after_chapter
from ai_handler import (
    analyze_writing_style,
    plan_chapter_with_ai,
    generate_chapter_content,
    audit_and_revise_chapter_once,
    reduce_ai_flavor_with_loop,
)
from domain_spec_loader import (
    load_story_domain_text,
    load_chapter_spec_text,
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

def write_chapter_file(filepath, content):
    """将内容写入章节文件"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"章节已写入: {filepath}")
    except Exception as e:
        print(f"写入文件 {filepath} 时出错: {e}")


def write_runtime_artifacts(chapter_number, chapter_plan_text, current_context, trace_data):
    """写入 runtime 工件，便于排查“为什么这样写”。"""
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        intent_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.intent.md")
        context_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.context.json")
        trace_path = os.path.join(RUNTIME_DIR, f"chapter-{chapter_number:04d}.trace.json")

        intent_text = (chapter_plan_text or "")
        if len(intent_text) > MAX_RUNTIME_INTENT_CHARS:
            intent_text = intent_text[:MAX_RUNTIME_INTENT_CHARS] + "\n\n…（intent 已截断）"
        with open(intent_path, "w", encoding="utf-8") as f:
            f.write(intent_text)

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
            if not (name.endswith(".intent.md") or name.endswith(".context.json") or name.endswith(".trace.json")):
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

def process_chapter(chapter_number, input_dir, output_dir, length):
    """处理单个章节：读取、分析风格、生成、保存、分析上下文、更新上下文"""
    print(f"\n--- 处理章节 {chapter_number} ---")
    input_filepath = os.path.join(input_dir, f"{chapter_number}.md")
    output_filepath = os.path.join(output_dir, f"{chapter_number}.md")

    if not ensure_input_chapter_ready(chapter_number, input_dir, input_filepath):
        return False

    # 1. 读取原始或上一章节内容 (用于风格分析和续写参考)
    # 优先读取输入目录的原始文件用于风格分析
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

    # 获取上一章节的输出内容用于续写参考 (如果不是第一章)
    previous_chapter_content = None
    if chapter_number > 1:
        prev_output_filepath = os.path.join(output_dir, f"{chapter_number - 1}.md")
        if os.path.exists(prev_output_filepath):
             print(f"读取上一章节输出参考: {prev_output_filepath}")
             previous_chapter_content = read_chapter_file(prev_output_filepath)
        else:
             print(f"警告：未找到上一章节 {prev_output_filepath} 的输出文件，将不提供续写参考。")

    # 2. 分析写作风格 (基于原始章节)
    writing_style = analyze_writing_style(original_content)
    if not writing_style:
        print("错误：无法分析写作风格，使用默认风格 '幽默吐槽'。")
        writing_style = "幽默吐槽" # 提供一个回退
    else:
        print(f"分析得到的风格: {writing_style}")

    # 3. 获取当前上下文
    current_context = get_current_context()

    domain_text = load_story_domain_text()
    chapter_spec_text = load_chapter_spec_text(chapter_number)
    author_intent_text = load_author_intent_text()
    current_focus_text = load_current_focus_text()
    if domain_text:
        print("已加载领域圣经 (story_domain/*.md) 并注入生成提示。")
    if chapter_spec_text:
        print(f"已加载本章规格: chapter_specs/{chapter_number}.md")
    elif os.path.isdir(CHAPTER_SPECS_DIR):
        print(f"提示: 未找到 {CHAPTER_SPECS_DIR}/{chapter_number}.md，本章将仅依据上下文与风格生成。")
    if author_intent_text:
        print("已加载作者长期意图: author_intent.md")
    if current_focus_text:
        print("已加载近期焦点: current_focus.md")

    # 4. 先做本章意图规划，再生成正文
    chapter_plan_text = plan_chapter_with_ai(
        current_context,
        chapter_number,
        previous_chapter_content=previous_chapter_content,
        chapter_spec_text=chapter_spec_text,
        author_intent_text=author_intent_text,
        current_focus_text=current_focus_text,
    )
    if chapter_plan_text:
        print("本章意图规划完成，将用于约束正文生成焦点。")
    else:
        print("警告：本章意图规划失败，将按原有路径直接生成正文。")

    new_chapter_content = generate_chapter_content(
        current_context,
        writing_style,
        length,
        previous_chapter_content,
        target_chapter_number=chapter_number,
        domain_text=domain_text,
        chapter_spec_text=chapter_spec_text,
        chapter_plan_text=chapter_plan_text,
        author_intent_text=author_intent_text,
        current_focus_text=current_focus_text,
    )
    if not new_chapter_content:
        print(f"错误：未能生成章节 {chapter_number} 的内容，跳过此章节。")
        return False # 表示处理失败

    # 5. 审校并自动修订一次（必要时）
    new_chapter_content = audit_and_revise_chapter_once(
        new_chapter_content,
        chapter_number,
        writing_style,
        chapter_plan_text=chapter_plan_text,
        domain_text=domain_text,
        chapter_spec_text=chapter_spec_text,
        author_intent_text=author_intent_text,
        current_focus_text=current_focus_text,
    )

    # 5.5 对比原文与生成文，执行去模板化重写循环（降低 AI 味）
    new_chapter_content = reduce_ai_flavor_with_loop(
        reference_text=original_content,
        chapter_content=new_chapter_content,
        chapter_number=chapter_number,
        writing_style=writing_style,
        chapter_plan_text=chapter_plan_text,
        domain_text=domain_text,
        chapter_spec_text=chapter_spec_text,
    )

    # 写出 runtime 工件（intent/context/trace）
    write_runtime_artifacts(
        chapter_number,
        chapter_plan_text,
        current_context,
        {
            "chapter": chapter_number,
            "has_domain_text": bool(domain_text),
            "has_chapter_spec_text": bool(chapter_spec_text),
            "has_author_intent": bool(author_intent_text),
            "has_current_focus": bool(current_focus_text),
            "reference_file": input_filepath,
            "output_file": output_filepath,
        },
    )
    cleanup_runtime_artifacts()

    # 6. 写入新章节文件
    write_chapter_file(output_filepath, new_chapter_content)

    # 7. 更新并保存故事上下文（内部会完成 AI 上下文分析）
    # 即使 AI 分析失败，也仍会更新章节号与章节结尾摘要
    update_story_context_after_chapter(chapter_number, new_chapter_content)

    print(f"章节 {chapter_number} 处理完成。")
    return True # 表示处理成功
