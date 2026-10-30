"""冲突消解智能体实现"""

from karma.agents.scientometrics_prompts import CONFLICT_RESOLUTION

import logging
from typing import List, Tuple, Optional
from karma.core.base_agent import BaseAgent
from karma.core.data_structures import KnowledgeTriple

logger = logging.getLogger(__name__)


class ConflictResolutionAgent(BaseAgent):
    """处理矛盾知识的冲突消解智能体。"""

    def __init__(self, client, model_name: str):
        system_prompt = CONFLICT_RESOLUTION
        super().__init__(client, model_name, system_prompt)

    def process(self, new_triples: List[KnowledgeTriple], existing_triples: List[KnowledgeTriple]) -> List[KnowledgeTriple]:
        """消解新增三元组与已有三元组之间的冲突。"""
        return self.resolve_conflicts(new_triples, existing_triples)[0]

    def resolve_conflicts(self, new_triples: List[KnowledgeTriple], existing_triples: List[KnowledgeTriple]) -> Tuple[List[KnowledgeTriple], int, int, float]:
        """检查并消解关系冲突。"""
        final_triples = []

        for new_triple in new_triples:
            conflicting_triple = self._find_contradiction(new_triple, existing_triples)

            if conflicting_triple:
                # 简单消解规则：保留置信度较高的三元组
                if new_triple.confidence > conflicting_triple.confidence:
                    final_triples.append(new_triple)
            else:
                final_triples.append(new_triple)

        return final_triples, 0, 0, 0.0

    def _find_contradiction(self, new_triple: KnowledgeTriple, existing_triples: List[KnowledgeTriple]) -> Optional[KnowledgeTriple]:
        """查找相互矛盾的三元组。"""
        contradiction_pairs = {
            ("treats", "causes"), ("inhibits", "activates"),
            ("increases", "decreases"), ("upregulates", "downregulates")
        }

        for existing in existing_triples:
            if (existing.head.lower() == new_triple.head.lower() and
                existing.tail.lower() == new_triple.tail.lower()):

                rel_pair = (existing.relation, new_triple.relation)
                if rel_pair in contradiction_pairs or rel_pair[::-1] in contradiction_pairs:
                    return existing

        return None