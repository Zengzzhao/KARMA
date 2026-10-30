"""摘要 Agent：将高相关性文献片段压缩为保留证据的摘要。"""

from karma.agents.scientometrics_prompts import SUMMARIZER

import logging
from typing import List, Tuple

from karma.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SummarizerAgent(BaseAgent):
    """
    负责文本片段摘要生成的智能体。

    本智能体负责：
    1. 将高相关性片段压缩为简洁摘要
    2. 保留指标名称、公式、限制条件和数值信息
    3. 保留实体关系和定量信息
    4. 过滤相关性过低的内容
    """

    def __init__(self, client, model_name: str):
        """
        初始化摘要生成智能体。

        参数：
            client: OpenAI 客户端实例
            model_name: 大语言模型名称
        """
        system_prompt = SUMMARIZER

        super().__init__(client, model_name, system_prompt)

    def process(self, segments: List[str], relevance_threshold: float = 0.2) -> List[str]:
        """
        为多个文本片段生成摘要。

        参数：
            segments: 待处理的文本片段列表
            relevance_threshold: 保留或处理片段所需的最低相关性评分

        返回：
            摘要列表
        """
        summaries = []

        for segment in segments:
            if isinstance(segment, dict):
                text = segment.get('text', '')
                relevance = segment.get('score', 1.0)
            else:
                text = segment
                relevance = 1.0  # 未提供评分时默认视为相关

            if relevance < relevance_threshold:
                summaries.append("[OMITTED - Low Relevance]")
                continue

            summary = self._summarize_single_segment(text)
            summaries.append(summary)

        return summaries

    def _summarize_single_segment(self, text: str) -> str:
        """
        为单个文本片段生成摘要。

        参数：
            text: 待处理的文本

        返回：
            生成的摘要文本
        """
        # 跳过过短的片段
        if len(text.split()) < 15:
            return text  # 文本过短、无法有效压缩时直接返回原文

        prompt = f"""请生成 100 个词以内的科学计量指标抽取式摘要，保留原文语言。
输入中存在完整公式、局限性陈述、贡献归属和关系证据时，优先原样保留。
遵守系统规则，仅输出纯文本摘要。
待分析文本：
{text}"""

        try:
            summary, _, _, _ = self._make_llm_call(prompt, temperature=0.2)

            # 执行基本校验和清理
            summary = summary.strip()

            # 处理空响应或低质量响应
            if not summary or summary.lower() in ['[low content]', 'low content', 'n/a']:
                # 回退处理：提取关键句
                return self._extract_key_sentences(text)

            # 确保摘要在长度限制内
            if len(summary.split()) > 120:  # 允许一定的长度浮动
                # 保留句子结构后截断文本
                sentences = summary.split('. ')
                truncated_summary = ""
                word_count = 0

                for sentence in sentences:
                    sentence_words = len(sentence.split())
                    if word_count + sentence_words <= 100:
                        truncated_summary += sentence + ". "
                        word_count += sentence_words
                    else:
                        break

                summary = truncated_summary.strip()

            return summary

        except Exception as e:
            logger.warning(f"片段摘要生成失败： {str(e)}")
            return self._extract_key_sentences(text)

    def _extract_key_sentences(self, text: str) -> str:
        """
        模型摘要失败时，通过提取关键句生成回退摘要。

        参数：
            text: 待处理的文本

        返回：
            从文本中提取的关键句
        """
        sentences = text.split('. ')

        # 根据指标定义、关系词和数值信息评估句子重要性。
        scored_sentences = []

        for sentence in sentences:
            score = self._score_sentence_importance(sentence)
            scored_sentences.append((sentence, score))

        # 按评分排序并选取高分句子
        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        # 在词数限制内选取高分句子
        selected_sentences = []
        word_count = 0

        for sentence, score in scored_sentences:
            sentence_words = len(sentence.split())
            if word_count + sentence_words <= 100 and score > 0.3:
                selected_sentences.append(sentence)
                word_count += sentence_words

        if selected_sentences:
            return '. '.join(selected_sentences) + '.'
        else:
            # 最终回退为原文前 100 个词
            words = text.split()[:100]
            return ' '.join(words) + '...'

    def _score_sentence_importance(self, sentence: str) -> float:
        """
        评估句子对科学计量知识抽取的重要性。

        参数：
            sentence: 待评分的句子

        返回：
            重要性评分（0～1）
        """
        sentence_lower = sentence.lower()
        score = 0.0

        # 高价值的指标、关系和评价词。
        high_value_terms = [
            'inhibit', 'activate', 'regulate', 'express', 'bind', 'interact',
            'cause', 'treat', 'prevent', 'induce', 'suppress', 'enhance',
            'protein', 'gene', 'enzyme', 'receptor', 'pathway', 'mechanism',
            'disease', 'cancer', 'tumor', 'therapy', 'treatment', 'drug',
            'significant', 'increase', 'decrease', 'effect', 'response'
        ]

        # 统计高价值词语
        for term in high_value_terms:
            if term in sentence_lower:
                score += 0.1

        # 为含数值数据的句子加分
        import re
        if re.search(r'\d+\.?\d*\s*(%|mg|μg|ng|mM|μM|nM|p\s*[<>=])', sentence):
            score += 0.3

        # 为疑似实体名称（首字母大写词语）加分
        capitalized_words = re.findall(r'\b[A-Z][A-Za-z0-9-]+\b', sentence)
        score += len(capitalized_words) * 0.05

        # 对过短或过长的句子扣分
        word_count = len(sentence.split())
        if word_count < 5:
            score *= 0.5
        elif word_count > 50:
            score *= 0.8

        return min(1.0, score)

    def summarize_segment(self, segment: str) -> Tuple[str, int, int, float]:
        """
        为兼容旧接口保留的方法。

        参数：
            segment: 待处理的文本片段

        返回：
            返回元组 (summary, prompt_tokens, completion_tokens, processing_time)
        """
        summary = self._summarize_single_segment(segment)
        return summary, 0, 0, 0.0  # 词元数由内部调用统一统计。
