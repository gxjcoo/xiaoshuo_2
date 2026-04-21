import os
import re
import argparse

def chinese_to_arabic(chinese_num_str):
    chinese_num_map = {
        '零': 0,
        '一': 1,
        '二': 2,
        '三': 3,
        '四': 4,
        '五': 5,
        '六': 6,
        '七': 7,
        '八': 8,
        '九': 9,
        '两': 2,
    }
    unit_map = {
        '十': 10,
        '百': 100,
        '千': 1000,
        '万': 10000,
        '亿': 100000000,
    }
    total = 0
    current = 0
    for c in chinese_num_str:
        if c in unit_map:
            unit = unit_map[c]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        elif c in chinese_num_map:
            current += chinese_num_map[c]
        else:
            pass
    total += current
    return total

def process_filename(filename):
    match = re.match(r'^第(.+?)章', filename)
    if not match:
        return None
    chapter_num_str = match.group(1).strip()
    
    if chapter_num_str.isdigit():
        num = int(chapter_num_str)
    else:
        try:
            num = int(chapter_num_str)
        except ValueError:
            try:
                num = chinese_to_arabic(chapter_num_str)
            except:
                return None
    
    return f"{num}.md"

def main(dir_path):
    if not os.path.isdir(dir_path):
        print(f"错误：目录不存在: {dir_path}")
        return
    for filename in os.listdir(dir_path):
        if filename.endswith('.md'):
            new_name = process_filename(filename)
            if new_name:
                original_path = os.path.join(dir_path, filename)
                new_path = os.path.join(dir_path, new_name)
                if original_path != new_path:
                    try:
                        os.rename(original_path, new_path)
                        print(f"Renamed '{filename}' to '{new_name}'")
                    except Exception as e:
                        print(f"Error renaming {filename}: {str(e)}")
            else:
                print(f"Skipped file: {filename}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="将章节文件名中的中文序数等转为阿拉伯数字编号")
    parser.add_argument(
        "directory",
        nargs="?",
        default="chapters_out",
        help="要处理的目录（默认 chapters_out）",
    )
    args = parser.parse_args()
    main(args.directory)