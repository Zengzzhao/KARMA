"""关系抽取 Agent：从文献摘要中识别指标之间的有向关系。"""

from karma.agents.scientometrics_prompts import RELATIONSHIP

import logging
from typing import List, Tuple
import json

from karma.core.base_agent import BaseAgent
from karma.core.data_structures import KGEntity, KnowledgeTriple

logger = logging.getLogger(__name__)


class RelationshipExtractionAgent(BaseAgent):
    """
    科学计量实体关系抽取 Agent。

    本智能体负责：
    1. 识别已抽取实体之间的关系
    2. 按科学计量关系标签分类
    3. 处理否定和条件性关系
    4. 为抽取的关系提供置信度
    """

    def __init__(self, client, model_name: str):
        """
        初始化关系抽取智能体。

        参数：
            client: OpenAI 客户端实例
            model_name: 大语言模型名称
        """
        system_prompt = RELATIONSHIP

        super().__init__(client, model_name, system_prompt)

    def process(self, summaries: List[str], entities: List[KGEntity]) -> List[KnowledgeTriple]:
        """
        根据给定实体，从摘要中抽取关系。

        参数：
            summaries: 文本摘要列表
            entities: 待处理的实体集合

        返回：
            抽取的知识三元组列表
        """
        if not entities:
            return []

        all_relationships = []

        for summary in summaries:
            if summary and summary not in ["[OMITTED - Low Relevance]", "[LOW CONTENT]"]:
                relationships = self._extract_relationships_from_text(summary, entities)
                all_relationships.extend(relationships)

        # 关系去重
        unique_relationships = self._deduplicate_relationships(all_relationships)

        return unique_relationships

    def _extract_relationships_from_text(self, text: str, entities: List[KGEntity]) -> List[KnowledgeTriple]:
        """
        使用大语言模型从文本中抽取关系。

        参数：
            text: 待处理的文本
            entities: 待处理的实体集合

        返回：
            KnowledgeTriple 对象列表
        """
        if len(entities) < 2:  # 至少需要两个实体才能建立关系。
            return []

        # 为提示词创建实体清单。
        entity_names = [ent.name for ent in entities]
        entity_bullets = "\n".join(
            f"- {ent.name}（类型：{ent.entity_type}）" for ent in entities
        )

        prompt = f"""实体名称清单（端点必须完全匹配；清单本身不是证据）：
{entity_bullets}
按照系统定义抽取有依据的科学计量关系。
仅使用以下文本中的证据，只返回 JSON 数组。
待分析文本：
{text}"""

        try:
            response, _, _, _ = self._make_llm_call(prompt, temperature=0.1)

            # 解析 JSON 响应。
            relations_data = self._parse_json_response(response)

            triples = []
            for rel_data in relations_data:
                if isinstance(rel_data, dict) and all(key in rel_data for key in ["head", "relation", "tail"]):
                    # 检查关系两端是否存在于实体清单。
                    head = rel_data.get("head", "").strip()
                    tail = rel_data.get("tail", "").strip()

                    if self._entity_exists(head, entity_names) and self._entity_exists(tail, entity_names):
                        confidence = float(rel_data.get("confidence", 0.5))
                        evidence = rel_data.get("evidence", "")

                        # 估计清晰度和相关性。
                        clarity = self._estimate_clarity(head, rel_data.get("relation", ""), tail)
                        relevance = self._estimate_relevance(head, rel_data.get("relation", ""), tail)

                        triple = KnowledgeTriple(
                            head=head,
                            relation=rel_data.get("relation", "").strip(),
                            tail=tail,
                            confidence=confidence,
                            clarity=clarity,
                            relevance=relevance,
                            source="relationship_extraction"
                        )
                        triples.append(triple)

            return triples

        except Exception as e:
            logger.warning(f"关系抽取失败： {str(e)}")
            return []

    def _entity_exists(self, entity_name: str, entity_list: List[str]) -> bool:
        """
        检查实体名称是否在列表中，忽略大小写。

        参数：
            entity_name: 待检查的实体名称
            entity_list: 实体名称列表

        返回：
            实体存在时返回 True
        """
        entity_lower = entity_name.lower()
        return any(ent.lower() == entity_lower for ent in entity_list)

    def _estimate_clarity(self, head: str, relation: str, tail: str) -> float:
        """
        估计关系三元组的清晰度。

        参数：
            head: 主体实体
            relation: 关系类型
            tail: 客体实体

        返回：
            清晰度评分（0～1）
        """
        clarity = 0.5  # 基础分数。

        # 具体关系具有更高的清晰度。
        specific_relations = ["treats", "inhibits", "activates", "causes", "regulates"]
        if relation.lower() in specific_relations:
            clarity += 0.2

        # 具体实体通常具有更高的清晰度。
        generic_terms = ["protein", "gene", "drug", "disease", "chemical"]
        if head.lower() not in generic_terms:
            clarity += 0.1
        if tail.lower() not in generic_terms:
            clarity += 0.1

        # 过于宽泛的关系降低清晰度。
        if relation.lower() in ["associated_with", "interacts_with"]:
            clarity -= 0.1

        return min(1.0, max(0.1, clarity))

    def _estimate_relevance(self, head: str, relation: str, tail: str) -> float:
        """
        估计科学计量关系三元组的相关性。

        参数：
            head: 主体实体
            relation: 关系类型
            tail: 客体实体

        返回：
            相关性评分（0～1）
        """
        relevance = 0.5  # 基础分数。

        # 兼容旧版关系相关性规则。
        therapeutic_relations = ["treats", "prevents", "causes", "inhibits", "activates"]
        if relation.lower() in therapeutic_relations:
            relevance += 0.2

        # 旧版领域关键词规则，后续应迁移为指标相关规则。
        disease_keywords = ["cancer", "disease", "disorder", "syndrome", "infection"]
        if any(keyword in head.lower() or keyword in tail.lower() for keyword in disease_keywords):
            relevance += 0.1

        drug_keywords = ["drug", "medication", "inhibitor", "agonist", "antagonist", "therapy"]
        if any(keyword in head.lower() or keyword in tail.lower() for keyword in drug_keywords):
            relevance += 0.1

        return min(1.0, max(0.1, relevance))

    def _deduplicate_relationships(self, relationships: List[KnowledgeTriple]) -> List[KnowledgeTriple]:
        """
        删除重复关系。

        参数：
            relationships: 待去重的关系列表

        返回：
            去重后的关系列表
        """
        if not relationships:
            return []

        unique_rels = {}

        for rel in relationships:
            # 创建去重键。
            key = f"{rel.head.lower()}__{rel.relation.lower()}__{rel.tail.lower()}"

            # 重复关系保留置信度更高的一条。
            if key not in unique_rels or rel.confidence > unique_rels[key].confidence:
                unique_rels[key] = rel

        return list(unique_rels.values())

    def extract_relationships(self, text: str, entities: List[KGEntity]) -> Tuple[List[KnowledgeTriple], int, int, float]:
        """
        为兼容旧接口保留的方法。

        参数：
            text: 待处理的文本
            entities: 待处理的实体集合

        返回：
            返回元组 (relationship_list, prompt_tokens, completion_tokens, processing_time)
        """
        relationships = self._extract_relationships_from_text(text, entities)
        return relationships, 0, 0, 0.0  # 词元数由内部调用统一统计。
