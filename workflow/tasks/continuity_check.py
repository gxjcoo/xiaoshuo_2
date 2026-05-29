"""
跨章节连贯性检查任务 - 检查与前章的衔接自然度

功能：
- 检查人物状态一致性
- 检查情节发展连贯性
- 检查伏笔回收情况
- 检查时间线逻辑
"""

import json
from typing import Any, Dict, List, Optional

from ..base import TaskNode


class ContinuityCheckTask(TaskNode):
    """跨章节连贯性检查"""

    @property
    def id(self) -> str:
        return "continuity_check"

    @property
    def name(self) -> str:
        return "连贯性检查"

    @property
    def deps(self) -> list:
        return ["audit_revise"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行连贯性检查
        
        输入：
            - chapter_number: 当前章节号
            - final_content: 当前章节最终内容
            - previous_chapter_content: 前一章内容（可选）
            - story_context: 故事上下文
            
        输出：
            - continuity_report: 连贯性检查报告
            - continuity_issues: 发现的问题列表
            - continuity_score: 连贯性得分 (0-100)
        """
        from llm.client import call_deepseek_api
        from config import CONTEXT_ANALYSIS_MODEL, CONTEXT_ANALYSIS_MAX_TOKENS
        from context_manager import load_story_context
        
        chapter_number = context.get("chapter_number")
        final_content = context.get("final_content")
        story_context = context.get("story_context") or load_story_context()
        
        if not final_content:
            raise ValueError("没有最终内容可用于检查")
        
        # 获取前一章内容
        previous_content = context.get("previous_chapter_content")
        if not previous_content and chapter_number > 1:
            previous_content = self._load_previous_chapter(chapter_number)
        
        if not previous_content:
            print(f"  警告: 未找到前一章内容，跳过连贯性检查")
            return {
                "continuity_report": "无前一章内容，跳过检查",
                "continuity_issues": [],
                "continuity_score": 100
            }
        
        # 构建检查提示词
        prompt = self._build_continuity_prompt(
            chapter_number,
            previous_content,
            final_content,
            story_context
        )
        
        # 调用 LLM 进行连贯性分析
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的小说编辑，专注于检查跨章节的连贯性。请仔细分析两个章节之间的衔接，找出任何不一致或不自然的地方。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            result = call_deepseek_api(
                messages,
                CONTEXT_ANALYSIS_MODEL,
                max_tokens=CONTEXT_ANALYSIS_MAX_TOKENS,
                temperature=0.1,
                response_format={"type": "json_object"},
                task_label=f"连贯性检查-第{chapter_number}章"
            )
            
            if result:
                analysis = json.loads(result)
                
                # 提取检查结果
                issues = analysis.get("issues", [])
                score = analysis.get("overall_score", 100)
                report = analysis.get("summary", "")
                
                # 打印检查结果
                print(f"  连贯性检查完成:")
                print(f"    - 得分: {score}/100")
                print(f"    - 问题数: {len(issues)}")
                
                if issues:
                    print(f"    - 主要问题:")
                    for issue in issues[:3]:  # 只显示前3个问题
                        print(f"      * {issue.get('description', '未知问题')}")
                
                return {
                    "continuity_report": report,
                    "continuity_issues": issues,
                    "continuity_score": score
                }
            
        except Exception as e:
            print(f"  警告: 连贯性检查失败: {e}")
        
        return {
            "continuity_report": "检查失败",
            "continuity_issues": [],
            "continuity_score": 100
        }

    def _load_previous_chapter(self, current_chapter: int) -> Optional[str]:
        """加载前一章内容"""
        import os
        
        # 尝试从输出目录加载
        output_dir = "output_chapters"
        prev_file = os.path.join(output_dir, f"{current_chapter - 1}.md")
        
        if os.path.exists(prev_file):
            with open(prev_file, "r", encoding="utf-8") as f:
                return f.read()
        
        # 尝试从输入目录加载
        input_dir = context.get("chapters_dir", "chapters")
        prev_file = os.path.join(input_dir, f"{current_chapter - 1}.md")
        
        if os.path.exists(prev_file):
            with open(prev_file, "r", encoding="utf-8") as f:
                return f.read()
        
        return None

    def _build_continuity_prompt(
        self,
        chapter_number: int,
        previous_content: str,
        current_content: str,
        story_context: Dict[str, Any]
    ) -> str:
        """构建连贯性检查提示词"""
        
        # 提取关键上下文信息
        protagonist = story_context.get("protagonist_info", {}).get("name", "未知")
        recent_summary = story_context.get("recent_plot_summary", "")
        pending_hooks = story_context.get("pending_hooks", [])
        
        hooks_text = ""
        if pending_hooks:
            hooks_text = "当前未回收的伏笔:\n"
            for hook in pending_hooks[:5]:  # 只显示前5个
                hooks_text += f"- {hook.get('content', '未知')}\n"
        
        prompt = f"""请分析以下两个相邻章节的连贯性：

## 基本信息
- 当前章节: 第{chapter_number}章
- 主角: {protagonist}
- 最近剧情摘要: {recent_summary}

{hooks_text}

## 前一章内容（第{chapter_number - 1}章）:
{previous_content[:3000]}...

## 当前章节内容（第{chapter_number}章）:
{current_content[:3000]}...

## 检查要求:
1. **人物状态一致性**: 人物的位置、状态、情绪是否前后一致？
2. **情节发展连贯性**: 剧情发展是否自然？是否有跳跃或断裂？
3. **时间线逻辑**: 时间流逝是否合理？
4. **伏笔处理**: 前文埋下的伏笔是否被妥善处理或提及？
5. **对话连贯性**: 人物对话是否符合上下文？
6. **场景转换**: 场景切换是否自然？

请以 JSON 格式输出：
{{
    "issues": [
        {{
            "type": "问题类型",
            "description": "问题描述",
            "severity": "严重程度(1-5)",
            "suggestion": "修改建议"
        }}
    ],
    "overall_score": 85,
    "summary": "总体评价"
}}"""
        
        return prompt

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "final_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "final_content"]

    def get_output_keys(self) -> list:
        return ["continuity_report", "continuity_issues", "continuity_score"]