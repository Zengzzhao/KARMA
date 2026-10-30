"""
KARMA 的 PDF 读取工具。

提供 PDF 文本提取功能，
包含错误处理及论文文本清理。
"""

import logging
from pathlib import Path
from typing import Optional

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

logger = logging.getLogger(__name__)


class PDFReader:
    """
    支持错误处理的 PDF 文本提取工具。

    提供 PDF 文本提取、回退处理，
    以及论文文本的清理功能。
    """

    def __init__(self):
        """初始化 PDF 读取器。"""
        if PyPDF2 is None:
            logger.warning("未安装 PyPDF2，无法完整使用 PDF 读取功能。")

    def extract_text(self, pdf_path: Path) -> str:
        """
        从 PDF 文件中提取文本。

        参数：
            pdf_path: PDF 文件路径

        返回：
            提取的文本内容

        异常：
            FileNotFoundError：PDF 文件不存在
            Exception：PDF 读取失败
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在： {pdf_path}")

        if PyPDF2 is None:
            raise ImportError("读取 PDF 需要 PyPDF2，请运行：pip install PyPDF2")

        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                # 检查 PDF 是否加密
                if pdf_reader.is_encrypted:
                    logger.warning(f"PDF {pdf_path} 已加密，正在尝试解密……")
                    try:
                        pdf_reader.decrypt('')  # 尝试使用空密码解密
                    except Exception as e:
                        logger.error(f"PDF 解密失败： {e}")
                        raise

                # 提取所有页面的文本
                total_pages = len(pdf_reader.pages)
                logger.info(f"正在从 {total_pages} 页中提取文本……")

                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\\n\\n"
                    except Exception as e:
                        logger.warning(f"第 {page_num + 1} 页文本提取失败： {e}")
                        continue

                if not text.strip():
                    logger.warning(f"未从 PDF 中提取到文本： {pdf_path}")
                    return ""

                # 对提取的文本进行后处理
                text = self._post_process_text(text)

                logger.info(f"已从 PDF 中提取 {len(text)} 个字符")
                return text

        except Exception as e:
            logger.error(f"PDF 读取失败 {pdf_path}: {str(e)}")
            raise

    def _post_process_text(self, text: str) -> str:
        """
        清理提取的文本以改善文本质量。

        参数：
            text: 待处理的文本

        返回：
            清理并规范化后的文本
        """
        if not text:
            return ""

        # 删除多余空白
        import re
        text = re.sub(r'\\n\\s*\\n', '\\n\\n', text)  # 统一段落换行
        text = re.sub(r'[ \\t]+', ' ', text)  # 统一空格
        text = re.sub(r'\\n ', '\\n', text)  # 删除行首空格

        # 修正常见的 PDF 文本提取问题
        # 去除换行处的断词连字符
        text = re.sub(r'-\\n([a-z])', r'\\1', text)

        # 合并跨行断开的单词
        text = re.sub(r'([a-z])\\n([a-z])', r'\\1\\2', text)

        # 清理多余空格
        text = re.sub(r'\\s+', ' ', text)

        return text.strip()

    def is_pdf_readable(self, pdf_path: Path) -> bool:
        """
        检查 PDF 文件是否可读取。

        参数：
            pdf_path: PDF 文件路径

        返回：
            PDF 可读取时返回 True
        """
        try:
            self.extract_text(pdf_path)
            return True
        except Exception:
            return False

    def get_pdf_info(self, pdf_path: Path) -> Optional[dict]:
        """
        获取 PDF 文件的内置元数据。

        参数：
            pdf_path: PDF 文件路径

        返回：
            PDF 元数据字典，失败时返回 None
        """
        if PyPDF2 is None:
            return None

        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                info = {
                    'pages': len(pdf_reader.pages),
                    'encrypted': pdf_reader.is_encrypted,
                    'metadata': {}
                }

                # 存在元数据时提取对应字段
                if pdf_reader.metadata:
                    metadata = pdf_reader.metadata
                    info['metadata'] = {
                        'title': metadata.get('/Title', ''),
                        'author': metadata.get('/Author', ''),
                        'subject': metadata.get('/Subject', ''),
                        'creator': metadata.get('/Creator', ''),
                        'producer': metadata.get('/Producer', ''),
                        'creation_date': str(metadata.get('/CreationDate', '')),
                        'modification_date': str(metadata.get('/ModDate', ''))
                    }

                return info

        except Exception as e:
            logger.error(f"PDF 信息获取失败： {e}")
            return None