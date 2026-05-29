"""
高级拆书任务 - 适用于长篇小说（50万字以上）

分层渐进式分析策略：
1. 第一层：快速扫描（采样关键章节）
2. 第二层：深度分析（针对各维度的最佳样本）
3. 第三层：全书视野（伏笔、分卷等需要全貌的维度）
"""

import json
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from ..base import TaskNode


@dataclass
class ChapterInfo:
    """章节元信息"""
    index: int
    filename: str
    char_count: int
    is_volume_start: bool = False
    is_volume_end: bool = False
    is转折点: bool = False


class DecomposeAdvancedTask(TaskNode):
    """高级拆书任务 - 适用于长篇小说"""

    @property
    def id(self) -> str:
        return "decompose_advanced"

    @property
    def name(self) -> str:
        return "高级拆书"

    @property
    def deps(self) -> list:
        return ["split_novel"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行高级拆书分析
        
        输入：
            - chapters_dir: 章节目录
            - chapters: 章节文件列表
            - novel_length: 小说总字数（用于自适应策略）
            
        输出：
            - book_profile: 完整设定文档
            - book_profile_path: 设定文件路径
            - decompose_strategy: 使用的拆书策略描述
        """
        from llm.client import call_deepseek_api
        from config import (
            CONTEXT_ANALYSIS_MODEL, 
            CONTEXT_ANALYSIS_MAX_TOKENS,
            DECOMPOSE_MAX_CHARS_PER_CALL
        )
        
        chapters_dir = context.get("chapters_dir", "chapters")
        chapters = context.get("chapters", [])
        novel_length = context.get("novel_length", 0)
        
        if not chapters:
            chapters = sorted([
                f for f in os.listdir(chapters_dir)
                if f.endswith(".md") and f[0].isdigit()
            ])
        
        if not chapters:
            raise ValueError("没有找到章节文件")
        
        # 自适应策略选择
        strategy = self._select_strategy(len(chapters), novel_length)
        print(f"拆书策略: {strategy['name']} ({strategy['description']})")
        
        # 执行分层分析
        book_profile = {}
        
        # 第一层：快速扫描 - 世界观、力量体系、主角设定
        print("第一层：快速扫描...")
        quick_results = self._layer1_quick_scan(
            chapters, chapters_dir, strategy, call_deepseek_api, 
            CONTEXT_ANALYSIS_MODEL, DECOMPOSE_MAX_CHARS_PER_CALL
        )
        book_profile.update(quick_results)
        
        # 第二层：深度分析 - 角色关系、金手指、写作风格
        print("第二层：深度分析...")
        deep_results = self._layer2_deep_analysis(
            chapters, chapters_dir, strategy, call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL, DECOMPOSE_MAX_CHARS_PER_CALL
        )
        book_profile.update(deep_results)
        
        # 第三层：全书视野 - 伏笔系统、分卷规划、核心冲突
        print("第三层：全书视野...")
        full_results = self._layer3_full_analysis(
            chapters, chapters_dir, strategy, call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL, DECOMPOSE_MAX_CHARS_PER_CALL
        )
        book_profile.update(full_results)
        
        # 保存结果
        output_path = context.get("decompose_output", "book_profile.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(book_profile, f, ensure_ascii=False, indent=2)
        
        print(f"高级拆书完成，设定文档已保存至: {output_path}")
        
        return {
            "book_profile": book_profile,
            "book_profile_path": output_path,
            "decompose_strategy": strategy
        }

    def _select_strategy(self, chapter_count: int, novel_length: int) -> Dict[str, Any]:
        """根据小说规模选择拆书策略"""
        
        if novel_length >= 1_000_000 or chapter_count >= 300:
            return {
                "name": "超长篇策略",
                "description": "适用于100万字以上，300+章",
                "quick_scan_count": 15,  # 快速扫描章节数
                "deep_analysis_per_dim": 5,  # 每个维度深度分析章节数
                "volume_sample_ratio": 0.1,  # 每卷采样比例
                "max_chars_per_call": 20000,
                "use_volume_structure": True,
                "incremental_analysis": True
            }
        elif novel_length >= 500_000 or chapter_count >= 150:
            return {
                "name": "长篇策略",
                "description": "适用于50-100万字，150-300章",
                "quick_scan_count": 10,
                "deep_analysis_per_dim": 4,
                "volume_sample_ratio": 0.15,
                "max_chars_per_call": 18000,
                "use_volume_structure": True,
                "incremental_analysis": False
            }
        elif novel_length >= 200_000 or chapter_count >= 60:
            return {
                "name": "中篇策略",
                "description": "适用于20-50万字，60-150章",
                "quick_scan_count": 8,
                "deep_analysis_per_dim": 3,
                "volume_sample_ratio": 0.2,
                "max_chars_per_call": 15000,
                "use_volume_structure": False,
                "incremental_analysis": False
            }
        else:
            return {
                "name": "短篇策略",
                "description": "适用于20万字以下",
                "quick_scan_count": 7,
                "deep_analysis_per_dim": 3,
                "volume_sample_ratio": 0.3,
                "max_chars_per_call": 15000,
                "use_volume_structure": False,
                "incremental_analysis": False
            }

    def _layer1_quick_scan(
        self, 
        chapters: List[str], 
        chapters_dir: str, 
        strategy: Dict,
        call_api_func, 
        model: str, 
        max_chars: int
    ) -> Dict[str, Any]:
        """第一层：快速扫描 - 世界观、力量体系、主角设定"""
        
        # 采样策略：开篇 + 关键转折点 + 卷首
        sample_indices = self._get_quick_scan_indices(chapters, strategy)
        sample_files = [chapters[i] for i in sample_indices]
        
        print(f"  快速扫描采样: {len(sample_files)} 章")
        
        # 加载内容
        content = self._load_chapters_content(sample_files, chapters_dir, max_chars)
        
        # 并行分析多个维度
        results = {}
        
        # 世界观与力量体系
        world_result = self._analyze_with_prompt(
            content,
            "世界观与力量体系",
            "请从以下章节中提取世界观设定和力量体系。包括：\n"
            "1. 世界背景：地理、历史、文化、社会结构\n"
            "2. 力量体系：修炼/战斗/能力系统的规则、等级、限制\n"
            "3. 特殊设定：独特的世界观元素\n\n"
            "请用 JSON 格式输出：{\"world_setting\": {...}, \"power_system\": {...}}",
            call_api_func, model, max_chars
        )
        results.update(world_result)
        
        # 主角档案
        protagonist_result = self._analyze_with_prompt(
            content,
            "主角档案",
            "请从以下章节中提取主角信息。包括：\n"
            "1. 基本信息：姓名、年龄、背景\n"
            "2. 性格特征：核心性格、成长变化\n"
            "3. 能力体系：初始能力、成长轨迹\n"
            "4. 人际关系：重要关系、阵营归属\n\n"
            "请用 JSON 格式输出：{\"protagonist\": {...}}",
            call_api_func, model, max_chars
        )
        results.update(protagonist_result)
        
        return results

    def _layer2_deep_analysis(
        self, 
        chapters: List[str], 
        chapters_dir: str, 
        strategy: Dict,
        call_api_func, 
        model: str, 
        max_chars: int
    ) -> Dict[str, Any]:
        """第二层：深度分析 - 角色关系、金手指、写作风格"""
        
        results = {}
        
        # 角色关系分析 - 需要看不同阶段的互动
        character_indices = self._get_character_analysis_indices(chapters, strategy)
        character_files = [chapters[i] for i in character_indices]
        character_content = self._load_chapters_content(character_files, chapters_dir, max_chars)
        
        character_result = self._analyze_with_prompt(
            character_content,
            "角色关系",
            "请从以下章节中分析角色关系网络。包括：\n"
            "1. 主要对手：反派/对手阵营、动机、能力、与主角的关系\n"
            "2. 重要配角：盟友、导师、关键NPC\n"
            "3. 阵营关系：势力分布、利益冲突\n\n"
            "请用 JSON 格式输出：{\"antagonists\": [...], \"supporting_characters\": [...], \"factions\": [...]}",
            call_api_func, model, max_chars
        )
        results.update(character_result)
        
        # 金手指分析 - 需要看能力展现和限制
        golden_finger_indices = self._get_ability_showcase_indices(chapters, strategy)
        golden_finger_files = [chapters[i] for i in golden_finger_indices]
        golden_finger_content = self._load_chapters_content(golden_finger_files, chapters_dir, max_chars)
        
        golden_finger_result = self._analyze_with_prompt(
            golden_finger_content,
            "金手指设定",
            "请从以下章节中提取主角的特殊能力设定。包括：\n"
            "1. 核心能力：主角独有的特殊能力、外挂、优势\n"
            "2. 能力限制：使用条件、副作用、成长要求\n"
            "3. 能力成长：升级路径、关键转折点\n\n"
            "请用 JSON 格式输出：{\"golden_finger\": {...}}",
            call_api_func, model, max_chars
        )
        results.update(golden_finger_result)
        
        # 写作风格分析 - 需要看不同阶段的风格变化
        style_indices = self._get_style_analysis_indices(chapters, strategy)
        style_files = [chapters[i] for i in style_indices]
        style_content = self._load_chapters_content(style_files, chapters_dir, max_chars)
        
        from llm.style_analysis import analyze_writing_style
        try:
            style_result = analyze_writing_style(style_content)
            results["writing_style_guide"] = style_result
        except Exception as e:
            print(f"  警告: 写作风格分析失败: {e}")
            results["writing_style_guide"] = "（风格分析失败）"
        
        return results

    def _layer3_full_analysis(
        self, 
        chapters: List[str], 
        chapters_dir: str, 
        strategy: Dict,
        call_api_func, 
        model: str, 
        max_chars: int
    ) -> Dict[str, Any]:
        """第三层：全书视野 - 伏笔系统、分卷规划、核心冲突"""
        
        results = {}
        
        # 伏笔系统分析 - 需要全书视野
        print("  分析伏笔系统...")
        foreshadow_indices = self._get_foreshadow_analysis_indices(chapters, strategy)
        foreshadow_files = [chapters[i] for i in foreshadow_indices]
        foreshadow_content = self._load_chapters_content(foreshadow_files, chapters_dir, max_chars * 2)  # 伏笔分析需要更多内容
        
        foreshadow_result = self._analyze_with_prompt(
            foreshadow_content,
            "伏笔系统",
            "请从以下章节中分析伏笔系统。包括：\n"
            "1. 已埋伏笔：未解决的悬念、承诺、暗示\n"
            "2. 已回收伏笔：已解决的伏笔、回收方式\n"
            "3. 伏笔模式：作者常用的伏笔手法\n\n"
            "请用 JSON 格式输出：{\"foreshadowing\": {\"pending\": [...], \"resolved\": [...], \"patterns\": [...]}}",
            call_api_func, model, max_chars * 2
        )
        results.update(foreshadow_result)
        
        # 分卷规划分析 - 需要识别卷结构
        print("  分析分卷结构...")
        if strategy["use_volume_structure"]:
            volume_result = self._analyze_volume_structure(chapters, chapters_dir, strategy, call_api_func, model, max_chars)
            results.update(volume_result)
        
        # 核心冲突分析 - 需要全书视角
        print("  分析核心冲突...")
        conflict_indices = self._get_conflict_analysis_indices(chapters, strategy)
        conflict_files = [chapters[i] for i in conflict_indices]
        conflict_content = self._load_chapters_content(conflict_files, chapters_dir, max_chars)
        
        conflict_result = self._analyze_with_prompt(
            conflict_content,
            "核心冲突",
            "请从以下章节中分析核心冲突。包括：\n"
            "1. 主线冲突：贯穿全书的核心矛盾\n"
            "2. 支线冲突：重要的支线矛盾\n"
            "3. 冲突层次：个人、势力、世界观层面的冲突\n\n"
            "请用 JSON 格式输出：{\"core_conflict\": {...}, \"sub_conflicts\": [...], \"conflict_layers\": {...}}",
            call_api_func, model, max_chars
        )
        results.update(conflict_result)
        
        return results

    # ==================== 索引计算方法 ====================
    
    def _get_quick_scan_indices(self, chapters: List[str], strategy: Dict) -> List[int]:
        """获取快速扫描的章节索引"""
        total = len(chapters)
        count = strategy["quick_scan_count"]
        
        if total <= count:
            return list(range(total))
        
        indices = []
        
        # 开篇（前5章）
        indices.extend(range(min(5, total)))
        
        # 关键转折点（均匀分布）
        if count > 5:
            step = (total - 5) // (count - 5)
            for i in range(5, count - 2):
                idx = 5 + (i - 5) * step
                if idx < total:
                    indices.append(idx)
        
        # 结尾（最后2章）
        indices.extend([total - 2, total - 1])
        
        return sorted(set(i for i in indices if 0 <= i < total))

    def _get_character_analysis_indices(self, chapters: List[str], strategy: Dict) -> List[int]:
        """获取角色分析的章节索引"""
        total = len(chapters)
        count = strategy["deep_analysis_per_dim"]
        
        if total <= count * 2:
            return list(range(total))
        
        # 角色互动通常在：开篇、中段高潮、结尾
        indices = []
        
        # 开篇（角色登场）
        indices.extend(range(min(3, total)))
        
        # 中段（角色发展）
        mid = total // 2
        indices.extend([mid - 2, mid - 1, mid])
        
        # 结尾（角色结局）
        indices.extend([total - 3, total - 2, total - 1])
        
        return sorted(set(i for i in indices if 0 <= i < total))

    def _get_ability_showcase_indices(self, chapters: List[str], strategy: Dict) -> List[int]:
        """获取能力展现的章节索引"""
        total = len(chapters)
        
        # 能力展现通常在：初次觉醒、关键战斗、能力突破
        indices = []
        
        # 初次觉醒（开篇）
        indices.extend(range(min(5, total)))
        
        # 关键战斗（均匀分布）
        step = total // 5
        for i in range(1, 5):
            idx = i * step
            if idx < total:
                indices.append(idx)
        
        # 能力突破（结尾前）
        indices.extend([total - 3, total - 2, total - 1])
        
        return sorted(set(i for i in indices if 0 <= i < total))

    def _get_style_analysis_indices(self, chapters: List[str], strategy: Dict) -> List[int]:
        """获取风格分析的章节索引"""
        total = len(chapters)
        
        # 风格分析需要看不同阶段的写作
        indices = []
        
        # 开篇风格
        indices.extend(range(min(3, total)))
        
        # 中段风格
        mid = total // 2
        indices.extend([mid - 1, mid])
        
        # 结尾风格
        indices.extend([total - 2, total - 1])
        
        # 不同卷的风格（如果有卷结构）
        if strategy["use_volume_structure"]:
            volume_size = 20  # 假设每卷20章
            for vol_start in range(0, total, volume_size):
                if vol_start < total:
                    indices.append(vol_start)
        
        return sorted(set(i for i in indices if 0 <= i < total))

    def _get_foreshadow_analysis_indices(self, chapters: List[str], strategy: Dict) -> List[int]:
        """获取伏笔分析的章节索引 - 需要全书视野"""
        total = len(chapters)
        
        # 伏笔分析需要覆盖全书
        indices = []
        
        # 采样比例
        sample_ratio = strategy["volume_sample_ratio"]
        sample_count = max(20, int(total * sample_ratio))
        
        # 均匀采样
        step = max(1, total // sample_count)
        for i in range(0, total, step):
            indices.append(i)
        
        # 确保包含开篇和结尾
        if 0 not in indices:
            indices.insert(0, 0)
        if total - 1 not in indices:
            indices.append(total - 1)
        
        return sorted(set(i for i in indices if 0 <= i < total))

    def _get_conflict_analysis_indices(self, chapters: List[str], strategy: Dict) -> List[int]:
        """获取冲突分析的章节索引"""
        total = len(chapters)
        
        # 冲突通常在：开篇引入、中段升级、结尾解决
        indices = []
        
        # 开篇（引入冲突）
        indices.extend(range(min(5, total)))
        
        # 中段（冲突升级）
        mid = total // 2
        indices.extend([mid - 3, mid - 2, mid - 1, mid, mid + 1, mid + 2])
        
        # 结尾（冲突解决）
        indices.extend([total - 5, total - 4, total - 3, total - 2, total - 1])
        
        return sorted(set(i for i in indices if 0 <= i < total))

    # ==================== 内容加载方法 ====================
    
    def _load_chapters_content(
        self, 
        chapter_files: List[str], 
        chapters_dir: str, 
        max_chars: int
    ) -> str:
        """加载章节内容"""
        contents = []
        total_chars = 0
        
        for chapter_file in chapter_files:
            filepath = os.path.join(chapters_dir, chapter_file)
            if not os.path.exists(filepath):
                continue
            
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            if total_chars + len(content) > max_chars:
                # 截断
                remaining = max_chars - total_chars
                content = content[:remaining] + "\n...(已截断)"
                contents.append(content)
                break
            
            contents.append(content)
            total_chars += len(content)
        
        return "\n\n---\n\n".join(contents)

    # ==================== 分析方法 ====================
    
    def _analyze_with_prompt(
        self, 
        content: str, 
        dimension_name: str, 
        prompt_template: str,
        call_api_func, 
        model: str, 
        max_chars: int
    ) -> Dict[str, Any]:
        """使用提示词分析内容"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的小说分析师。请从提供的章节中准确提取信息，输出合法的 JSON 格式。"
            },
            {
                "role": "user",
                "content": f"{prompt_template}\n\n章节内容：\n{content}"
            }
        ]
        
        try:
            result = call_api_func(
                messages,
                model,
                max_tokens=4096,
                temperature=0.1,
                response_format={"type": "json_object"},
                task_label=f"拆书-{dimension_name}"
            )
            
            if result:
                return json.loads(result)
            return {}
        except Exception as e:
            print(f"  警告: {dimension_name} 分析失败: {e}")
            return {}

    def _analyze_volume_structure(
        self, 
        chapters: List[str], 
        chapters_dir: str, 
        strategy: Dict,
        call_api_func, 
        model: str, 
        max_chars: int
    ) -> Dict[str, Any]:
        """分析分卷结构"""
        
        # 采样每卷的开头和结尾
        volume_size = 20  # 假设每卷20章
        total = len(chapters)
        
        volume_samples = []
        for vol_start in range(0, total, volume_size):
            vol_end = min(vol_start + volume_size - 1, total - 1)
            
            # 采样卷首和卷尾
            if vol_start < total:
                volume_samples.append(chapters[vol_start])
            if vol_end != vol_start and vol_end < total:
                volume_samples.append(chapters[vol_end])
        
        content = self._load_chapters_content(volume_samples, chapters_dir, max_chars)
        
        prompt = (
            "请从以下章节中分析小说的分卷结构。包括：\n"
            "1. 卷划分：按情节节点划分卷册\n"
            "2. 每卷核心事件：每卷的主要情节转折\n"
            "3. 卷间联系：各卷之间的承接关系\n\n"
            "请用 JSON 格式输出：{\"volume_plan\": [...]}"
        )
        
        return self._analyze_with_prompt(content, "分卷规划", prompt, call_api_func, model, max_chars)

    # ==================== 验证方法 ====================
    
    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapters_dir" in context or "chapters" in context

    def get_required_keys(self) -> list:
        return ["chapters_dir"]

    def get_output_keys(self) -> list:
        return ["book_profile", "book_profile_path", "decompose_strategy"]