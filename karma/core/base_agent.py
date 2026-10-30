"""
KARMA 框架的智能体基类。

本模块提供所有智能体共同继承的抽象基类，
统一处理接口并复用公共功能。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple, Optional
import time
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    所有 KARMA 智能体的抽象基类。

    提供模型客户端管理、
    词元统计、错误处理和性能监测等公共功能。

    属性：
        client: OpenAI 客户端实例
        model_name: 大语言模型名称
        system_prompt: 智能体系统提示词；调用时可覆盖默认值
        metrics: 性能统计数据
    """

    def __init__(self, client: OpenAI, model_name: str, system_prompt: str = ""):
        """
        初始化智能体基类。

        参数：
            client: OpenAI 客户端实例
            model_name: 大语言模型名称
            system_prompt: 智能体系统提示词；调用时可覆盖默认值
        """
        self.client = client
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.metrics = {
            'total_calls': 0,
            'total_prompt_tokens': 0,
            'total_completion_tokens': 0,
            'total_time': 0.0,
            'error_count': 0
        }

    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """
        智能体的主要处理方法。

        所有具体智能体类都必须实现此方法。
        """
        pass

    def _make_llm_call(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int, int, float]:
        """
        调用大语言模型，处理错误并记录调用统计。

        参数：
            prompt: 用户提示词
            temperature: 采样温度
            max_tokens: 最大生成词元数
            system_prompt: 智能体系统提示词；调用时可覆盖默认值

        返回：
            返回元组 (response_content, prompt_tokens, completion_tokens, processing_time)

        异常：
            Exception：模型调用失败
        """
        start_time = time.time()

        try:
            messages = [
                {"role": "system", "content": system_prompt or self.system_prompt},
                {"role": "user", "content": prompt}
            ]

            call_kwargs = {
                "model": self.model_name,
                "messages": messages,
                "temperature": temperature
            }

            if max_tokens:
                call_kwargs["max_tokens"] = max_tokens

            response = self.client.chat.completions.create(**call_kwargs)

            content = response.choices[0].message.content.strip()
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            processing_time = time.time() - start_time

            # 更新调用统计。
            self.metrics['total_calls'] += 1
            self.metrics['total_prompt_tokens'] += prompt_tokens
            self.metrics['total_completion_tokens'] += completion_tokens
            self.metrics['total_time'] += processing_time

            return content, prompt_tokens, completion_tokens, processing_time

        except Exception as e:
            processing_time = time.time() - start_time
            self.metrics['error_count'] += 1
            self.metrics['total_time'] += processing_time

            logger.error(f"{self.__class__.__name__} 大语言模型调用失败： {str(e)}")
            raise

    def _extract_float_from_text(self, text: str, default: float = 0.5) -> float:
        """
        从文本响应中提取浮点数。

        参数：
            text: 待处理的文本
            default: 未提取到数值时使用的默认值

        返回：
            提取的浮点数，限制在 [0.0, 1.0] 范围内
        """
        import re

        # 查找文本中的浮点数。
        float_matches = re.findall(r"[-+]?\d*\.\d+|\d+", text)
        if float_matches:
            try:
                score = float(float_matches[0])
                # 将分数限制在 [0.0, 1.0]。
                return max(0.0, min(1.0, score))
            except ValueError:
                pass

        return default

    def _parse_json_response(self, response: str) -> List[Dict]:
        """
        解析模型返回的 JSON，并处理解析错误。

        参数：
            response: 包含 JSON 的模型响应

        返回：
            解析得到的 JSON 数据；失败时返回空列表
        """
        import json

        try:
            # 优先查找 JSON 数组。
            if "[" in response and "]" in response:
                json_str = response[response.find("["):response.rfind("]")+1]
                return json.loads(json_str)

            # 尝试将完整响应解析为 JSON。
            return json.loads(response)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 响应解析失败： {e}")
            return []

    def get_metrics(self) -> Dict:
        """
        获取当前智能体的性能统计。

        返回：
            性能统计字典
        """
        return self.metrics.copy()

    def reset_metrics(self):
        """重置所有性能统计。"""
        self.metrics = {
            'total_calls': 0,
            'total_prompt_tokens': 0,
            'total_completion_tokens': 0,
            'total_time': 0.0,
            'error_count': 0
        }

    def __str__(self) -> str:
        """返回智能体的字符串表示。"""
        return f"{self.__class__.__name__}(model={self.model_name})"

    def __repr__(self) -> str:
        """返回智能体的详细状态表示。"""
        return f"{self.__class__.__name__}(model={self.model_name}, calls={self.metrics['total_calls']})"
