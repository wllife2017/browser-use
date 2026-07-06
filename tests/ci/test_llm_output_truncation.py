"""Regression test: structured output cut off at the completion-token cap must raise a
clear truncation error, not a misleading JSON parse error ('Unterminated string...')."""

import pytest
from pydantic import BaseModel

from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import UserMessage
from browser_use.llm.openai.chat import ChatOpenAI


class AnswerFormat(BaseModel):
	answer: str


async def test_openai_truncated_structured_output_raises_clear_error(httpserver):
	"""finish_reason='length' with JSON cut mid-string must surface the token cap, not a parse error."""
	httpserver.expect_request('/v1/chat/completions', method='POST').respond_with_json(
		{
			'id': 'chatcmpl-test',
			'object': 'chat.completion',
			'created': 0,
			'model': 'gpt-4o',
			'choices': [
				{
					'index': 0,
					'message': {'role': 'assistant', 'content': '{"answer": "this output was cut off mid-sent'},
					'finish_reason': 'length',
				}
			],
			'usage': {'prompt_tokens': 10, 'completion_tokens': 4096, 'total_tokens': 4106},
		}
	)

	llm = ChatOpenAI(model='gpt-4o', api_key='test-key', base_url=httpserver.url_for('/v1'))

	with pytest.raises(ModelProviderError) as exc_info:
		await llm.ainvoke([UserMessage(content='answer at length')], output_format=AnswerFormat)

	assert 'truncated' in str(exc_info.value), f'expected a truncation error, got: {exc_info.value}'
	assert 'max_completion_tokens' in str(exc_info.value)


async def test_openai_normal_structured_output_still_parses(httpserver):
	httpserver.expect_request('/v1/chat/completions', method='POST').respond_with_json(
		{
			'id': 'chatcmpl-test',
			'object': 'chat.completion',
			'created': 0,
			'model': 'gpt-4o',
			'choices': [
				{
					'index': 0,
					'message': {'role': 'assistant', 'content': '{"answer": "complete answer"}'},
					'finish_reason': 'stop',
				}
			],
			'usage': {'prompt_tokens': 10, 'completion_tokens': 8, 'total_tokens': 18},
		}
	)

	llm = ChatOpenAI(model='gpt-4o', api_key='test-key', base_url=httpserver.url_for('/v1'))

	result = await llm.ainvoke([UserMessage(content='answer briefly')], output_format=AnswerFormat)
	assert result.completion.answer == 'complete answer'
