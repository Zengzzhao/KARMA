#!/usr/bin/env python3
"""
KARMA 主程序入口

使用默认参数运行 KARMA 文档处理流程，
并输出各阶段结果及统计信息。
"""

import os
import sys
import argparse
import csv
from pathlib import Path
from datetime import datetime

# 将 karma 包目录添加到 Python 模块搜索路径
sys.path.insert(0, '/Users/luyuxing/Projects/KARMA')

from karma import KARMAPipeline
from karma.config import create_default_config
from karma.utils.cli_localization import ChineseArgumentParser


def save_relationships_to_csv(result, csv_path, integration_threshold):
    """将抽取的关系、评分和整合状态保存为 CSV 文件。"""
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'head_entity', 'relation', 'tail_entity',
            'confidence', 'clarity', 'relevance',
            'integration_score', 'passed_integration',
            'source_stage', 'processing_notes'
        ]

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        # 收集不同阶段的关系
        all_relationships = []

        # 添加各阶段的关系
        stages = [
            ('relationships', 'initial_extraction'),
            ('aligned_triples', 'after_alignment'),
            ('final_triples', 'after_conflict_resolution'),
            ('integrated_triples', 'integrated_final')
        ]

        for attr_name, stage_name in stages:
            if hasattr(result, attr_name):
                rels = getattr(result, attr_name)
                if rels:
                    for rel in rels:
                        all_relationships.append((rel, stage_name))

        # 关系去重，并保留最新阶段的记录
        unique_relationships = {}
        stage_priority = {
            'initial_extraction': 1,
            'after_alignment': 2,
            'after_conflict_resolution': 3,
            'integrated_final': 4
        }

        for rel, stage in all_relationships:
            key = f"{rel.head.lower()}_{rel.relation.lower()}_{rel.tail.lower()}"
            if key not in unique_relationships or stage_priority[stage] > stage_priority[unique_relationships[key][1]]:
                unique_relationships[key] = (rel, stage)

        # 将关系写入 CSV
        for rel, stage in unique_relationships.values():
            integration_score = 0.5 * rel.confidence + 0.25 * rel.clarity + 0.25 * rel.relevance
            passed_integration = integration_score >= integration_threshold

            if stage == 'integrated_final':
                notes = "已成功整合到知识图谱"
            elif stage == 'after_conflict_resolution':
                notes = "已通过冲突消解，但未通过最终评估"
            elif stage == 'after_alignment':
                notes = "已通过模式对齐，但未通过冲突消解或评估"
            else:
                notes = "未通过流程前期筛选"

            writer.writerow({
                'head_entity': rel.head,
                'relation': rel.relation,
                'tail_entity': rel.tail,
                'confidence': f"{rel.confidence:.3f}",
                'clarity': f"{rel.clarity:.3f}",
                'relevance': f"{rel.relevance:.3f}",
                'integration_score': f"{integration_score:.3f}",
                'passed_integration': 'YES' if passed_integration else 'NO',
                'source_stage': stage,
                'processing_notes': notes
            })

    return len(unique_relationships)


