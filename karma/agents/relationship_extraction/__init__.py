"""
关系抽取智能体模块

关系抽取智能体负责：
1. 识别已抽取实体之间的关系
2. 按科学计量关系标签对关系分类
3. 处理同一实体对的多种关系
"""

from .agent import RelationshipExtractionAgent

__all__ = ['RelationshipExtractionAgent']