import os
import re
import argparse

def natural_sort_key(s):
    """Helper function for natural sorting (e.g., 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]

def combine_chapters(input_dir, output_file):
    """Combines markdown chapter files from input_dir into output_file."""
    
    if not os.path.isdir(input_dir):
        print(f"错误：输入目录 '{input_dir}' 不存在或不是一个目录。")
        return

    try:
        # 获取目录中所有的 .md 文件
        files = [f for f in os.listdir(input_dir) if f.endswith('.md')]
        
        # 按文件名进行自然排序
        files.sort(key=natural_sort_key)
        
        if not files:
            print(f"错误：在目录 '{input_dir}' 中未找到 .md 文件。")
            return

        print(f"找到 {len(files)} 个章节文件，将合并到 '{output_file}'...")

        with open(output_file, 'w', encoding='utf-8') as outfile:
            for i, filename in enumerate(files):
                filepath = os.path.join(input_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(content)
                        # 在每个文件内容后添加两个换行符作为分隔
                        if i < len(files) - 1: # 不在最后一个文件后添加
                            outfile.write("\n\n") 
                    print(f"  - 已添加: {filename}")
                except Exception as e:
                    print(f"警告：读取文件 '{filepath}' 时出错: {e}")

        print(f"合并完成！结果已保存至 '{output_file}'")

    except Exception as e:
        print(f"合并过程中发生错误: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="将目录内章节 .md 按文件名自然序合并为一个文件")
    parser.add_argument(
        "input_dir",
        help="章节所在目录（内含 1.md、2.md …）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="combined.md",
        help="合并输出文件路径（默认 combined.md）",
    )
    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir_path = args.input_dir if os.path.isabs(args.input_dir) else os.path.join(script_dir, args.input_dir)
    output_filepath = args.output if os.path.isabs(args.output) else os.path.join(script_dir, args.output)
    combine_chapters(input_dir_path, output_filepath)
