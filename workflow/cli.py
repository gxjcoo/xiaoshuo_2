"""
工作流 CLI 入口 - 替换 app.py 的主函数

提供命令行接口来执行工作流
"""

import argparse
import os
import sys
from typing import List, Optional

from .engine import DAG, WorkflowEngine
from .dag_builder import (
    build_chapter_dag,
    build_full_dag,
    print_dag_structure
)
from .tasks.split import SplitNovelTask
from .tasks.decompose import DecomposeBookTask
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


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="小说同结构改编工作流引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整工作流（单章）
  python -m workflow.cli run --chapter 1
  
  # 完整工作流（多章）
  python -m workflow.cli run --start 1 --end 10
  
  # 仅拆书分析
  python -m workflow.cli decompose
  
  # 单独执行某个步骤
  python -m workflow.cli run --chapter 1 --only style_analysis
  
  # 恢复中断的工作流
  python -m workflow.cli resume
  
  # 查看工作流状态
  python -m workflow.cli status
  
  # 列出所有任务
  python -m workflow.cli list
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # run 命令
    run_parser = subparsers.add_parser("run", help="执行工作流")
    run_parser.add_argument("--chapter", type=int, help="处理单个章节")
    run_parser.add_argument("--start", type=int, help="起始章节")
    run_parser.add_argument("--end", type=int, help="结束章节")
    run_parser.add_argument("--input_dir", default="input_chapters", help="输入目录")
    run_parser.add_argument("--output_dir", default="output_chapters", help="输出目录")
    run_parser.add_argument("--novel", help="小说文件路径（用于切章）")
    run_parser.add_argument("--no_strict_source_plot", action="store_true", help="关闭严格结构适配")
    run_parser.add_argument("--no_entity_rewrite", action="store_true", help="关闭实体改写")
    run_parser.add_argument("--no_context_update", action="store_true", help="不更新上下文")
    run_parser.add_argument("--no_continuity_check", action="store_true", help="关闭连贯性检查")
    run_parser.add_argument("--no_foreshadow_manager", action="store_true", help="关闭伏笔管理")
    run_parser.add_argument("--no_style_consistency", action="store_true", help="关闭风格一致性验证")
    run_parser.add_argument("--volume_size", type=int, default=20, help="每卷章节数（用于分卷处理）")
    run_parser.add_argument("--length", type=int, default=3000, help="目标字数")
    run_parser.add_argument("--only", help="仅执行指定任务")
    run_parser.add_argument("--resume", action="store_true", help="恢复之前的执行")
    run_parser.add_argument("--state_file", default="workflow_state.json", help="状态文件路径")
    
    # decompose 命令
    decompose_parser = subparsers.add_parser("decompose", help="拆书分析")
    decompose_parser.add_argument("--input_dir", default="input_chapters", help="输入目录")
    decompose_parser.add_argument("--output", default="book_profile.json", help="输出文件")
    decompose_parser.add_argument("--novel", help="小说文件路径")
    
    # resume 命令
    resume_parser = subparsers.add_parser("resume", help="恢复中断的工作流")
    resume_parser.add_argument("--state_file", default="workflow_state.json", help="状态文件路径")
    
    # status 命令
    status_parser = subparsers.add_parser("status", help="查看工作流状态")
    status_parser.add_argument("--state_file", default="workflow_state.json", help="状态文件路径")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出所有任务")
    
    return parser


