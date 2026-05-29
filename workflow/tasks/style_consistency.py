"""
风格一致性验证任务 - 验证生成内容风格与原作一致

功能：
- 比较生成内容与原作风格
- 检查用词、句式、节奏等风格元素
- 生成风格一致性报告
- 提供风格调整建议
"""

import json
from typing import Any, Dict, Optional

from ..base import TaskNode


class StyleConsistencyTask(TaskNode):
    """风格一致性验证"""

    @property
    def id(self) -> str:
        return "style_consistency"

    @property
    def name(self) -> str:
        return "风格一致性"

    @property
    def deps(self) -> list:
        return ["audit_revise"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行风格一致性验证
        
        输入：
            - chapter_number: 当前章节号
            - final_content: 当前章节最终内容
            - reference_text: 原文参考文本
            - writing_style_guide: 写作风格指南（可选）
            
        输出：
            - style_report: 风格一致性报告
            - style_score: 风格得分 (0-100)
            - style_issues: 风格问题列表
            - style_suggestions: 风格调整建议
        """
        from llm.client import call_deepseek_api
        from config import CONTEXT_ANALYSIS_MODEL, CONTEXT_ANALYSIS_MAX_TOKENS
        from context_manager import load_story_context
        
        chapter_number = context.get("chapter_number")
        final_content = context.get("final_content")
        reference_text = context.get("reference_text")
        story_context = context.get("story_context") or load_story_context()
        
        if not final_content:
            raise ValueError("没有最终内容可用于风格验证")
        
        # 获取写作风格指南
        style_guide = context.get("writing_style_guide") or story_context.get("writing_style_guide", "")
        
        # 如果没有参考文本，尝试加载
        if not reference_text:
            reference_text = self._load_reference_text(chapter_number)
        
        if not reference_text:
            print(f"  警告: 未找到参考文本，跳过风格一致性验证")
            return {
                "style_report": "无参考文本，跳过验证",
                "style_score": 100,
                "style_issues": [],
                "style_suggestions": []
            }
        
        # 分析风格一致性
        analysis = self._analyze_style_consistency(
            chapter_number,
            final_content,
            reference_text,
            style_guide,
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        
        if not analysis:
            print(f"  警告: 风格分析失败")
            return {
                "style_report": "分析失败",
                "style_score": 100,
                "style_issues": [],
                "style_suggestions": []
            }
        
        # 提取分析结果
        score = analysis.get("overall_score", 100)
        issues = analysis.get("issues", [])
        suggestions = analysis.get("suggestions", [])
        summary = analysis.get("summary", "")
        
        # 打印风格检查报告
        print(f"  风格一致性验证完成:")
        print(f"    - 得分: {score}/100")
        print(f"    - 问题数: {len(issues)}")
        
        if issues:
            print(f"    - 主要问题:")
            for issue in issues[:3]:
                print(f"      * {issue.get('description', '未知问题')}")
        
        if suggestions:
            print(f"    - 调整建议:")
            for suggestion in suggestions[:2]:
                print(f"      * {suggestion.get('suggestion', '无建议')}")
        
        return {
            "style_report": summary,
            "style_score": score,
            "style_issues": issues,
            "style_suggestions": suggestions
        }

    def _load_reference_text(self, chapter_number: int) -> Optional[str]:
        """加载参考文本"""
        import os
        
        # 从输入目录加载
        input_dir = context.get("chapters_dir", "chapters")
        ref_file = os.path.join(input_dir, f"{chapter_number}.md")
        
        if os.path.exists(ref_file):
            with open(ref_file, "r", encoding="utf-8") as f:
                return f.read()
        
        return None

    def _analyze_style_consistency(
        self,
        chapter_number: int,
        generated_content: str,
        reference_text: str,
        style_guide: str,
        call_api_func,
        model: str,
        max_tokens: int
    ) -> Dict[str, Any]:
        """分析风格一致性"""
        
        style_guide_text = ""
        if style_guide:
            style_guide_text = f"""
## 写作风格指南:
{style_guide[:2000]}
"""
        
        prompt = f"""请分析生成内容与原作风格的一致性：

## 章节信息
- 章节号: 第{chapter_number}章

{style_guide_text}

## 生成内容:
{generated_content[:3000]}

## 原文参考:
{reference_text[:3000]}

## 分析要求:
1. **用词风格**: 词汇选择、用语习惯是否一致？
2. **句式结构**: 句子长度、复杂度、节奏是否匹配？
3. **叙述视角**: 人称、视角是否保持一致？
4. **语言风格**: 口语化/书面化程度、文风是否统一？
5. **细节描写**: 描写密度、细节处理是否相似？
6. **对话风格**: 对话方式、语气是否符合原作？

请以 JSON 格式输出：
{{
    "issues": [
        {{
            "category": "问题类别",
            "description": "问题描述",
            "severity": "严重程度(1-5)",
            "example": "具体例子"
        }}
    ],
    "suggestions": [
        {{
            "category": "调整类别",
            "suggestion": "具体建议",
            "priority": "优先级(高/中/低)"
        }}
    ],
    "overall_score": 85,
    "summary": "总体评价"
}}"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的文学编辑，擅长分析和比较写作风格。请仔细比较生成内容与原作风格的一致性，提供详细的分析和建议。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            result = call_api_func(
                messages,
                model,
                max_tokens=max_tokens,
                temperature=0.1,
                response_format={"type": "json_object"},
                task_label=f"风格一致性-第{chapter_number}章"
            )
            
            if result:
                return json.loads(result)
                
        except Exception as e:
            print(f"  警告: 风格分析失败: {e}")
        
        return None

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "final_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "final_content"]

    def get_output_keys(self) -> list:
        return ["style_report", "style_score", "style_issues", "style_suggestions"]