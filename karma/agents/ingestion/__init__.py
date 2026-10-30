"""
文档接收智能体模块

文档接收智能体负责：
1. 接收并规范化原始文档文本
2. 提取标题、作者、发表日期等元数据
3. 规范化文本格式并处理常见字符识别错误
"""

from .agent import IngestionAgent

__all__ = ['IngestionAgent']