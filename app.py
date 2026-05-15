import argparse
import os
import sys
import time # 引入 time 模块

# 导入新模块的功能
# 确保能找到同级目录的模块 (如果脚本不在项目根目录运行可能需要)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from config import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, STRICT_SOURCE_PLOT, ENTITY_REWRITE, INTER_CHAPTER_SLEEP, RUNTIME_DIR
from context_manager import load_story_context # 直接使用返回的上下文
from chapter_processor import process_chapter, preload_chapter_anchors


def pre_scan_entities_for_range(input_dir, start_chapter, end_chapter, force_reanalyze=False):
    """预扫描目标范围及下一章实体，保证跨章名称映射先于生成稳定下来。"""
    from entity_rewriter import (
        load_cached_entity_map,
        load_global_entity_map,
        save_global_entity_map,
        extract_entity_map_from_reference,
        merge_entity_maps,
        save_entity_map,
        flatten_entity_map,
    )
    from chapter_processor import read_chapter_file, reference_still_placeholder

    global_map = load_global_entity_map()
    scan_end = max(end_chapter, start_chapter) + 1
    print(f"\n--- 实体预扫描：第 {start_chapter} 到 {scan_end} 章（含下一章预览）---")
    scanned = 0
    reused = 0
    for ch in range(start_chapter, scan_end + 1):
        filepath = os.path.join(input_dir, f"{ch}.md")
        if not os.path.isfile(filepath):
            continue
        content = read_chapter_file(filepath)
        if not content or reference_still_placeholder(content, ch):
            continue

        cached = None if force_reanalyze else load_cached_entity_map(ch)
        if cached:
            global_map = merge_entity_maps(global_map, cached, chapter_number=ch)
            reused += 1
            continue

        print(f"  预扫描第 {ch} 章实体")
        chapter_map = extract_entity_map_from_reference(content, ch, existing_map=global_map)
        if chapter_map:
            save_entity_map(ch, chapter_map)
            global_map = merge_entity_maps(global_map, chapter_map, chapter_number=ch)
            flat = flatten_entity_map(chapter_map)
            print(f"    新增/确认 {sum(len(v) for v in flat.values())} 个实体映射")
        scanned += 1

    save_global_entity_map(global_map)
    print(f"实体预扫描完成：新扫描 {scanned} 章，复用缓存 {reused} 章。")

