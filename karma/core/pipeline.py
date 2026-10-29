"""
KARMA Main Pipeline Implementation

This module contains the main KARMA pipeline that orchestrates all agents
to process documents and extract knowledge.
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
    Main KARMA pipeline for automated knowledge graph enrichment.

    This class orchestrates the entire pipeline:
    1. Ingestion -> 2. Reading -> 3. Summarization -> 4. Entity Extraction
    -> 5. Relationship Extraction -> 6. Schema Alignment
    -> 7. Conflict Resolution -> 8. Evaluation -> Integration
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
        Initialize KARMA pipeline with API credentials.

        Args:
            api_key: OpenAI API key
            base_url: Optional API base URL for Azure or custom endpoints
            model_name: Model identifier
            debug_dir: Per-step trace root; None disables tracing.
            integration_threshold: Minimum score to integrate knowledge
        """
        # Initialize OpenAI client
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = OpenAI(**client_kwargs)
        self.model_name = model_name
        self.integration_threshold = integration_threshold
        self.debug_dir = debug_dir
        self.last_debug_dir: Optional[Path] = None

        # Initialize all agent instances
        self._initialize_agents()

        # Initialize knowledge graph and utilities
        self.knowledge_graph = KnowledgeGraph()
        self.pdf_reader = PDFReader()

        # Track processing
        self.output_log: List[str] = []

    @classmethod
    def from_config(cls, config) -> 'KARMAPipeline':
        """
        Create pipeline from configuration object.

        Args:
            config: KARMAConfig instance

        Returns:
            Configured pipeline instance
        """
        # Validate and setup configuration
        config.validate()
        config.setup_logging()

        # Create pipeline instance
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
        """Initialize all KARMA agents."""
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
        domain: str = "biomedical",
        relevance_threshold: float = 0.2,
        *,
        input_type: str = "auto"
    ) -> IntermediateOutput:
        """
        Process a document and extract knowledge.

        Args:
            source: Text content or path to PDF/text file
            domain: Domain context for relevance scoring
            relevance_threshold: Minimum relevance score for segments
            input_type: "text" for literal text, "file" for a required file,
                or "auto" for legacy string detection. Path objects are files.

        Returns:
            IntermediateOutput containing all pipeline results
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
            self._log(f"Step debug files: {trace.directory.resolve()}")

        try:
            # Step 1: Load and ingest document
            raw_text = trace.run(
                0, "load_document", {"source": source, "input_type": input_type},
                lambda: self._load_document(source, input_type=input_type), ("raw_text",)
            )
            intermediate.raw_text = raw_text

            self._log("Starting KARMA pipeline...")

            # Step 2: Ingestion - Extract metadata and normalize text
            self._log("[1/8] Running Ingestion Agent...")
            step_start = time.time()

            metadata, normalized_content = trace.run(
                1, "ingestion", {"raw_text": raw_text},
                lambda: self.ingestion_agent.process(raw_text),
                ("metadata", "normalized_content"), self.ingestion_agent
            )
            intermediate.metadata = metadata

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("ingestion", step_time)
            self._log(f"[1/8] Ingestion completed in {step_time:.2f}s")

            # Step 3: Reader - Segment and score relevance
            self._log("[2/8] Running Reader Agent...")
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
            self._log(f"[2/8] Reader completed in {step_time:.2f}s. "
                     f"Segments: {len(all_segments)}, Relevant: {len(relevant_segments)}")

            # Step 4: Summarizer - Create concise summaries
            self._log("[3/8] Running Summarizer Agent...")
            step_start = time.time()

            summaries = trace.run(
                3, "summarizer", {"relevant_segments": relevant_segments},
                lambda: self.summarizer_agent.process(relevant_segments),
                ("summaries",), self.summarizer_agent
            )
            intermediate.summaries = summaries

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("summarizer", step_time)
            self._log(f"[3/8] Summarizer completed in {step_time:.2f}s. "
                     f"Summaries: {len(summaries)}")

            # Step 5: Entity Extraction - Identify entities
            self._log("[4/8] Running Entity Extraction Agent...")
            step_start = time.time()

            entities = trace.run(
                4, "entity_extraction", {"summaries": summaries},
                lambda: self.entity_extraction_agent.process(summaries),
                ("entities",), self.entity_extraction_agent
            )
            intermediate.entities = entities

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("entity_extraction", step_time)
            self._log(f"[4/8] Entity extraction completed in {step_time:.2f}s. "
                     f"Entities: {len(entities)}")

            # Step 6: Relationship Extraction - Find relationships
            self._log("[5/8] Running Relationship Extraction Agent...")
            step_start = time.time()

            relationships = trace.run(
                5, "relationship_extraction", {"summaries": summaries, "entities": entities},
                lambda: self.relationship_extraction_agent.process(summaries, entities),
                ("relationships",), self.relationship_extraction_agent
            )
            intermediate.relationships = relationships

            step_time = time.time() - step_start
            intermediate.metrics.add_agent_time("relationship_extraction", step_time)
            self._log(f"[5/8] Relationship extraction completed in {step_time:.2f}s. "
                     f"Relationships: {len(relationships)}")

            # Step 7: Schema Alignment - Align to standard schema
            self._log("[6/8] Running Schema Alignment Agent...")
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
            self._log(f"[6/8] Schema alignment completed in {step_time:.2f}s")

            # Step 8: Conflict Resolution - Handle contradictions
            self._log("[7/8] Running Conflict Resolution Agent...")
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
            self._log(f"[7/8] Conflict resolution completed in {step_time:.2f}s. "
                     f"Non-conflicting: {len(resolved_relationships)}")

            # Step 9: Evaluation - Final quality assessment
            self._log("[8/8] Running Evaluator Agent...")
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
            self._log(f"[8/8] Evaluation completed in {step_time:.2f}s. "
                     f"Integrated: {len(integrated_triples)}")

            # Step 10: Update Knowledge Graph
            def integrate():
                self._update_knowledge_graph(aligned_entities, integrated_triples)
                return self.knowledge_graph.to_dict()

            trace.run(
                9, "knowledge_graph", {"entities": aligned_entities,
                                       "triples": integrated_triples,
                                       "previous_statistics": self.knowledge_graph.get_statistics()},
                integrate, ("knowledge_graph",)
            )

            # Finalize metrics
            total_time = time.time() - start_time
            intermediate.metrics.processing_time = total_time

            self._log(f"KARMA pipeline completed in {total_time:.2f}s. "
                     f"Added {len(integrated_triples)} knowledge triples.")

            return intermediate

        except Exception as e:
            intermediate.metrics.error_count += 1
            logger.error(f"Pipeline failed: {str(e)}")
            raise

    def _load_document(self, source: Union[str, Path], *, input_type: str = "auto") -> str:
        """
        Load document content from various sources.

        Args:
            source: File path or text content
            input_type: Explicit text/file mode or backwards-compatible auto detection

        Returns:
            Raw text content
        """
        if input_type not in {"auto", "text", "file"}:
            raise ValueError('input_type must be "auto", "text", or "file"')
        if input_type == "text":
            if not isinstance(source, str):
                raise TypeError('Text input must be a string')
            return source

        if input_type == "file" or isinstance(source, Path):
            source_path = Path(source)
            if not source_path.is_file():
                raise FileNotFoundError(f"Input file not found or not a regular file: {source_path}")
            if source_path.suffix.lower() == '.pdf':
                return self.pdf_reader.extract_text(source_path)
            return source_path.read_text(encoding='utf-8')

        if isinstance(source, (str, Path)):
            source_path = Path(source)

            # Check if it's a file path
            try:
                source_exists = source_path.exists()
            except OSError as exc:
                # Raw text may exceed the filesystem's filename length limit.
                # Only strings can represent text; preserve errors for explicit paths.
                if isinstance(source, str) and exc.errno == errno.ENAMETOOLONG:
                    return source
                raise

            if source_exists:
                if source_path.suffix.lower() == '.pdf':
                    return self.pdf_reader.extract_text(source_path)
                else:
                    # Assume text file
                    with open(source_path, 'r', encoding='utf-8') as f:
                        return f.read()
            else:
                # Treat as raw text if not a valid file path
                return str(source)
        else:
            return str(source)

    def _update_knowledge_graph(self, entities: List[KGEntity], triples: List[KnowledgeTriple]):
        """
        Update the internal knowledge graph with new knowledge.

        Args:
            entities: New entities to add
            triples: New triples to add
        """
        # Add entities
        for entity in entities:
            self.knowledge_graph.add_entity(entity)

        # Add triples
        for triple in triples:
            self.knowledge_graph.add_triple(triple)

    def _log(self, message: str):
        """
        Log message to both logger and internal log.

        Args:
            message: Message to log
        """
        logger.info(message)
        self.output_log.append(message)

    def get_knowledge_graph(self) -> KnowledgeGraph:
        """
        Get the current knowledge graph.

        Returns:
            Current knowledge graph
        """
        return self.knowledge_graph

    def clear_knowledge_graph(self):
        """Clear the knowledge graph."""
        self.knowledge_graph = KnowledgeGraph()
        self._log("Knowledge graph cleared")

    def export_knowledge_graph(self, output_path: Union[str, Path]) -> Dict:
        """
        Export knowledge graph to file.

        Args:
            output_path: Path to save the knowledge graph

        Returns:
            Dictionary representation of the knowledge graph
        """
        self.knowledge_graph.save_to_file(output_path)
        return self.knowledge_graph.to_dict()

    def get_pipeline_statistics(self) -> Dict:
        """
        Get statistics about the pipeline and knowledge graph.

        Returns:
            Dictionary of statistics
        """
        stats = {
            'knowledge_graph': self.knowledge_graph.get_statistics(),
            'agents': {}
        }

        # Get agent-specific metrics
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
        domain: str = "biomedical",
        relevance_threshold: float = 0.2
    ) -> List[IntermediateOutput]:
        """
        Process multiple documents in batch.

        Args:
            sources: List of document sources
            domain: Domain context
            relevance_threshold: Minimum relevance threshold

        Returns:
            List of processing results
        """
        results = []

        for i, source in enumerate(sources):
            self._log(f"Processing document {i+1}/{len(sources)}: {source}")
            try:
                result = self.process_document(source, domain, relevance_threshold)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {source}: {str(e)}")
                # Create empty result for failed processing
                failed_result = IntermediateOutput()
                failed_result.metrics.error_count = 1
                results.append(failed_result)

        return results
