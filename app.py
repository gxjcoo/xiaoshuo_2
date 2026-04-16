import argparse
import os
import sys
import time # 引入 time 模块

# 导入新模块的功能
# 确保能找到同级目录的模块 (如果脚本不在项目根目录运行可能需要)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from config import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR
from context_manager import load_story_context # 直接使用返回的上下文
from chapter_processor import process_chapter

def main():
    start_time = time.time() # 记录开始时间
    parser = argparse.ArgumentParser(description="使用 AI 根据现有章节续写小说")
    parser.add_argument("--input_dir", type=str, default=DEFAULT_INPUT_DIR, help="包含原始章节文件的目录")
    parser.add_argument("--output_dir", type=str, default=DEFAULT_OUTPUT_DIR, help="存放生成章节文件的目录")
    parser.add_argument("--start_chapter", type=int, default=None, help="要开始生成的起始章节号 (包含)")
    parser.add_argument("--end_chapter", type=int, default=None, help="要结束生成的章节号 (包含)")
    parser.add_argument("--chapter", type=int, default=None, help="只生成指定的单个章节号")
    parser.add_argument("--length", type=int, default=3000, help="期望生成章节的大致字数")
    
    args = parser.parse_args()

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

    # 循环处理指定范围的章节
    all_successful = True
    processed_count = 0
    total_chapters_in_range = end_chapter - start_chapter + 1

    for chapter_num in range(start_chapter, end_chapter + 1):
        chapter_start_time = time.time()
        success = process_chapter(chapter_num, 
                                  args.input_dir, 
                                  args.output_dir, 
                                  args.length)
        chapter_end_time = time.time()
        chapter_duration = chapter_end_time - chapter_start_time
        
        processed_count += 1
        progress_percent = (processed_count / total_chapters_in_range) * 100
        
        if not success:
            print(f"章节 {chapter_num} 处理失败。耗时: {chapter_duration:.2f} 秒. (进度: {progress_percent:.1f}%)")
            all_successful = False
            # 决定是否中断
            # break # 如果希望失败时中断
        else:
             print(f"章节 {chapter_num} 处理成功。耗时: {chapter_duration:.2f} 秒. (进度: {progress_percent:.1f}%)")
             time.sleep(30)

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
