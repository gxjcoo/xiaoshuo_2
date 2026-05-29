"""
TaskNode 基类 - 定义任务节点的统一接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class TaskNode(ABC):
    """任务节点基类，所有工作流步骤必须继承此类"""

    def __init__(self):
        self._context: Dict[str, Any] = {}

    @property
    @abstractmethod
    def id(self) -> str:
        """节点唯一标识"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """节点显示名称"""
        pass

    @property
    def deps(self) -> List[str]:
        """依赖的任务 ID 列表，子类可覆盖"""
        return []

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务逻辑
        
        Args:
            context: 工作流上下文，包含前置节点的输出和共享数据
            
        Returns:
            本节点的输出结果字典
        """
        pass

    def validate_inputs(self, context: Dict[str, Any]) -> bool:
        """
        验证输入是否满足执行条件
        
        Args:
            context: 工作流上下文
            
        Returns:
            True 表示输入有效，False 表示缺少必要输入
        """
        return True

    def can_skip(self, context: Dict[str, Any]) -> bool:
        """
        判断是否可以跳过此节点（如已完成且结果仍有效）
        
        Args:
            context: 工作流上下文
            
        Returns:
            True 表示可跳过
        """
        return False

    def get_required_keys(self) -> List[str]:
        """
        返回执行所需的 context 键列表，用于输入验证
        子类应覆盖此方法以声明依赖
        """
        return []

    def get_output_keys(self) -> List[str]:
        """
        返回本节点输出的键列表，用于 DAG 构建和验证
        子类应覆盖此方法以声明输出
        """
        return []
