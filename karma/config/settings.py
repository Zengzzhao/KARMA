"""
KARMA 框架的配置设置。

管理模型设置、
接口配置和处理流程参数。
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """大语言模型调用配置。"""
    name: str = "gpt-4o"
    api_key: str = ""
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    timeout: int = 60


@dataclass
class PipelineConfig:
    """处理流程参数配置。"""
    relevance_threshold: float = 0.2
    integration_threshold: float = 0.6
    batch_size: int = 5
    max_segments: int = 100
    max_entities_per_segment: int = 20
    enable_caching: bool = True
    parallel_processing: bool = False


@dataclass
class AgentConfig:
    """各智能体的参数配置。"""
    ingestion: Dict = field(default_factory=lambda: {"extract_metadata": True})
    reader: Dict = field(default_factory=lambda: {"segment_min_length": 30})
    summarizer: Dict = field(default_factory=lambda: {"max_summary_length": 100})
    entity_extraction: Dict = field(default_factory=lambda: {"min_entity_length": 2})
    relationship_extraction: Dict = field(default_factory=lambda: {"min_confidence": 0.3})
    schema_alignment: Dict = field(default_factory=lambda: {"use_ontology_mapping": True})
    conflict_resolution: Dict = field(default_factory=lambda: {"resolution_strategy": "confidence"})
    evaluator: Dict = field(default_factory=lambda: {"confidence_weight": 0.5, "clarity_weight": 0.25, "relevance_weight": 0.25})


@dataclass
class LoggingConfig:
    """日志配置。"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file_path: Optional[str] = None
    max_file_size: int = 10_000_000  # 日志文件大小上限：10 MB
    backup_count: int = 5


