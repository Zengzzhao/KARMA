"""
KARMA：使用多智能体大语言模型自动构建和补充知识图谱

通过多个专用大语言模型智能体抽取、验证和整合科学知识，
形成结构化知识图谱的多智能体框架。

主要类：
    KARMAPipeline：文档处理主流程
    KnowledgeTriple：抽取的知识关系
    KGEntity：知识图谱实体
    KARMAConfig：配置管理

示例：
    >>> from karma import KARMAPipeline
    >>> from karma.config import create_default_config
    >>>
    >>> config = create_default_config(api_key="your-api-key")
    >>> pipeline = KARMAPipeline.from_config(config)
    >>> result = pipeline.process_document("path/to/document.pdf")
    >>> print(f"已抽取 {len(result.integrated_triples)} 个知识三元组")
"""

__version__ = "1.0.0"
__author__ = "Yuxing Lu"
__email__ = "yxlu0613@gmail.com"

# 导入核心模块
from .core.pipeline import KARMAPipeline
from .core.data_structures import (
    KnowledgeTriple,
    KGEntity,
    IntermediateOutput,
    KnowledgeGraph,
    DocumentMetadata,
    ProcessingMetrics
)

# 导入配置模块
from .config import KARMAConfig, load_config, save_config

# 导入智能体，供直接调用或扩展使用
from .agents import (
    IngestionAgent,
    ReaderAgent,
    SummarizerAgent,
    EntityExtractionAgent,
    RelationshipExtractionAgent,
    SchemaAlignmentAgent,
    ConflictResolutionAgent,
    EvaluatorAgent
)

__all__ = [
    # 核心类
    'KARMAPipeline',
    'KnowledgeTriple',
    'KGEntity',
    'IntermediateOutput',
    'KnowledgeGraph',
    'DocumentMetadata',
    'ProcessingMetrics',

    # 配置
    'KARMAConfig',
    'load_config',
    'save_config',

    # 智能体，供直接调用或扩展使用
    'IngestionAgent',
    'ReaderAgent',
    'SummarizerAgent',
    'EntityExtractionAgent',
    'RelationshipExtractionAgent',
    'SchemaAlignmentAgent',
    'ConflictResolutionAgent',
    'EvaluatorAgent'
]


def get_version() -> str:
    """获取 KARMA 版本字符串。"""
    return __version__


def get_info() -> dict:
    """获取 KARMA 软件包信息。"""
    return {
        'name': 'KARMA',
        'version': __version__,
        'author': __author__,
        'email': __email__,
        'description': '多智能体大语言模型知识图谱构建与补充',
        'agents': [
            'IngestionAgent', 'ReaderAgent', 'SummarizerAgent',
            'EntityExtractionAgent', 'RelationshipExtractionAgent',
            'SchemaAlignmentAgent', 'ConflictResolutionAgent', 'EvaluatorAgent'
        ]
    }