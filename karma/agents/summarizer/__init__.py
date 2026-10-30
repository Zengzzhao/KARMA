"""
摘要生成智能体模块

摘要生成智能体负责：
1. 将高相关性片段压缩为简洁摘要
2. 保留知识抽取所需的关键技术细节
3. 保留实体关系和定量数据
"""

from .agent import SummarizerAgent

__all__ = ['SummarizerAgent']