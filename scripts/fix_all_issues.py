#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量修复所有已发现的问题：
1. 三尺青锋替换错误 (保留独立"三尺青锋"和"三尺青锋客")
2. 重复文本模式
3. 标题修复
4. 名称不一致
5. 冯啸舟自称"袁某"
6. 标题格式修复
"""

import os
import re
from pathlib import Path

OUTPUT_DIR = Path("output_chapters")

def fix_sanchi_qingfeng_errors(content):
    """修复三尺青锋替换错误，保留独立"三尺青锋"和"三尺青锋客"角色名"""
    
    # 优先级从高到低替换（先匹配更长的模式）
    replacements = [
        # 多字组合模式（必须先处理）
        ('青锋灵三尺青锋', '青锋灵剑'),
        ('青锋三尺青锋柄', '青锋剑柄'),
        # "X三尺青锋"模式（X+剑的组合）
        ('玄三尺青锋', '玄剑'),
        ('道三尺青锋', '道剑'),
        ('灵三尺青锋', '灵剑'),
        ('一三尺青锋', '一剑'),
        # "三尺青锋X"模式（剑+X的组合）
        ('三尺青锋身', '剑身'),
        ('三尺青锋光', '剑光'),
        ('三尺青锋鸣', '剑鸣'),
        ('三尺青锋意', '剑意'),
        ('三尺青锋鞘', '剑鞘'),
        ('三尺青锋脊', '剑脊'),
        ('三尺青锋罡', '剑罡'),
        ('三尺青锋芒', '剑芒'),
        ('三尺青锋气', '剑气'),
        ('三尺青锋诀', '剑诀'),
        ('三尺青锋法', '剑法'),
        ('三尺青锋术', '剑术'),
        ('三尺青锋道', '剑道'),
        ('三尺青锋客', '剑客'),
        ('三尺青锋修', '剑修'),
        ('三尺青锋灵', '剑灵'),
        ('三尺青锋阵', '剑阵'),
        ('三尺青锋招', '剑招'),
        ('三尺青锋式', '剑式'),
        ('三尺青锋势', '剑势'),
        ('三尺青锋力', '剑力'),
        ('三尺青锋速', '剑速'),
        ('三尺青锋锋', '剑锋'),
        ('三尺青锋刃', '剑刃'),
        ('三尺青锋柄', '剑柄'),
    ]
    
    result = content
    for old, new in replacements:
        result = result.replace(old, new)
    
    return result

def fix_duplicate_text_patterns(content):
    """修复所有已知的重复文本模式"""
    
    # 重复模式修复映射 - 使用 (X){2,} 匹配X重复2次及以上
    duplicate_fixes = [
        # 2字词重复2+次
        (r'(同门){2,}', '同门'),
        (r'(神异){2,}', '神异'),
        (r'(龙之){2,}', '龙之'),
        (r'(之争){2,}', '之争'),
        (r'(天地){2,}', '天地'),
        (r'(乾坤){2,}', '天地'),
        (r'(精华){2,}', '精华'),
        (r'(黑衣){2,}', '黑衣'),
        (r'(白衣){2,}', '白衣'),
        (r'(青锋){2,}', '青锋'),
        (r'(灵气){2,}', '灵气'),
        (r'(剑气){2,}', '剑气'),
        (r'(道法){2,}', '道法'),
        (r'(夜夜){2,}', '夜夜'),
        # 尾部单字重复（如 悬赏金金 → 悬赏金）
        (r'悬赏金金+', '悬赏金'),
        (r'龙心丹丹+', '龙心丹'),
        # 含重复的复合词
        (r'龙血精华精华+', '龙血精华'),
        (r'地地+基石', '地基石'),
    ]
    
    result = content
    for pattern, replacement in duplicate_fixes:
        # 多次替换以处理嵌套情况
        for _ in range(5):
            new_result = re.sub(pattern, replacement, result)
            if new_result == result:
                break
            result = new_result
    
    return result

def fix_title(content, chapter_num):
    """修复标题问题"""
    lines = content.split('\n')
    if not lines:
        return content
    
    first_line = lines[0]
    
    # 修复标题中的重复字符
    title_match = re.match(r'(# 第\d+章\s+)(.*)', first_line)
    if title_match:
        prefix = title_match.group(1)
        title = title_match.group(2)
        
        # 修复标题中的重复
        original_title = title
        title = re.sub(r'夜夜夜夜+', '夜夜', title)
        title = re.sub(r'神异神异+', '神异', title)
        title = re.sub(r'龙之龙之+', '龙之', title)
        title = re.sub(r'同门同门+', '同门', title)
        title = re.sub(r'之争之争+', '之争', title)
        title = re.sub(r'天地天地+', '天地', title)
        title = re.sub(r'乾坤乾坤+', '天地', title)
        title = re.sub(r'精华精华+', '精华', title)
        
        if title != original_title:
            lines[0] = prefix + title
            content = '\n'.join(lines)
            print(f"  修复标题: '{original_title}' → '{title}'")
    
    return content

def fix_title_format(content, chapter_num):
    """修复标题格式（中文数字→阿拉伯数字等）"""
    lines = content.split('\n')
    if not lines:
        return content
    
    first_line = lines[0].strip()
    
    # 中文数字映射
    cn_to_arabic = {
        '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
        '六': '6', '七': '7', '八': '8', '九': '9', '十': '10',
        '十一': '11', '十二': '12', '十三': '13', '十四': '14', '十五': '15',
        '十六': '16', '十七': '17', '十八': '18', '十九': '19', '二十': '20',
        '二十一': '21', '二十二': '22', '二十三': '23', '二十四': '24', '二十五': '25',
        '二十六': '26', '二十七': '27', '二十八': '28', '二十九': '29', '三十': '30',
        '三十一': '31', '三十二': '32', '三十三': '33', '三十四': '34', '三十五': '35',
        '三十六': '36', '三十七': '37', '三十八': '38', '三十九': '39', '四十': '40',
        '四十一': '41', '四十二': '42', '四十三': '43', '四十四': '44', '四十五': '45',
        '四十六': '46', '四十七': '47', '四十八': '48', '四十九': '49', '五十': '50',
        '五十一': '51', '五十二': '52', '五十三': '53', '五十四': '54', '五十五': '55',
        '五十六': '56', '五十七': '57', '五十八': '58', '五十九': '59', '六十': '60',
        '六十一': '61', '六十二': '62', '六十三': '63', '六十四': '64', '六十五': '65',
        '六十六': '66', '六十七': '67', '六十八': '68', '六十九': '69', '七十': '70',
        '七十一': '71', '七十二': '72', '七十三': '73', '七十四': '74', '七十五': '75',
        '七十六': '76', '七十七': '77', '七十八': '78', '七十九': '79', '八十': '80',
        '八十一': '81', '八十二': '82', '八十三': '83', '八十四': '84', '八十五': '85',
        '八十六': '86', '八十七': '87', '八十八': '88', '八十九': '89', '九十': '90',
        '九十一': '91', '九十二': '92', '九十三': '93', '九十四': '94', '九十五': '95',
        '九十六': '96', '九十七': '97', '九十八': '98', '九十九': '99', '一百': '100',
    }
    
    # 检查是否为中文数字标题格式 "第七十章 ..."
    cn_pattern = re.match(r'第([\u4e00-\u9fa5]+)章\s+(.*)', first_line)
    if cn_pattern:
        cn_num = cn_pattern.group(1)
        rest = cn_pattern.group(2)
        if cn_num in cn_to_arabic:
            arabic_num = cn_to_arabic[cn_num]
            new_title = f"# 第{arabic_num}章 {rest}"
            lines[0] = new_title
            content = '\n'.join(lines)
            print(f"  修复标题格式: '{first_line}' → '{new_title}'")
    
    return content

def fix_name_inconsistencies(content):
    """修复名称不一致问题"""
    # 白虹道观 → 清虚观
    if '白虹道观' in content:
        content = content.replace('白虹道观', '清虚观')
        print("  修复名称: '白虹道观' → '清虚观'")
    
    return content

def fix_character_self_reference(content, chapter_num):
    """修复冯啸舟自称错误"""
    # 袁某 → 冯某（冯啸舟的自称）
    # 只在冯啸舟出现的章节中修复
    if '冯啸舟' in content or '冯道兄' in content or '袁道兄' in content:
        original = content
        
        # 袁某 → 冯某
        content = content.replace('袁某', '冯某')
        # 袁道兄 → 冯道兄
        content = content.replace('袁道兄', '冯道兄')
        
        if content != original:
            count_yuan = original.count('袁某') + original.count('袁道兄')
            print(f"  修复自称: '袁某/袁道兄' → '冯某/冯道兄' ({count_yuan} 处)")
    
    return content

def fix_single_chapter(chapter_num):
    """修复单个章节文件"""
    filepath = OUTPUT_DIR / f"{chapter_num}.md"
    if not filepath.exists():
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  读取错误: {e}")
        return False
    
    original_content = content
    changes = []
    
    # 1. 修复三尺青锋替换错误
    content = fix_sanchi_qingfeng_errors(content)
    
    # 2. 修复重复文本
    content = fix_duplicate_text_patterns(content)
    
    # 3. 修复标题
    content = fix_title(content, chapter_num)
    
    # 4. 修复标题格式
    content = fix_title_format(content, chapter_num)
    
    # 5. 修复名称不一致
    content = fix_name_inconsistencies(content)
    
    # 6. 修复角色自称
    content = fix_character_self_reference(content, chapter_num)
    
    # 如果有修改，写回文件
    if content != original_content:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"  写入错误: {e}")
            return False
    
    return False

def main():
    """主函数"""
    print("=" * 60)
    print("批量修复所有已发现的问题")
    print("=" * 60)
    print()
    
    if not OUTPUT_DIR.exists():
        print("错误：output_chapters目录不存在")
        return
    
    fixed_files = []
    error_files = []
    
    for i in range(1, 101):
        filepath = OUTPUT_DIR / f"{i}.md"
        if not filepath.exists():
            continue
        
        print(f"处理第{i}章...")
        
        try:
            if fix_single_chapter(i):
                fixed_files.append(i)
                print(f"  [OK] 已修复")
            else:
                print(f"  [--] 无需修改")
        except Exception as e:
            error_files.append((i, str(e)))
            print(f"  [ERR] 错误: {e}")
    
    print()
    print("=" * 60)
    print("修复完成")
    print("=" * 60)
    print(f"已修复文件数: {len(fixed_files)}")
    print(f"错误文件数: {len(error_files)}")
    
    if fixed_files:
        print(f"\n已修复的章节: {', '.join(map(str, fixed_files))}")
    
    if error_files:
        print(f"\n错误的章节:")
        for ch, err in error_files:
            print(f"  第{ch}章: {err}")
    
    # 保存修复日志
    log_file = "fix_log.txt"
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write("批量修复日志\n")
        f.write("=" * 60 + "\n")
        f.write(f"修复时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"已修复文件数: {len(fixed_files)}\n")
        f.write(f"错误文件数: {len(error_files)}\n\n")
        
        f.write("已修复章节列表:\n")
        for ch in fixed_files:
            f.write(f"  第{ch}章\n")
        
        if error_files:
            f.write("\n错误章节列表:\n")
            for ch, err in error_files:
                f.write(f"  第{ch}章: {err}\n")
    
    print(f"\n修复日志已保存到: {log_file}")

if __name__ == "__main__":
    main()