import json
import os
import datetime
import copy

# 从 config 模块导入相关常量
from config import CONTEXT_FILE, PRUNED_ARCHIVE_FILE, MAX_CONTEXT_BYTES, DEFAULT_CONTEXT
from ai_handler import analyze_context_with_ai

# 全局变量，存储当前加载的故事上下文
story_context = {}

def load_story_context():
    """加载故事上下文"""
    global story_context
    if not os.path.exists(CONTEXT_FILE):
        print(f"警告: 故事上下文文件 {CONTEXT_FILE} 未找到。将创建新的上下文文件并使用默认值。")
        # Initialize with default context (use deepcopy to avoid modifying the constant)
        story_context = copy.deepcopy(DEFAULT_CONTEXT)
        # Immediately save to create the file
        save_story_context() 
        print(f"已创建并保存默认故事上下文到: {CONTEXT_FILE}")
        return story_context 
    else:
        try:
            with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
                story_context = json.load(f)
            print(f"成功加载故事上下文: {CONTEXT_FILE}")
            # Ensure essential keys exist after loading, using defaults if missing
            for key, default_value in DEFAULT_CONTEXT.items():
                story_context.setdefault(key, copy.deepcopy(default_value))
            return story_context
        except Exception as e:
            print(f"加载故事上下文文件 {CONTEXT_FILE} 时出错: {e}。将使用默认上下文。")
            # Initialize with default context if loading failed
            story_context = copy.deepcopy(DEFAULT_CONTEXT)
            return story_context

