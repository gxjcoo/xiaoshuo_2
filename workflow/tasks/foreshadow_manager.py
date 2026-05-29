"""
伏笔管理任务 - 跟踪伏笔埋设和回收状态

功能：
- 分析当前章节中的伏笔埋设
- 检查伏笔回收情况
- 更新伏笔状态
- 生成伏笔管理报告
"""

import json
from typing import Any, Dict, List

from ..base import TaskNode


class ForeshadowManagerTask(TaskNode):
    """伏笔埋设和回收管理"""

    @property
    def id(self) -> str:
        return "foreshadow_manager"

    @property
    def name(self) -> str:
        return "伏笔管理"

    @property
    def deps(self) -> list:
        return ["audit_revise"]

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行伏笔管理
        
        输入：
            - chapter_number: 当前章节号
            - final_content: 当前章节最终内容
            - story_context: 故事上下文
            
        输出：
            - foreshadow_report: 伏笔管理报告
            - new_foreshadows: 新埋设的伏笔列表
            - resolved_foreshadows: 已回收的伏笔列表
            - pending_foreshadows: 当前未回收的伏笔列表
        """
        from llm.client import call_deepseek_api
        from config import CONTEXT_ANALYSIS_MODEL, CONTEXT_ANALYSIS_MAX_TOKENS
        from context_manager import load_story_context, save_story_context
        
        chapter_number = context.get("chapter_number")
        final_content = context.get("final_content")
        story_context = context.get("story_context") or load_story_context()
        
        if not final_content:
            raise ValueError("没有最终内容可用于伏笔管理")
        
        # 获取现有伏笔列表
        existing_hooks = story_context.get("pending_hooks", [])
        
        # 分析当前章节的伏笔情况
        analysis = self._analyze_foreshadows(
            chapter_number,
            final_content,
            existing_hooks,
            call_deepseek_api,
            CONTEXT_ANALYSIS_MODEL,
            CONTEXT_ANALYSIS_MAX_TOKENS
        )
        
        if not analysis:
            print(f"  警告: 伏笔分析失败")
            return {
                "foreshadow_report": "分析失败",
                "new_foreshadows": [],
                "resolved_foreshadows": [],
                "pending_foreshadows": existing_hooks
            }
        
        # 提取分析结果
        new_hooks = analysis.get("new_foreshadows", [])
        resolved_hooks = analysis.get("resolved_foreshadows", [])
        summary = analysis.get("summary", "")
        
        # 更新伏笔状态
        updated_hooks = self._update_foreshadow_state(
            existing_hooks,
            new_hooks,
            resolved_hooks,
            chapter_number
        )
        
        # 更新故事上下文
        story_context["pending_hooks"] = updated_hooks
        save_story_context()
        
        # 打印伏笔管理报告
        print(f"  伏笔管理完成:")
        print(f"    - 新埋设: {len(new_hooks)} 个")
        print(f"    - 已回收: {len(resolved_hooks)} 个")
        print(f"    - 未回收: {len([h for h in updated_hooks if h.get('status') == 'open'])} 个")
        
        if new_hooks:
            print(f"    - 新伏笔:")
            for hook in new_hooks[:3]:
                print(f"      * {hook.get('content', '未知')}")
        
        if resolved_hooks:
            print(f"    - 已回收:")
            for hook in resolved_hooks[:3]:
                print(f"      * {hook.get('content', '未知')}")
        
        return {
            "foreshadow_report": summary,
            "new_foreshadows": new_hooks,
            "resolved_foreshadows": resolved_hooks,
            "pending_foreshadows": updated_hooks
        }

    def _analyze_foreshadows(
        self,
        chapter_number: int,
        content: str,
        existing_hooks: List[Dict],
        call_api_func,
        model: str,
        max_tokens: int
    ) -> Dict[str, Any]:
        """分析章节中的伏笔情况"""
        
        # 构建现有伏笔文本
        existing_hooks_text = ""
        if existing_hooks:
            existing_hooks_text = "当前未回收的伏笔:\n"
            for i, hook in enumerate(existing_hooks[:10], 1):
                existing_hooks_text += f"{i}. {hook.get('content', '未知')} (第{hook.get('chapter_introduced', '?')}章)\n"
        
        prompt = f"""请分析以下章节中的伏笔情况：

## 章节信息
- 章节号: 第{chapter_number}章

{existing_hooks_text}

## 章节内容:
{content[:4000]}

## 分析要求:
1. **新伏笔识别**: 找出本章新埋设的伏笔（悬念、未解之谜、暗示等）
2. **伏笔回收检查**: 检查本章是否回收或推进了之前的伏笔
3. **伏笔质量评估**: 伏笔是否自然、有张力

请以 JSON 格式输出：
{{
    "new_foreshadows": [
        {{
            "content": "伏笔内容",
            "type": "类型(悬念/暗示/铺垫/其他)",
            "importance": "重要性(高/中/低)",
            "expected_resolution": "预期回收方式"
        }}
    ],
    "resolved_foreshadows": [
        {{
            "content": "原伏笔内容",
            "resolution": "回收方式",
            "satisfaction": "满意度(1-5)"
        }}
    ],
    "summary": "伏笔管理总结"
}}"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的小说结构分析师，擅长识别和管理伏笔。请准确分析章节中的伏笔埋设和回收情况。"
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
                task_label=f"伏笔管理-第{chapter_number}章"
            )
            
            if result:
                return json.loads(result)
                
        except Exception as e:
            print(f"  警告: 伏笔分析失败: {e}")
        
        return None

    def _update_foreshadow_state(
        self,
        existing_hooks: List[Dict],
        new_hooks: List[Dict],
        resolved_hooks: List[Dict],
        current_chapter: int
    ) -> List[Dict]:
        """更新伏笔状态"""
        
        # 创建已回收伏笔的索引
        resolved_contents = set()
        for hook in resolved_hooks:
            resolved_contents.add(hook.get("content", ""))
        
        # 更新现有伏笔状态
        updated_hooks = []
        for hook in existing_hooks:
            hook_content = hook.get("content", "")
            
            # 检查是否被回收
            if hook_content in resolved_contents:
                hook["status"] = "resolved"
                hook["chapter_resolved"] = current_chapter
                hook["resolution"] = next(
                    (r.get("resolution", "") for r in resolved_hooks if r.get("content") == hook_content),
                    ""
                )
            else:
                hook["status"] = "open"
            
            updated_hooks.append(hook)
        
        # 添加新伏笔
        for hook in new_hooks:
            updated_hooks.append({
                "id": f"hook_{current_chapter}_{len(updated_hooks)}",
                "content": hook.get("content", ""),
                "type": hook.get("type", "其他"),
                "importance": hook.get("importance", "中"),
                "chapter_introduced": current_chapter,
                "status": "open",
                "expected_resolution": hook.get("expected_resolution", "")
            })
        
        return updated_hooks

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        return "chapter_number" in context and "final_content" in context

    def get_required_keys(self) -> list:
        return ["chapter_number", "final_content"]

    def get_output_keys(self) -> list:
        return ["foreshadow_report", "new_foreshadows", "resolved_foreshadows", "pending_foreshadows"]