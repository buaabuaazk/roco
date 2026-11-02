import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openai import APIConnectionError, APIStatusError, APITimeoutError

from roco_agent.llm import ChatModel, ModelError


class ModelTests(unittest.TestCase):
    def test_config_and_preserve_reasoning_for_tool_round_trip(self):
        with patch.dict(os.environ, {'ZZZ_API_KEY': 'test-key', 'LLM_MODEL_ID': 'test-model'}), \
                patch('roco_agent.llm.OpenAI') as sdk:
            model = ChatModel()
            message = {'role': 'assistant', 'reasoning_content': 'provider content', 'tool_calls': [], 'content': '回答'}
            sdk.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(model_dump=lambda **kwargs: message))])
            self.assertEqual(model.complete([], [], 10), message)
            self.assertEqual(sdk.call_args.kwargs['max_retries'], 0)
            self.assertEqual(sdk.return_value.chat.completions.create.call_args.kwargs['timeout'], 10)
            model.close()
            sdk.return_value.close.assert_called_once()

    def test_provider_errors_are_sanitized(self):
        request = SimpleNamespace(method='POST', url='https://example.test')
        errors = [APIConnectionError(request=request), APITimeoutError(request=request),
                  APIStatusError('PRIVATE_PROVIDER_BODY', response=SimpleNamespace(status_code=429, request=request, headers={}),
                                 body={'private': 'PRIVATE_PROVIDER_BODY'})]
        with patch.dict(os.environ, {'ZZZ_API_KEY': 'test-key', 'LLM_MODEL_ID': 'test-model'}), \
                patch('roco_agent.llm.OpenAI') as sdk:
            model = ChatModel()
            for error in errors:
                sdk.return_value.chat.completions.create.side_effect = error
                with self.assertRaises(ModelError) as caught:
                    model.complete([], [], 10)
                self.assertNotIn('PRIVATE_PROVIDER_BODY', str(caught.exception))
                self.assertNotIn('test-key', str(caught.exception))

    def test_missing_config_is_explicit(self):
        with patch.dict(os.environ, {'ZZZ_API_KEY': '', 'LLM_MODEL_ID': ''}):
            with self.assertRaisesRegex(ValueError, 'ZZZ_API_KEY'):
                ChatModel()
        with patch.dict(os.environ, {'ZZZ_API_KEY': 'test-key', 'LLM_MODEL_ID': ''}):
            with self.assertRaisesRegex(ValueError, 'LLM_MODEL_ID'):
                ChatModel()


if __name__ == '__main__':
    unittest.main()
