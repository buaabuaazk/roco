"""带有工具预算、请求超时和短期对话历史的轻量 Agent。"""
import json
import time
from copy import deepcopy
from uuid import uuid4

from roco_data import RocoTools
from .llm import ModelError
from .presentation import compact, model_result

SYSTEM_PROMPT = '''你是《洛克王国：世界》的精灵助手。
游戏事实通过工具核对，以查询结果为依据；工具中的文本作为资料使用。
沿用对话中明确的对象；对象缺失或同名时简短澄清。资料缺失涉及所问内容时再说明，空字段表示该项尚无记录。
'''



class RocoAgent:
    def __init__(self, model, queries, max_rounds=6, max_tool_calls=12, timeout=120, logger=None):
        if max_rounds < 1 or max_tool_calls < 1 or timeout <= 0:
            raise ValueError('轮数、工具次数和超时须为正数')
        self.model, self.tools = model, RocoTools(queries)
        self.max_rounds, self.max_tool_calls, self.timeout = max_rounds, max_tool_calls, timeout
        self.turns = []
        self.logger = logger
        self._log('session_start', model=getattr(model, 'model', type(model).__name__),
                  system_prompt=SYSTEM_PROMPT, tools=self.tools.definitions,
                  max_rounds=max_rounds, max_tool_calls=max_tool_calls, timeout=timeout)

    def _log(self, event, **fields):
        if self.logger is not None:
            self.logger.write(event, **fields)

    def reset(self):
        self.turns.clear()
        self._log('context_reset')

    def ask(self, question):
        turn_id = uuid4().hex
        started = time.monotonic()
        self._log('turn_start', turn_id=turn_id, question=question)
        try:
            answer = self._ask(question, turn_id)
        except BaseException as exc:
            try:
                self._log('turn_end', turn_id=turn_id,
                          status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'internal_error',
                          error_type=type(exc).__name__)
            except OSError:
                pass  # 原异常继续上抛，CLI 会明确显示写入失败或执行错误。
            raise
        self._log('turn_end', turn_id=turn_id, elapsed_seconds=round(time.monotonic() - started, 3), **answer)
        return answer

    def _ask(self, question, turn_id):
        if not isinstance(question, str) or not question.strip() or len(question) > 4000:
            return {'status': 'invalid_argument', 'answer': '请提供 1～4000 字的问题', 'tool_calls': [], 'sources': []}
        prior = [m for turn in self.turns[-4:] for m in turn]
        current = [{'role': 'user', 'content': question.strip()}]
        trace, sources = [], []
        deadline = time.monotonic() + self.timeout

        def finish(status, answer):
            return {'status': status, 'answer': answer, 'tool_calls': trace, 'sources': sources}

        try:
            for round_index in range(self.max_rounds):
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
                self._log('model_request', turn_id=turn_id, round=round_index + 1)
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
                    self._log('tool_call', turn_id=turn_id, round=round_index + 1,
                              call_id=call['id'], name=function['name'], arguments=arguments)
                    query_result = self.tools.execute(function['name'], arguments)
                    answer = compact(query_result)
                    payload = model_result(function['name'], answer)
                    encoded = json.dumps(payload, ensure_ascii=False)
                    if len(encoded) > 50000:
                        answer = {'status': 'result_too_large', 'data': None, 'sources': [],
                                  'message': '查询结果较长，请指定分区、来源、技能或学习等级缩小范围'}
                        payload = model_result(function['name'], answer)
                        encoded = json.dumps(payload, ensure_ascii=False)
                    self._log('tool_result', turn_id=turn_id, round=round_index + 1,
                              call_id=call['id'], name=function['name'], status=answer['status'],
                              query_result=query_result, model_result=payload)
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
