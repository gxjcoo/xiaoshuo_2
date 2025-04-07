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
            
            # 尝试从 key_items_abilities 删除，但不删除 core_characters 和 core_items
            # 只有超过15个项目时才删除
            abilities_list = story_context.get('protagonist_info', {}).get('key_items_abilities', [])
            core_items = story_context.get('core_items', [])
            core_characters = story_context.get('core_characters', [])
            
            if len(abilities_list) > 15:  # 修改：只有超过15个时才删除
                for item in abilities_list[:]:
                    if item not in core_items and item not in core_characters:
                        removed_ability = abilities_list.pop(abilities_list.index(item))
                        removed_items_archive["protagonist_info"]["key_items_abilities"].append(removed_ability)
                        items_pruned_this_iteration += 1
                        break

            # 尝试从 key_relationships 删除 (删除第一个键值对)，但不删除核心配角
            # 只有超过15个关系时才删除
            relationships_dict = story_context.get('protagonist_info', {}).get("key_relationships", {})
            core_characters = story_context.get('core_characters', [])
            
            if len(relationships_dict) > 15:  # 修改：只有超过15个时才删除
                # 遍历找到第一个不是核心配角的关系
                for key in list(relationships_dict.keys()):
                    if key not in core_characters:
                        removed_relation_value = relationships_dict.pop(key)
                        removed_items_archive["protagonist_info"]["key_relationships"][key] = removed_relation_value
                        items_pruned_this_iteration += 1
                        break
                
            # 尝试从 key_elements 删除，但不删除与核心道具相关的元素
            # 只有超过15个元素时才删除
            elements_list = story_context.get('world_setting', {}).get('key_elements', [])
            core_items = story_context.get('core_items', [])
            
            if len(elements_list) > 15:  # 修改：只有超过15个时才删除
                for element in elements_list[:]:
                    # 检查元素是否与核心道具相关（简单检查是否包含核心道具的名称）
                    is_core_related = False
                    for core_item in core_items:
                        if core_item in element:
                            is_core_related = True
                            break
                    
                    if not is_core_related:
                        removed_element = elements_list.pop(elements_list.index(element))
                        removed_items_archive["world_setting"]["key_elements"].append(removed_element)
                        items_pruned_this_iteration += 1
                        break

            if items_pruned_this_iteration == 0:
                print("警告：上下文大小超限，但所有可修剪列表/字典均已为最小保留数量（15个）或与核心内容相关，无法进一步减小。")
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
    
    # 自动检测并添加核心配角与道具
    print("开始自动检测核心配角和道具...")
    new_core_characters = auto_add_core_characters(new_chapter_content)
    new_core_items = auto_add_core_items(new_chapter_content)
    
    if new_core_characters:
        print(f"本章节新增核心配角: {', '.join(new_core_characters)}")
    else:
        print("本章节未检测到需要添加的新核心配角")
        
    if new_core_items:
        print(f"本章节新增核心道具: {', '.join(new_core_items)}")
    else:
        print("本章节未检测到需要添加的新核心道具")
    
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

# 核心配角和道具管理函数
def add_core_character(character_name):
    """添加核心配角到故事上下文中
    
    Args:
        character_name: 配角名称
        
    Returns:
        bool: 添加是否成功
    """
    global story_context
    try:
        if 'core_characters' not in story_context:
            story_context['core_characters'] = []
            
        # 检查是否已存在，避免重复添加
        if character_name not in story_context['core_characters']:
            story_context['core_characters'].append(character_name)
            print(f"已添加核心配角: {character_name}")
            save_story_context()
            return True
        else:
            print(f"核心配角 {character_name} 已存在，无需重复添加")
            return False
    except Exception as e:
        print(f"添加核心配角时出错: {e}")
        return False

def remove_core_character(character_name):
    """从核心配角列表中移除一个配角
    
    Args:
        character_name: 要移除的配角名称
        
    Returns:
        bool: 移除是否成功
    """
    global story_context
    try:
        if 'core_characters' in story_context and character_name in story_context['core_characters']:
            story_context['core_characters'].remove(character_name)
            print(f"已移除核心配角: {character_name}")
            save_story_context()
            return True
        else:
            print(f"核心配角 {character_name} 不存在，无法移除")
            return False
    except Exception as e:
        print(f"移除核心配角时出错: {e}")
        return False

