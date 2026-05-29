"""
DAG 引擎核心 - 有向无环图管理和工作流执行

负责：
- DAG 构建和验证
- 拓扑排序
- 任务调度和执行
- 状态管理集成
"""

import json
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Type

from .base import TaskNode
from .state import StateStore
from .progress import ProgressTracker


class DAG:
    """有向无环图（DAG）管理器"""

    def __init__(self):
        self.nodes: Dict[str, TaskNode] = {}
        self.edges: Dict[str, Set[str]] = defaultdict(set)  # node_id -> set of dependent node_ids
        self.reverse_edges: Dict[str, Set[str]] = defaultdict(set)  # node_id -> set of dependency node_ids

    def add_node(self, node: TaskNode):
        """添加任务节点"""
        self.nodes[node.id] = node
        # 自动添加依赖边
        for dep_id in node.deps:
            self.edges[dep_id].add(node.id)
            self.reverse_edges[node.id].add(dep_id)

    def add_edge(self, from_id: str, to_id: str):
        """添加依赖边"""
        if from_id not in self.nodes:
            raise ValueError(f"节点 {from_id} 不存在")
        if to_id not in self.nodes:
            raise ValueError(f"节点 {to_id} 不存在")
        self.edges[from_id].add(to_id)
        self.reverse_edges[to_id].add(from_id)

    def validate(self) -> List[str]:
        """
        验证 DAG 是否有效（无环）
        
        Returns:
            错误信息列表，空列表表示验证通过
        """
        errors = []
        
        # 检查所有依赖的节点是否存在
        for node_id, node in self.nodes.items():
            for dep_id in node.deps:
                if dep_id not in self.nodes:
                    errors.append(f"节点 {node_id} 依赖的节点 {dep_id} 不存在")
        
        # 检查是否有环（使用 Kahn 算法）
        in_degree = defaultdict(int)
        for node_id in self.nodes:
            for dep_id in self.reverse_edges[node_id]:
                in_degree[node_id] += 1
        
        queue = deque([node_id for node_id in self.nodes if in_degree[node_id] == 0])
        visited_count = 0
        
        while queue:
            current = queue.popleft()
            visited_count += 1
            for neighbor in self.edges[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if visited_count != len(self.nodes):
            errors.append("DAG 中存在循环依赖")
        
        return errors

    def topological_sort(self) -> List[str]:
        """
        拓扑排序，返回任务执行顺序
        
        Returns:
            任务 ID 列表，按执行顺序排列
        """
        in_degree = defaultdict(int)
        for node_id in self.nodes:
            for dep_id in self.reverse_edges[node_id]:
                in_degree[node_id] += 1
        
        queue = deque([node_id for node_id in self.nodes if in_degree[node_id] == 0])
        result = []
        
        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbor in sorted(self.edges[current]):  # 排序保证确定性
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        return result

    def get_execution_order(self) -> List[str]:
        """获取执行顺序（拓扑排序的别名）"""
        return self.topological_sort()

    def get_node(self, node_id: str) -> Optional[TaskNode]:
        """获取节点"""
        return self.nodes.get(node_id)

    def get_dependencies(self, node_id: str) -> Set[str]:
        """获取节点的所有依赖"""
        return self.reverse_edges.get(node_id, set())

    def get_dependents(self, node_id: str) -> Set[str]:
        """获取依赖此节点的所有节点"""
        return self.edges.get(node_id, set())

    def to_definition(self) -> Dict[str, Any]:
        """导出 DAG 定义"""
        definition = {
            "nodes": {},
            "edges": []
        }
        for node_id, node in self.nodes.items():
            definition["nodes"][node_id] = {
                "name": node.name,
                "deps": list(node.deps)
            }
        for from_id, to_ids in self.edges.items():
            for to_id in to_ids:
                definition["edges"].append([from_id, to_id])
        return definition


class WorkflowEngine:
    """工作流引擎 - 执行 DAG 定义的工作流"""

    def __init__(
        self,
        dag: DAG,
        state_file: str = "workflow_state.json",
        auto_skip: bool = True
    ):
        """
        初始化工作流引擎
        
        Args:
            dag: DAG 实例
            state_file: 状态文件路径
            auto_skip: 是否自动跳过已完成的任务
        """
        self.dag = dag
        self.state = StateStore(state_file)
        self.progress = ProgressTracker()
        self.auto_skip = auto_skip
        self.context: Dict[str, Any] = {}

    def run(self, resume: bool = True) -> Dict[str, Any]:
        """
        执行工作流
        
        Args:
            resume: 是否尝试恢复之前的执行
            
        Returns:
            执行摘要
        """
        # 验证 DAG
        errors = self.dag.validate()
        if errors:
            print("DAG 验证失败:")
            for error in errors:
                print(f"  - {error}")
            return {"status": "failed", "errors": errors}
        
        # 尝试恢复或创建新运行
        if resume:
            existing_state = self.state.load_existing_run()
            if existing_state:
                print(f"恢复之前的运行: run_id={existing_state.get('run_id')}")
                self.context = existing_state.get("context", {})
            else:
                self.state.create_new_run(self.dag.to_definition())
        else:
            self.state.create_new_run(self.dag.to_definition())
        
        # 获取执行顺序
        execution_order = self.dag.get_execution_order()
        
        # 开始进度追踪
        dag_tree = self._build_dag_tree()
        self.progress.start_workflow(len(execution_order), dag_tree)
        
        # 执行任务
        for task_id in execution_order:
            node = self.dag.get_node(task_id)
            if not node:
                continue
            
            # 检查是否可跳过
            if self.auto_skip and self.state.get_task_status(task_id) == "completed":
                self.progress.skip_task(task_id, "已完成")
                # 加载之前的输出到上下文
                outputs = self.state.get_task_outputs(task_id)
                self.context.update(outputs)
                continue
            
            # 检查输入
            if not node.validate_inputs(self.context):
                self.progress.fail_task(task_id, "输入验证失败")
                self.state.update_task_status(task_id, "failed", error="输入验证失败")
                self.state.set_overall_status("failed")
                continue
            
            # 执行任务
            self.progress.start_task(task_id, node.name)
            self.state.update_task_status(task_id, "running")
            
            try:
                outputs = node.execute(self.context)
                if outputs:
                    self.context.update(outputs)
                    self.state.update_task_status(task_id, "completed", outputs=outputs)
                else:
                    self.state.update_task_status(task_id, "completed")
                self.progress.complete_task(task_id, success=True)
            except Exception as e:
                error_msg = str(e)
                self.state.update_task_status(task_id, "failed", error=error_msg)
                self.progress.fail_task(task_id, error_msg)
                self.state.set_overall_status("failed")
                self.progress.stop_workflow()
                return self.state.get_summary()
        
        # 完成
        self.state.set_overall_status("completed")
        self.progress.stop_workflow()
        
        # 显示汇总报告
        summary = self.state.get_summary()
        task_details = self._collect_task_details()
        self.progress.display_summary(summary, task_details)
        
        return summary

    def run_single_task(self, task_id: str) -> Dict[str, Any]:
        """
        单独执行某个任务（用于调试）
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务输出
        """
        node = self.dag.get_node(task_id)
        if not node:
            raise ValueError(f"任务 {task_id} 不存在")
        
        # 加载已有状态
        self.state.load_existing_run()
        
        print(f"单独执行任务: {node.name} ({task_id})")
        
        # 检查输入
        if not node.validate_inputs(self.context):
            print("警告: 输入验证失败，尝试继续执行...")
        
        # 执行
        try:
            outputs = node.execute(self.context)
            print(f"任务执行成功")
            return outputs or {}
        except Exception as e:
            print(f"任务执行失败: {e}")
            raise

    def list_tasks(self) -> List[Dict[str, Any]]:
        """列出所有任务"""
        tasks = []
        for node_id in self.dag.get_execution_order():
            node = self.dag.get_node(node_id)
            if node:
                tasks.append({
                    "id": node.id,
                    "name": node.name,
                    "deps": list(node.deps),
                    "status": self.state.get_task_status(node.id)
                })
        return tasks

    def _build_dag_tree(self) -> Dict:
        """构建 DAG 树结构用于显示"""
        # 简化版本：返回节点列表
        return {node_id: list(self.dag.get_dependents(node_id)) 
                for node_id in self.dag.nodes}

    def _collect_task_details(self) -> List[Dict[str, Any]]:
        """收集任务详情用于报告"""
        details = []
        for node_id in self.dag.get_execution_order():
            node = self.dag.get_node(node_id)
            if node:
                task_state = self.state.state.get("tasks", {}).get(node_id, {})
                details.append({
                    "id": node_id,
                    "name": node.name,
                    "status": task_state.get("status", "pending"),
                    "duration": task_state.get("duration_seconds", 0),
                    "error": task_state.get("error", "")
                })
        return details