@dataclass
class KARMAConfig:
    """KARMA 框架的主配置类。"""
    model: ModelConfig = field(default_factory=ModelConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # 输出设置
    output_dir: str = "output"
    save_intermediate: bool = True
    save_debug_steps: bool = True
    debug_dir: Optional[str] = None  # 默认使用 <output_dir>/debug
    export_format: str = "json"  # 可选格式：json、csv 或 both

    # 性能设置
    enable_metrics: bool = True
    memory_limit_mb: int = 1024

    def to_dict(self) -> Dict:
        """将配置转换为字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'KARMAConfig':
        """从字典创建配置。"""
        config = cls()

        # 更新模型配置
        if 'model' in data:
            model_data = data['model']
            config.model = ModelConfig(**model_data)

        # 更新流程配置
        if 'pipeline' in data:
            pipeline_data = data['pipeline']
            config.pipeline = PipelineConfig(**pipeline_data)

        # 更新智能体配置
        if 'agents' in data:
            agents_data = data['agents']
            config.agents = AgentConfig(**agents_data)

        # 更新日志配置
        if 'logging' in data:
            logging_data = data['logging']
            config.logging = LoggingConfig(**logging_data)

        # 更新其他字段
        for key, value in data.items():
            if key not in ['model', 'pipeline', 'agents', 'logging'] and hasattr(config, key):
                setattr(config, key, value)

        return config

    def validate(self) -> bool:
        """
        验证配置是否合法。

        返回：
            配置有效时返回 True

        异常：
            ValueError：配置无效
        """
        # 验证模型配置
        if not self.model.api_key:
            raise ValueError("必须提供接口密钥")

        if not (0.0 <= self.model.temperature <= 2.0):
            raise ValueError("采样温度必须介于 0.0 和 2.0 之间")

        # 验证流程配置
        if not (0.0 <= self.pipeline.relevance_threshold <= 1.0):
            raise ValueError("相关性阈值必须介于 0.0 和 1.0 之间")

        if not (0.0 <= self.pipeline.integration_threshold <= 1.0):
            raise ValueError("整合阈值必须介于 0.0 和 1.0 之间")

        if self.pipeline.batch_size <= 0:
            raise ValueError("批次大小必须为正数")

        # 验证输出目录
        output_path = Path(self.output_dir)
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ValueError(f"无法创建输出目录： {e}")

        return True

    def setup_logging(self):
        """根据配置初始化日志。"""
        logging_level = getattr(logging, self.logging.level.upper(), logging.INFO)

        # 配置基本日志
        handlers = []

        # 控制台日志处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging_level)
        console_formatter = logging.Formatter(self.logging.format)
        console_handler.setFormatter(console_formatter)
        handlers.append(console_handler)

        # 按配置添加文件日志处理器
        if self.logging.file_path:
            try:
                from logging.handlers import RotatingFileHandler
                file_handler = RotatingFileHandler(
                    self.logging.file_path,
                    maxBytes=self.logging.max_file_size,
                    backupCount=self.logging.backup_count
                )
                file_handler.setLevel(logging_level)
                file_formatter = logging.Formatter(self.logging.format)
                file_handler.setFormatter(file_formatter)
                handlers.append(file_handler)
            except Exception as e:
                logger.warning(f"文件日志初始化失败： {e}")

        # 配置根日志记录器
        logging.basicConfig(
            level=logging_level,
            format=self.logging.format,
            handlers=handlers,
            force=True
        )

        # 设置指定日志记录器的级别
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)


def load_config(config_path: Union[str, Path]) -> KARMAConfig:
    """
    从文件加载配置。

    参数：
        config_path: 配置文件路径

    返回：
        加载后的配置

    异常：
        FileNotFoundError：配置文件不存在
        ValueError：配置文件无效
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在： {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.suffix.lower() == '.json':
                data = json.load(f)
            else:
                # 尝试按 JSON 格式解析
                data = json.load(f)

        config = KARMAConfig.from_dict(data)
        config.validate()
        return config

    except json.JSONDecodeError as e:
        raise ValueError(f"配置文件中的 JSON 格式无效： {e}")
    except Exception as e:
        raise ValueError(f"配置加载失败： {e}")


def save_config(config: KARMAConfig, config_path: Union[str, Path]):
    """
    将配置保存到文件。

    参数：
        config: 配置对象
        config_path: 配置文件路径
    """
    config_path = Path(config_path)

    # 确保父目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"配置已保存到 {config_path}")

    except Exception as e:
        logger.error(f"配置保存失败： {e}")
        raise


def create_default_config(api_key: str, output_dir: str = "output") -> KARMAConfig:
    """
    使用指定的接口密钥创建默认配置。

    参数：
        api_key: OpenAI 接口密钥
        output_dir: 输出目录路径

    返回：
        默认配置
    """
    config = KARMAConfig()
    config.model.api_key = api_key
    config.output_dir = output_dir

    return config


def get_environment_config() -> KARMAConfig:
    """
    根据环境变量创建配置。

    返回：
        根据环境变量生成的配置
    """
    import os

    config = KARMAConfig()

    # 从环境变量读取模型配置
    if os.getenv('KARMA_API_KEY'):
        config.model.api_key = os.getenv('KARMA_API_KEY')
    if os.getenv('KARMA_BASE_URL'):
        config.model.base_url = os.getenv('KARMA_BASE_URL')
    if os.getenv('KARMA_MODEL'):
        config.model.name = os.getenv('KARMA_MODEL')

    # 从环境变量读取流程配置
    if os.getenv('KARMA_RELEVANCE_THRESHOLD'):
        config.pipeline.relevance_threshold = float(os.getenv('KARMA_RELEVANCE_THRESHOLD'))
    if os.getenv('KARMA_INTEGRATION_THRESHOLD'):
        config.pipeline.integration_threshold = float(os.getenv('KARMA_INTEGRATION_THRESHOLD'))

    # 从环境变量读取输出配置
    if os.getenv('KARMA_OUTPUT_DIR'):
        config.output_dir = os.getenv('KARMA_OUTPUT_DIR')

    return config