def get_core_characters():
    """获取所有核心配角
    
    Returns:
        list: 核心配角列表
    """
    global story_context
    return story_context.get('core_characters', [])

def add_core_item(item_name):
    """添加核心道具到故事上下文中
    
    Args:
        item_name: 道具名称
        
    Returns:
        bool: 添加是否成功
    """
    global story_context
    try:
        if 'core_items' not in story_context:
            story_context['core_items'] = []
            
        # 检查是否已存在，避免重复添加
        if item_name not in story_context['core_items']:
            story_context['core_items'].append(item_name)
            print(f"已添加核心道具: {item_name}")
            save_story_context()
            return True
        else:
            print(f"核心道具 {item_name} 已存在，无需重复添加")
            return False
    except Exception as e:
        print(f"添加核心道具时出错: {e}")
        return False

def remove_core_item(item_name):
    """从核心道具列表中移除一个道具
    
    Args:
        item_name: 要移除的道具名称
        
    Returns:
        bool: 移除是否成功
    """
    global story_context
    try:
        if 'core_items' in story_context and item_name in story_context['core_items']:
            story_context['core_items'].remove(item_name)
            print(f"已移除核心道具: {item_name}")
            save_story_context()
            return True
        else:
            print(f"核心道具 {item_name} 不存在，无法移除")
            return False
    except Exception as e:
        print(f"移除核心道具时出错: {e}")
        return False

def get_core_items():
    """获取所有核心道具
    
    Returns:
        list: 核心道具列表
    """
    global story_context
    return story_context.get('core_items', [])

