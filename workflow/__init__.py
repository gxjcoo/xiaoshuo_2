"""
小说工作流引擎 - 基于 DAG 的任务编排系统

主要组件：
- base.py: TaskNode 基类定义
- engine.py: DAG 引擎核心
- state.py: 状态持久化管理
- progress.py: 进度追踪与可视化
- tasks/: 具体任务节点实现
"""

from .base import TaskNode
from .engine import DAG, WorkflowEngine
from .state import StateStore
from .progress import ProgressTracker

__all__ = ["TaskNode", "DAG", "WorkflowEngine", "StateStore", "ProgressTracker"]
