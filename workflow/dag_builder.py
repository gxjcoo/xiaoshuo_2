"""
DAG 构建器 - 定义工作流任务图

声明所有任务节点及其依赖关系
"""

from typing import Dict, List, Optional

from .engine import DAG
from .tasks.split import SplitNovelTask
from .tasks.decompose import DecomposeBookTask
from .tasks.decompose_advanced import DecomposeAdvancedTask
from .tasks.inject_profile import InjectProfileTask
from .tasks.style_analysis import StyleAnalysisTask
from .tasks.outline_extract import OutlineExtractTask
from .tasks.entity_rewrite import EntityRewriteTask
from .tasks.chapter_plan import ChapterPlanTask
from .tasks.content_generate import ContentGenerateTask
from .tasks.audit_revise import AuditReviseTask
from .tasks.continuity_check import ContinuityCheckTask
from .tasks.foreshadow_manager import ForeshadowManagerTask
from .tasks.style_consistency import StyleConsistencyTask
from .tasks.write_output import WriteOutputTask
from .tasks.update_context import UpdateContextTask


def build_chapter_dag(
    chapter_number: int,
    enable_decompose: bool = False,
    use_advanced_decompose: bool = False,
    enable_entity_rewrite: bool = True,
    enable_context_update: bool = True,
    enable_continuity_check: bool = True,
    enable_foreshadow_manager: bool = True,
    enable_style_consistency: bool = True
) -> DAG:
    """
    构建单章处理的 DAG
    
    Args:
        chapter_number: 章节号
        enable_decompose: 是否包含拆书任务
        use_advanced_decompose: 是否使用高级拆书（适用于长篇小说）
        enable_entity_rewrite: 是否启用实体改写
        enable_context_update: 是否更新上下文
        enable_continuity_check: 是否启用连贯性检查
        enable_foreshadow_manager: 是否启用伏笔管理
        enable_style_consistency: 是否启用风格一致性验证
        
    Returns:
        DAG 实例
    """
    dag = DAG()
    
    # 添加所有节点
    dag.add_node(SplitNovelTask())
    dag.add_node(StyleAnalysisTask())
    dag.add_node(OutlineExtractTask())
    dag.add_node(ChapterPlanTask())
    dag.add_node(ContentGenerateTask())
    dag.add_node(AuditReviseTask())
    dag.add_node(WriteOutputTask())
    
    # 可选节点
    if enable_decompose:
        if use_advanced_decompose:
            dag.add_node(DecomposeAdvancedTask())
            # 覆盖 inject_profile 的依赖
            inject_node = InjectProfileTask()
            inject_node.deps = ["decompose_advanced"]
            dag.add_node(inject_node)
        else:
            dag.add_node(DecomposeBookTask())
            dag.add_node(InjectProfileTask())
        # 手动添加 inject_profile 到 chapter_plan 的依赖
        dag.add_edge("inject_profile", "chapter_plan")
    
    if enable_entity_rewrite:
        dag.add_node(EntityRewriteTask())
    
    if enable_context_update:
        dag.add_node(UpdateContextTask())
    
    # 新增的可选节点
    if enable_continuity_check:
        dag.add_node(ContinuityCheckTask())
    
    if enable_foreshadow_manager:
        dag.add_node(ForeshadowManagerTask())
    
    if enable_style_consistency:
        dag.add_node(StyleConsistencyTask())
    
    return dag


def build_full_dag(
    start_chapter: int,
    end_chapter: int,
    enable_decompose: bool = True,
    use_advanced_decompose: bool = False,
    enable_entity_rewrite: bool = True,
    enable_context_update: bool = True,
    enable_continuity_check: bool = True,
    enable_foreshadow_manager: bool = True,
    enable_style_consistency: bool = True,
    volume_size: int = 20
) -> DAG:
    """
    构建完整工作流的 DAG（多章处理，支持分卷）
    
    Args:
        start_chapter: 起始章节
        end_chapter: 结束章节
        enable_decompose: 是否包含拆书任务
        use_advanced_decompose: 是否使用高级拆书（适用于长篇小说）
        enable_entity_rewrite: 是否启用实体改写
        enable_context_update: 是否更新上下文
        enable_continuity_check: 是否启用连贯性检查
        enable_foreshadow_manager: 是否启用伏笔管理
        enable_style_consistency: 是否启用风格一致性验证
        volume_size: 每卷章节数（用于分卷处理）
        
    Returns:
        DAG 实例
    """
    dag = DAG()
    
    # 添加全局节点
    dag.add_node(SplitNovelTask())
    
    # 拆书和设定注入节点
    if enable_decompose:
        if use_advanced_decompose:
            dag.add_node(DecomposeAdvancedTask())
            # 覆盖 inject_profile 的依赖
            inject_node = InjectProfileTask()
            inject_node.deps = ["decompose_advanced"]
            dag.add_node(inject_node)
        else:
            dag.add_node(DecomposeBookTask())
            dag.add_node(InjectProfileTask())
    
    # 添加每章的处理节点
    for chapter_num in range(start_chapter, end_chapter + 1):
        # 为每章创建带编号的节点
        chapter_nodes = _create_chapter_nodes(
            chapter_num,
            enable_entity_rewrite,
            enable_context_update,
            enable_continuity_check,
            enable_foreshadow_manager,
            enable_style_consistency,
            start_chapter
        )
        
        for node in chapter_nodes:
            dag.add_node(node)
    
    return dag


