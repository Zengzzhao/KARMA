"""命令行帮助和常见参数错误的中文显示，不修改参数名称及解析规则。"""

import argparse
import re
import sys


class ChineseArgumentParser(argparse.ArgumentParser):
    """为主命令及其子命令提供统一的中文界面。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._positionals.title = "位置参数"
        self._optionals.title = "可选参数"
        for action in self._actions:
            if isinstance(action, argparse._HelpAction):
                action.help = "显示帮助信息并退出"

    def format_usage(self):
        """翻译自动生成的用法标题。"""
        return super().format_usage().replace("usage: ", "用法：", 1)

    def format_help(self):
        """翻译帮助页中的用法标题。"""
        return super().format_help().replace("usage: ", "用法：", 1)

    def error(self, message):
        """以中文显示常见参数错误，保留具体参数及输入值。"""
        translations = (
            ("the following arguments are required:", "缺少必需参数："),
            ("unrecognized arguments:", "无法识别的参数："),
            ("expected one argument", "需要一个参数值"),
            ("expected at least one argument", "至少需要一个参数值"),
            ("invalid choice:", "无效的选项值："),
            ("choose from", "可选值为"),
            ("not allowed with argument", "不能与以下参数同时使用："),
            ("argument ", "参数 "),
        )
        for original, translated in translations:
            message = message.replace(original, translated)
        message = re.sub(r"invalid (\w+) value:", r"无效的 \1 类型值：", message)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}：错误：{message}\n")
