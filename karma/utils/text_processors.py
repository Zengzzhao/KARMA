"""
KARMA 文本处理工具。

本模块提供多种文本处理函数，
用于文本清理、规范化和预处理。
"""

import re
import logging
from typing import List, Dict, Set
from pathlib import Path

logger = logging.getLogger(__name__)


class TextProcessor:
    """
    用于文档预处理的文本工具。

    本类提供文本清理和规范化功能，
    为科学文献文本处理提供通用工具。
    """

    def __init__(self):
        """初始化文本处理器。"""
        self.biomedical_abbreviations = self._load_biomedical_abbreviations()
        self.stopwords = self._load_stopwords()

    def clean_text(self, text: str) -> str:
        """
        清理并规范化待处理文本。

        参数：
            text: 待处理的文本

        返回：
            清理后的文本
        """
        if not text:
            return ""

        # 删除不可打印字符
        text = ''.join(char for char in text if char.isprintable() or char.isspace())

        # 统一空白字符
        text = re.sub(r'\\s+', ' ', text)
        text = re.sub(r'\\n\\s*\\n', '\\n\\n', text)

        # 修正字符编码问题
        encoding_fixes = {
            'â€™': "'",
            'â€œ': '"',
            'â€\\x9d': '"',
            'â€"': '-',
            'Ã¡': 'á',
            'Ã©': 'é',
            'Ã­': 'í',
            'Ã³': 'ó',
            'Ãº': 'ú'
        }

        for bad, good in encoding_fixes.items():
            text = text.replace(bad, good)

        return text.strip()

    def normalize_biomedical_text(self, text: str) -> str:
        """
        规范化科学文献文本。

        参数：
            text: 待处理的文本

        返回：
            规范化后的文本
        """
        # 规范化希腊字母和符号
        greek_mapping = {
            'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta',
            'ε': 'epsilon', 'ζ': 'zeta', 'η': 'eta', 'θ': 'theta',
            'ι': 'iota', 'κ': 'kappa', 'λ': 'lambda', 'μ': 'mu',
            'ν': 'nu', 'ξ': 'xi', 'ο': 'omicron', 'π': 'pi',
            'ρ': 'rho', 'σ': 'sigma', 'τ': 'tau', 'υ': 'upsilon',
            'φ': 'phi', 'χ': 'chi', 'ψ': 'psi', 'ω': 'omega'
        }

        for greek, latin in greek_mapping.items():
            text = text.replace(greek, latin)

        # 规范化单位和符号
        unit_mapping = {
            '°C': ' degrees Celsius',
            '°F': ' degrees Fahrenheit',
            '±': ' plus/minus ',
            '≤': ' less than or equal to ',
            '≥': ' greater than or equal to ',
            '→': ' leads to ',
            '←': ' derived from ',
            '↑': ' increases ',
            '↓': ' decreases '
        }

        for symbol, replacement in unit_mapping.items():
            text = text.replace(symbol, replacement)

        return text

    def extract_sentences(self, text: str) -> List[str]:
        """
        在保留缩写的前提下提取句子。

        参数：
            text: 待处理的文本

        返回：
            句子列表
        """
        # 保护缩写，避免将缩写中的句点识别为句子边界
        protected_text = text

        # 保护常见缩写，避免被误判为句末。
        for abbrev in self.biomedical_abbreviations:
            pattern = f"\\\\b{re.escape(abbrev)}\\\\.\\\\s+"
            protected_text = re.sub(pattern, f"{abbrev}[DOT] ", protected_text)

        # 按句末标点划分句子
        sentences = re.split(r'[.!?]+\\s+', protected_text)

        # 还原受保护的缩写
        sentences = [sent.replace('[DOT]', '.') for sent in sentences]

        # 过滤过短句子
        sentences = [sent.strip() for sent in sentences if len(sent.strip()) > 10]

        return sentences

    def remove_references(self, text: str) -> str:
        """
        删除文本中的参考文献部分和引用标记。

        参数：
            text: 待处理的文本

        返回：
            删除参考文献和引用标记后的文本
        """
        # 删除参考文献部分
        ref_patterns = [
            r'\\n\\s*REFERENCES\\s*\\n.*$',
            r'\\n\\s*References\\s*\\n.*$',
            r'\\n\\s*Bibliography\\s*\\n.*$',
            r'\\n\\s*BIBLIOGRAPHY\\s*\\n.*$'
        ]

        for pattern in ref_patterns:
            text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

        # 删除正文中的引用标记
        citation_patterns = [
            r'\\([^)]*\\d{4}[^)]*\\)',  # 作者与年份格式的引用
            r'\\[\\d+(?:,\\s*\\d+)*\\]',  # [1, 2, 3]
            r'\\([^)]*et al\\.?[^)]*\\)',  # 多作者与年份格式的引用
        ]

        for pattern in citation_patterns:
            text = re.sub(pattern, '', text)

        return text

    def extract_keywords(self, text: str, min_length: int = 3) -> Set[str]:
        """
        提取潜在领域关键词。

        参数：
            text: 待处理的文本
            min_length: 关键词的最小长度

        返回：
            候选关键词集合
        """
        # 转换为小写后处理
        text_lower = text.lower()

        # 提取潜在术语。
        patterns = [
            r'\\b[a-z]+-?[0-9]+[a-z]*\\b',  # 历史规则：匹配带数字的基因符号
            r'\\b[a-z]+(?:ase|in|ism|osis|itis|oma)\\b',  # 历史规则：匹配医学词语后缀
            r'\\b(?:anti|pro|pre|post|sub|super|hyper|hypo)-[a-z]+\\b'  # 历史规则：匹配医学词语前缀
        ]

        keywords = set()

        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            keywords.update(match for match in matches if len(match) >= min_length)

        # 删除停用词
        keywords = keywords - self.stopwords

        return keywords

    def _load_biomedical_abbreviations(self) -> Set[str]:
        """加载常见缩写。"""
        abbreviations = {
            'Dr', 'Prof', 'vs', 'etc', 'i.e', 'e.g', 'cf', 'et al',
            'DNA', 'RNA', 'mRNA', 'tRNA', 'rRNA', 'miRNA',
            'PCR', 'qPCR', 'RT-PCR', 'ELISA', 'FACS', 'HPLC',
            'mg', 'μg', 'ng', 'kg', 'mL', 'μL', 'nL',
            'mM', 'μM', 'nM', 'pM', 'pH', 'pI',
            'min', 'hr', 'sec', 'mol', 'bp', 'kb', 'Mb',
            'Fig', 'Table', 'Eq', 'Ref', 'Suppl'
        }
        return abbreviations

    def _load_stopwords(self) -> Set[str]:
        """加载常用英文停用词。"""
        stopwords = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for',
            'from', 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on',
            'that', 'the', 'to', 'was', 'were', 'will', 'with', 'the',
            'this', 'but', 'they', 'have', 'had', 'what', 'said', 'each',
            'which', 'she', 'do', 'how', 'their', 'if', 'up', 'out', 'many',
            'then', 'them', 'these', 'so', 'some', 'her', 'would', 'make',
            'like', 'into', 'him', 'time', 'two', 'more', 'go', 'no', 'way',
            'could', 'my', 'than', 'first', 'been', 'call', 'who', 'oil',
            'its', 'now', 'find', 'long', 'down', 'day', 'did', 'get', 'come',
            'made', 'may', 'part'
        }
        return stopwords
