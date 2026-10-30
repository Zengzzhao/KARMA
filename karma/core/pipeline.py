"""
KARMA 主处理流程实现

本模块通过主流程编排各个智能体，
完成文档处理和知识抽取。
"""

import errno
import logging
import time
import os
from typing import List, Union, Optional, Dict
from pathlib import Path

from openai import OpenAI

from .debug_trace import DebugTrace

from .data_structures import (
    KnowledgeTriple, KGEntity, IntermediateOutput,
    DocumentMetadata, ProcessingMetrics, KnowledgeGraph
)

from ..agents import (
    IngestionAgent, ReaderAgent, SummarizerAgent,
    EntityExtractionAgent, RelationshipExtractionAgent,
    SchemaAlignmentAgent, ConflictResolutionAgent, EvaluatorAgent
)

from karma.utils.pdf_reader import PDFReader

logger = logging.getLogger(__name__)


class KARMAPipeline:
    """
    自动抽取和补充知识图谱的 KARMA 主流程。

    按以下顺序组织完整处理流程：
    1. 文档接收 → 2. 阅读分块 → 3. 摘要生成 → 4. 实体抽取
    → 5. 关系抽取 → 6. 模式对齐
    → 7. 冲突消解 → 8. 质量评估 → 图谱整合
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model_name: str = "gpt-4o",
        integration_threshold: float = 0.6,
        debug_dir: Optional[Union[str, Path]] = "output/debug"
    ):
        """
        使用接口凭据初始化 KARMA 处理流程。

        参数：
            api_key: OpenAI 接口密钥
            base_url: 可选的接口基础地址，用于 Azure 或自定义接口
            model_name: 大语言模型名称
            debug_dir: 逐步调试记录的根目录；为 None 时关闭记录
            integration_threshold: 知识整合的最低评分
        """
        # 初始化 OpenAI 客户端
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = OpenAI(**client_kwargs)
        self.model_name = model_name
        self.integration_threshold = integration_threshold
        self.debug_dir = debug_dir
        self.last_debug_dir: Optional[Path] = None

        # 初始化各智能体实例
        self._initialize_agents()

        # 初始化知识图谱和辅助工具
        self.knowledge_graph = KnowledgeGraph()
        self.pdf_reader = PDFReader()

        # 记录处理过程
        self.output_log: List[str] = []

    @classmethod
    def from_config(cls, config) -> 'KARMAPipeline':
        """
        根据配置对象创建处理流程。

        参数：
            config: 配置对象

        返回：
            已配置的处理流程实例
        """
        # 验证配置并初始化日志
        config.validate()
        config.setup_logging()

        # 创建处理流程实例
        pipeline = cls(
            api_key=config.model.api_key,
            base_url=config.model.base_url,
            model_name=config.model.name,
            integration_threshold=config.pipeline.integration_threshold,
            debug_dir=(config.debug_dir or Path(config.output_dir) / "debug")
            if config.save_debug_steps else None
        )

        return pipeline

    def _initialize_agents(self):
        """初始化所有 KARMA 智能体。"""
        self.ingestion_agent = IngestionAgent(self.client, self.model_name)
        self.reader_agent = ReaderAgent(self.client, self.model_name)
        self.summarizer_agent = SummarizerAgent(self.client, self.model_name)
        self.entity_extraction_agent = EntityExtractionAgent(self.client, self.model_name)
        self.relationship_extraction_agent = RelationshipExtractionAgent(self.client, self.model_name)
        self.schema_alignment_agent = SchemaAlignmentAgent(self.client, self.model_name)
        self.conflict_resolution_agent = ConflictResolutionAgent(self.client, self.model_name)
        self.evaluator_agent = EvaluatorAgent(
            self.client, self.model_name,
            integrate_threshold=self.integration_threshold
        )

    def process_document(
        self,
        source: Union[str, Path],
        domain: str = "scientometrics",
        relevance_threshold: float = 0.2,
        *,
        input_type: str = "auto"
    ) -> IntermediateOutput:
        """
        处理单篇文档并抽取知识。

        参数：
            source: 原始文本或 PDF、文本文件路径
            domain: 领域上下文
            relevance_threshold: 保留或处理片段所需的最低相关性评分
            input_type: 输入类型：text 表示原始文本，file 表示文件，auto 自动判断
                Path 对象始终按文件处理。

        返回：
            包含所有流程结果的 IntermediateOutput 对象
        """
        start_time = time.time()
        intermediate = IntermediateOutput()
        self.last_debug_dir = None
        trace = DebugTrace(self.debug_dir, {
            "model": self.model_name,
            "domain_requested": domain,
            "relevance_threshold": relevance_threshold,
            "integration_threshold": self.integration_threshold,
            "input_type": input_type,
        })
        self.last_debug_dir = trace.directory
        if trace.directory is not None:
            self._log(f"逐步调试文件目录： {trace.directory.resolve()}")

        try:
            # 步骤 1：读取并接收文档。
            raw_text = trace.run(
                0, "load_document", {"source": source, "input_type": input_type},
                lambda: self._load_document(source, input_type=input_type), ("raw_text",)
            )
            intermediate.raw_text = raw_text

            self._log("正在启动 KARMA 处理流程……")

            # 步骤 2：提取元数据并清洗正文。
            self._log("[1/8] 正在执行文档接收智能体……")
            step_start = time.time()

            metadata, normalized_content = trace.run(
                1, "ingestion", {"raw_text": raw_text},
                lambda: self.ingestion_agent.process(raw_text),
                ("metadata", "normalized_content"), self.ingestion_agent
            )
            intermediate.metadata = metadata

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("ingestion", step_time)
            self._log(f"[1/8] 文档接收完成，耗时 {step_time:.2f} 秒")

            # 步骤 3：分块并评估相关性。
            self._log("[2/8] 正在执行阅读分块智能体……")
            step_start = time.time()

            all_segments, relevant_segments = trace.run(
                2, "reader", {"normalized_content": normalized_content,
                              "relevance_threshold": relevance_threshold},
                lambda: self.reader_agent.process(normalized_content, relevance_threshold),
                ("all_segments", "relevant_segments"), self.reader_agent
            )
            intermediate.segments = all_segments
            intermediate.relevant_segments = relevant_segments

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("reader", step_time)
            self._log(f"[2/8] 阅读分块完成，耗时 {step_time:.2f} 秒。 "
                     f"片段数： {len(all_segments)}, 相关片段数： {len(relevant_segments)}")

            # 步骤 4：生成摘要。
            self._log("[3/8] 正在执行摘要生成智能体……")
            step_start = time.time()

            summaries = trace.run(
                3, "summarizer", {"relevant_segments": relevant_segments},
                lambda: self.summarizer_agent.process(relevant_segments),
                ("summaries",), self.summarizer_agent
            )
            intermediate.summaries = summaries

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("summarizer", step_time)
            self._log(f"[3/8] 摘要生成完成，耗时 {step_time:.2f} 秒。 "
                     f"摘要数： {len(summaries)}")

            # 步骤 5：抽取指标实体。
            self._log("[4/8] 正在执行实体抽取智能体……")
            step_start = time.time()

            entities = trace.run(
                4, "entity_extraction", {"summaries": summaries, "metadata": metadata},
                lambda: self._extract_document_entities(summaries, metadata),
                ("entities",), self.entity_extraction_agent
            )
            intermediate.entities = entities

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("entity_extraction", step_time)
            self._log(f"[4/8] 实体抽取完成，耗时 {step_time:.2f} 秒。 "
                     f"实体数： {len(entities)}")

            # 步骤 6：抽取实体关系。
            self._log("[5/8] 正在执行关系抽取智能体……")
            step_start = time.time()

            relationships = trace.run(
                5, "relationship_extraction", {"summaries": summaries, "entities": entities},
                lambda: self.relationship_extraction_agent.process(summaries, entities),
                ("relationships",), self.relationship_extraction_agent
            )
            intermediate.relationships = relationships

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("relationship_extraction", step_time)
            self._log(f"[5/8] 关系抽取完成，耗时 {step_time:.2f} 秒。 "
                     f"关系数： {len(relationships)}")

            # 步骤 7：对齐实体和关系标签。
            self._log("[6/8] 正在执行模式对齐智能体……")
            step_start = time.time()

            aligned_entities, aligned_relationships = trace.run(
                6, "schema_alignment", {"entities": entities, "relationships": relationships},
                lambda: self.schema_alignment_agent.process(entities, relationships),
                ("aligned_entities", "aligned_relationships"), self.schema_alignment_agent
            )
            intermediate.aligned_entities = aligned_entities
            intermediate.aligned_triples = aligned_relationships

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("schema_alignment", step_time)
            self._log(f"[6/8] 模式对齐完成，耗时 {step_time:.2f} 秒")

            # 步骤 8：处理关系冲突。
            self._log("[7/8] 正在执行冲突消解智能体……")
            step_start = time.time()

            resolved_relationships = trace.run(
                7, "conflict_resolution", {"new_triples": aligned_relationships,
                                          "existing_triples": self.knowledge_graph.triples},
                lambda: self.conflict_resolution_agent.process(
                    aligned_relationships, self.knowledge_graph.triples),
                ("resolved_relationships",), self.conflict_resolution_agent
            )
            intermediate.final_triples = resolved_relationships

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("conflict_resolution", step_time)
            self._log(f"[7/8] 冲突消解完成，耗时 {step_time:.2f} 秒。 "
                     f"无冲突关系数： {len(resolved_relationships)}")

            # 步骤 9：评估关系质量。
            self._log("[8/8] 正在执行质量评估智能体……")
            step_start = time.time()

            integrated_triples = trace.run(
                8, "evaluator", {"candidate_triples": resolved_relationships,
                                 "integration_threshold": self.integration_threshold},
                lambda: self.evaluator_agent.process(resolved_relationships),
                ("integrated_triples",), self.evaluator_agent
            )
            intermediate.integrated_triples = integrated_triples

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("evaluator", step_time)
            self._log(f"[8/8] 质量评估完成，耗时 {step_time:.2f} 秒。 "
                     f"已整合关系数： {len(integrated_triples)}")

            # 步骤 10：更新知识图谱。
            def integrate():
                self._update_knowledge_graph(aligned_entities, integrated_triples)
                return self.knowledge_graph.to_dict()

            trace.run(
                9, "knowledge_graph", {"entities": aligned_entities,
                                       "triples": integrated_triples,
                                       "previous_statistics": self.knowledge_graph.get_statistics()},
                integrate, ("knowledge_graph",)
            )

            # 汇总处理指标。
            total_time = time.time() - start_time
            intermediate.metrics.processing_time = total_time

            self._log(f"KARMA 处理完成，总耗时 {total_time:.2f} 秒。 "
                     f"新增 {len(integrated_triples)} 个知识三元组.")

            return intermediate

        except Exception as e:
            intermediate.metrics.error_count += 1
            logger.error(f"流程执行失败： {str(e)}")
            raise

    def _extract_document_entities(self, summaries, metadata):
        """抽取指标，并仅根据元数据添加当前论文实体。"""
        entities = [entity for entity in self.entity_extraction_agent.process(summaries)
                    if entity.entity_type.lower() != "paper"]

        def available(value):
            if not isinstance(value, str):
                return ""
            value = value.strip()
            return "" if value.lower() in {
                "", "unknown", "unknown title", "n/a", "none", "null", "未知", "未知标题"
            } else value

        title = available(metadata.title)
        doi = available(metadata.doi)
        name = title or doi
        if name:
            entities.insert(0, KGEntity(
                entity_id=name, name=name, entity_type="Paper",
                normalized_id=doi or "N/A"
            ))
        else:
            self._log("标题和 DOI 均不可用，未创建论文实体")
        return entities

    def _load_document(self, source: Union[str, Path], *, input_type: str = "auto") -> str:
        """
        从文件或文本输入加载文档内容。

        参数：
            source: 原始文本或 PDF、文本文件路径
            input_type: 输入类型：text 表示原始文本，file 表示文件，auto 自动判断

        返回：
            原始文本内容
        """
        if input_type not in {"auto", "text", "file"}:
            raise ValueError('input_type 必须为 "auto"、"text" 或 "file"')
        if input_type == "text":
            if not isinstance(source, str):
                raise TypeError('文本输入必须为字符串')
            return source

        if input_type == "file" or isinstance(source, Path):
            source_path = Path(source)
            if not source_path.is_file():
                raise FileNotFoundError(f"输入文件不存在或不是普通文件： {source_path}")
            if source_path.suffix.lower() == '.pdf':
                return self.pdf_reader.extract_text(source_path)
            return source_path.read_text(encoding='utf-8')

        if isinstance(source, (str, Path)):
            source_path = Path(source)

            # 检查是否为文件路径。
            try:
                source_exists = source_path.exists()
            except OSError as exc:
                # 原始文本可能超过文件名长度限制；此时按文本处理。
                if isinstance(source, str) and exc.errno == errno.ENAMETOOLONG:
                    return source
                raise

            if source_exists:
                if source_path.suffix.lower() == '.pdf':
                    return self.pdf_reader.extract_text(source_path)
                else:
                    # 按文本文件读取。
                    with open(source_path, 'r', encoding='utf-8') as f:
                        return f.read()
            else:
                # 无效路径按原始文本处理。
                return str(source)
        else:
            return str(source)

    def _update_knowledge_graph(self, entities: List[KGEntity], triples: List[KnowledgeTriple]):
        """
        将新实体和关系添加到内部知识图谱。

        参数：
            entities: 待处理的实体集合
            triples: 知识三元组列表
        """
        # 添加实体。
        for entity in entities:
            self.knowledge_graph.add_entity(entity)

        # 添加关系。
        for triple in triples:
            self.knowledge_graph.add_triple(triple)

    def _log(self, message: str):
        """
        同时向日志系统和内部日志列表写入消息。

        参数：
            message: 待记录的日志消息
        """
        logger.info(message)
        self.output_log.append(message)

    def get_knowledge_graph(self) -> KnowledgeGraph:
        """
        获取当前知识图谱。

        返回：
            当前知识图谱
        """
        return self.knowledge_graph

    def clear_knowledge_graph(self):
        """清空知识图谱。"""
        self.knowledge_graph = KnowledgeGraph()
        self._log("知识图谱已清空")

    def export_knowledge_graph(self, output_path: Union[str, Path]) -> Dict:
        """
        将知识图谱导出到文件。

        参数：
            output_path: 知识图谱保存路径

        返回：
            知识图谱的字典表示
        """
        self.knowledge_graph.save_to_file(output_path)
        return self.knowledge_graph.to_dict()

    def get_pipeline_statistics(self) -> Dict:
        """
        获取流程和知识图谱的统计信息。

        返回：
            统计信息字典
        """
        stats = {
            'knowledge_graph': self.knowledge_graph.get_statistics(),
            'agents': {}
        }

        # 获取各 Agent 的统计信息。
        agents = [
            ('ingestion', self.ingestion_agent),
            ('reader', self.reader_agent),
            ('summarizer', self.summarizer_agent),
            ('entity_extraction', self.entity_extraction_agent),
            ('relationship_extraction', self.relationship_extraction_agent),
            ('schema_alignment', self.schema_alignment_agent),
            ('conflict_resolution', self.conflict_resolution_agent),
            ('evaluator', self.evaluator_agent)
        ]

        for name, agent in agents:
            stats['agents'][name] = agent.get_metrics()

        return stats

    def process_batch(
        self,
        sources: List[Union[str, Path]],
        domain: str = "scientometrics",
        relevance_threshold: float = 0.2
    ) -> List[IntermediateOutput]:
        """
        批量处理多篇文档。

        参数：
            sources: 文档来源列表
            domain: 领域上下文
            relevance_threshold: 保留或处理片段所需的最低相关性评分

        返回：
            处理结果列表
        """
        results = []

        for i, source in enumerate(sources):
            self._log(f"正在处理第 {i+1}/{len(sources)} 篇文档： {source}")
            try:
                result = self.process_document(source, domain, relevance_threshold)
                results.append(result)
            except Exception as e:
                logger.error(f"处理失败 {source}: {str(e)}")
                # 为失败的文档创建空结果。
                failed_result = IntermediateOutput()
                failed_result.metrics.error_count = 1
                results.append(failed_result)

        return results