def _create_chapter_nodes(
    chapter_number: int,
    enable_entity_rewrite: bool,
    enable_context_update: bool,
    enable_continuity_check: bool = True,
    enable_foreshadow_manager: bool = True,
    enable_style_consistency: bool = True,
    start_chapter: int = 1
) -> list:
    """为单章创建所有处理节点"""
    
    # 全局任务 ID 列表（不添加章节号）
    global_task_ids = {"split_novel", "decompose_book", "decompose_advanced", "inject_profile"}
    
    # 需要严格串行执行的任务（依赖前一章的同类型任务）
    serial_task_ids = {"entity_rewrite", "update_context"}
    
    class ChapterTaskWrapper:
        """包装任务节点，添加章节号到 ID"""
        def __init__(self, task, chapter_num):
            self.task = task
            self.chapter_num = chapter_num
            self._id = f"{task.id}_ch{chapter_num}"
            self._chapter_number = chapter_num
        
        @property
        def id(self):
            return self._id
        
        @property
        def name(self):
            return f"{self.task.name} (第{self.chapter_num}章)"
        
        @property
        def deps(self):
            # 全局依赖保持原样，章节依赖添加章节号
            result = []
            for dep in self.task.deps:
                if dep in global_task_ids:
                    result.append(dep)
                else:
                    result.append(f"{dep}_ch{self.chapter_num}")
            
            # 对需要串行的任务，添加前章依赖
            if self.task.id in serial_task_ids and self.chapter_num > start_chapter:
                result.append(f"{self.task.id}_ch{self.chapter_num - 1}")
            
            return result
        
        def execute(self, context):
            # 设置章节号到上下文
            context["chapter_number"] = self.chapter_num
            return self.task.execute(context)
        
        def validate_inputs(self, context):
            context["chapter_number"] = self.chapter_num
            return self.task.validate_inputs(context)
        
        def get_required_keys(self):
            return self.task.get_required_keys()
        
        def get_output_keys(self):
            return self.task.get_output_keys()
    
    nodes = []
    
    # 风格分析节点
    nodes.append(ChapterTaskWrapper(StyleAnalysisTask(), chapter_number))
    
    # 骨架抽取节点
    nodes.append(ChapterTaskWrapper(OutlineExtractTask(), chapter_number))
    
    # 实体改写节点（可选）
    if enable_entity_rewrite:
        nodes.append(ChapterTaskWrapper(EntityRewriteTask(), chapter_number))
    
    # 意图规划节点
    nodes.append(ChapterTaskWrapper(ChapterPlanTask(), chapter_number))
    
    # 正文生成节点
    nodes.append(ChapterTaskWrapper(ContentGenerateTask(), chapter_number))
    
    # 审计修订节点
    nodes.append(ChapterTaskWrapper(AuditReviseTask(), chapter_number))
    
    # 连贯性检查节点（可选）
    if enable_continuity_check:
        nodes.append(ChapterTaskWrapper(ContinuityCheckTask(), chapter_number))
    
    # 伏笔管理节点（可选）
    if enable_foreshadow_manager:
        nodes.append(ChapterTaskWrapper(ForeshadowManagerTask(), chapter_number))
    
    # 风格一致性验证节点（可选）
    if enable_style_consistency:
        nodes.append(ChapterTaskWrapper(StyleConsistencyTask(), chapter_number))
    
    # 写入输出节点
    nodes.append(ChapterTaskWrapper(WriteOutputTask(), chapter_number))
    
    # 更新上下文节点（可选）
    if enable_context_update:
        nodes.append(ChapterTaskWrapper(UpdateContextTask(), chapter_number))
    
    return nodes


def get_dag_description(enable_decompose: bool = True, use_advanced_decompose: bool = False) -> Dict[str, List[str]]:
    """
    获取 DAG 的人类可读描述
    
    Args:
        enable_decompose: 是否启用拆书功能
        use_advanced_decompose: 是否使用高级拆书
        
    Returns:
        字典，键为节点 ID，值为依赖列表
    """
    description = {
        "split_novel": [],
        "style_analysis": ["split_novel"],
        "outline_extract": ["split_novel"],
        "entity_rewrite": ["split_novel"],
        "chapter_plan": ["style_analysis", "outline_extract", "entity_rewrite"],
        "content_generate": ["chapter_plan"],
        "audit_revise": ["content_generate"],
        "continuity_check": ["audit_revise"],
        "foreshadow_manager": ["audit_revise"],
        "style_consistency": ["audit_revise"],
        "write_output": ["continuity_check", "foreshadow_manager", "style_consistency"],
        "update_context": ["write_output"]
    }
    
    # 如果启用拆书，添加相关节点和依赖
    if enable_decompose:
        if use_advanced_decompose:
            description["decompose_advanced"] = ["split_novel"]
            description["inject_profile"] = ["decompose_advanced"]
        else:
            description["decompose_book"] = ["split_novel"]
            description["inject_profile"] = ["decompose_book"]
        description["chapter_plan"].append("inject_profile")
    
    return description


def print_dag_structure(enable_decompose: bool = True, use_advanced_decompose: bool = False):
    """打印 DAG 结构"""
    description = get_dag_description(enable_decompose, use_advanced_decompose)
    
    print("\n工作流 DAG 结构:")
    print("-" * 50)
    
    for node_id, deps in description.items():
        if deps:
            print(f"  {node_id} <- {', '.join(deps)}")
        else:
            print(f"  {node_id} (起点)")
    
    print("-" * 50)
    print()
