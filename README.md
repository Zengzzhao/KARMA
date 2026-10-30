# KARMA：多智能体知识图谱构建与补充

本工程基于 KARMA，面向 Scientometrics 期刊 2004—2024 年论文中的科学计量指标知识抽取。当前系统提示词已改为中文，目标包括指标、公式、局限性、论文与指标关系以及指标间关系。

当前版本是领域迁移的初步实现。公式、局限性和证据的结构化保存仍需后续开发，不能将提示词中提出的要求视为已经实现的数据字段。

## 安装与运行

在本工程目录安装，才能使用本地修改后的版本：

```bash
cd /Users/zengzizhao/Desktop/KARMA
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 设置接口密钥后处理示例论文
export KARMA_API_KEY="你的接口密钥"
python main.py Example_Paper.pdf --output-dir output --verbose
```

已有虚拟环境时直接激活即可。依赖声明要求 Python 3.8 或更高版本，核心依赖为 `openai`、`PyPDF2` 和 `typing-extensions`。

根目录入口会保存关系明细 CSV、知识图谱 JSON、中间结果 JSON 和逐步调试文件。`main.py` 默认使用 `gpt-4o-mini`，相关性阈值为 0.2，整合阈值为 0.5。

```bash
# 查看参数说明
python main.py --help

# 使用已保存的配置（可在配置中指定接口地址）
karma process Example_Paper.pdf --config karma_config.json --output output/results.json --save-intermediate

# 创建或验证配置
karma config create --api-key "你的接口密钥" --config-file karma_config.json
karma config validate --config-file karma_config.json

# 查看软件包信息
karma info
```

`karma process` 的 `--output` 决定图谱文件位置，实际图谱文件扩展名为 `.kg.json`；`--output-dir` 决定默认调试目录的根路径。使用配置文件时，输出目录取配置中的值。

## 工程目录

| 路径 | 用途 |
|---|---|
| `main.py` | 单文档处理入口及关系明细导出 |
| `karma.sh` | 包装主程序的启动脚本 |
| `karma/cli.py` | 文档处理、配置管理和信息查询命令 |
| `karma/core/pipeline.py` | 智能体实例化、顺序编排和图谱整合 |
| `karma/core/base_agent.py` | 模型调用、响应解析和调用统计 |
| `karma/core/data_structures.py` | 元数据、实体、三元组和中间结果结构 |
| `karma/core/debug_trace.py` | 各步骤输入输出快照 |
| `karma/agents/scientometrics_prompts.py` | 科学计量领域的中文系统提示词 |
| `karma/agents/` | 八个智能体的实现 |
| `karma/utils/` | PDF 读取与文本处理工具 |
| `karma/config/` | 配置读取、校验和日志配置 |
| `examples/basic_usage.py` | 读取配置并处理中文示例文本 |
| `docs/scientometrics_prompt_migration.md` | 领域迁移说明和当前边界 |

## 智能体与数据链路

当前工程通过 `KARMAPipeline` 顺序调用八个智能体，未使用 LangGraph。各智能体继承统一基类，共用模型客户端，通过 Python 对象传递阶段结果。

| 步骤 | 实现 | 输入与输出 |
|---|---|---|
| 文档加载 | `PDFReader` 或文本文件读取 | 文件 → 原始文本 |
| 文档接收 | `IngestionAgent` | 原始文本 → 元数据和规范化正文 |
| 阅读分块 | `ReaderAgent` | 正文 → 全部分块及相关分块 |
| 摘要生成 | `SummarizerAgent` | 相关分块 → 摘要列表 |
| 实体抽取 | `EntityExtractionAgent` | 摘要 → 指标实体；主流程补充论文实体 |
| 关系抽取 | `RelationshipExtractionAgent` | 摘要和实体 → 关系三元组 |
| 模式对齐 | `SchemaAlignmentAgent` | 实体和三元组 → 规范化结果 |
| 冲突消解 | `ConflictResolutionAgent` | 新增及已有三元组 → 保留的关系 |
| 质量评估 | `EvaluatorAgent` | 候选关系 → 达到阈值的关系 |
| 图谱整合 | 主流程 | 实体和通过评估的关系 → 知识图谱 |

前五个智能体会调用模型；模式对齐、冲突消解和质量评估目前执行本地规则。它们的角色提示词不会自动替代规则实现。整合评分为 `0.5 × confidence + 0.25 × clarity + 0.25 × relevance`。

