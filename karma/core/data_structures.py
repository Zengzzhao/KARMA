"""
KARMA 框架的核心数据结构。

定义处理流程中使用的基础数据结构，
包括知识三元组、实体和各阶段的中间结果。
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Union
import json


@dataclass
class KnowledgeTriple:
    """
    表示知识图谱中的一条有向关系。

    知识三元组由主体（head）、关系（relation）、
    客体（tail）以及质量评分组成。

    属性：
        head: 主体实体
        relation: 关系类型
        tail: 客体实体
        confidence: 模型置信度评分 [0-1]
        source: 三元组的来源阶段或来源标识
        relevance: 领域相关性评分 [0-1]
        clarity: 语言表达清晰度评分 [0-1]
    """
    head: str
    relation: str
    tail: str
    confidence: float = 0.0
    source: str = "unknown"
    relevance: float = 0.0
    clarity: float = 0.0

    def __str__(self) -> str:
        """返回关系三元组的字符串表示。"""
        return f"({self.head}) -[{self.relation}]-> ({self.tail})"

    def to_dict(self) -> Dict:
        """转换为可序列化的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'KnowledgeTriple':
        """从字典创建实例。"""
        return cls(**data)


@dataclass
class KGEntity:
    """
    表示知识图谱中的规范化实体。

    属性：
        entity_id: 唯一标识符
        entity_type: 实体类型，例如 Paper、Indicator
        name: 显示名称
        normalized_id: 规范化标识，例如论文的 DOI
        aliases: 实体的其他名称
    """
    entity_id: str
    entity_type: str = "Unknown"
    name: str = ""
    normalized_id: str = "N/A"
    aliases: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        """返回实体的字符串表示。"""
        return f"{self.name} ({self.entity_type})"

    def to_dict(self) -> Dict:
        """转换为可序列化的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'KGEntity':
        """从字典创建实例。"""
        return cls(**data)


@dataclass
class DocumentMetadata:
    """
    待处理文档的元数据。

    属性：
        title: 文档标题
        authors: 作者列表
        pub_date: 发表日期
        doi: 数字对象标识符 DOI
    """
    title: str = "Unknown Title"
    authors: List[str] = field(default_factory=list)
    pub_date: str = "N/A"
    doi: str = "N/A"

    def to_dict(self) -> Dict:
        """转换为可序列化的字典。"""
        return asdict(self)


@dataclass
class ProcessingMetrics:
    """
    记录处理性能的统计数据。

    属性：
        prompt_tokens: 输入 Token 数
        completion_tokens: 输出 Token 数
        processing_time: 总处理时间（秒）
        agent_times: 各 Agent 的处理时间
        error_count: 错误数量
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    processing_time: float = 0.0
    agent_times: Dict[str, float] = field(default_factory=dict)
    error_count: int = 0

    def add_agent_time(self, agent_name: str, time: float):
        """记录某个 Agent 的处理时间。"""
        self.agent_times[agent_name] = time
        self.processing_time += time

    def to_dict(self) -> Dict:
        """转换为可序列化的字典。"""
        return asdict(self)


@dataclass
class IntermediateOutput:
    """
    保存处理流程各阶段的中间输出。

    记录完整流程状态，包括原始输入、
    中间结果及最终输出，供调试和分析使用。
    """
    # 输入数据
    raw_text: str = ""
    metadata: Optional[DocumentMetadata] = None

    # 各阶段输出
    segments: List[Dict] = field(default_factory=list)
    relevant_segments: List[Dict] = field(default_factory=list)
    summaries: List[str] = field(default_factory=list)
    entities: List[KGEntity] = field(default_factory=list)
    relationships: List[KnowledgeTriple] = field(default_factory=list)
    aligned_entities: List[KGEntity] = field(default_factory=list)
    aligned_triples: List[KnowledgeTriple] = field(default_factory=list)
    final_triples: List[KnowledgeTriple] = field(default_factory=list)
    integrated_triples: List[KnowledgeTriple] = field(default_factory=list)

    # 性能统计
    metrics: ProcessingMetrics = field(default_factory=ProcessingMetrics)

    def to_dict(self) -> Dict:
        """转换为可序列化为 JSON 的字典。"""
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, list) and value:
                if hasattr(value[0], 'to_dict'):
                    result[key] = [item.to_dict() for item in value]
                else:
                    result[key] = value
            else:
                result[key] = value
        return result

    def save_to_file(self, filepath: str):
        """将中间结果保存为 JSON 文件。"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'IntermediateOutput':
        """从 JSON 文件加载中间结果。"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 根据字典重建对象
        instance = cls()
        for key, value in data.items():
            if key == 'entities' and value:
                instance.entities = [KGEntity.from_dict(item) for item in value]
            elif key in ['relationships', 'aligned_triples', 'final_triples', 'integrated_triples'] and value:
                setattr(instance, key, [KnowledgeTriple.from_dict(item) for item in value])
            elif key == 'metadata' and value:
                # 兼容旧版本中已经移除的字段。
                instance.metadata = DocumentMetadata(**{
                    k: v for k, v in value.items()
                    if k not in {"journal", "document_type", "pmid"}
                })
            elif key == 'metrics' and value:
                instance.metrics = ProcessingMetrics(**value)
            else:
                setattr(instance, key, value)

        return instance


@dataclass
class KnowledgeGraph:
    """
    表示完整的知识图谱结构。

    属性：
        entities: 图谱中的实体名称集合
        triples: 知识三元组列表
        metadata: 图谱级元数据
    """
    entities: set = field(default_factory=set)
    triples: List[KnowledgeTriple] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def add_entity(self, entity: Union[str, KGEntity]):
        """向知识图谱添加实体。"""
        if isinstance(entity, KGEntity):
            self.entities.add(entity.name)
        else:
            self.entities.add(entity)

    def add_triple(self, triple: KnowledgeTriple):
        """向知识图谱添加关系，并自动补充关系两端实体。"""
        self.triples.append(triple)
        # 自动补充关系两端实体。
        self.entities.add(triple.head)
        self.entities.add(triple.tail)

    def get_statistics(self) -> Dict:
        """获取知识图谱统计信息。"""
        relation_counts = {}
        entity_type_counts = {}

        for triple in self.triples:
            relation_counts[triple.relation] = relation_counts.get(triple.relation, 0) + 1

        return {
            'entity_count': len(self.entities),
            'triple_count': len(self.triples),
            'unique_relations': len(relation_counts),
            'relation_distribution': relation_counts,
            'avg_confidence': sum(t.confidence for t in self.triples) / len(self.triples) if self.triples else 0
        }

    def to_dict(self) -> Dict:
        """转换为可序列化的字典。"""
        return {
            'entities': list(self.entities),
            'triples': [triple.to_dict() for triple in self.triples],
            'metadata': self.metadata,
            'statistics': self.get_statistics()
        }

    def save_to_file(self, filepath: str):
        """将知识图谱保存为 JSON 文件。"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'KnowledgeGraph':
        """从 JSON 文件加载知识图谱。"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        kg = cls()
        kg.entities = set(data.get('entities', []))
        kg.triples = [KnowledgeTriple.from_dict(triple_data) for triple_data in data.get('triples', [])]
        kg.metadata = data.get('metadata', {})

        return kg