def cmd_run(args: argparse.Namespace):
    """执行工作流"""
    # 确定处理范围
    if args.chapter:
        start_chapter = args.chapter
        end_chapter = args.chapter
    elif args.start and args.end:
        start_chapter = args.start
        end_chapter = args.end
    else:
        print("错误: 请指定 --chapter 或 --start/--end")
        sys.exit(1)
    
    # 构建 DAG
    enable_decompose = args.novel is not None
    dag = build_full_dag(
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        enable_decompose=enable_decompose,
        enable_entity_rewrite=not args.no_entity_rewrite,
        enable_context_update=not args.no_context_update,
        enable_continuity_check=not args.no_continuity_check,
        enable_foreshadow_manager=not args.no_foreshadow_manager,
        enable_style_consistency=not args.no_style_consistency,
        volume_size=args.volume_size
    )
    
    # 如果指定了 --only，过滤任务
    if args.only:
        # 创建只包含指定任务的 DAG
        filtered_dag = DAG()
        for node_id in dag.nodes:
            if node_id == args.only or node_id in _get_upstream_nodes(dag, args.only):
                filtered_dag.add_node(dag.nodes[node_id])
        dag = filtered_dag
    
    # 显示 DAG 结构
    print_dag_structure()
    
    # 创建引擎并执行
    engine = WorkflowEngine(dag, state_file=args.state_file)
    
    # 设置初始上下文
    engine.context = {
        "start_chapter": start_chapter,
        "end_chapter": end_chapter,
        "input_dir": args.input_dir,
        "output_dir": args.output_dir,
        "novel_path": args.novel,
        "strict_source_plot": not args.no_strict_source_plot,
        "entity_rewrite_enabled": not args.no_entity_rewrite,
        "target_length": args.length,
        "volume_size": args.volume_size
    }
    
    # 执行
    summary = engine.run(resume=args.resume)
    
    # 输出结果
    if summary.get("status") == "completed":
        print(f"\n工作流执行完成！")
    else:
        print(f"\n工作流执行失败: {summary.get('status')}")
        sys.exit(1)


def cmd_decompose(args: argparse.Namespace):
    """执行拆书分析"""
    from .engine import DAG, WorkflowEngine
    
    # 创建仅包含拆书任务的 DAG
    dag = DAG()
    dag.add_node(SplitNovelTask())
    dag.add_node(DecomposeBookTask())
    
    # 创建引擎
    engine = WorkflowEngine(dag)
    
    # 设置上下文
    engine.context = {
        "novel_path": args.novel,
        "chapters_dir": args.input_dir,
        "decompose_output": args.output
    }
    
    # 执行
    summary = engine.run(resume=False)
    
    if summary.get("status") == "completed":
        print(f"\n拆书完成！设定文档已保存至: {args.output}")
    else:
        print(f"\n拆书失败")
        sys.exit(1)


def cmd_resume(args: argparse.Namespace):
    """恢复中断的工作流"""
    from .engine import WorkflowEngine
    from .state import StateStore
    
    # 加载状态
    state = StateStore(args.state_file)
    existing = state.load_existing_run()
    
    if not existing:
        print("未找到可恢复的工作流")
        sys.exit(1)
    
    print(f"恢复工作流: run_id={existing.get('run_id')}")
    
    # 重建 DAG
    dag_definition = existing.get("dag", {})
    dag = DAG()
    
    # 从 tasks 模块导入所有节点类型
    from .tasks import (
        SplitNovelTask, DecomposeBookTask, InjectProfileTask, StyleAnalysisTask,
        OutlineExtractTask, EntityRewriteTask, ChapterPlanTask,
        ContentGenerateTask, AuditReviseTask, ContinuityCheckTask,
        ForeshadowManagerTask, StyleConsistencyTask, WriteOutputTask,
        UpdateContextTask
    )
    
    # 重新创建节点
    task_classes = {
        "split_novel": SplitNovelTask,
        "decompose_book": DecomposeBookTask,
        "inject_profile": InjectProfileTask,
        "style_analysis": StyleAnalysisTask,
        "outline_extract": OutlineExtractTask,
        "entity_rewrite": EntityRewriteTask,
        "chapter_plan": ChapterPlanTask,
        "content_generate": ContentGenerateTask,
        "audit_revise": AuditReviseTask,
        "continuity_check": ContinuityCheckTask,
        "foreshadow_manager": ForeshadowManagerTask,
        "style_consistency": StyleConsistencyTask,
        "write_output": WriteOutputTask,
        "update_context": UpdateContextTask
    }
    
    for node_id, node_info in dag_definition.get("nodes", {}).items():
        if node_id in task_classes:
            dag.add_node(task_classes[node_id]())
    
    # 执行
    engine = WorkflowEngine(dag, state_file=args.state_file)
    summary = engine.run(resume=True)
    
    if summary.get("status") == "completed":
        print(f"\n工作流恢复完成！")
    else:
        print(f"\n工作流恢复失败")
        sys.exit(1)


