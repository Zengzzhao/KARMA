#!/bin/bash

# KARMA 处理流程启动脚本
# 本脚本提供运行 KARMA 处理流程的命令行入口

# 终端输出颜色
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
PURPLE='\\033[0;35m'
CYAN='\\033[0;36m'
NC='\\033[0m' # 重置颜色

# 默认参数
API_KEY="${KARMA_API_KEY}"
MODEL="gpt-4o-mini"
RELEVANCE_THRESHOLD="0.2"
INTEGRATION_THRESHOLD="0.5"
OUTPUT_DIR="karma_output"
DOMAIN="biomedical"
VERBOSE=""

# 输出带颜色的提示
print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}    KARMA 流程启动器${NC}"
    echo -e "${BLUE}================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# 显示使用说明
show_usage() {
    echo "用法： $0 [OPTIONS] <input_file>"
    echo ""
    echo "选项："
    echo "  -k, --api-key KEY           OpenAI 接口密钥（默认读取 KARMA_API_KEY 环境变量）"
    echo "  -m, --model MODEL           使用模型（默认：gpt-4o-mini）"
    echo "  -r, --relevance-threshold   相关性阈值（默认：0.2）"
    echo "  -i, --integration-threshold 整合阈值（默认：0.5）"
    echo "  -o, --output-dir DIR        输出目录（默认：karma_output）"
    echo "  -d, --domain DOMAIN         领域上下文（默认：biomedical，历史兼容值，不切换提示词）"
    echo "  -v, --verbose               输出详细信息"
    echo "  -h, --help                  显示帮助信息"
    echo ""
    echo "示例："
    echo "  $0 document.pdf"
    echo "  $0 -m gpt-4 -r 0.3 -i 0.7 document.pdf"
    echo "  $0 --verbose --output-dir results/ document.pdf"
}

# 检查运行环境
check_prerequisites() {
    print_info "正在检查运行环境……"

    # 检查 Python 是否可用
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 Python 3，请安装 Python 3.8 或更高版本"
        exit 1
    fi

    # 检查 Python 版本
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [[ $(echo "$python_version < 3.8" | bc -l) -eq 1 ]]; then
        print_error "需要 Python 3.8 或更高版本，当前版本： $python_version"
        exit 1
    fi

    # 检查 main.py 是否存在
    if [[ ! -f "main.py" ]]; then
        print_error "未找到 main.py，请在 KARMA 工程根目录运行此脚本。"
        exit 1
    fi

    print_success "运行环境检查通过"
}

# 运行处理流程
run_pipeline() {
    local input_file="$1"

    print_header
    print_info "正在启动 KARMA 处理流程……"
    print_info "输入： $input_file"
    print_info "模型： $MODEL"
    print_info "输出： $OUTPUT_DIR"

    # 检查输入文件是否存在
    if [[ ! -f "$input_file" ]]; then
        print_error "输入文件不存在： $input_file"
        exit 1
    fi

    # 组装执行命令
    cmd="python3 main.py"
    cmd="$cmd \\"$input_file\\""
    cmd="$cmd --api-key \\"$API_KEY\\""
    cmd="$cmd --model $MODEL"
    cmd="$cmd --relevance-threshold $RELEVANCE_THRESHOLD"
    cmd="$cmd --integration-threshold $INTEGRATION_THRESHOLD"
    cmd="$cmd --output-dir \\"$OUTPUT_DIR\\""
    cmd="$cmd --domain $DOMAIN"

    if [[ -n "$VERBOSE" ]]; then
        cmd="$cmd --verbose"
    fi

    print_info "正在执行： $cmd"
    echo ""

    # 执行命令
    eval $cmd
    exit_code=$?

    echo ""
    if [[ $exit_code -eq 0 ]]; then
        print_success "流程执行完成！"
        print_info "结果已保存到： $OUTPUT_DIR"
    else
        print_error "流程执行失败，退出码： $exit_code"
        exit $exit_code
    fi
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -k|--api-key)
            API_KEY="$2"
            shift 2
            ;;
        -m|--model)
            MODEL="$2"
            shift 2
            ;;
        -r|--relevance-threshold)
            RELEVANCE_THRESHOLD="$2"
            shift 2
            ;;
        -i|--integration-threshold)
            INTEGRATION_THRESHOLD="$2"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -d|--domain)
            DOMAIN="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="--verbose"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        -*)
            print_error "未知选项： $1"
            show_usage
            exit 1
            ;;
        *)
            # 该参数作为输入文件
            INPUT_FILE="$1"
            shift
            ;;
    esac
done

# 检查是否提供输入文件
if [[ -z "$INPUT_FILE" ]]; then
    print_error "必须提供输入文件"
    show_usage
    exit 1
fi

# 检查是否提供接口密钥
if [[ -z "$API_KEY" ]]; then
    print_error "必须提供接口密钥，请设置 KARMA_API_KEY 环境变量或使用 -k 选项"
    exit 1
fi

# 检查运行环境
check_prerequisites

# 运行处理流程
run_pipeline "$INPUT_FILE"