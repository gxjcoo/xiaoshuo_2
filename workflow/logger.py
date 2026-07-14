"""
工作流日志工具 - 同时输出到控制台和日志文件

用法:
    from .logger import workflow_logger
    workflow_logger.info("消息")
    workflow_logger.error("错误", exc_info=True)
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional


class WorkflowLogger:
    """工作流专用日志器，同时输出到控制台和文件"""
    
    def __init__(self, log_dir: str = "logs", log_name: Optional[str] = None):
        """
        初始化日志器
        
        Args:
            log_dir: 日志文件目录
            log_name: 日志文件名（默认使用时间戳）
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成日志文件名
        if log_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_name = f"workflow_{timestamp}.log"
        
        self.log_file = os.path.join(log_dir, log_name)
        
        # 创建 logger
        self.logger = logging.getLogger("workflow")
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加 handler
        if not self.logger.handlers:
            # 文件 handler - 记录所有级别
            file_handler = logging.FileHandler(
                self.log_file, encoding="utf-8", mode="a"
            )
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
            
            # 控制台 handler - 只记录 WARNING 及以上
            # 不添加控制台 handler，保持原有的 print 输出习惯
            # 日志文件用于事后排查
    
    def debug(self, msg: str):
        self.logger.debug(msg)
    
    def info(self, msg: str):
        self.logger.info(msg)
    
    def warning(self, msg: str):
        self.logger.warning(msg)
    
    def error(self, msg: str, exc_info: bool = False):
        self.logger.error(msg, exc_info=exc_info)
    
    def critical(self, msg: str, exc_info: bool = False):
        self.logger.critical(msg, exc_info=exc_info)
    
    def task_start(self, task_id: str, task_name: str):
        """记录任务开始"""
        self.info(f"任务开始: {task_id} ({task_name})")
    
    def task_complete(self, task_id: str, duration: float):
        """记录任务完成"""
        self.info(f"任务完成: {task_id} ({duration:.1f}s)")
    
    def task_fail(self, task_id: str, error: str, traceback_str: str = ""):
        """记录任务失败"""
        self.error(f"任务失败: {task_id} | 错误: {error}")
        if traceback_str:
            self.error(f"调用栈:\n{traceback_str}")
    
    def task_retry(self, task_id: str, attempt: int, max_retries: int, delay: float):
        """记录任务重试"""
        self.warning(f"任务重试: {task_id} (尝试 {attempt}/{max_retries})，等待 {delay}s")
    
    def llm_call(self, task_label: str, model: str, attempt: int, max_retries: int):
        """记录LLM调用"""
        self.debug(f"LLM调用: {task_label} | 模型={model} | 尝试 {attempt}/{max_retries}")
    
    def llm_fail(self, task_label: str, error: str):
        """记录LLM调用失败"""
        self.error(f"LLM调用失败: {task_label} | 错误: {error}")
    
    def workflow_start(self, total_tasks: int):
        """记录工作流开始"""
        self.info(f"工作流开始: 共 {total_tasks} 个任务")
    
    def workflow_end(self, status: str, completed: int, failed: int, total_duration: float):
        """记录工作流结束"""
        self.info(f"工作流结束: 状态={status} | 完成={completed} | 失败={failed} | 耗时={total_duration:.1f}s")
    
    def get_log_file(self) -> str:
        """获取日志文件路径"""
        return self.log_file


# 全局单例
workflow_logger = WorkflowLogger()
