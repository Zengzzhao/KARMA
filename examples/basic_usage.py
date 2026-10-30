#!/usr/bin/env python3
"""
KARMA 基本使用示例。

演示如何使用 KARMA 处理文档，
并抽取知识三元组。
"""

import argparse
from pathlib import Path

from karma import KARMAPipeline
from karma.config import load_config
from karma.utils.cli_localization import ChineseArgumentParser


def main():
    """示例主函数。"""
    parser = ChineseArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=Path(__file__).resolve().parents[1] / "karma_config.json",
        help="JSON 配置文件（默认：工程根目录下的 karma_config.json）",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    # 初始化处理流程
    pipeline = KARMAPipeline.from_config(config)
    print(f"接口地址： {pipeline.client.base_url}")
    print(f"模型： {pipeline.model_name}")

    # 直接输入文本的示例
    sample_text = """
    科学计量指标应用示例（虚构文本，仅用于演示流程）

    本文将 h 指数用于一组研究人员的科研表现比较。
    研究人员的 h 指数为 h，表示其至少有 h 篇论文分别获得不少于 h 次引用。
    本文指出，h 指数受学术生涯长度影响，跨职业阶段比较时应谨慎解释。
    """

    print("正在处理示例文本……")
    result = pipeline.process_document(
        sample_text,
        input_type="text",
        relevance_threshold=config.pipeline.relevance_threshold,
    )

    # 显示结果
    print(f"\n已抽取 {len(result.integrated_triples)} 个知识三元组:")
    for i, triple in enumerate(result.integrated_triples, 1):
        print(f"{i}. {triple.head} --[{triple.relation}]--> {triple.tail}")
        print(f"   置信度： {triple.confidence:.2f}, "
              f"清晰度： {triple.clarity:.2f}, "
              f"相关性： {triple.relevance:.2f}")

    print(f"\n已抽取 {len(result.entities)} 个实体:")
    for entity in result.entities:
        print(f"- {entity.name} ({entity.entity_type})")

    # 导出结果
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    kg_path = output_dir / "sample_knowledge_graph.json"
    pipeline.export_knowledge_graph(kg_path)
    print(f"\n知识图谱已保存到： {kg_path}")

    # 显示处理统计
    print(f"\n处理统计：")
    print(f"- 总耗时： {result.metrics.processing_time:.2f} 秒")
    print(f"- 输入词元数： {result.metrics.prompt_tokens}")
    print(f"- 输出词元数： {result.metrics.completion_tokens}")


if __name__ == "__main__":
    main()
