"""Agent task command handler."""

import logging
import os
from typing import Any

from browser_use.skill_cli.sessions import SessionInfo

logger = logging.getLogger(__name__)


async def handle(session: SessionInfo, params: dict[str, Any]) -> Any:
	"""Handle agent run command.

	Runs a task using the local browser-use agent.
	"""
	task = params.get('task')
	if not task:
		return {'success': False, 'error': 'No task provided'}

	return await _handle_local_task(session, params)


async def _handle_local_task(session: SessionInfo, params: dict[str, Any]) -> Any:
	"""Handle task execution locally with browser-use agent."""
	task = params['task']
	max_steps = params.get('max_steps')
	model = params.get('llm')  # Optional model override

	try:
		# Import agent and LLM
		from browser_use.agent.service import Agent

		# Try to get LLM from environment (with optional model override)
		llm = await get_llm(model=model)
		if llm is None:
			if model:
				return {
					'success': False,
					'error': f'Could not initialize model "{model}". '
					f'Make sure the appropriate API key is set (OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY).',
				}
			return {
				'success': False,
				'error': 'No LLM configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY',
			}

		# Create and run agent
		agent = Agent(
			task=task,
			llm=llm,
			browser_session=session.browser_session,
		)

		logger.info(f'Running local agent task: {task}')
		run_kwargs = {}
		if max_steps is not None:
			run_kwargs['max_steps'] = max_steps
		result = await agent.run(**run_kwargs)

		# Extract result info
		final_result = result.final_result() if result else None

		return {
			'success': True,
			'task': task,
			'steps': len(result) if result else 0,
			'result': str(final_result) if final_result else None,
			'done': result.is_done() if result else False,
		}

	except Exception as e:
		logger.exception(f'Local agent task failed: {e}')
		return {
			'success': False,
			'error': str(e),
			'task': task,
		}


def _get_verified_models() -> dict[str, set[str]]:
	"""Extract verified model names from SDK sources of truth."""
	import typing

	from anthropic.types.model_param import ModelParam
	from openai.types.shared.chat_model import ChatModel

	from browser_use.llm.google.chat import VerifiedGeminiModels

	# OpenAI: ChatModel is a Literal type
	openai_models = set(typing.get_args(ChatModel))

	# Anthropic: ModelParam is Union[Literal[...], str] - extract the Literal
	anthropic_literal = typing.get_args(ModelParam)[0]
	anthropic_models = set(typing.get_args(anthropic_literal))

	# Google: VerifiedGeminiModels Literal
	google_models = set(typing.get_args(VerifiedGeminiModels))

	return {
		'openai': openai_models,
		'anthropic': anthropic_models,
		'google': google_models,
	}


_VERIFIED_MODELS: dict[str, set[str]] | None = None


def _get_provider_for_model(model: str) -> str | None:
	"""Determine the provider by checking SDK verified model lists."""
	global _VERIFIED_MODELS
	if _VERIFIED_MODELS is None:
		_VERIFIED_MODELS = _get_verified_models()

	for provider, models in _VERIFIED_MODELS.items():
		if model in models:
			return provider

	return None


def get_llm(model: str | None = None) -> Any:
	"""Get LLM instance from environment configuration.

	Args:
		model: Optional model name to use. If provided, will instantiate
		       the appropriate provider for that model. If not provided,
		       auto-detects from available API keys.

	Supported providers: OpenAI, Anthropic, Google.
	Model names are validated against each SDK's verified model list.
	"""
	from browser_use.llm import ChatAnthropic, ChatGoogle, ChatOpenAI

	if model:
		provider = _get_provider_for_model(model)

		if provider == 'openai':
			return ChatOpenAI(model=model)
		elif provider == 'anthropic':
			return ChatAnthropic(model=model)
		elif provider == 'google':
			return ChatGoogle(model=model)
		else:
			logger.warning(f'Unknown model: {model}. Not in any verified model list.')
			return None

	# No model specified - auto-detect from available API keys
	if os.environ.get('OPENAI_API_KEY'):
		return ChatOpenAI(model='o3')

	if os.environ.get('ANTHROPIC_API_KEY'):
		return ChatAnthropic(model='claude-sonnet-4-0')

	if os.environ.get('GOOGLE_API_KEY'):
		return ChatGoogle(model='gemini-flash-latest')

	return None