def main():
    """主执行函数。"""
    parser = ChineseArgumentParser(
        description="KARMA：多智能体知识图谱构建与补充",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用默认设置处理 PDF
  python main.py document.pdf

  # 使用自定义接口密钥和模型
  python main.py document.pdf --api-key YOUR_KEY --model gpt-4

  # 使用自定义阈值
  python main.py document.pdf --relevance-threshold 0.3 --integration-threshold 0.7

  # 指定输出目录
  python main.py document.pdf --output-dir results/experiment1
        """
    )

    parser.add_argument('input', help='输入文档路径（PDF 或文本文件）')
    parser.add_argument('--api-key',
                       default=os.getenv('KARMA_API_KEY'),
                       help='OpenAI 接口密钥（默认读取 KARMA_API_KEY 环境变量）')
    parser.add_argument('--model', default='gpt-4o-mini', help='使用的模型（默认：gpt-4o-mini）')
    parser.add_argument('--relevance-threshold', type=float, default=0.2, help='相关性阈值（默认：0.2）')
    parser.add_argument('--integration-threshold', type=float, default=0.5, help='整合阈值（默认：0.5）')
    parser.add_argument('--output-dir', default='karma_output', help='输出目录（默认：karma_output）')
    parser.add_argument('--domain', default='scientometrics', help='领域上下文（默认：scientometrics）')
    parser.add_argument('--debug-dir', help='带编号的逐步调试文件保存目录')
    parser.add_argument('--no-debug-steps', action='store_true', help='关闭逐步调试文件')
    parser.add_argument('--verbose', '-v', action='store_true', help='输出详细信息')

    args = parser.parse_args()

    # 检查输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 错误：输入文件不存在： {input_path}")
        return 1

    if not args.api_key:
        print("❌ 错误：缺少接口密钥，请设置 KARMA_API_KEY 环境变量或使用 --api-key")
        return 1

    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("🚀 KARMA 知识图谱构建与补充流程")
    print("=" * 60)
    print(f"📄 输入： {input_path}")
    print(f"🤖 模型： {args.model}")
    print(f"📊 相关性阈值： {args.relevance_threshold}")
    print(f"📊 整合阈值： {args.integration_threshold}")
    print(f"📁 输出目录： {output_dir}")
    print(f"🕒 开始时间： {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # 创建配置
        config = create_default_config(api_key=args.api_key, output_dir=args.output_dir)
        config.save_debug_steps = not args.no_debug_steps
        config.debug_dir = args.debug_dir
        config.model.name = args.model
        config.pipeline.relevance_threshold = args.relevance_threshold
        config.pipeline.integration_threshold = args.integration_threshold

        # 初始化处理流程
        print("🔧 正在初始化 KARMA 处理流程……")
        pipeline = KARMAPipeline.from_config(config)

        # 处理文档
        print(f"📖 正在处理文档： {input_path.name}")
        print("⏳ 处理可能需要几分钟……")

        result = pipeline.process_document(
            input_path,
            domain=args.domain,
            relevance_threshold=args.relevance_threshold
        )

        print("✅ 处理成功完成！")
        print("=" * 60)

        # 显示结果统计
        print("📊 处理结果：")
        print(f"   📝 文本片段数： {len(result.segments)}")
        print(f"   ✨ 相关片段数： {len(result.relevant_segments)}")
        print(f"   📄 摘要数： {len(result.summaries)}")
        print(f"   🏷️  抽取实体数： {len(result.entities)}")
        print(f"   🔗 初始关系数： {len(result.relationships) if result.relationships else 0}")
        print(f"   ✅ 最终整合三元组数： {len(result.integrated_triples)}")
        print(f"   ⏱️  总处理耗时： {result.metrics.processing_time:.2f} 秒")

        # 保存所有结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. 将所有关系保存为 CSV
        csv_path = output_dir / f"all_relationships_{timestamp}.csv"
        total_rels = save_relationships_to_csv(result, csv_path, args.integration_threshold)

        passed_count = len(result.integrated_triples)
        failed_count = total_rels - passed_count
        success_rate = (passed_count / total_rels * 100) if total_rels > 0 else 0

        print(f"\n📊 关系分析：")
        print(f"   📋 抽取关系总数： {total_rels}")
        print(f"   ✅ 通过整合： {passed_count}")
        print(f"   ❌ 未通过整合： {failed_count}")
        print(f"   📈 通过率： {success_rate:.1f}%")
        print(f"   💾 关系明细 CSV 已保存： {csv_path}")

        # 2. 导出知识图谱
        kg_path = output_dir / f"knowledge_graph_{timestamp}.json"
        pipeline.export_knowledge_graph(kg_path)
        print(f"   💾 知识图谱已保存： {kg_path}")

        # 3. 保存中间结果
        intermediate_path = output_dir / f"intermediate_results_{timestamp}.json"
        result.save_to_file(intermediate_path)
        print(f"   💾 中间结果已保存： {intermediate_path}")

        # 显示示例结果
        if result.entities and args.verbose:
            print(f"\n🏷️ 实体示例：")
            entity_types = {}
            for entity in result.entities:
                entity_types[entity.entity_type] = entity_types.get(entity.entity_type, 0) + 1

            for entity_type, count in sorted(entity_types.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"   {entity_type}: {count}")

        if result.integrated_triples and args.verbose:
            print(f"\n🔗 知识三元组示例：")
            for i, triple in enumerate(result.integrated_triples[:5], 1):
                integration_score = 0.5 * triple.confidence + 0.25 * triple.clarity + 0.25 * triple.relevance
                print(f"   {i}. {triple.head} --[{triple.relation}]--> {triple.tail}")
                print(f"      评分： {integration_score:.3f} （置信度：{triple.confidence:.2f}，清晰度：{triple.clarity:.2f}，相关性：{triple.relevance:.2f}）")

        print(f"\n🎉 KARMA 处理成功完成！")
        print(f"📁 所有结果已保存到： {output_dir}")
        return 0

    except Exception as e:
        print(f"❌ 处理过程中发生错误： {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
