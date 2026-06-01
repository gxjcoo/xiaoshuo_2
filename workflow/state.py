"""
StateStore - 工作流状态持久化管理

负责保存和恢复工作流执行状态，支持中断后继续执行

优化：任务输出存储到独立文件，状态文件只保留元数据，避免文件膨胀
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class StateStore:
    """工作流状态存储管理器"""

    def __init__(self, state_file: str = "workflow_state.json", output_dir: str = None):
        """
        初始化状态存储
        
        Args:
            state_file: 状态文件路径
            output_dir: 任务输出存储目录（默认为 state_file 同级的 task_outputs 目录）
        """
        self.state_file = state_file
        self.state: Dict[str, Any] = {}
        
        # 任务输出存储目录
        if output_dir is None:
            base_dir = os.path.dirname(os.path.abspath(state_file))
            output_dir = os.path.join(base_dir, "task_outputs")
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def create_new_run(self, dag_definition: Dict[str, Any]) -> str:
        """
        创建新的工作流运行
        
        Args:
            dag_definition: DAG 定义数据（不再存入状态文件，每次运行时重建）
            
        Returns:
            run_id: 运行唯一标识
        """
        run_id = str(uuid.uuid4())[:8]
        self.state = {
            "run_id": run_id,
            "status": "running",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "dag_node_count": len(dag_definition.get("nodes", {})),
            "tasks": {},
            "context": {}
        }
        self._save()
        return run_id

    def load_existing_run(self) -> Optional[Dict[str, Any]]:
        """
        加载已有的工作流运行状态
        
        Returns:
            状态字典，如果文件不存在返回 None
        """
        if not os.path.exists(self.state_file):
            return None
        
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                self.state = json.load(f)
            print(f"已加载工作流状态: run_id={self.state.get('run_id')}")
            return self.state
        except (json.JSONDecodeError, Exception) as e:
            print(f"警告: 加载状态文件失败: {e}")
            return None

    def update_task_status(
        self,
        task_id: str,
        status: str,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """
        更新任务状态
        
        Args:
            task_id: 任务 ID
            status: 状态 (pending/running/completed/failed/skipped)
            outputs: 任务输出（存到独立文件，不放入状态文件）
            error: 错误信息
        """
        if task_id not in self.state.get("tasks", {}):
            self.state.setdefault("tasks", {})[task_id] = {
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "duration_seconds": 0,
                "has_outputs": False,
                "error": None
            }
        
        task_state = self.state["tasks"][task_id]
        task_state["status"] = status
        
        if status == "running":
            task_state["started_at"] = datetime.now().isoformat()
        elif status in ("completed", "failed", "skipped"):
            task_state["completed_at"] = datetime.now().isoformat()
            # 计算持续时间
            if task_state.get("started_at"):
                start = datetime.fromisoformat(task_state["started_at"])
                end = datetime.fromisoformat(task_state["completed_at"])
                task_state["duration_seconds"] = (end - start).total_seconds()
        
        # 任务输出存储到独立文件，避免状态文件膨胀
        if outputs:
            self._save_task_outputs(task_id, outputs)
            task_state["has_outputs"] = True
        if error:
            task_state["error"] = error
        
        self.state["updated_at"] = datetime.now().isoformat()
        self._save()

    def set_context(self, key: str, value: Any):
        """设置上下文数据"""
        self.state.setdefault("context", {})[key] = value
        self._save()

    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文数据"""
        return self.state.get("context", {}).get(key, default)

    def set_global_context(self, global_context: Dict[str, Any]):
        """保存全局配置（用于恢复时重建上下文）"""
        self.state["global_context"] = global_context
        self._save()

    def get_task_status(self, task_id: str) -> str:
        """获取任务状态"""
        return self.state.get("tasks", {}).get(task_id, {}).get("status", "pending")

    def get_task_outputs(self, task_id: str) -> Dict[str, Any]:
        """获取任务输出（从独立文件加载）"""
        # 优先从独立文件加载
        outputs = self._load_task_outputs(task_id)
        if outputs:
            return outputs
        # 兼容旧格式：如果状态中还有 outputs 字段
        return self.state.get("tasks", {}).get(task_id, {}).get("outputs", {})

    def set_overall_status(self, status: str):
        """设置整体状态"""
        self.state["status"] = status
        self.state["updated_at"] = datetime.now().isoformat()
        self._save()

    def get_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        tasks = self.state.get("tasks", {})
        summary = {
            "run_id": self.state.get("run_id"),
            "status": self.state.get("status"),
            "created_at": self.state.get("created_at"),
            "updated_at": self.state.get("updated_at"),
            "total_tasks": len(tasks),
            "completed": sum(1 for t in tasks.values() if t.get("status") == "completed"),
            "failed": sum(1 for t in tasks.values() if t.get("status") == "failed"),
            "skipped": sum(1 for t in tasks.values() if t.get("status") == "skipped"),
            "pending": sum(1 for t in tasks.values() if t.get("status") == "pending"),
            "total_duration": sum(t.get("duration_seconds", 0) for t in tasks.values())
        }
        return summary

    def _save_task_outputs(self, task_id: str, outputs: Dict[str, Any]):
        """将任务输出保存到独立文件"""
        output_file = os.path.join(self.output_dir, f"{task_id}_output.json")
        tmp_file = output_file + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(outputs, f, ensure_ascii=False, indent=2, default=str)
            # 原子替换
            if os.name == "nt" and os.path.exists(output_file):
                os.remove(output_file)
            os.rename(tmp_file, output_file)
        except Exception as e:
            print(f"警告: 保存任务输出失败 [{task_id}]: {e}")
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except:
                    pass

    def _load_task_outputs(self, task_id: str) -> Dict[str, Any]:
        """从独立文件加载任务输出"""
        output_file = os.path.join(self.output_dir, f"{task_id}_output.json")
        if not os.path.exists(output_file):
            return {}
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"警告: 加载任务输出失败 [{task_id}]: {e}")
            return {}

    def _save(self):
        """保存状态到文件（原子写入，防止损坏）"""
        tmp_file = self.state_file + ".tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            # 原子替换：先写临时文件再rename
            if os.name == "nt":  # Windows
                if os.path.exists(self.state_file):
                    os.remove(self.state_file)
            os.rename(tmp_file, self.state_file)
        except Exception as e:
            print(f"警告: 保存状态文件失败: {e}")
            # 清理临时文件
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except:
                    pass