def save_story_context():
    """保存故事上下文，并在需要时同步修剪旧条目到存档文件以控制大小"""
    global story_context
    removed_items_archive = {
        "protagonist_info": {"key_items_abilities": [], "key_relationships": {}},
        "world_setting": {"key_elements": []}
    } 
    total_removed_count = 0

    try:
        # 循环修剪直到大小符合要求
        while True:
            current_bytes = len(json.dumps(story_context, ensure_ascii=False).encode('utf-8'))
            if current_bytes <= MAX_CONTEXT_BYTES:
                break 

            items_pruned_this_iteration = 0
            
            # 尝试从 key_items_abilities 删除
            abilities_list = story_context.get('protagonist_info', {}).get('key_items_abilities', [])
            if abilities_list:
                removed_ability = abilities_list.pop(0)
                removed_items_archive["protagonist_info"]["key_items_abilities"].append(removed_ability)
                items_pruned_this_iteration += 1

            # 尝试从 key_relationships 删除 (删除第一个键值对)
            relationships_dict = story_context.get('protagonist_info', {}).get("key_relationships", {})
            if relationships_dict:
                # 获取第一个键 (字典在 Python 3.7+ 保持插入顺序)
                first_key = next(iter(relationships_dict))
                removed_relation_value = relationships_dict.pop(first_key)
                removed_items_archive["protagonist_info"]["key_relationships"][first_key] = removed_relation_value
                items_pruned_this_iteration += 1
                
            # 尝试从 key_elements 删除
            elements_list = story_context.get('world_setting', {}).get('key_elements', [])
            if elements_list:
                removed_element = elements_list.pop(0)
                removed_items_archive["world_setting"]["key_elements"].append(removed_element)
                items_pruned_this_iteration += 1

            if items_pruned_this_iteration == 0:
                print("警告：上下文大小超限，但所有可修剪列表/字典均已为空，无法进一步减小。")
                break 
                
            total_removed_count += items_pruned_this_iteration
            # 重新计算大小，继续循环判断

        # --- 如果有条目被删除，则更新存档文件 --- 
        if total_removed_count > 0:
            print(f"上下文大小超过 {MAX_CONTEXT_BYTES} 字节，已同步修剪 {total_removed_count} 个条目。")
            try:
                # 加载现有存档或初始化
                existing_archive = {"protagonist_info": {"key_items_abilities": [], "key_relationships": {}}, "world_setting": {"key_elements": []}}
                if os.path.exists(PRUNED_ARCHIVE_FILE):
                    with open(PRUNED_ARCHIVE_FILE, 'r', encoding='utf-8') as af:
                        try:
                            loaded_archive = json.load(af)
                            # 简单验证结构，不是列表，且包含顶级键
                            if isinstance(loaded_archive, dict) and "protagonist_info" in loaded_archive and "world_setting" in loaded_archive:
                                existing_archive = loaded_archive
                            else:
                                print(f"警告：存档文件 {PRUNED_ARCHIVE_FILE} 格式不符合预期，将使用空结构重新创建。")
                        except json.JSONDecodeError:
                            print(f"警告：存档文件 {PRUNED_ARCHIVE_FILE} 格式错误，将使用空结构重新创建。")
                
                # 合并本次删除的条目到现有存档
                # 合并 abilities
                existing_archive["protagonist_info"].setdefault("key_items_abilities", []).extend(
                    removed_items_archive["protagonist_info"]["key_items_abilities"])
                # 合并 relationships (更新字典)
                existing_archive["protagonist_info"].setdefault("key_relationships", {}).update(
                    removed_items_archive["protagonist_info"]["key_relationships"])
                # 合并 elements
                existing_archive["world_setting"].setdefault("key_elements", []).extend(
                    removed_items_archive["world_setting"]["key_elements"])

                # 写回存档文件
                with open(PRUNED_ARCHIVE_FILE, 'w', encoding='utf-8') as af:
                    json.dump(existing_archive, af, ensure_ascii=False, indent=4)
                print(f"已将被删除的 {total_removed_count} 个条目信息合并到存档文件 {PRUNED_ARCHIVE_FILE}")

            except Exception as archive_e:
                print(f"写入或合并存档文件 {PRUNED_ARCHIVE_FILE} 时出错: {archive_e}")
            # --- 存档逻辑结束 ---

        # 保存（可能已修剪的）上下文到主文件
        with open(CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(story_context, f, ensure_ascii=False, indent=4)
            # print(f"故事上下文已保存至 {CONTEXT_FILE}") 
            
    except Exception as e:
        print(f"保存故事上下文 {CONTEXT_FILE} 时出错: {e}")


def deep_merge_dicts(source, destination):
    """递归地合并两个字典。source 的值会覆盖 destination 的值。"""
    for key, value in source.items():
        if isinstance(value, dict):
            # 获取 node or create one
            node = destination.setdefault(key, {})
            deep_merge_dicts(value, node)
        elif isinstance(value, list):
             # 如果目标中不存在该键或不是列表，则直接用源列表覆盖
            if key not in destination or not isinstance(destination[key], list):
                destination[key] = value
            else:
                # 如果目标中已存在列表，则合并两个列表（去重，保持源列表顺序优先）
                existing_set = set(destination[key])
                merged_list = destination[key][:] 
                for item in value:
                    if item not in existing_set:
                        merged_list.append(item)
                        existing_set.add(item)
                destination[key] = merged_list
        else:
            destination[key] = value
    return destination

def simplify_context_items(max_items=15, max_elements=25):
    """简化上下文中的关键列表项，保持列表不超过指定的最大项数
    max_items: 主角能力和关系的最大项数
    max_elements: 世界元素的最大项数
    """
    global story_context
    
    # 创建存档结构，用于存储被删除的项目
    removed_items_archive = {
        "protagonist_info": {"key_items_abilities": [], "key_relationships": {}},
        "world_setting": {"key_elements": []}
    }
    total_removed_count = 0
    
    # 简化 key_items_abilities
    abilities_list = story_context.get('protagonist_info', {}).get('key_items_abilities', [])
    if len(abilities_list) > max_items:
        # 提取要移除的项目
        items_to_remove = abilities_list[:-max_items]
        # 保留最新的 max_items 个项目
        story_context['protagonist_info']['key_items_abilities'] = abilities_list[-max_items:]
        # 添加到存档
        removed_items_archive["protagonist_info"]["key_items_abilities"] = items_to_remove
        total_removed_count += len(items_to_remove)
        print(f"已简化主角能力/物品列表至 {max_items} 项，移除了 {len(items_to_remove)} 项")
    
    # 简化 key_relationships
    relationships_dict = story_context.get('protagonist_info', {}).get('key_relationships', {})
    if len(relationships_dict) > max_items:
        # 获取所有键
        all_keys = list(relationships_dict.keys())
        # 要保留的键（最新的 max_items 个）
        keys_to_keep = all_keys[-max_items:]
        # 要移除的键
        keys_to_remove = all_keys[:-max_items]
        
        # 创建新的关系字典，只包含要保留的键
        new_relationships = {k: relationships_dict[k] for k in keys_to_keep}
        # 创建要存档的关系字典
        removed_relationships = {k: relationships_dict[k] for k in keys_to_remove}
        
        # 更新上下文和存档
        story_context['protagonist_info']['key_relationships'] = new_relationships
        removed_items_archive["protagonist_info"]["key_relationships"] = removed_relationships
        total_removed_count += len(keys_to_remove)
        print(f"已简化主角关系列表至 {max_items} 项，移除了 {len(keys_to_remove)} 项")
    
    # 简化 key_elements
    elements_list = story_context.get('world_setting', {}).get('key_elements', [])
    if len(elements_list) > max_elements:
        # 提取要移除的项目
        elements_to_remove = elements_list[:-max_elements]
        # 保留最新的 max_elements 个项目
        story_context['world_setting']['key_elements'] = elements_list[-max_elements:]
        # 添加到存档
        removed_items_archive["world_setting"]["key_elements"] = elements_to_remove
        total_removed_count += len(elements_to_remove)
        print(f"已简化世界元素列表至 {max_elements} 项，移除了 {len(elements_to_remove)} 项")
    
    # 如果有内容被移除，则更新存档文件
    if total_removed_count > 0:
        print(f"共有 {total_removed_count} 个项目被简化移除，正在更新存档...")
        try:
            # 加载现有存档或初始化
            existing_archive = {
                "protagonist_info": {"key_items_abilities": [], "key_relationships": {}}, 
                "world_setting": {"key_elements": []}
            }
            if os.path.exists(PRUNED_ARCHIVE_FILE):
                with open(PRUNED_ARCHIVE_FILE, 'r', encoding='utf-8') as af:
                    try:
                        loaded_archive = json.load(af)
                        # 简单验证结构，不是列表，且包含顶级键
                        if isinstance(loaded_archive, dict) and "protagonist_info" in loaded_archive and "world_setting" in loaded_archive:
                            existing_archive = loaded_archive
                        else:
                            print(f"警告：存档文件 {PRUNED_ARCHIVE_FILE} 格式不符合预期，将使用空结构重新创建。")
                    except json.JSONDecodeError:
                        print(f"警告：存档文件 {PRUNED_ARCHIVE_FILE} 格式错误，将使用空结构重新创建。")
            
            # 合并本次删除的条目到现有存档
            # 合并 abilities
            existing_archive["protagonist_info"].setdefault("key_items_abilities", []).extend(
                removed_items_archive["protagonist_info"]["key_items_abilities"])
            # 合并 relationships (更新字典)
            existing_archive["protagonist_info"].setdefault("key_relationships", {}).update(
                removed_items_archive["protagonist_info"]["key_relationships"])
            # 合并 elements
            existing_archive["world_setting"].setdefault("key_elements", []).extend(
                removed_items_archive["world_setting"]["key_elements"])

            # 写回存档文件
            with open(PRUNED_ARCHIVE_FILE, 'w', encoding='utf-8') as af:
                json.dump(existing_archive, af, ensure_ascii=False, indent=4)
            print(f"已将被删除的 {total_removed_count} 个条目信息合并到存档文件 {PRUNED_ARCHIVE_FILE}")

        except Exception as archive_e:
            print(f"写入或合并存档文件 {PRUNED_ARCHIVE_FILE} 时出错: {archive_e}")


def update_story_context_after_chapter(chapter_number, new_chapter_content):
    """根据新章节内容，调用 AI 分析并更新全局 story_context"""
    global story_context
    
    print("基础上下文更新：章节号 -> {}, 摘要已更新。".format(chapter_number))
    story_context["last_generated_chapter"] = chapter_number
    
    # 提取章节结尾作为摘要（去除空行后的最后3行有效内容）
    lines = new_chapter_content.strip().split('\n') if new_chapter_content else []
    # 过滤掉空行
    non_empty_lines = [line for line in lines if line.strip()]
    # 获取最后3行非空内容
    summary_lines = non_empty_lines[-3:] if len(non_empty_lines) >= 3 else non_empty_lines
    story_context["recent_plot_summary"] = "\n".join(summary_lines)
    print(f"已提取章节结尾作为摘要: {summary_lines}")
    
    # Call AI analysis internally
    print("准备调用 AI 分析上下文...")
    context_for_ai = copy.deepcopy(story_context) 
    ai_analysis_result = analyze_context_with_ai(context_for_ai, new_chapter_content) 
    
    # Merge AI results (existing robust logic)
    if ai_analysis_result and isinstance(ai_analysis_result, dict):
        print("准备合并 AI 分析结果...")
        # 分别合并主角信息和世界设定
        merged_protagonist = False 
        merged_world = False 

        if "protagonist_info" in ai_analysis_result and isinstance(ai_analysis_result["protagonist_info"], dict): 
            try:
                deep_merge_dicts(ai_analysis_result["protagonist_info"], story_context.setdefault("protagonist_info", {}))
                print("已深度合并 AI 分析的主角信息更新。")
                merged_protagonist = True
            except Exception as e:
                 print(f"警告: 合并主角信息时出错: {e}") 

        if "world_setting" in ai_analysis_result and isinstance(ai_analysis_result["world_setting"], dict): 
            try:
                deep_merge_dicts(ai_analysis_result["world_setting"], story_context.setdefault("world_setting", {}))
                print("已深度合并 AI 分析的世界设定更新。")
                merged_world = True
            except Exception as e:
                 print(f"警告: 合并世界设定时出错: {e}") 

        # Add checks for merge success like in app_back.py
        if not merged_protagonist:
             print("AI 返回的主角信息部分无效、缺失或合并失败，跳过合并。")
        if not merged_world:
             print("AI 返回的世界设定部分无效、缺失或合并失败，跳过合并。")

    else:
        print("本次 AI 上下文分析未产生有效更新。详细上下文信息可能未更新。")
    
    # 在保存前简化上下文项目
    print("正在简化上下文关键项目...")
    simplify_context_items(max_items=15, max_elements=25)
        
    # 更新完后立即保存
    print(f"正在保存章节 {chapter_number} 后的故事上下文...")
    save_story_context()

# 提供一个获取当前上下文的函数，避免直接操作全局变量（虽然内部还是操作了）
def get_current_context():
    """返回当前加载的故事上下文的副本"""
    global story_context
    return copy.deepcopy(story_context)
