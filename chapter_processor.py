import os
import json

# 从其他模块导入所需函数和常量
from config import DEFAULT_OUTPUT_DIR
from context_manager import get_current_context, update_story_context_after_chapter
from ai_handler import analyze_writing_style, generate_chapter_content, analyze_context_with_ai

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

def process_chapter(chapter_number, input_dir, output_dir, length):
    """处理单个章节：读取、分析风格、生成、保存、分析上下文、更新上下文"""
    print(f"\n--- 处理章节 {chapter_number} ---")
    input_filepath = os.path.join(input_dir, f"{chapter_number}.md")
    output_filepath = os.path.join(output_dir, f"{chapter_number}.md")

    # 1. 读取原始或上一章节内容 (用于风格分析和续写参考)
    # 优先读取输入目录的原始文件用于风格分析
    print(f"读取原始章节: {input_filepath}")
    original_content = read_chapter_file(input_filepath)
    if not original_content:
        print(f"错误：无法读取原始章节 {input_filepath}，跳过此章节。")
        return False # 表示处理失败
        
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

    # 4. 生成新章节内容
    new_chapter_content = generate_chapter_content(current_context, 
                                                   writing_style, 
                                                   length,
                                                   previous_chapter_content,
                                                   target_chapter_number=chapter_number)
    if not new_chapter_content:
        print(f"错误：未能生成章节 {chapter_number} 的内容，跳过此章节。")
        return False # 表示处理失败

    # 5. 写入新章节文件
    write_chapter_file(output_filepath, new_chapter_content)

    # 6. 使用 AI 分析新章节内容以更新上下文
    ai_analysis_result = analyze_context_with_ai(current_context, new_chapter_content)

    # 7. 更新并保存故事上下文
    # 注意：即使 AI 分析失败 (ai_analysis_result is None)，我们仍然需要更新章节号和摘要
    # 传递完整的章节内容，让update_story_context_after_chapter函数提取正确的结尾摘要
    update_story_context_after_chapter(chapter_number, new_chapter_content)

    print(f"章节 {chapter_number} 处理完成。")
    return True # 表示处理成功