PDF 文本由 PyPDF2 提取，随后进行清洗。阅读节点主要依据双换行符分段，再识别章节特征；它不是完整的版面或章节解析器。清洗后段落边界消失时，可能将整篇文档识别成一个片段，单独翻译提示词不能修复此问题。

## 目标实体与关系

论文实体类型为 `Paper`，程序优先用元数据 `title` 作为名称，标题不可用时使用 `doi`，两者都不可用则不创建。模型只负责识别 `Indicator` 指标实体。

| 标签 | 方向 | 含义 |
|---|---|---|
| `proposes` | 论文 → 指标 | 本文首次提出、命名或正式定义指标 |
| `modifies` | 论文 → 指标 | 本文实际修正或扩展指标 |
| `applies` | 论文 → 指标 | 本文将已有指标用于分析、评价或比较 |
| `variant_of` | 变体指标 → 原指标 | 保留核心思想或公式结构的变体 |
| `derived_from` | 派生指标 → 来源指标 | 直接来源于另一指标且存在实质改动 |
| `improves_on` | 改进指标 → 被改进指标 | 明确针对缺陷或适用性问题改进 |
| `alternative_to` | 指标 ↔ 指标 | 特定条件下构成替代或竞争方案 |
| `component_of` | 组成指标 → 整体指标 | 作为输入或子指标纳入复合指标 |

标签与方向由中文提示词规定，当前不是完整的程序端约束验证。

## Python 调用

```python
import os
from karma import KARMAPipeline
from karma.config import create_default_config

config = create_default_config(api_key=os.environ["KARMA_API_KEY"], output_dir="output")
pipeline = KARMAPipeline.from_config(config)
result = pipeline.process_document("Example_Paper.pdf", relevance_threshold=0.2)

print(f"已抽取 {len(result.integrated_triples)} 个知识三元组")
for triple in result.integrated_triples:
    print(triple.head, triple.relation, triple.tail)
pipeline.export_knowledge_graph("output/knowledge_graph.json")

# 批量处理时复用同一流程实例，知识图谱会持续累积
results = pipeline.process_batch(["doc1.pdf", "doc2.pdf"])
```

## 配置与数据结构

配置示例：

```json
{
  "model": {
    "name": "gpt-4o-mini",
    "api_key": "你的接口密钥",
    "base_url": null
  },
  "pipeline": {
    "relevance_threshold": 0.2,
    "integration_threshold": 0.5
  },
  "output_dir": "output",
  "save_debug_steps": true,
  "debug_dir": null
}
```

配置对象还包含部分预留参数，不能假定每个参数都已接入各节点。`domain` 目前用于记录领域上下文，不会动态切换系统提示词。`get_environment_config()` 可读取 `KARMA_API_KEY`、`KARMA_BASE_URL`、`KARMA_MODEL`、`KARMA_RELEVANCE_THRESHOLD`、`KARMA_INTEGRATION_THRESHOLD` 和 `KARMA_OUTPUT_DIR`；各命令行入口具体支持的覆盖方式以帮助信息为准。

`DocumentMetadata` 仅保留 `title`、`authors`、`pub_date`、`doi`。实体结构包含 `entity_id`、`entity_type`、`name`、`normalized_id`、`aliases`。三元组示例：

```json
{
  "head": "示例论文标题",
  "relation": "applies",
  "tail": "h-index",
  "confidence": 0.9,
  "clarity": 0.8,
  "relevance": 0.8,
  "source": "relationship_extraction"
}
```

模型调用使用普通对话接口，依靠提示词要求返回 JSON，再由代码解析并转换为数据对象；没有启用严格的模型输出结构校验。

## 调试与流程追踪

### 逐步调试文件（数据链路追踪）

默认每次 `process_document()` 都会创建一个独立的调试目录，步骤完成后立即写入
对应 JSON 文件，无需等待整篇文档处理结束。批量处理时，每篇文档使用独立目录。

```text
<output_dir>/debug/<UTC时间戳>_<随机标识>/
├── 00_load_document.json             # 文件解析后的完整原始文本
├── 01_ingestion.json                 # 元数据、清洗后的正文
├── 02_reader.json                    # 全部分块、评分、筛选后的分块
├── 03_summarizer.json                # 各块摘要
├── 04_entity_extraction.json         # 实体及类型、标准编号、别名
├── 05_relationship_extraction.json   # 抽取的关系及评分
├── 06_schema_alignment.json          # 对齐前后的实体与关系
├── 07_conflict_resolution.json       # 新关系、已有关系、冲突处理结果
├── 08_evaluator.json                 # 候选关系、阈值、通过筛选的关系
└── 09_knowledge_graph.json           # 本次入图数据、更新后的完整图谱
```

