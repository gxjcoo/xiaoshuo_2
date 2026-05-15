"""测试共享 fixture：把项目根目录加进 sys.path，避免被测代码必须先安装。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
