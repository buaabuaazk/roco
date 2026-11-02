"""通过智增增的 OpenAI 兼容接口调用模型。"""
import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

BASE_URL = 'https://api.zhizengzeng.com/v1'
DEFAULT_MODEL = 'deepseek-v4.1-flash'


class ModelError(RuntimeError):
    """适合向用户显示的脱敏模型错误。"""


class ChatModel:
    def __init__(self, model=None):
        key = os.environ.get('ZZZ_API_KEY', '').strip()
        self.model = (model or '').strip() or os.environ.get('LLM_MODEL_ID', '').strip() or DEFAULT_MODEL
        if not key:
            raise ValueError('请在本机环境变量中设置 ZZZ_API_KEY')
        self.client = OpenAI(api_key=key, base_url=BASE_URL, timeout=60, max_retries=0)

    def close(self):
        self.client.close()

    def complete(self, messages, tools, timeout):
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=tools, tool_choice='auto',
                max_tokens=2048, timeout=min(timeout, 60),
            )
        except APITimeoutError:
            raise ModelError('模型请求超时，请稍后重试') from None
        except APIConnectionError:
            raise ModelError('模型连接失败，请检查网络与代理配置') from None
        except APIStatusError as exc:
            raise ModelError(f'模型请求失败：HTTP {exc.status_code}；请检查账号、模型权限和接口支持') from None
        if not response.choices:
            raise ModelError('模型返回了空的 choices')
        if response.choices[0].finish_reason == 'length':
            raise ModelError('模型输出达到长度上限，请缩小问题范围')
        message = response.choices[0].message.model_dump(exclude_none=True)
        # 保留兼容模型在后续工具回传中可能需要的 reasoning_content。
        return {k: v for k, v in message.items() if k in ('role', 'content', 'tool_calls', 'reasoning_content', 'refusal')}