每个文件包含：

- `step` / `name`：步骤编号和名称。
- `previous_file`：上一执行步骤的文件名；具体数据依赖看 `inputs`。
- `inputs` / `outputs`：该步骤的完整输入和输出，中文直接显示。
- `parameters`：模型名称、请求领域、阈值、输入类型，不包含 API 配置或密钥。
- `started_at` / `finished_at` / `elapsed_seconds`：UTC 时间及耗时。
- `agent_metrics_delta`：该步骤新增的模型调用数、Token 数、错误数等；非 Agent 步骤为空。
- `status`：`completed` 或 `failed`。失败时额外记录 `error` 的类型、消息和调用栈。

输入在执行前复制，输出在执行后立即保存，因此后续原地修改不会覆盖之前的快照。
如果某步抛出异常，此步仍保存失败记录，之前的文件保留，后续步骤不产生文件。
Agent 内部自行捕获并兜底的错误不会将整个步骤标为失败，可结合 `agent_metrics_delta`
和运行日志判断。调试目录无法写入时会报错，不会静默声称已保存。

这些文件记录的是节点边界数据，不是每次模型请求的原始 prompt/response，也不改变
现有抽取逻辑。例如关系节点已经丢弃的 `evidence` 不会在调试文件中凭空恢复。

```bash
# 根目录入口：默认保存到 karma_output/debug/
python main.py Example_Paper.pdf

# 修改结果目录，调试文件随之保存到 results/debug/
python main.py Example_Paper.pdf --output-dir results

# 两个入口都支持自定义调试目录及关闭开关
python main.py Example_Paper.pdf --debug-dir output/my_trace
karma process Example_Paper.pdf --config karma_config.json --debug-dir output/my_trace
python main.py Example_Paper.pdf --no-debug-steps
```

以上命令沿用原有的 API 凭据设置方式。控制台日志会打印本次调试目录。
Python API 可通过 `pipeline.last_debug_dir` 获取最近一次的目录路径：

```python
pipeline = KARMAPipeline(api_key=api_key, debug_dir="output/debug")
result = pipeline.process_document("Example_Paper.pdf")
print(pipeline.last_debug_dir)

# 关闭：KARMAPipeline(api_key=api_key, debug_dir=None)
```

使用配置对象或 JSON 配置时，顶层字段 `save_debug_steps`（默认 `true`）控制开关，
`debug_dir`（默认 `null`）指定根目录；未指定时使用 `<output_dir>/debug`。
该开关独立于原有的 `save_intermediate` / `--save-intermediate`。


## 当前仍需迁移的部分

- 摘要长度限制可能丢失公式、评价或关系证据。
- 实体数据结构尚无公式和局限性字段；关系解析未保存模型响应中的 `evidence`。
- 既有实体提取回退规则、摘要回退词表和部分评分规则尚未完整迁移到科学计量领域。
- 扫描版 PDF、复杂公式、双栏文本以及章节边界需要进一步处理；当前流程不提供完整的 OCR 或公式识别。

中文化覆盖本工程的说明、注释、帮助和运行消息。代码标识符、命令参数、JSON 字段、关系标签、英文论文匹配规则、原文实体及证据保留原样，以维持数据兼容性。依赖包元数据的标准分类标签、原始引用和 MIT 许可文本也保留原文。

## 开发与检查

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 检查 Python 语法及入口帮助，不调用模型
python -m compileall -q karma main.py examples setup.py
python main.py --help
python -m karma.cli --help
bash -n karma.sh
```

当前工程没有随附测试目录。涉及抽取逻辑的后续修改，应另行准备带人工标注的论文样本，并评估指标识别、关系方向、贡献归属和证据保留情况。

## 原项目与引用

原项目作者：Yuxing Lu。原项目仓库：[KARMA](https://github.com/YuxingLu613/KARMA)。论文：[KARMA 原论文](https://arxiv.org/abs/2502.06472)。以下保留原始文献条目，方便学术引用：

```bibtex
@article{lu2025karma,
  title={KARMA: Leveraging Multi-Agent LLMs for Automated Knowledge Graph Enrichment},
  author={Lu, Yuxing and Wang, Jinzhuo},
  journal={arXiv preprint arXiv:2502.06472},
  year={2025}
}
```

本项目采用 MIT 许可证，详见 [许可原文](LICENSE)。原项目问题反馈入口：[问题列表](https://github.com/YuxingLu613/KARMA/issues)。
