"""质量评估智能体实现"""

from karma.agents.scientometrics_prompts import EVALUATOR

import logging
from typing import List, Tuple
from karma.core.base_agent import BaseAgent
from karma.core.data_structures import KnowledgeTriple

logger = logging.getLogger(__name__)


class EvaluatorAgent(BaseAgent):
    """负责最终质量评估及整合判断的智能体。"""

    def __init__(self, client, model_name: str, integrate_threshold: float = 0.6):
        system_prompt = EVALUATOR
        super().__init__(client, model_name, system_prompt)
        self.integrate_threshold = integrate_threshold

    def process(self, triples: List[KnowledgeTriple]) -> List[KnowledgeTriple]:
        """根据质量评分评估并筛选三元组。"""
        return self.finalize_triples(triples)[0]

    def finalize_triples(self, candidate_triples: List[KnowledgeTriple]) -> Tuple[List[KnowledgeTriple], int, int, float]:
        """根据整合阈值筛选三元组。"""
        integrated_triples = []

        for triple in candidate_triples:
            # 确保各项评分均已设置
            if triple.confidence <= 0:
                triple.confidence = 0.5
            if triple.clarity <= 0:
                triple.clarity = 0.5
            if triple.relevance <= 0:
                triple.relevance = 0.5

            # 计算整合评分
            integration_score = self._aggregate_scores(triple)

            # 保留达到阈值的三元组
            if integration_score >= self.integrate_threshold:
                integrated_triples.append(triple)

        return integrated_triples, 0, 0, 0.0

    def _aggregate_scores(self, triple: KnowledgeTriple) -> float:
        """将各项质量评分合并为最终评分。"""
        # 加权平均：置信度占 50%，清晰度占 25%，相关性占 25%
        return (0.5 * triple.confidence + 0.25 * triple.clarity + 0.25 * triple.relevance)