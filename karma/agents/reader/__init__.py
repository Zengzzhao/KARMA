"""
阅读分块智能体模块

阅读分块智能体负责：
1. 将规范化文本划分为逻辑块
2. 根据领域知识评估片段相关性
3. 过滤致谢、参考文献等低相关性内容
"""

from .agent import ReaderAgent

__all__ = ['ReaderAgent']