def detect_potential_core_characters(chapter_content):
    """分析章节内容，检测可能的核心配角
    
    Args:
        chapter_content: 章节内容文本
        
    Returns:
        list: 检测到的潜在核心配角列表
    """
    from ai_handler import call_deepseek_api
    import json
    
    # 获取当前已有的核心配角
    current_core_characters = get_core_characters()
    
    print("正在分析章节内容以检测潜在的核心配角...")
    
    # 构建提示词
    prompt = f"""请分析以下章节内容，识别出可能的核心配角人物。核心配角是指在故事发展中扮演重要角色，
    且可能在未来章节中继续出现的角色。

    已有的核心配角（请勿重复推荐这些角色）: {', '.join(current_core_characters) if current_core_characters else '无'}

    在分析时，请特别关注以下与故事世界观相关的要素：
    1. 与"永恒集团"（全球顶级科技集团，内部有永恒研究所研究两界穿越）相关的角色
    2. 对两界时间规则（流速比1:1.2）有了解或影响的角色
    3. 对灵气（波动频率10^-34秒左右，能量密度超普通空气千倍，螺旋状结构）有研究或控制能力的角色
    4. 与主角（科研背景出身的盗墓专家，曾在永恒集团担任顾问）有重要关联的角色

    请根据以下标准综合判断：
    1. 角色在对话中的出场频率
    2. 角色对情节的影响程度
    3. 角色的独特性或特殊能力
    4. 角色与主角的关系紧密程度
    5. 角色在整个故事结构中的潜在价值（考虑到小说计划为15卷共720万字的大型结构）

    根据分析，以下章节中可能的核心配角是谁？只返回角色名称列表，格式为JSON数组，例如 ["角色1", "角色2"]。
    如果没有检测到新的核心配角，则返回空数组 []。

    章节内容：
    {chapter_content[:2000]}...（内容过长已截断）
    """
    
    try:
        # 调用AI API分析
        response = call_deepseek_api(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        if not response or "content" not in response:
            print("AI分析未返回有效结果")
            return []
            
        content = response["content"].strip()
        
        # 尝试解析JSON响应
        try:
            # 查找内容中的JSON数组
            import re
            json_match = re.search(r'\[.*\]', content)
            if json_match:
                json_str = json_match.group(0)
                potential_characters = json.loads(json_str)
                return potential_characters if isinstance(potential_characters, list) else []
            else:
                print(f"无法从AI响应中识别出JSON格式: {content}")
                return []
        except json.JSONDecodeError as je:
            print(f"解析AI返回的JSON时出错: {je}")
            return []
            
    except Exception as e:
        print(f"检测核心配角时出错: {e}")
        return []

def auto_add_core_characters(chapter_content):
    """自动检测并添加核心配角
    
    Args:
        chapter_content: 章节内容
        
    Returns:
        list: 新添加的核心配角列表
    """
    # 检测潜在的核心配角
    potential_characters = detect_potential_core_characters(chapter_content)
    
    if not potential_characters:
        print("未检测到新的潜在核心配角")
        return []
    
    # 添加检测到的配角
    new_added = []
    for character in potential_characters:
        if add_core_character(character):
            new_added.append(character)
    
    if new_added:
        print(f"已自动添加 {len(new_added)} 个新的核心配角: {', '.join(new_added)}")
    
    return new_added

def detect_potential_core_items(chapter_content):
    """分析章节内容，检测可能的核心道具
    
    Args:
        chapter_content: 章节内容文本
        
    Returns:
        list: 检测到的潜在核心道具列表
    """
    from ai_handler import call_deepseek_api
    import json
    
    # 获取当前已有的核心道具
    current_core_items = get_core_items()
    
    print("正在分析章节内容以检测潜在的核心道具...")
    
    # 构建提示词
    prompt = f"""请分析以下章节内容，识别出可能的核心道具或物品。核心道具是指在故事发展中具有重要作用，
    且可能在未来章节中继续出现或发挥作用的物品。

    已有的核心道具（请勿重复推荐这些道具）: {', '.join(current_core_items) if current_core_items else '无'}

    在分析时，请特别关注以下与故事世界观相关的要素：
    1. 与"永恒集团"研究相关的科技装备或实验器材
    2. 可能影响或测量两界时间流速（比例1:1.2）的装置
    3. 与灵气（波动频率10^-34秒左右，能量密度超普通空气千倍，螺旋状结构）相关的物品
    4. 与主角盗墓专业相关的工具或文物
    5. 跨越两界的特殊物品或能量载体

    请根据以下标准综合判断：
    1. 道具在故事中的出现频率
    2. 道具对情节的影响程度
    3. 道具的独特性或特殊功能
    4. 道具与主角或重要角色的关联程度
    5. 道具在整个故事结构（15卷720万字）中的潜在价值和作用

    根据分析，以下章节中可能的核心道具是什么？只返回道具名称列表，格式为JSON数组，例如 ["道具1", "道具2"]。
    如果没有检测到新的核心道具，则返回空数组 []。

    章节内容：
    {chapter_content[:2000]}...（内容过长已截断）
    """
    
    try:
        # 调用AI API分析
        response = call_deepseek_api(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        if not response or "content" not in response:
            print("AI分析未返回有效结果")
            return []
            
        content = response["content"].strip()
        
        # 尝试解析JSON响应
        try:
            # 查找内容中的JSON数组
            import re
            json_match = re.search(r'\[.*\]', content)
            if json_match:
                json_str = json_match.group(0)
                potential_items = json.loads(json_str)
                return potential_items if isinstance(potential_items, list) else []
            else:
                print(f"无法从AI响应中识别出JSON格式: {content}")
                return []
        except json.JSONDecodeError as je:
            print(f"解析AI返回的JSON时出错: {je}")
            return []
            
    except Exception as e:
        print(f"检测核心道具时出错: {e}")
        return []

def auto_add_core_items(chapter_content):
    """自动检测并添加核心道具
    
    Args:
        chapter_content: 章节内容
        
    Returns:
        list: 新添加的核心道具列表
    """
    # 检测潜在的核心道具
    potential_items = detect_potential_core_items(chapter_content)
    
    if not potential_items:
        print("未检测到新的潜在核心道具")
        return []
    
    # 添加检测到的道具
    new_added = []
    for item in potential_items:
        if add_core_item(item):
            new_added.append(item)
    
    if new_added:
        print(f"已自动添加 {len(new_added)} 个新的核心道具: {', '.join(new_added)}")
    
    return new_added
