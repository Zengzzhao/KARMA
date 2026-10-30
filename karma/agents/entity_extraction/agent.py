"""指标实体抽取 Agent：从摘要文本中识别科学计量指标。"""

from karma.agents.scientometrics_prompts import ENTITY

import logging
from typing import List, Tuple, Dict
import json
import re

from karma.core.base_agent import BaseAgent
from karma.core.data_structures import KGEntity

logger = logging.getLogger(__name__)


class EntityExtractionAgent(BaseAgent):
    """
    科学计量指标实体抽取 Agent。

    本智能体负责：
    1. 识别科学计量指标
    2. 按领域类型分类实体
    3. 在有明确依据时保留规范化标识
    4. 处理实体名称和别名
    """

    def __init__(self, client, model_name: str):
        """
        初始化实体抽取智能体。

        参数：
            client: OpenAI 客户端实例
            model_name: 大语言模型名称
        """
        system_prompt = ENTITY

        super().__init__(client, model_name, system_prompt)

    def process(self, summaries: List[str]) -> List[KGEntity]:
        """
        从多个文本摘要中抽取实体。

        参数：
            summaries: 文本摘要列表

        返回：
            抽取并去重后的实体列表
        """
        all_entities = []

        for summary in summaries:
            if summary and summary not in ["[OMITTED - Low Relevance]", "[LOW CONTENT]"]:
                entities = self._extract_entities_from_text(summary)
                all_entities.extend(entities)

        # 去除重复实体。
        unique_entities = self._deduplicate_entities(all_entities)

        return unique_entities

    def _extract_entities_from_text(self, text: str) -> List[KGEntity]:
        """
        从单段文本中抽取实体。

        参数：
            text: 待处理的文本

        返回：
            KGEntity 对象列表
        """
        prompt = f"""仅抽取明确命名的 Indicator 实体，不抽取 Paper 实体。
当前论文节点由程序根据元数据创建，无需识别或输出论文标题、DOI。
使用 mention、type、normalized_id、aliases 字段，不得补充无依据的别名或虚构编号。
仅返回 JSON 数组。
待分析文本：
{text}"""

        try:
            response, _, _, _ = self._make_llm_call(prompt, temperature=0.1)

            # 解析 JSON 响应。
            entities_data = self._parse_json_response(response)

            entity_list = []
            for ent_data in entities_data:
                if (isinstance(ent_data, dict) and "mention" in ent_data
                        and str(ent_data.get("type", "")).lower() != "paper"):
                    entity = KGEntity(
                        entity_id=ent_data.get("mention", ""),
                        entity_type=ent_data.get("type", "Unknown"),
                        name=ent_data.get("mention", ""),
                        normalized_id=ent_data.get("normalized_id", "N/A"),
                        aliases=ent_data.get("aliases", [])
                    )
                    entity_list.append(entity)

            return entity_list

        except Exception as e:
            logger.warning(f"文本实体抽取失败： {str(e)}")
            # 模型失败时使用简单正则规则兜底。
            return self._fallback_entity_extraction(text)

    def _fallback_entity_extraction(self, text: str) -> List[KGEntity]:
        """
        模型抽取失败时，使用已有模式匹配规则回退提取。

        参数：
            text: 待处理的文本

        返回：
            KGEntity 对象列表
        """
        entities = []

        # 旧版通用正则兜底规则；主流程优先使用模型结果。
        patterns = {
            'Gene': [
                r'\b[A-Z][A-Z0-9]{2,}[a-z]?\b',  # 大写缩写或符号
                r'\b[A-Z]{1,2}[0-9]+[A-Z]?\b'     # 字母数字组合
            ],
            'Protein': [
                r'\b[A-Z][a-z]+[0-9]*\s*receptor\b',  # 受体名称
                r'\b[A-Z][a-z]+ase\b',                # 以 ase 结尾的名称
                r'\b[A-Z][a-z]+in\b'                  # 以 in 结尾的名称
            ],
            'Drug': [
                r'\b[a-z]+mycin\b',                   # 兼容旧版后缀
                r'\b[a-z]+cillin\b',                  # 兼容旧版后缀
                r'\b[a-z]+statin\b'                   # 兼容旧版后缀
            ],
            'Disease': [
                r'\b[a-z]+\s+cancer\b',               # 兼容旧版疾病表达
                r'\b[a-z]+\s+disease\b',              # 兼容旧版疾病表达
                r'\b[a-z]+\s+syndrome\b'              # 兼容旧版疾病表达
            ]
        }

        for entity_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    mention = match.group().strip()
                    if len(mention) > 2:  # 忽略过短匹配。
                        entity = KGEntity(
                            entity_id=mention,
                            entity_type=entity_type,
                            name=mention,
                            normalized_id="N/A"
                        )
                        entities.append(entity)

        return entities

    def _deduplicate_entities(self, entities: List[KGEntity]) -> List[KGEntity]:
        """
        根据名称相似性合并重复实体。

        参数：
            entities: 待处理的实体集合

        返回：
            去重后的实体列表
        """
        if not entities:
            return []

        unique_entities = {}

        for entity in entities:
            # 创建用于比较的规范化键。
            key = entity.name.lower().strip()

                # 已存在时合并信息。
            if key in unique_entities:
                existing = unique_entities[key]

                # 优先保留更具体的实体类型。
                if entity.entity_type != "Unknown" and existing.entity_type == "Unknown":
                    existing.entity_type = entity.entity_type

                # 合并别名。
                if entity.aliases:
                    existing.aliases.extend(entity.aliases)
                    existing.aliases = list(set(existing.aliases))  # 删除重复项

                # 优先保留有效的规范化编号。
                if entity.normalized_id != "N/A" and existing.normalized_id == "N/A":
                    existing.normalized_id = entity.normalized_id

            else:
                unique_entities[key] = entity

        return list(unique_entities.values())

    def extract_entities(self, text: str) -> Tuple[List[KGEntity], int, int, float]:
        """
        为兼容旧接口保留的方法。

        参数：
            text: 待处理的文本

        返回：
            返回元组 (entity_list, prompt_tokens, completion_tokens, processing_time)
        """
        entities = self._extract_entities_from_text(text)
        return entities, 0, 0, 0.0  # 词元数由内部调用统一统计。
