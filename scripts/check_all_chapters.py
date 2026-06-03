#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面检查所有输出章节文件的问题
"""

import os
import re
import sys
from pathlib import Path

def check_chapter_file(filepath):
    """检查单个章节文件的问题"""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return [{"type": "读取错误", "message": str(e)}]
    
    filename = os.path.basename(filepath)
    chapter_num = filename.replace('.md', '')
    
    # 1. 检查标题格式
    lines = content.split('\n')
    if lines:
        first_line = lines[0].strip()
        if not first_line.startswith('# 第') or '章' not in first_line:
            issues.append({
                "type": "标题格式",
                "message": f"第一行不是标准标题格式: {first_line[:50]}..."
            })
        
        # 检查标题中的重复模式
        title_match = re.match(r'# 第\d+章\s+(.+)', first_line)
        if title_match:
            title = title_match.group(1)
            # 检查标题中的重复字符
            for pattern in ['神异', '夜夜', '天地', '乾坤', '精华', '青锋', '剑气', '道法']:
                if pattern * 2 in title:
                    issues.append({
                        "type": "标题重复",
                        "message": f"标题中包含重复模式 '{pattern}': {title}"
                    })
    
    # 2. 检查"三尺青锋"替换错误
    # 匹配错误的替换模式：三尺青锋后面跟着本应属于"剑"的字
    sword_error_patterns = [
        (r'三尺青锋身', '剑身'),
        (r'三尺青锋光', '剑光'),
        (r'三尺青锋鸣', '剑鸣'),
        (r'三尺青锋意', '剑意'),
        (r'三尺青锋鞘', '剑鞘'),
        (r'三尺青锋脊', '剑脊'),
        (r'三尺青锋罡', '剑罡'),
        (r'三尺青锋芒', '剑芒'),
        (r'三尺青锋气', '剑气'),
        (r'三尺青锋诀', '剑诀'),
        (r'三尺青锋法', '剑法'),
        (r'三尺青锋术', '剑术'),
        (r'三尺青锋道', '剑道'),
        (r'三尺青锋客', '剑客'),
        (r'三尺青锋修', '剑修'),
        (r'三尺青锋灵', '剑灵'),
        (r'三尺青锋阵', '剑阵'),
        (r'三尺青锋招', '剑招'),
        (r'三尺青锋式', '剑式'),
        (r'三尺青锋势', '剑势'),
        (r'三尺青锋力', '剑力'),
        (r'三尺青锋速', '剑速'),
        (r'三尺青锋锋', '剑锋'),
        (r'三尺青锋刃', '剑刃'),
        (r'一三尺青锋', '一剑'),
        (r'玄三尺青锋', '玄剑'),
        (r'道三尺青锋', '道剑'),
        (r'青锋灵三尺青锋', '青锋灵剑'),
        (r'青锋三尺青锋柄', '青锋剑柄'),
        (r'三尺青锋柄', '剑柄'),
        (r'灵三尺青锋', '灵剑'),
    ]
    
    for error_pattern, correct in sword_error_patterns:
        matches = re.findall(error_pattern, content)
        if matches:
            issues.append({
                "type": "三尺青锋替换错误",
                "message": f"发现 '{error_pattern}' 应为 '{correct}'，出现 {len(matches)} 次",
                "pattern": error_pattern,
                "replacement": correct,
                "count": len(matches)
            })
    
    # 3. 检查重复文本模式
    duplicate_patterns = [
        # 悬赏金重复
        (r'悬赏金金+', '悬赏金'),
        # 龙心丹重复
        (r'龙心丹丹+', '龙心丹'),
        # 龙血精华重复
        (r'龙血精华精华+', '龙血精华'),
        # 同门师姐重复
        (r'同门同门+', '同门'),
        # 地基石重复
        (r'地地+基石', '地基石'),
        # 之争重复
        (r'之争之争+', '之争'),
        # 龙之重复
        (r'龙之龙之+', '龙之'),
        # 神异重复
        (r'神异神异+', '神异'),
        # 夜夜重复
        (r'夜夜夜夜+', '夜夜'),
        # 天地重复
        (r'天地天地+', '天地'),
        # 乾坤重复
        (r'乾坤乾坤+', '乾坤'),
        # 精华重复
        (r'精华精华+', '精华'),
    ]
    
    for pattern, correct in duplicate_patterns:
        matches = re.findall(pattern, content)
        if matches:
            issues.append({
                "type": "重复文本",
                "message": f"发现重复模式 '{pattern}' 应为 '{correct}'，出现 {len(matches)} 次",
                "pattern": pattern,
                "replacement": correct,
                "count": len(matches)
            })
    
    # 4. 检查冯啸舟自称"袁某"
    if '袁某' in content:
        # 检查上下文是否与冯啸舟相关
        yuan_matches = re.findall(r'冯啸舟.*?袁某|袁某.*?冯啸舟', content, re.DOTALL)
        if not yuan_matches:
            # 如果没有直接关联，检查章节是否涉及冯啸舟
            if '冯啸舟' in content:
                issues.append({
                    "type": "角色自称错误",
                    "message": "冯啸舟自称'袁某'，应为'冯某'",
                    "pattern": "袁某",
                    "replacement": "冯某"
                })
    
    # 5. 检查"白虹道观" vs "清虚观"不一致
    if '白虹道观' in content:
        issues.append({
            "type": "名称不一致",
            "message": "使用了'白虹道观'，应为'清虚观'",
            "pattern": "白虹道观",
            "replacement": "清虚观"
        })
    
    # 6. 检查修订说明（虽然已修复，但再确认一下）
    revision_patterns = [
        r'[（(]修订说明[：:][^）)]*[）)]',
        r'[（(]修改说明[：:][^）)]*[）)]',
        r'[（(]修正说明[：:][^）)]*[）)]',
        r'[（(]修订记录[：:][^）)]*[）)]',
    ]
    
    for pattern in revision_patterns:
        matches = re.findall(pattern, content)
        if matches:
            issues.append({
                "type": "修订说明",
                "message": f"发现修订说明: {matches[0][:30]}..."
            })
    
    return issues

def main():
    """主函数"""
    output_dir = Path("output_chapters")
    if not output_dir.exists():
        print("错误：output_chapters目录不存在")
        return
    
    # 收集所有问题
    all_issues = {}
    total_files = 0
    files_with_issues = 0
    
    # 按类别统计问题统计
    issue_stats = {}
    
    for i in range(1, 101):
        filepath = output_dir / f"{i}.md"
        if not filepath.exists():
            continue
        
        total_files += 1
        issues = check_chapter_file(filepath)
        
        if issues:
            files_with_issues += 1
            all_issues[str(i)] = issues
            
            # 统计问题类型
            for issue in issues:
                issue_type = issue["type"]
                if issue_type not in issue_stats:
                    issue_stats[issue_type] = {"count": 0, "files": []}
                issue_stats[issue_type]["count"] += 1
                if str(i) not in issue_stats[issue_type]["files"]:
                    issue_stats[issue_type]["files"].append(str(i))
    
    # 输出统计摘要
    print("=" * 60)
    print("章节文件全面检查报告")
    print("=" * 60)
    print(f"检查文件总数: {total_files}")
    print(f"存在问题文件数: {files_with_issues}")
    print(f"无问题文件数: {total_files - files_with_issues}")
    print()
    
    # 输出问题类型统计
    print("问题类型统计:")
    print("-" * 40)
    for issue_type, stats in sorted(issue_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        print(f"{issue_type}: {stats['count']} 个文件")
        # 显示前5个文件
        files_str = ", ".join(stats["files"][:5])
        if len(stats["files"]) > 5:
            files_str += f" 等共 {len(stats['files'])} 个文件"
        print(f"  涉及文件: {files_str}")
    print()
    
    # 输出详细报告（按问题类型）
    print("详细问题报告:")
    print("=" * 60)
    
    # 按问题类型分组显示
    for issue_type in issue_stats:
        print(f"\n【{issue_type}】")
        print("-" * 40)
        
        # 收集该类型的所有问题
        type_issues = {}
        for chapter, issues in all_issues.items():
            for issue in issues:
                if issue["type"] == issue_type:
                    if chapter not in type_issues:
                        type_issues[chapter] = []
                    type_issues[chapter].append(issue)
        
        # 按章节号排序显示
        for chapter in sorted(type_issues.keys(), key=lambda x: int(x)):
            chapter_issues = type_issues[chapter]
            print(f"第{chapter}章:")
            for issue in chapter_issues:
                print(f"  - {issue['message']}")
    
    # 生成修复建议
    print("\n" + "=" * 60)
    print("修复建议:")
    print("=" * 60)
    
    if "三尺青锋替换错误" in issue_stats:
        print("1. 【三尺青锋替换错误】需要批量修复")
        print("   建议：创建修复脚本，将错误的三尺青锋替换为正确的剑相关词汇")
        print("   注意：保留'三尺青锋'作为独立名词和'三尺青锋客'作为角色名")
    
    if "重复文本" in issue_stats:
        print("2. 【重复文本】需要批量修复")
        print("   建议：更新fix_duplicate_text()函数的映射表，添加新发现的重复模式")
    
    if "角色自称错误" in issue_stats:
        print("3. 【角色自称错误】需要手动修复")
        print("   建议：检查冯啸舟自称'袁某'的上下文，改为'冯某'")
    
    if "名称不一致" in issue_stats:
        print("4. 【名称不一致】需要手动修复")
        print("   建议：将'白虹道观'统一改为'清虚观'")
    
    if "标题重复" in issue_stats:
        print("5. 【标题重复】需要手动修复")
        print("   建议：修复标题中的重复字符")
    
    # 保存报告到文件
    report_file = "chapter_check_report.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("章节文件全面检查报告\n")
        f.write("=" * 60 + "\n")
        f.write(f"检查时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"检查文件总数: {total_files}\n")
        f.write(f"存在问题文件数: {files_with_issues}\n")
        f.write(f"无问题文件数: {total_files - files_with_issues}\n\n")
        
        f.write("问题类型统计:\n")
        f.write("-" * 40 + "\n")
        for issue_type, stats in sorted(issue_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            f.write(f"{issue_type}: {stats['count']} 个文件\n")
            files_str = ", ".join(stats["files"][:10])
            if len(stats["files"]) > 10:
                files_str += f" 等共 {len(stats['files'])} 个文件"
            f.write(f"  涉及文件: {files_str}\n")
        
        f.write("\n详细问题列表:\n")
        f.write("=" * 60 + "\n")
        for chapter in sorted(all_issues.keys(), key=lambda x: int(x)):
            issues = all_issues[chapter]
            f.write(f"\n第{chapter}章:\n")
            for issue in issues:
                f.write(f"  - [{issue['type']}] {issue['message']}\n")
    
    print(f"\n详细报告已保存到: {report_file}")

if __name__ == "__main__":
    main()