def cmd_status(args: argparse.Namespace):
    """查看工作流状态"""
    from .state import StateStore
    
    state = StateStore(args.state_file)
    existing = state.load_existing_run()
    
    if not existing:
        print("未找到工作流状态")
        return
    
    summary = state.get_summary()
    
    print("\n工作流状态:")
    print("-" * 50)
    print(f"运行 ID: {summary.get('run_id')}")
    print(f"状态: {summary.get('status')}")
    print(f"创建时间: {summary.get('created_at')}")
    print(f"更新时间: {summary.get('updated_at')}")
    print(f"总任务数: {summary.get('total_tasks')}")
    print(f"已完成: {summary.get('completed')}")
    print(f"失败: {summary.get('failed')}")
    print(f"跳过: {summary.get('skipped')}")
    print(f"待执行: {summary.get('pending')}")
    print(f"总耗时: {summary.get('total_duration', 0):.1f}s")
    print("-" * 50)
    
    # 显示各任务状态
    tasks = existing.get("tasks", {})
    if tasks:
        print("\n任务详情:")
        for task_id, task_info in tasks.items():
            status = task_info.get("status", "pending")
            duration = task_info.get("duration_seconds", 0)
            print(f"  {task_id}: {status} ({duration:.1f}s)")


def cmd_list(args: argparse.Namespace):
    """列出所有任务"""
    print("\n可用任务:")
    print("-" * 50)
    
    tasks = [
        ("split_novel", "切章", "将小说文本分割为章节"),
        ("decompose_book", "拆书", "提取世界观、人物、设定等"),
        ("inject_profile", "设定注入", "将拆书结果注入到故事上下文"),
        ("style_analysis", "风格分析", "分析写作风格"),
        ("outline_extract", "骨架抽取", "提取结构化骨架"),
        ("entity_rewrite", "实体改写", "提取和应用实体映射"),
        ("chapter_plan", "意图规划", "规划章节意图"),
        ("content_generate", "正文生成", "生成章节正文"),
        ("audit_revise", "审计修订", "审计和修订内容"),
        ("continuity_check", "连贯性检查", "检查跨章节连贯性"),
        ("foreshadow_manager", "伏笔管理", "管理伏笔埋设和回收"),
        ("style_consistency", "风格一致性", "验证风格一致性"),
        ("write_output", "写入输出", "写入输出文件"),
        ("update_context", "更新上下文", "更新故事上下文")
    ]
    
    for task_id, name, desc in tasks:
        print(f"  {task_id:<20} {name:<10} {desc}")
    
    print("-" * 50)
    print("\nDAG 依赖关系:")
    print_dag_structure()


def _get_upstream_nodes(dag: DAG, node_id: str) -> set:
    """获取节点的所有上游节点"""
    upstream = set()
    queue = [node_id]
    
    while queue:
        current = queue.pop(0)
        deps = dag.get_dependencies(current)
        for dep in deps:
            if dep not in upstream:
                upstream.add(dep)
                queue.append(dep)
    
    return upstream


def main(args: Optional[List[str]] = None):
    """主入口"""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    if not parsed_args.command:
        parser.print_help()
        sys.exit(0)
    
    # 执行对应的命令
    commands = {
        "run": cmd_run,
        "decompose": cmd_decompose,
        "resume": cmd_resume,
        "status": cmd_status,
        "list": cmd_list
    }
    
    if parsed_args.command in commands:
        commands[parsed_args.command](parsed_args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
