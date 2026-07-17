"""统一日志工具模块。

提供带控制台输出的 logger，替代散布各处的 print() 调用。

用法：
    from log_utils import get_logger
    logger = get_logger(__name__)
    logger.info("处理第 %d 章", chapter_number)
    logger.warning("API 调用失败: %s", error, exc_info=True)
"""

import logging
import sys

# 全局标记，避免重复配置
_configured = False


def get_logger(name: str) -> logging.Logger:
    """获取带控制台输出的 logger。

    Args:
        name: logger 名称，通常传 __name__

    Returns:
        配置好的 Logger 实例
    """
    global _configured
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(name)s %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
