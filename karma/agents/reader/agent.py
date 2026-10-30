"""
阅读分块智能体实现

阅读分块智能体负责文档分块和相关性评分，
为后续处理筛选有效内容。
"""

from karma.agents.scientometrics_prompts import READER

import logging
from typing import List, Dict, Tuple
import re

from karma.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ReaderAgent(BaseAgent):
    """
    负责文档分块和相关性评分的阅读智能体。

    本智能体负责：
    1. 将规范化文本划分为段落级逻辑块
    2. 根据领域知识为每个片段赋予相关性分数
    3. 根据相关性阈值过滤内容
    4. 识别标题、章节等文档结构特征
    """

    def __init__(self, client, model_name: str):
        """
        初始化阅读分块智能体。

        参数：
            client: OpenAI 客户端实例
            model_name: 大语言模型名称
        """
        system_prompt = READER

        super().__init__(client, model_name, system_prompt)

    def process(self, content: str, relevance_threshold: float = 0.2) -> Tuple[List[Dict], List[Dict]]:
        """
        划分文本，并评估每个片段的相关性。

        参数：
            content: 待分块的文本内容
            relevance_threshold: 保留或处理片段所需的最低相关性评分

        返回：
            返回元组 (all_segments, relevant_segments)
        """
        # 划分逻辑片段
        segments = self._split_into_segments(content)

        # 评估各片段的相关性
        scored_segments = self._score_segments_batch(segments)

        # 筛选相关片段
        relevant_segments = [
            seg for seg in scored_segments
            if seg.get('score', 0.0) >= relevance_threshold
        ]

        return scored_segments, relevant_segments

    def _split_into_segments(self, content: str) -> List[Dict]:
        """
        根据文本结构划分逻辑片段。

        参数：
            content: 待分块的文本内容

        返回：
            片段字典列表
        """
        segments = []

        # 按双换行符划分段落
        raw_segments = content.split('\n\n')

        for i, segment_text in enumerate(raw_segments):
            segment_text = segment_text.strip()
            if not segment_text:
                continue

            # 根据内容判断章节类型
            section_type = self._identify_section_type(segment_text)

            segment = {
                'text': segment_text,
                'score': 0.0,  # 由后续评分步骤填充
                'section': section_type,
                'position': i,
                'word_count': len(segment_text.split())
            }

            segments.append(segment)

        return segments

    def _identify_section_type(self, text: str) -> str:
        """
        根据内容模式识别章节类型。

        参数：
            text: 待处理的文本

        返回：
            章节类型标识
        """
        text_lower = text.lower()

        # 常见章节标题
        section_patterns = {
            'abstract': [r'^abstract\b', r'summary\b'],
            'introduction': [r'^introduction\b', r'^background\b'],
            'methods': [r'^methods?\b', r'^methodology\b', r'^materials\b', r'^experimental\b'],
            'results': [r'^results?\b', r'^findings\b', r'^outcomes?\b'],
            'discussion': [r'^discussion\b', r'^conclusion\b', r'^implications\b'],
            'references': [r'^references?\b', r'^bibliography\b', r'^\d+\.\s+\w+.*et al'],
            'acknowledgments': [r'^acknowledgments?\b', r'^acknowledgements?\b'],
            'funding': [r'^funding\b', r'^grants?\b', r'^financial\b'],
            'supplementary': [r'^supplement', r'^appendix\b', r'^additional\b']
        }

        for section_type, patterns in section_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return section_type

        # 未识别出章节标题时，根据内容特征分类
        if len(text.split()) < 10:
            return 'header'
        elif re.search(r'\d+\.\s+\w+.*\(\d{4}\)', text):  # 引用格式
            return 'references'
        elif text.startswith(('Figure', 'Table', 'Fig.')):
            return 'figure_caption'
        else:
            return 'content'

    def _score_segments_batch(self, segments: List[Dict]) -> List[Dict]:
        """
        批量评估多个片段的相关性。

        参数：
            segments: 待处理的文本片段列表

        返回：
            包含相关性评分的片段列表
        """
        # 分批处理片段以提高效率
        batch_size = 5
        scored_segments = []

        for i in range(0, len(segments), batch_size):
            batch = segments[i:i+batch_size]
            scores = self._batch_score_relevance(batch)

            for j, segment in enumerate(batch):
                if j < len(scores):
                    segment['score'] = scores[j]
                else:
                    segment['score'] = self._get_default_score(segment)
                scored_segments.append(segment)

        return scored_segments

    def _batch_score_relevance(self, segments: List[Dict]) -> List[float]:
        """
        使用大语言模型为一批片段评估相关性。

        参数：
            segments: 待处理的文本片段列表

        返回：
            相关性评分列表
        """
        if not segments:
            return []

        # 构造批量评分提示词
        segment_texts = []
        for i, seg in enumerate(segments):
            section_info = f" [章节: {seg['section']}]" if seg.get('section') != 'content' else ""
            segment_texts.append(f"片段 {i+1}{section_info}:\n{seg['text'][:500]}...")

        prompt = f"""请评估以下片段对科学计量指标抽取的相关性。
按输入顺序输出评分，每行一个，不附加说明。
{chr(10).join(segment_texts)}"""

        try:
            response, _, _, _ = self._make_llm_call(prompt, temperature=0.1)

            lines = response.strip().split('\n')
            scores = []

            for line in lines:
                score = self._extract_float_from_text(line.strip(), default=0.5)
                scores.append(score)

            # 确保每个片段都有评分
            while len(scores) < len(segments):
                scores.append(0.5)

            return scores[:len(segments)]

        except Exception as e:
            logger.warning(f"批量评分失败： {str(e)}")
            return [self._get_default_score(seg) for seg in segments]

    def _get_default_score(self, segment: Dict) -> float:
        """
        根据片段特征返回默认相关性评分。

        参数：
            segment: 待处理的文本片段

        返回：
            默认相关性评分
        """
        section_type = segment.get('section', 'content')
        word_count = segment.get('word_count', 0)

        # 根据章节类型设置默认评分
        section_scores = {
            'results': 0.8,
            'discussion': 0.7,
            'abstract': 0.6,
            'introduction': 0.5,
            'content': 0.5,
            'methods': 0.3,
            'references': 0.1,
            'acknowledgments': 0.1,
            'funding': 0.1,
            'supplementary': 0.2,
            'header': 0.2,
            'figure_caption': 0.4
        }

        base_score = section_scores.get(section_type, 0.5)

        # 根据内容长度调整评分
        if word_count < 10:
            base_score *= 0.5  # 降低过短片段的相关性评分
        elif word_count > 100:
            base_score *= 1.1  # 较长片段可能包含更多有效信息

        return min(1.0, max(0.0, base_score))

    def score_relevance(self, segment: str) -> Tuple[float, int, int, float]:
        """
        为兼容旧接口保留的方法。

        参数：
            segment: 待处理的文本片段

        返回：
            返回元组 (relevance_score, prompt_tokens, completion_tokens, processing_time)
        """
        segment_dict = {'text': segment, 'section': 'content', 'word_count': len(segment.split())}
        scored_segments = self._score_segments_batch([segment_dict])

        if scored_segments:
            return scored_segments[0]['score'], 0, 0, 0.0
        else:
            return 0.5, 0, 0, 0.0

    def split_into_segments(self, content: str) -> List[Dict]:
        """
        为兼容旧接口保留的方法。

        参数：
            content: 待分块的文本内容

        返回：
            片段字典列表
        """
        all_segments, _ = self.process(content)
        return all_segments