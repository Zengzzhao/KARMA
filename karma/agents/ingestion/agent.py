"""
文档接收智能体实现

文档接收智能体负责文本格式规范化，
并从输入内容中提取元数据。
"""

from karma.agents.scientometrics_prompts import INGESTION

import logging
from typing import Dict, Tuple
import re
from pathlib import Path

from karma.core.base_agent import BaseAgent
from karma.core.data_structures import DocumentMetadata

logger = logging.getLogger(__name__)


class IngestionAgent(BaseAgent):
    """
    负责文档处理和元数据提取的接收智能体。

    本智能体负责：
    1. 处理主流程传入的原始文档文本
    2. 将文档内容转换为一致的规范化文本
    3. 提取标题、作者、日期和 DOI 等元数据
    4. 修正常见字符识别错误并规范化文本
    """

    def __init__(self, client, model_name: str):
        """
        初始化文档接收智能体。

        参数：
            client: OpenAI 客户端实例
            model_name: 大语言模型名称
        """
        system_prompt = INGESTION

        super().__init__(client, model_name, system_prompt)

    def process(self, raw_text: str, source_info: Dict = None) -> Tuple[DocumentMetadata, str]:
        """
        提取原始文本的元数据并规范化正文。

        参数：
            raw_text: 待处理的原始文本
            source_info: 可选的来源信息，例如文件路径或网址

        返回：
            返回元组 (DocumentMetadata, normalized_content)
        """
        # 使用模型提取元数据。
        metadata = self._extract_metadata(raw_text)

        # 清洗正文内容。
        normalized_content = self._normalize_text(raw_text)

        return metadata, normalized_content

    def _extract_metadata(self, text: str) -> DocumentMetadata:
        """
        使用大语言模型提取文档元数据。

        参数：
            text: 待处理的文本

        返回：
            包含提取信息的 DocumentMetadata 对象
        """
        # 截取前 5000 个字符以降低开销，元数据通常位于文档开头
        sample_text = text[:5000] if len(text) > 5000 else text

        prompt = f"""请分析文档片段，提取当前论文中能够确定的以下元数据：
- 标题
- 作者（姓名列表）
- 发表日期（信息充分时使用 YYYY-MM-DD 格式，不猜测缺失部分）
- DOI（数字对象标识符）

未知标题、日期使用 Unknown；作者缺失使用 []；DOI 缺失使用 N/A。
请严格使用以下 JSON 格式返回，保留原文标题和姓名，不添加额外说明：
{{
  "title": "...",
  "authors": ["...", "..."],
  "pub_date": "...",
  "doi": "..."
}}

文档片段：
{sample_text}"""

        try:
            response, _, _, _ = self._make_llm_call(prompt, temperature=0.1)

            # 解析 JSON 响应
            metadata_dict = self._parse_json_response(response)
            if metadata_dict and isinstance(metadata_dict, dict):
                return DocumentMetadata(
                    title=metadata_dict.get("title", "Unknown Title"),
                    authors=metadata_dict.get("authors", []),
                    pub_date=metadata_dict.get("pub_date", "N/A"),
                    doi=metadata_dict.get("doi", "N/A"),
                )

        except Exception as e:
            logger.warning(f"元数据提取失败： {str(e)}")

        # 回退处理：尝试通过正则表达式提取基本元数据
        return self._extract_metadata_fallback(text)

    def _extract_metadata_fallback(self, text: str) -> DocumentMetadata:
        """
        模型提取失败时，通过正则表达式提取元数据。

        参数：
            text: 待处理的文本

        返回：
            包含基本信息的 DocumentMetadata 对象
        """
        metadata = DocumentMetadata()

        # 提取标题，通常取首个符合长度要求的非空行
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 200:  # 合理的标题长度范围
                metadata.title = line
                break

        # 提取 DOI
        doi_pattern = r'10\.\d{4,}(?:\.\d+)?\/[^\s]+'
        doi_match = re.search(doi_pattern, text)
        if doi_match:
            metadata.doi = doi_match.group()

        # 从常见格式中提取可能的作者。
        author_patterns = [
            r'Authors?:?\s*([A-Za-z\s,.-]+?)(?:\n|$)',
            r'By\s+([A-Za-z\s,.-]+?)(?:\n|$)'
        ]
        for pattern in author_patterns:
            author_match = re.search(pattern, text[:1000], re.IGNORECASE)
            if author_match:
                authors_text = author_match.group(1).strip()
                metadata.authors = [
                    author.strip() for author in re.split(r'[,;]', authors_text)
                    if author.strip() and len(author.strip()) > 2
                ]
                break

        return metadata

    def _normalize_text(self, text: str) -> str:
        """
        清洗文本，使后续处理使用统一格式。

        参数：
            text: 待处理的文本

        返回：
            规范化后的文本内容
        """
        # 删除多余空白
        text = re.sub(r'\n\s*\n', '\n\n', text)  # 统一段落换行
        text = re.sub(r'[ \t]+', ' ', text)      # 统一空格

        # 处理常见字符识别错误
        ocr_fixes = {
            r'\bﬁ\b': 'fi',           # 常见连字错误
            r'\bﬂ\b': 'fl',
            r'\b1\b(?=\w)': 'I',      # 修正数字 1 与字母 I 混淆的情况
            r'\b0\b(?=[a-z])': 'o',   # 修正数字 0 与字母 o 混淆的情况
            r'([a-z])1([a-z])': r'\1l\2',  # 修正单词内部数字 1 与字母 l 混淆的情况
        }

        for pattern, replacement in ocr_fixes.items():
            text = re.sub(pattern, replacement, text)

        # 规范化 Unicode 字符
        unicode_fixes = {
            'α': 'alpha',
            'β': 'beta',
            'γ': 'gamma',
            'δ': 'delta',
            'ε': 'epsilon',
            'μ': 'mu',
            '°': ' degrees',
            '±': '+/-',
            '→': ' -> ',
            '←': ' <- ',
            '↑': ' up ',
            '↓': ' down '
        }

        for unicode_char, replacement in unicode_fixes.items():
            text = text.replace(unicode_char, replacement)

        # 清理替换操作引入的多余空格
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def ingest_document(self, raw_text: str) -> Dict:
        """
        为兼容旧接口保留的方法。

        参数：
            raw_text: 待处理的原始文本

        返回：
            包含元数据和正文的字典
        """
        metadata, content = self.process(raw_text)

        return {
            "metadata": metadata.to_dict(),
            "content": content
        }
