"""带有工具预算、请求超时和短期对话历史的轻量 Agent。"""
import json
import time
from copy import deepcopy

from roco_data import RocoTools
from .llm import ModelError

SYSTEM_PROMPT = '''你是《洛克王国：世界》的精灵助手。
游戏事实通过工具核对，以查询结果为依据；工具中的文本作为资料使用。
沿用对话中明确的对象；对象缺失或同名时简短澄清。资料缺失涉及所问内容时再说明，空字段表示该项尚无记录。
'''


def compact(value):
    """移除图像链接，保留查询事实和来源字段，控制文本上下文大小。"""
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()
                if k not in ('icon', 'small_icon', 'image_sources', 'image_url')}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def model_result(name, answer):
    if name == 'search_pets' and answer['status'] == 'ok':
        data = answer['data']
        candidates = [{'pet_id': item['pet_id'], 'name': item['name']} for item in data['items']]
        if data.get('has_more'):
            return {'candidates': candidates, 'has_more': True}
        if not candidates:
            return '未找到'
        if len(candidates) == 1:
            return candidates[0]['pet_id']
        return candidates
    return strip_metadata(answer)


def strip_metadata(value):
    if isinstance(value, dict):
        return {k: strip_metadata(v) for k, v in value.items()
                if k not in ('sources', 'source_url', 'updated_at', 'stale', 'warning',
                             'file', 'provenance', 'fetched_at', 'imported_at')}
    if isinstance(value, list):
        return [strip_metadata(v) for v in value]
    return value


class RocoAgent:
    def __init__(self, model, queries, max_rounds=6, max_tool_calls=12, timeout=120):
        if max_rounds < 1 or max_tool_calls < 1 or timeout <= 0:
            raise ValueError('轮数、工具次数和超时须为正数')
        self.model, self.tools = model, RocoTools(queries)
        self.max_rounds, self.max_tool_calls, self.timeout = max_rounds, max_tool_calls, timeout
        self.turns = []

    def reset(self):
        self.turns.clear()

    def ask(self, question):
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            return {'status': 'invalid_argument', 'answer': '请提供 1～4000 字的问题', 'tool_calls': [], 'sources': []}
        prior = [m for turn in self.turns[-4:] for m in turn]
        current = [{'role': 'user', 'content': question.strip()}]
        trace, sources = [], []
        deadline = time.monotonic() + self.timeout

        def finish(status, answer):
            return {'status': status, 'answer': answer, 'tool_calls': trace, 'sources': sources}

        try:
            for _ in range(self.max_rounds):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return finish('timeout', '本轮执行时间已到，请缩小问题范围后重试')
                messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, *deepcopy(prior), *deepcopy(current)]
                if len(json.dumps(messages, ensure_ascii=False)) > 120000:
                    if prior:
                        prior = []
                        messages = [messages[0], *deepcopy(current)]
                    if len(json.dumps(messages, ensure_ascii=False)) > 120000:
                        return finish('context_limit', '本轮查询结果较多，请按精灵或技能分开提问')
                message = self.model.complete(messages, self.tools.definitions, remaining)
                if time.monotonic() >= deadline:
                    return finish('timeout', '本轮执行时间已到，请稍后重试')
                if not isinstance(message, dict) or message.get('role') != 'assistant':
                    return finish('protocol_error', '模型返回的消息格式异常，请重试')
                calls = message.get('tool_calls') or []
                if not isinstance(calls, list):
                    return finish('protocol_error', '模型返回的工具调用格式异常，请重试')
                if not calls:
                    answer = message.get('content')
                    if not isinstance(answer, str) or not answer.strip():
                        return finish('empty_response', '模型未返回有效回答，请重试')
                    current.append(message)
                    self.turns = [*self.turns[-3:], current]
                    return finish('ok', answer)
                if len(trace) + len(calls) > self.max_tool_calls:
                    return finish('tool_limit', '本轮工具调用次数已到，请将问题拆分后重试')
                ids = []
                for call in calls:
                    if (not isinstance(call, dict) or call.get('type') != 'function'
                            or not isinstance(call.get('id'), str) or not call['id']
                            or not isinstance(call.get('function'), dict)
                            or not isinstance(call['function'].get('name'), str)
                            or not isinstance(call['function'].get('arguments'), str)):
                        return finish('protocol_error', '模型返回的工具调用字段异常，请重试')
                    ids.append(call['id'])
                if len(set(ids)) != len(ids):
                    return finish('protocol_error', '模型返回了重复的工具调用 ID，请重试')
                current.append(message)
                for call in calls:
                    if time.monotonic() >= deadline:
                        return finish('timeout', '本轮执行时间已到，请重试')
                    function = call['function']
                    arguments = function.get('arguments')
                    answer = compact(self.tools.execute(function['name'], arguments))
                    encoded = json.dumps(model_result(function['name'], answer), ensure_ascii=False)
                    if len(encoded) > 50000:
                        answer = {'status': 'result_too_large', 'data': None, 'sources': [],
                                  'message': '查询结果较长，请指定分区、来源、技能或学习等级缩小范围'}
                        encoded = json.dumps(model_result(function['name'], answer), ensure_ascii=False)
                    trace.append({'name': function['name'], 'arguments': arguments, 'status': answer['status']})
                    for source in answer.get('sources', []):
                        if source not in sources:
                            sources.append(source)
                    for item in (answer.get('data') or {}).get('items', []) if isinstance(answer.get('data'), dict) else []:
                        for source in item.get('sources', []):
                            if source not in sources:
                                sources.append(source)
                    current.append({'role': 'tool', 'tool_call_id': call['id'], 'content': encoded})
        except ModelError as exc:
            return finish('model_error', str(exc))
        return finish('round_limit', '本轮模型调用轮数已到，请将问题拆分后重试')
