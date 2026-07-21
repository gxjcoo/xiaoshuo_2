"""
工作流任务节点实现

包含所有具体的工作流步骤：
- split: 切章
- entity_extract: 实体提取（LLM 主抽取）
- entity_validate: 实体校验（LTP 兜底补漏 + 归一化）
- entity_replace: 实体替换（全文替换并重新切章）
- decompose: 拆书（提取设定）
- decompose_advanced: 高级拆书（适用于长篇小说）
- inject_profile: 设定注入
- style_analysis: 风格分析
- outline_extract: 骨架抽取
- chapter_plan: 意图规划
- content_generate: 正文生成
- audit_revise: 审计修订
- continuity_check: 连贯性检查
- foreshadow_manager: 伏笔管理
- style_consistency: 风格一致性验证
- write_output: 写入输出
- update_context: 更新上下文
"""

from .split import SplitNovelTask
from .entity_extract import EntityExtractTask
from .entity_validate import EntityValidateTask
from .suggest_replacements import SuggestReplacementsTask
from .entity_replace import EntityReplaceTask
from .decompose import DecomposeBookTask
from .decompose_advanced import DecomposeAdvancedTask
from .inject_profile import InjectProfileTask
from .style_analysis import StyleAnalysisTask
from .outline_extract import OutlineExtractTask
from .chapter_plan import ChapterPlanTask
from .content_generate import ContentGenerateTask
from .audit_revise import AuditReviseTask
from .continuity_check import ContinuityCheckTask
from .foreshadow_manager import ForeshadowManagerTask
from .style_consistency import StyleConsistencyTask
from .write_output import WriteOutputTask
from .update_context import UpdateContextTask

__all__ = [
    "SplitNovelTask",
    "EntityExtractTask",
    "EntityValidateTask",
    "SuggestReplacementsTask",
    "EntityReplaceTask",
    "DecomposeBookTask",
    "DecomposeAdvancedTask",
    "InjectProfileTask",
    "StyleAnalysisTask",
    "OutlineExtractTask",
    "ChapterPlanTask",
    "ContentGenerateTask",
    "AuditReviseTask",
    "ContinuityCheckTask",
    "ForeshadowManagerTask",
    "StyleConsistencyTask",
    "WriteOutputTask",
    "UpdateContextTask"
]
