"""
ProgressTracker - 进度追踪与可视化

基于 rich 库实现终端进度条、DAG 状态展示和汇总报告
"""

import time
from typing import Any, Dict, List, Optional

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.tree import Tree
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class ProgressTracker:
    """进度追踪器，提供实时进度显示和最终报告"""

    def __init__(self):
        self.console = Console() if RICH_AVAILABLE else None
        self.progress: Optional[Any] = None
        self.task_ids: Dict[str, Any] = {}
        self.start_time: float = 0
        self.task_timings: Dict[str, float] = {}

    def start_workflow(self, total_tasks: int, dag_tree: Optional[Dict] = None):
        """
        开始工作流进度追踪
        
        Args:
            total_tasks: 总任务数
            dag_tree: DAG 依赖树结构（可选，用于展示）
        """
        self.start_time = time.time()
        
        if not RICH_AVAILABLE:
            print(f"工作流开始，共 {total_tasks} 个任务")
            return
        
        # 展示 DAG 结构
        if dag_tree:
            self._display_dag_tree(dag_tree)
        
        # 创建进度条
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        )
        self.progress.start()
        self.main_task = self.progress.add_task("整体进度", total=total_tasks)

    def start_task(self, task_id: str, task_name: str):
        """
        标记任务开始
        
        Args:
            task_id: 任务 ID
            task_name: 任务显示名称
        """
        self.task_timings[task_id] = time.time()
        
        if not RICH_AVAILABLE:
            print(f"  [{task_id}] 开始: {task_name}")
            return
        
        task_id_rich = self.progress.add_task(
            f"  {task_name}",
            total=1,
            visible=True
        )
        self.task_ids[task_id] = task_id_rich

    def complete_task(self, task_id: str, success: bool = True, message: str = ""):
        """
        标记任务完成
        
        Args:
            task_id: 任务 ID
            success: 是否成功
            message: 附加消息
        """
        duration = 0
        if task_id in self.task_timings:
            duration = time.time() - self.task_timings[task_id]
        
        status = "✓" if success else "✗"
        
        if not RICH_AVAILABLE:
            print(f"  [{task_id}] {status} 完成 ({duration:.1f}s) {message}")
            # 更新主进度
            return
        
        # 更新子任务进度
        if task_id in self.task_ids:
            self.progress.update(self.task_ids[task_id], completed=1)
        
        # 更新主进度
        self.progress.update(self.main_task, advance=1)

    def skip_task(self, task_id: str, reason: str = "已缓存"):
        """
        标记任务跳过
        
        Args:
            task_id: 任务 ID
            reason: 跳过原因
        """
        if not RICH_AVAILABLE:
            print(f"  [{task_id}] - 跳过: {reason}")
            return
        
        # 更新主进度
        self.progress.update(self.main_task, advance=1)

    def fail_task(self, task_id: str, error: str):
        """
        标记任务失败
        
        Args:
            task_id: 任务 ID
            error: 错误信息
        """
        duration = 0
        if task_id in self.task_timings:
            duration = time.time() - self.task_timings[task_id]
        
        if not RICH_AVAILABLE:
            print(f"  [{task_id}] ✗ 失败 ({duration:.1f}s): {error}")
            return
        
        # 更新子任务进度
        if task_id in self.task_ids:
            self.progress.update(self.task_ids[task_id], completed=1)
        
        # 更新主进度
        self.progress.update(self.main_task, advance=1)

    def stop_workflow(self):
        """停止进度追踪"""
        if self.progress:
            self.progress.stop()

    def display_summary(self, summary: Dict[str, Any], task_details: List[Dict[str, Any]]):
        """
        显示最终汇总报告
        
        Args:
            summary: 执行摘要
            task_details: 任务详情列表
        """
        if not RICH_AVAILABLE:
            print("\n" + "=" * 50)
            print("工作流执行完成")
            print(f"总任务: {summary.get('total_tasks', 0)}")
            print(f"完成: {summary.get('completed', 0)}")
            print(f"失败: {summary.get('failed', 0)}")
            print(f"跳过: {summary.get('skipped', 0)}")
            print(f"总耗时: {summary.get('total_duration', 0):.1f}s")
            print("=" * 50)
            return
        
        # 创建汇总表格
        table = Table(title="工作流执行汇总", show_header=True, header_style="bold magenta")
        table.add_column("指标", style="cyan")
        table.add_column("值", style="green")
        
        table.add_row("运行 ID", str(summary.get("run_id", "")))
        table.add_row("状态", self._status_style(summary.get("status", "")))
        table.add_row("总任务数", str(summary.get("total_tasks", 0)))
        table.add_row("已完成", str(summary.get("completed", 0)))
        table.add_row("失败", str(summary.get("failed", 0)))
        table.add_row("跳过", str(summary.get("skipped", 0)))
        table.add_row("总耗时", f"{summary.get('total_duration', 0):.1f}s")
        
        self.console.print()
        self.console.print(table)
        
        # 任务详情表格
        if task_details:
            detail_table = Table(title="任务执行详情", show_header=True, header_style="bold blue")
            detail_table.add_column("任务", style="cyan")
            detail_table.add_column("状态", style="bold")
            detail_table.add_column("耗时", style="green")
            detail_table.add_column("备注", style="dim")
            
            for task in task_details:
                status = task.get("status", "")
                status_display = self._status_style(status)
                duration = f"{task.get('duration', 0):.1f}s"
                note = task.get("error", "") if status == "failed" else task.get("message", "")
                
                detail_table.add_row(
                    task.get("name", ""),
                    status_display,
                    duration,
                    note[:50] if note else ""
                )
            
            self.console.print()
            self.console.print(detail_table)

    def _display_dag_tree(self, dag_tree: Dict):
        """显示 DAG 依赖树"""
        if not RICH_AVAILABLE:
            return
        
        tree = Tree("DAG 任务依赖图")
        self._build_tree(tree, dag_tree)
        self.console.print(tree)
        self.console.print()

    def _build_tree(self, tree: Tree, node: Dict):
        """递归构建树结构"""
        for task_id, children in node.items():
            branch = tree.add(f"[cyan]{task_id}[/cyan]")
            if isinstance(children, dict):
                self._build_tree(branch, children)

    def _status_style(self, status: str) -> str:
        """根据状态返回带样式的文本"""
        if not RICH_AVAILABLE:
            return status
        
        styles = {
            "running": "[bold yellow]运行中[/bold yellow]",
            "completed": "[bold green]完成[/bold green]",
            "failed": "[bold red]失败[/bold red]",
            "skipped": "[dim]- 跳过[/dim]",
            "pending": "[dim]等待中[/dim]"
        }
        return styles.get(status, status)

    def print(self, message: str, style: str = ""):
        """打印消息"""
        if self.console:
            self.console.print(message, style=style)
        else:
            print(message)
