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
from .tasks.decompose_advanced import DecomposeAdvancedTask
from .tasks.inject_profile import InjectProfileTask
from .tasks.style_analysis import StyleAnalysisTask
from .tasks.outline_extract import OutlineExtractTask
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
  
  # 高级拆书（适用于长篇小说）
  python -m workflow.cli decompose --advanced --novel novel.txt
  
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
    run_parser.add_argument("--input_dir", default="chapters", help="输入目录")
    run_parser.add_argument("--output_dir", default="output_chapters", help="输出目录")
    run_parser.add_argument("--novel", help="小说文件路径（用于切章）")
    run_parser.add_argument("--no_strict_source_plot", action="store_true", help="关闭严格结构适配")
    run_parser.add_argument("--no_context_update", action="store_true", help="不更新上下文")
    run_parser.add_argument("--no_continuity_check", action="store_true", help="关闭连贯性检查")
    run_parser.add_argument("--no_foreshadow_manager", action="store_true", help="关闭伏笔管理")
    run_parser.add_argument("--no_style_consistency", action="store_true", help="关闭风格一致性验证")
    run_parser.add_argument("--advanced_decompose", action="store_true", help="使用高级拆书（适用于长篇小说）")
    run_parser.add_argument("--volume_size", type=int, default=20, help="每卷章节数（用于分卷处理）")
    run_parser.add_argument("--length", type=int, default=3000, help="目标字数")
    run_parser.add_argument("--only", help="仅执行指定任务")
    run_parser.add_argument("--resume", action="store_true", help="恢复之前的执行")
    run_parser.add_argument("--state_file", default="workflow_state.json", help="状态文件路径")
    
    # decompose 命令
    decompose_parser = subparsers.add_parser("decompose", help="拆书分析")
    decompose_parser.add_argument("--input_dir", default="chapters", help="输入目录")
    decompose_parser.add_argument("--output", default="book_profile.json", help="输出文件")
    decompose_parser.add_argument("--novel", help="小说文件路径")
    decompose_parser.add_argument("--advanced", action="store_true", help="使用高级拆书模式（适用于长篇小说）")
    decompose_parser.add_argument("--novel_length", type=int, default=0, help="小说总字数（用于自动选择策略）")
    
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
        # 自动检测章节范围
        start_chapter, end_chapter = _auto_detect_chapters(args.input_dir, args.novel)
        if start_chapter is None:
            print("错误: 请指定 --chapter 或 --start/--end，或确保输入目录中有章节文件")
            sys.exit(1)
        print(f"自动检测到章节范围: {start_chapter} - {end_chapter}")
    
    # 构建 DAG
    enable_decompose = args.novel is not None
    use_advanced_decompose = args.advanced_decompose
    
    # 自动检测是否需要高级拆书
    if enable_decompose and not use_advanced_decompose:
        from config import DECOMPOSE_ADVANCED_AUTO, DECOMPOSE_ADVANCED_THRESHOLD
        if DECOMPOSE_ADVANCED_AUTO and args.novel:
            # 检查小说文件大小
            try:
                file_size = os.path.getsize(args.novel)
                # 估算字数（中文约2字节/字）
                estimated_chars = file_size // 2
                if estimated_chars >= DECOMPOSE_ADVANCED_THRESHOLD:
                    use_advanced_decompose = True
                    print(f"自动启用高级拆书模式（估算字数: {estimated_chars:,}）")
            except:
                pass
    
    dag = build_full_dag(
        start_chapter=start_chapter,
        end_chapter=end_chapter,
        enable_decompose=enable_decompose,
        use_advanced_decompose=use_advanced_decompose,
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
    print_dag_structure(enable_decompose, use_advanced_decompose)
    
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
        "target_length": args.length,
        "volume_size": args.volume_size,
        "use_advanced_decompose": use_advanced_decompose
    }
    
    # 执行
    summary = engine.run(resume=args.resume)
    
    # 输出结果
    if summary.get("status") == "completed":
        print(f"\n工作流执行完成！")
        # 显示日志文件位置
        from .logger import workflow_logger
        print(f"详细日志: {workflow_logger.get_log_file()}")
    else:
        print(f"\n工作流执行失败: {summary.get('status')}")
        # 显示日志文件位置
        from .logger import workflow_logger
        print(f"详细日志: {workflow_logger.get_log_file()}")
        # 显示失败任务详情
        tasks = summary.get("tasks", {})
        failed_tasks = [(k, v) for k, v in tasks.items() if v.get("status") == "failed"]
        if failed_tasks:
            print(f"\n失败任务 ({len(failed_tasks)} 个):")
            print("=" * 60)
            for task_id, task_info in failed_tasks:
                error = task_info.get("error", "未知错误")
                tb = task_info.get("traceback", "")
                print(f"\n任务: {task_id}")
                print(f"错误: {error}")
                if tb:
                    print(f"调用栈:\n{tb}")
                print("-" * 60)
        sys.exit(1)


