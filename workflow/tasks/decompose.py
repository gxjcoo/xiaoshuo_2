"""
拆书任务 - 从小说中提取各类设定信息

生成：
- 世界观设定
- 力量体系
- 金手指设定
- 主角档案
- 主要对手
- 分卷规划
- 伏笔系统
- 写作风格指南
- 核心冲突
"""

import json
import os
from typing import Any, Dict, List

from ..base import TaskNode


class DecomposeBookTask(TaskNode):
    """从原小说提取完整设定文档"""

    @property
    def id(self) -> str:
        return "decompose_book"

    @property
    def name(self) -> str:
        return "拆书"

    @property
    def deps(self) -> list:
        return ["split_novel"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行拆书分析
        
        输入：
            - chapters_dir: 章节目录
            - chapters: 章节文件列表
            - decompose_output: 输出文件路径
            
        输出：
            - book_profile: 完整设定文档
            - book_profile_path: 设定文件路径
        """
        from llm.client import call_deepseek_api
        from config import CONTEXT_ANALYSIS_MODEL, CONTEXT_ANALYSIS_MAX_TOKENS
        
        chapters_dir = context.get("chapters_dir", "chapters")
        chapters = context.get("chapters", [])
        output_path = context.get("decompose_output", "book_profile.json")
        
        if not chapters:
            # 尝试扫描目录
            chapters = sorted([
                f for f in os.listdir(chapters_dir)
                if f.endswith(".md") and f[0].isdigit()
            ])
        
        if not chapters:
            raise ValueError("没有找到章节文件")
        
        # 采样策略：取前3章+中间2章+末尾2章
        sample_chapters = self._sample_chapters(chapters, chapters_dir)
        
        print(f"拆书分析：采样 {len(sample_chapters)} 个章节进行分析")
        
        # 分维度进行分析
        book_profile = {}
        
        # 1. 世界观与力量体系
        print("  分析世界观与力量体系...")
        world_result = self._analyze_dimension(
            sample_chapters,
            "世界观与力量体系",
            "请分析以下章节，提取世界观设定和力量体系信息。包括：\n"
            "1. 世界背景：地理、历史、文化、社会结构\n"
            "2. 力量体系：修炼/战斗/能力系统的规则、等级、限制\n"
            "3. 特殊设定：独特的世界观元素\n\n"
            "请用 JSON 格式输出：{\"world_setting\": {...}, \"power_system\": {...}}",
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        book_profile.update(world_result)
        
        # 2. 主角档案与主要对手
        print("  分析主角档案与主要对手...")
        character_result = self._analyze_dimension(
            sample_chapters,
            "主角与对手",
            "请分析以下章节，提取主角和主要对手信息。包括：\n"
            "1. 主角档案：姓名、性格、背景、动机、成长弧线、特殊能力\n"
            "2. 主要对手：反派/对手阵营、动机、能力、与主角的关系\n\n"
            "请用 JSON 格式输出：{\"protagonist\": {...}, \"antagonists\": [...]}",
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        book_profile.update(character_result)
        
        # 3. 金手指设定与核心冲突
        print("  分析金手指与核心冲突...")
        conflict_result = self._analyze_dimension(
            sample_chapters,
            "金手指与核心冲突",
            "请分析以下章节，提取金手指设定和核心冲突。包括：\n"
            "1. 金手指设定：主角独有的特殊能力、外挂、优势及其限制\n"
            "2. 核心冲突：贯穿全书的核心矛盾和主题\n\n"
            "请用 JSON 格式输出：{\"golden_finger\": {...}, \"core_conflict\": {...}}",
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        book_profile.update(conflict_result)
        
        # 4. 伏笔系统与分卷规划
        print("  分析伏笔与分卷...")
        structure_result = self._analyze_dimension(
            sample_chapters,
            "伏笔与分卷",
            "请分析以下章节，提取伏笔系统和分卷规划。包括：\n"
            "1. 伏笔系统：已埋伏笔、可能的回收计划、悬念管理\n"
            "2. 分卷规划：按情节节点划分卷册，规划每卷核心事件\n\n"
            "请用 JSON 格式输出：{\"foreshadowing\": [...], \"volume_plan\": [...]}",
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        book_profile.update(structure_result)
        
        # 5. 写作风格指南（复用现有 style_analysis 逻辑）
        print("  分析写作风格...")
        style_result = self._analyze_writing_style(
            sample_chapters,
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        book_profile["writing_style_guide"] = style_result
        
        # 保存结果
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(book_profile, f, ensure_ascii=False, indent=2)
        
        print(f"拆书完成，设定文档已保存至: {output_path}")
        
        return {
            "book_profile": book_profile,
            "book_profile_path": output_path
        }

    def _sample_chapters(self, chapters: List[str], chapters_dir: str) -> List[str]:
        """采样章节：前3章+中间2章+末尾2章"""
        total = len(chapters)
        if total <= 7:
            return chapters
        
        sample_indices = []
        # 前3章
        sample_indices.extend(range(min(3, total)))
        # 中间2章
        mid = total // 2
        sample_indices.extend([mid - 1, mid])
        # 末尾2章
        sample_indices.extend([total - 2, total - 1])
        
        # 去重并排序
        sample_indices = sorted(set(i for i in sample_indices if 0 <= i < total))
        
        return [chapters[i] for i in sample_indices]

    def _load_chapters_content(
        self,
        chapter_files: List[str],
        chapters_dir: str,
        max_chars: int = 15000
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

    def _analyze_dimension(
        self,
        chapter_files: List[str],
        dimension_name: str,
        prompt_template: str,
        call_api_func,
        model: str,
        max_tokens: int
    ) -> Dict[str, Any]:
        """分析某个维度"""
        chapters_dir = "chapters"  # 默认目录
        content = self._load_chapters_content(chapter_files, chapters_dir)
        
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
                max_tokens=max_tokens,
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

    def _analyze_writing_style(
        self,
        chapter_files: List[str],
        call_api_func,
        model: str,
        max_tokens: int
    ) -> str:
        """分析写作风格"""
        from llm.style_analysis import analyze_writing_style
        
        chapters_dir = "chapters"
        content = self._load_chapters_content(chapter_files, chapters_dir)
        
        try:
            return analyze_writing_style(content)
        except Exception as e:
            print(f"  警告: 写作风格分析失败: {e}")
            return "（风格分析失败）"

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapters_dir" in context or "chapters" in context

    def get_required_keys(self) -> list:
        return ["chapters_dir"]

    def get_output_keys(self) -> list:
        return ["book_profile", "book_profile_path"]
