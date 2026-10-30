"""模式对齐智能体实现"""

from karma.agents.scientometrics_prompts import SCHEMA_ALIGNMENT

import logging
from typing import List, Tuple
from karma.core.base_agent import BaseAgent
from karma.core.data_structures import KGEntity, KnowledgeTriple

logger = logging.getLogger(__name__)


class SchemaAlignmentAgent(BaseAgent):
    """负责实体类型分类和关系规范化的模式对齐智能体。"""

    def __init__(self, client, model_name: str):
        system_prompt = SCHEMA_ALIGNMENT
        super().__init__(client, model_name, system_prompt)

    def process(self, entities: List[KGEntity], relationships: List[KnowledgeTriple]) -> Tuple[List[KGEntity], List[KnowledgeTriple]]:
        """将实体和关系对齐到标准模式。"""
        aligned_entities = self.align_entities(entities)[0]
        aligned_relationships = self.align_relationships(relationships)
        return aligned_entities, aligned_relationships

    def align_entities(self, entities: List[KGEntity]) -> Tuple[List[KGEntity], int, int, float]:
        """根据科学计量领域的实体类型进行分类。"""
        for entity in entities:
            if entity.entity_type == "Unknown":
                entity.entity_type = self._classify_entity_type(entity.name)
        return entities, 0, 0, 0.0

    def _classify_entity_type(self, entity_name: str) -> str:
        """使用已有的简单规则对实体类型分类。"""
        name_lower = entity_name.lower()

        # 兼容旧版类型规则。
        if any(suffix in name_lower for suffix in ['mycin', 'cillin', 'statin', 'inhibitor']):
            return "Drug"

        if entity_name.isupper() and len(entity_name) <= 10:
            return "Gene"

        if any(suffix in name_lower for suffix in ['ase', 'receptor', 'protein']):
            return "Protein"

        if any(keyword in name_lower for keyword in ['cancer', 'disease', 'syndrome', 'disorder']):
            return "Disease"

        return "Indicator"  # 默认类型

    def align_relationships(self, triples: List[KnowledgeTriple]) -> List[KnowledgeTriple]:
        """规范化关系标签。"""
        for triple in triples:
            triple.relation = self._normalize_relation(triple.relation)
        return triples

    def _normalize_relation(self, relation: str) -> str:
        """将关系名称转换为标准形式。"""
        synonyms = {
            "inhibit": "inhibits", "inhibited": "inhibits",
            "treat": "treats", "treated": "treats",
            "cause": "causes", "caused": "causes",
            "activate": "activates", "activates": "activates",
            "associated with": "associated_with",
            "interacts with": "interacts_with"
        }
        return synonyms.get(relation.lower(), relation.lower())