def cmd_decompose(args: argparse.Namespace):
    """执行拆书分析"""
    from .engine import DAG, WorkflowEngine
    
    # 确定是否使用高级拆书
    use_advanced = args.advanced
    
    # 自动检测
    if not use_advanced and args.novel_length > 0:
        from config import DECOMPOSE_ADVANCED_THRESHOLD
        if args.novel_length >= DECOMPOSE_ADVANCED_THRESHOLD:
            use_advanced = True
            print(f"根据小说字数自动启用高级拆书模式")
    
    # 创建拆书 DAG
    dag = DAG()
    dag.add_node(SplitNovelTask())
    
    if use_advanced:
        dag.add_node(DecomposeAdvancedTask())
        print("使用高级拆书模式（适用于长篇小说）")
    else:
        dag.add_node(DecomposeBookTask())
        print("使用标准拆书模式")
    
    # 创建引擎
    engine = WorkflowEngine(dag)
    
    # 设置上下文
    engine.context = {
        "novel_path": args.novel,
        "chapters_dir": args.input_dir,
        "decompose_output": args.output,
        "novel_length": args.novel_length
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
        SplitNovelTask, DecomposeBookTask, DecomposeAdvancedTask, InjectProfileTask, 
        StyleAnalysisTask, OutlineExtractTask, EntityRewriteTask, ChapterPlanTask,
        ContentGenerateTask, AuditReviseTask, ContinuityCheckTask,
        ForeshadowManagerTask, StyleConsistencyTask, WriteOutputTask,
        UpdateContextTask
    )
    
    # 重新创建节点
    task_classes = {
        "split_novel": SplitNovelTask,
        "decompose_book": DecomposeBookTask,
        "decompose_advanced": DecomposeAdvancedTask,
        "inject_profile": InjectProfileTask,
        "style_analysis": StyleAnalysisTask,
        "outline_extract": OutlineExtractTask,
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
    
    # 显示日志文件位置
    from .logger import workflow_logger
    log_file = workflow_logger.get_log_file()
    if os.path.exists(log_file):
        print(f"日志文件: {log_file}")
    
    # 显示各任务状态
    tasks = existing.get("tasks", {})
    if tasks:
        print("\n任务详情:")
        for task_id, task_info in tasks.items():
            status = task_info.get("status", "pending")
            duration = task_info.get("duration_seconds", 0)
            error = task_info.get("error", "")
            status_display = f"{status} ({duration:.1f}s)"
            if status == "failed" and error:
                status_display += f" | 错误: {error}"
            print(f"  {task_id}: {status_display}")
        
        # 显示失败任务的完整调用栈
        failed_tasks = [(k, v) for k, v in tasks.items() if v.get("status") == "failed"]
        if failed_tasks:
            print("\n" + "=" * 60)
            print("失败任务详情:")
            print("=" * 60)
            for task_id, task_info in failed_tasks:
                error = task_info.get("error", "未知错误")
                tb = task_info.get("traceback", "")
                print(f"\n任务: {task_id}")
                print(f"错误: {error}")
                if tb:
                    print(f"调用栈:\n{tb}")
                print("-" * 60)


def cmd_list(args: argparse.Namespace):
    """列出所有任务"""
    print("\n可用任务:")
    print("-" * 50)
    
    tasks = [
        ("split_novel", "切章", "将小说文本分割为章节"),
        ("decompose_book", "拆书", "提取世界观、人物、设定等"),
        ("decompose_advanced", "高级拆书", "适用于长篇小说（50万字以上）"),
        ("inject_profile", "设定注入", "将拆书结果注入到故事上下文"),
        ("style_analysis", "风格分析", "分析写作风格"),
        ("outline_extract", "骨架抽取", "提取结构化骨架"),
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


def _auto_detect_chapters(input_dir: str, novel_path: Optional[str] = None) -> tuple:
    """
    自动检测章节范围
    
    Args:
        input_dir: 输入目录
        novel_path: 小说文件路径（如果有）
    
    Returns:
        (start_chapter, end_chapter) 或 (None, None) 如果未找到章节
    """
    import re
    
    # 如果指定了小说文件，先切章
    if novel_path and os.path.exists(novel_path):
        print(f"检测到小说文件: {novel_path}")
        print("请先运行切章命令: python -m workflow.cli run --novel <file> --chapter 1")
        return None, None
    
    # 扫描输入目录
    if not os.path.exists(input_dir):
        print(f"输入目录不存在: {input_dir}")
        return None, None
    
    # 查找章节文件（格式：0001_chapter.md 或 chapter_0001.md）
    chapter_files = []
    for f in os.listdir(input_dir):
        if f.endswith('.md'):
            # 尝试提取章节号
            match = re.search(r'(\d+)', f)
            if match:
                chapter_num = int(match.group(1))
                chapter_files.append(chapter_num)
    
    if not chapter_files:
        print(f"在 {input_dir} 中未找到章节文件")
        return None, None
    
    chapter_files.sort()
    return chapter_files[0], chapter_files[-1]


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
