"""
KARMA 命令行接口。

提供命令行入口，用于运行 KARMA，
处理文档并管理配置。
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from karma import KARMAPipeline, __version__, get_info
from karma.config import KARMAConfig, load_config, save_config, create_default_config
from karma.utils.cli_localization import ChineseArgumentParser


def setup_logging(level: str = "INFO"):
    """初始化命令行日志。"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def process_command(args) -> int:
    """处理文档处理命令。"""
    try:
        # 加载或创建配置
        if args.config:
            config = load_config(args.config)
        else:
            # 根据命令行参数创建配置
            config = create_default_config(
                api_key=args.api_key,
                output_dir=args.output_dir
            )

            if args.model:
                config.model.name = args.model
            if args.base_url:
                config.model.base_url = args.base_url
            if args.relevance_threshold:
                config.pipeline.relevance_threshold = args.relevance_threshold
            if args.integration_threshold:
                config.pipeline.integration_threshold = args.integration_threshold

        if args.no_debug_steps:
            config.save_debug_steps = False
        if args.debug_dir:
            config.debug_dir = args.debug_dir

        # 使用命令行提供的接口密钥覆盖原配置
        if args.api_key:
            config.model.api_key = args.api_key

        # 验证配置
        if not config.model.api_key:
            print("错误：缺少接口密钥，请通过 --api-key 或配置文件提供。")
            return 1

        # 初始化日志
        setup_logging(args.log_level)

        # 创建处理流程
        pipeline = KARMAPipeline.from_config(config)

        # 处理输入
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"错误：输入文件不存在： {input_path}")
            return 1

        print(f"正在处理文档： {input_path}")
        print(f"使用模型： {config.model.name}")

        # 执行处理流程
        result = pipeline.process_document(
            input_path,
            domain=args.domain,
            relevance_threshold=config.pipeline.relevance_threshold
        )

        # 保存结果
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 导出知识图谱
        kg_path = output_path.with_suffix('.kg.json')
        pipeline.export_knowledge_graph(kg_path)

        # 按参数要求保存中间结果
        if args.save_intermediate:
            intermediate_path = output_path.with_suffix('.intermediate.json')
            result.save_to_file(intermediate_path)
            print(f"中间结果已保存到： {intermediate_path}")

        # 输出结果摘要
        print(f"\\n处理成功完成！")
        print(f"已抽取 {len(result.integrated_triples)} 个知识三元组")
        print(f"已发现 {len(result.entities)} 个实体")
        print(f"处理耗时： {result.metrics.processing_time:.2f} 秒")
        print(f"结果已保存到： {kg_path}")

        # 在详细模式下输出统计信息
        if args.verbose:
            stats = pipeline.get_pipeline_statistics()
            print(f"\\n流程统计：")
            print(f"知识图谱： {stats['knowledge_graph']}")

        return 0

    except Exception as e:
        print(f"处理过程中发生错误： {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def config_command(args) -> int:
    """处理配置管理命令。"""
    try:
        if args.config_action == "create":
            # 创建新配置
            if not args.api_key:
                print("错误：创建配置时必须提供接口密钥。")
                return 1

            config = create_default_config(args.api_key, args.output_dir)

            if args.model:
                config.model.name = args.model
            if args.base_url:
                config.model.base_url = args.base_url

            # 保存配置
            config_path = Path(args.config_file)
            save_config(config, config_path)
            print(f"配置已保存到： {config_path}")

        elif args.config_action == "show":
            # 显示现有配置
            config_path = Path(args.config_file)
            if not config_path.exists():
                print(f"配置文件不存在： {config_path}")
                return 1

            config = load_config(config_path)
            # 隐藏接口密钥，避免泄露
            config_dict = config.to_dict()
            config_dict['model']['api_key'] = '***HIDDEN***'

            print(json.dumps(config_dict, indent=2))

        elif args.config_action == "validate":
            # 验证配置
            config_path = Path(args.config_file)
            if not config_path.exists():
                print(f"配置文件不存在： {config_path}")
                return 1

            config = load_config(config_path)
            config.validate()
            print("配置验证通过！")

        return 0

    except Exception as e:
        print(f"配置错误： {str(e)}")
        return 1


def info_command(args) -> int:
    """处理软件包信息查询命令。"""
    info = get_info()

    print(f"KARMA v{info['version']}")
    print(f"作者： {info['author']}")
    print(f"说明： {info['description']}")
    print(f"\\n可用智能体：")
    for agent in info['agents']:
        print(f"  - {agent}")

    return 0


def main():
    """命令行主入口。"""
    parser = ChineseArgumentParser(
        description="KARMA：多智能体大语言模型知识图谱构建与补充",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 处理 PDF 文档
  karma process document.pdf --api-key YOUR_KEY --output results.json

  # 使用自定义模型和阈值
  karma process document.pdf --api-key YOUR_KEY --model gpt-4 \\
    --relevance-threshold 0.3 --integration-threshold 0.7

  # 使用配置文件
  karma process document.pdf --config config.json --output results.json

  # 创建配置文件
  karma config create --api-key YOUR_KEY --config-file karma_config.json

  # 显示版本和软件包信息
  karma info
        """
    )

    parser.add_argument('--version', action='version', version=f'KARMA {__version__}', help='显示版本号并退出')

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # 文档处理命令
    process_parser = subparsers.add_parser('process', help='处理文档')
    process_parser.add_argument('input', help='输入文档路径（PDF 或文本文件）')
    process_parser.add_argument('--api-key', help='OpenAI 接口密钥')
    process_parser.add_argument('--base-url', help='接口基础地址（用于 Azure 或自定义接口）')
    process_parser.add_argument('--model', default='gpt-4o', help='模型名称（默认：gpt-4o）')
    process_parser.add_argument('--config', help='配置文件路径')
    process_parser.add_argument('--output', default='karma_output.json', help='输出文件路径')
    process_parser.add_argument('--output-dir', default='output', help='输出目录')
    process_parser.add_argument('--domain', default='scientometrics', help='领域上下文')
    process_parser.add_argument('--relevance-threshold', type=float, help='相关性阈值（0～1）')
    process_parser.add_argument('--integration-threshold', type=float, help='整合阈值（0～1）')
    process_parser.add_argument('--debug-dir', help='带编号的逐步调试文件保存目录')
    process_parser.add_argument('--no-debug-steps', action='store_true', help='关闭逐步调试文件')
    process_parser.add_argument('--save-intermediate', action='store_true', help='保存中间结果')
    process_parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                                help='日志级别（默认：INFO）')
    process_parser.add_argument('--verbose', '-v', action='store_true', help='输出详细信息')
    process_parser.set_defaults(func=process_command)

    # 配置管理命令
    config_parser = subparsers.add_parser('config', help='管理配置')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='配置操作')

    # 创建配置子命令
    create_parser = config_subparsers.add_parser('create', help='创建新配置')
    create_parser.add_argument('--api-key', required=True, help='OpenAI 接口密钥')
    create_parser.add_argument('--model', default='gpt-4o', help='模型名称')
    create_parser.add_argument('--base-url', help='接口基础地址')
    create_parser.add_argument('--output-dir', default='output', help='输出目录')
    create_parser.add_argument('--config-file', default='karma_config.json', help='配置文件路径')

    # 查看配置子命令
    show_parser = config_subparsers.add_parser('show', help='显示配置')
    show_parser.add_argument('--config-file', default='karma_config.json', help='配置文件路径')

    # 验证配置子命令
    validate_parser = config_subparsers.add_parser('validate', help='验证配置')
    validate_parser.add_argument('--config-file', default='karma_config.json', help='配置文件路径')

    config_parser.set_defaults(func=config_command)

    # 信息查询命令
    info_parser = subparsers.add_parser('info', help='显示软件包信息')
    info_parser.set_defaults(func=info_command)

    # 解析命令行参数
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # 执行命令
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
