"""
实体抽取智能体模块

实体抽取智能体负责：
1. 从摘要文本中识别科学计量指标
2. 按科学计量领域分类实体
3. 在有明确依据时保留实体的规范化标识
"""

from .agent import EntityExtractionAgent

__all__ = ['EntityExtractionAgent']