def main():
    start_time = time.time() # 记录开始时间
    parser = argparse.ArgumentParser(
        description=(
            "同结构改编：对照 input 目录同名参考章生成 output（保留结构功能，实体表达可改）。"
            "默认衔接 input 原作上一章并锁定本章结构骨架；STRICT_SOURCE_PLOT=0 或 --no_strict_structure_adaptation 可改为实验模式（output 衔接等）。"
        )
    )
    parser.add_argument("--input_dir", type=str, default=DEFAULT_INPUT_DIR, help="包含原始章节文件的目录")
    parser.add_argument("--output_dir", type=str, default=DEFAULT_OUTPUT_DIR, help="存放生成章节文件的目录")
    parser.add_argument("--start_chapter", type=int, default=None, help="要开始生成的起始章节号 (包含)")
    parser.add_argument("--end_chapter", type=int, default=None, help="要结束生成的章节号 (包含)")
    parser.add_argument("--chapter", type=int, default=None, help="只生成指定的单个章节号")
    parser.add_argument("--length", type=int, default=3000, help="期望生成章节的大致字数")
    parser.add_argument(
        "--strict_source_plot",
        action="store_true",
        help="兼容旧参数：显式开启严格结构适配（默认已开；与 STRICT_SOURCE_PLOT=1 同义）。",
    )
    parser.add_argument(
        "--strict_plot_fidelity",
        action="store_true",
        help="兼容旧参数：显式开启严格结构适配。",
    )
    parser.add_argument(
        "--strict_structure_adaptation",
        action="store_true",
        help="显式开启严格结构适配（推荐新参数名）。",
    )
    parser.add_argument(
        "--no_strict_source_plot",
        action="store_true",
        help="兼容旧参数：关闭严格结构适配（实验/自由改编用）。",
    )
    parser.add_argument(
        "--no_strict_plot_fidelity",
        action="store_true",
        help="兼容旧参数：关闭严格结构适配（实验/自由改编用）。",
    )
    parser.add_argument(
        "--no_strict_structure_adaptation",
        action="store_true",
        help="关闭严格结构适配：允许用 output 衔接、生成稿反写上下文（实验/自由改编用）。",
    )
    parser.add_argument(
        "--force_reanalyze",
        action="store_true",
        help="忽略 runtime 中缓存的风格分析、结构骨架和章节意图，重新调用 LLM 分析。",
    )
    parser.add_argument(
        "--analyze_only",
        action="store_true",
        help="只生成/复用风格分析、结构骨架和章节意图，不生成正文、不审计、不更新上下文。",
    )
    parser.add_argument(
        "--entity_rewrite",
        action="store_true",
        help="显式开启实体改写（默认已开；与 ENTITY_REWRITE=1 同义）。",
    )
    parser.add_argument(
        "--no_entity_rewrite",
        action="store_true",
        help="关闭实体改写：不再为参考章生成新名映射，正文沿用原作角色/地名。",
    )
    parser.add_argument(
        "--entity_preview",
        action="store_true",
        help="实体预演：只扫描所有参考章的实体名并打印全局映射表，不生成正文。确认映射无误后再正式跑。",
    )
    parser.add_argument(
        "--no_entity_prescan",
        action="store_true",
        help="关闭正式运行前的实体预扫描。默认会预扫目标章节及下一章，保证跨章新名一致。",
    )
    parser.add_argument(
        "--continue_on_failure",
        action="store_true",
        help="章节处理失败后仍继续后续章节。默认失败即停止，避免前章未落盘时生成后章。",
    )
    parser.add_argument(
        "--sleep", type=int, default=None,
        help=f"章节间等待秒数（默认 {INTER_CHAPTER_SLEEP}s，也可通过 INTER_CHAPTER_SLEEP 环境变量配置）。",
    )

    args = parser.parse_args()
    strict_source_plot = bool(STRICT_SOURCE_PLOT)
    if (
        getattr(args, "strict_source_plot", False)
        or getattr(args, "strict_plot_fidelity", False)
        or getattr(args, "strict_structure_adaptation", False)
    ):
        strict_source_plot = True
    if (
        getattr(args, "no_strict_source_plot", False)
        or getattr(args, "no_strict_plot_fidelity", False)
        or getattr(args, "no_strict_structure_adaptation", False)
    ):
        strict_source_plot = False

    entity_rewrite = bool(ENTITY_REWRITE)
    if getattr(args, "entity_rewrite", False):
        entity_rewrite = True
    if getattr(args, "no_entity_rewrite", False):
        entity_rewrite = False

    inter_chapter_sleep = args.sleep if args.sleep is not None else INTER_CHAPTER_SLEEP

    # 初始化：加载故事上下文
    initial_context = load_story_context()
    # load_story_context 现在保证返回一个有效的字典 (加载的或默认的)
    # 不再需要检查 initial_context 是否为 None，因为它总会返回一个字典
    last_processed_chapter = initial_context.get("last_generated_chapter", 0)
    print(f"当前上下文记录的最后处理章节为: {last_processed_chapter}")

    # 确定处理范围
    start_chapter = args.start_chapter
    end_chapter = args.end_chapter
    single_chapter = args.chapter

    if single_chapter is not None:
        start_chapter = single_chapter
        end_chapter = single_chapter
    elif start_chapter is None:
        # 如果未指定 start_chapter，则从上次处理的下一章开始
        start_chapter = last_processed_chapter + 1
        print(f"未指定起始章节，将从上一章的下一章开始: {start_chapter}")
        # 如果同时未指定 end_chapter, 查找输入目录确定最后一章
        if end_chapter is None:
            try:
                # 查找输入目录下的所有 .md 文件
                input_files = [f for f in os.listdir(args.input_dir) 
                               if os.path.isfile(os.path.join(args.input_dir, f)) and f.endswith('.md')]
                # 提取章节号并找到最大值
                chapter_numbers = []
                for f in input_files:
                    try:
                        chapter_num = int(os.path.splitext(f)[0])
                        chapter_numbers.append(chapter_num)
                    except ValueError:
                        continue # 忽略无法转换为整数的文件名
                
                if chapter_numbers:
                    end_chapter = max(chapter_numbers)
                    print(f"未指定结束章节，自动检测到输入目录最大章节号为: {end_chapter}")
                else:
                    print(f"警告: 未指定结束章节，且无法在输入目录 {args.input_dir} 中找到有效的章节文件，将只处理起始章节 {start_chapter}。")
                    end_chapter = start_chapter
            except FileNotFoundError:
                 print(f"警告: 未指定结束章节，且输入目录 {args.input_dir} 不存在，将只处理起始章节 {start_chapter}。")
                 end_chapter = start_chapter
            except Exception as e:
                 print(f"警告: 查找输入目录章节时出错 ({e})，将只处理起始章节 {start_chapter}。")
                 end_chapter = start_chapter
                 
    elif end_chapter is None:
        # 如果指定了 start 但没指定 end，则只处理 start 这一章
        print(f"警告: 未指定结束章节，将只处理起始章节 {start_chapter}。")
        end_chapter = start_chapter
        
    if start_chapter > end_chapter:
        print(f"错误：起始章节 ({start_chapter}) 不能大于结束章节 ({end_chapter})。")
        sys.exit(1)

    print(f"\n=== 开始处理章节范围: {start_chapter} 到 {end_chapter} ===")
    if strict_source_plot:
        print("模式: 同结构改编（衔接 input 原作、结构功能以结构骨架为准、不据生成稿反写设定）。")
    else:
        print("模式: 实验（非严格结构适配）：output 衔接与上下文反写已打开，输出可能偏离 input 参考结构。")
    if entity_rewrite:
        print("实体改写: 已开启（参考章角色/地名/事件/物件名全局换名，跨章一致）。")
    else:
        print("实体改写: 已关闭（正文将沿用原作实体名）。")
    if args.analyze_only:
        print("分析模式: 只产出 runtime 分析工件，不生成正文。")
    if args.force_reanalyze:
        print("重分析模式: 忽略 runtime 缓存，重新生成分析工件。")

    # --- 实体预演模式 ---
    if args.entity_preview:
        if not entity_rewrite:
            print("错误：--entity_preview 需要实体改写处于开启状态（不要同时传 --no_entity_rewrite）。")
            sys.exit(1)
        from entity_rewriter import (
            load_global_entity_map,
            save_global_entity_map,
            extract_entity_map_from_reference,
            merge_entity_maps,
            save_entity_map,
            flatten_entity_map,
            format_global_map_for_preview,
        )
        from chapter_processor import read_chapter_file, reference_still_placeholder
        global_map = load_global_entity_map()
        for ch in range(start_chapter, end_chapter + 1):
            filepath = os.path.join(args.input_dir, f"{ch}.md")
            if not os.path.isfile(filepath):
                print(f"  第 {ch} 章：文件不存在，跳过")
                continue
            content = read_chapter_file(filepath)
            if not content or reference_still_placeholder(content, ch):
                print(f"  第 {ch} 章：占位/空文件，跳过")
                continue
            print(f"\n--- 扫描第 {ch} 章实体 ---")
            chapter_map = extract_entity_map_from_reference(content, ch, existing_map=global_map)
            if chapter_map:
                save_entity_map(ch, chapter_map)
                global_map = merge_entity_maps(global_map, chapter_map, chapter_number=ch)
                flat = flatten_entity_map(chapter_map)
                new_count = sum(len(v) for v in flat.values())
                print(f"  本章扫描到 {new_count} 个实体")
        save_global_entity_map(global_map)
        print("\n" + format_global_map_for_preview(global_map))
        print("\n预演完成。确认映射无误后去掉 --entity_preview 正式运行。")
        print(f"全局映射已保存到: {os.path.join(RUNTIME_DIR, 'global_entity_map.json')}")
        print("如需手动修正，可直接编辑该文件后正式跑。")
        return

    if entity_rewrite and not getattr(args, "no_entity_prescan", False):
        pre_scan_entities_for_range(
            args.input_dir,
            start_chapter,
            end_chapter,
            force_reanalyze=args.force_reanalyze,
        )

    # --- 双向校验：预加载所有章节首尾锚点 ---
    chapter_anchors = preload_chapter_anchors(args.input_dir, start_chapter, end_chapter)

    # 循环处理指定范围的章节
    all_successful = True
    processed_count = 0
    total_chapters_in_range = end_chapter - start_chapter + 1

    for chapter_num in range(start_chapter, end_chapter + 1):
        chapter_start_time = time.time()
        success = process_chapter(
            chapter_num,
            args.input_dir,
            args.output_dir,
            args.length,
            strict_source_plot=strict_source_plot,
            force_reanalyze=args.force_reanalyze,
            analyze_only=args.analyze_only,
            chapter_anchors=chapter_anchors,
            entity_rewrite=entity_rewrite,
        )
        chapter_end_time = time.time()
        chapter_duration = chapter_end_time - chapter_start_time
        
        processed_count += 1
        progress_percent = (processed_count / total_chapters_in_range) * 100
        
        if not success:
            print(f"章节 {chapter_num} 处理失败。耗时: {chapter_duration:.2f} 秒. (进度: {progress_percent:.1f}%)")
            all_successful = False
            if not args.continue_on_failure:
                print("已停止后续章节处理：前序章节未成功落盘。若确需跳过失败章节继续，请显式传入 --continue_on_failure。")
                break
        else:
             print(f"章节 {chapter_num} 处理成功。耗时: {chapter_duration:.2f} 秒. (进度: {progress_percent:.1f}%)")
             if not args.analyze_only and inter_chapter_sleep > 0 and chapter_num < end_chapter:
                 print(f"等待 {inter_chapter_sleep} 秒后继续下一章…")
                 time.sleep(inter_chapter_sleep)

    print(f"\n=== 章节处理完成 ({start_chapter} 到 {end_chapter}) ===")
    end_time = time.time() # 记录结束时间
    total_duration = end_time - start_time

    if all_successful:
        print("所有指定章节处理成功完成。")
    else:
        print("部分章节处理失败。请检查以上日志获取详细信息。")
    
    print(f"总耗时: {total_duration:.2f} 秒")

if __name__ == "__main__":
    main()
