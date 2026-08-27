import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, overload

import httpx
from ollama import AsyncClient as OllamaAsyncClient
from ollama import Options
from pydantic import BaseModel, ValidationError

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage
from browser_use.llm.ollama.serializer import OllamaMessageSerializer
from browser_use.llm.views import ChatInvokeCompletion

T = TypeVar('T', bound=BaseModel)
logger = logging.getLogger(__name__)

# These belong on AsyncClient.chat(), not in the model `options` dict.
_TOP_LEVEL_CHAT_KEYS = frozenset({'format', 'stream'})


def _unwrap_json_content(content: str) -> str:
	"""Strip markdown code fences that Ollama vision models often wrap around JSON."""
	text = content.strip()
	if text.startswith('```json') and text.endswith('```'):
		return text[7:-3].strip()
	if text.startswith('```') and text.endswith('```'):
		return text[3:-3].strip()
	return text


@dataclass
class ChatOllama(BaseChatModel):
	"""
	A wrapper around Ollama's chat model.
	"""

	model: str

	# # Model params
	# TODO (matic): Why is this commented out?
	# temperature: float | None = None

	# Client initialization parameters
	host: str | None = None
	timeout: float | httpx.Timeout | None = None
	client_params: dict[str, Any] | None = None
	ollama_options: Mapping[str, Any] | Options | None = None

	# Static
	@property
	def provider(self) -> str:
		return 'ollama'

	def _get_client_params(self) -> dict[str, Any]:
		"""Prepare client parameters dictionary."""
		return {
			'host': self.host,
			'timeout': self.timeout,
			'client_params': self.client_params,
		}

	def get_client(self) -> OllamaAsyncClient:
		"""
		Returns an OllamaAsyncClient client.
		"""
		return OllamaAsyncClient(host=self.host, timeout=self.timeout, **self.client_params or {})

	@property
	def name(self) -> str:
		return self.model

	def _chat_options(self) -> Mapping[str, Any] | Options | None:
		"""Return ollama_options with top-level chat keys removed.

		`format` and `stream` are parameters of `AsyncClient.chat()`, not model
		runtime options. Putting them in `ollama_options` is ignored or fights
		the structured-output schema we already pass as `format=`.
		"""
		options = self.ollama_options
		if not options or not isinstance(options, Mapping):
			return options

		dropped = sorted(key for key in options if key in _TOP_LEVEL_CHAT_KEYS)
		if not dropped:
			return options

		logger.warning(
			'Ignoring %s in ollama_options; those are top-level chat() parameters, not model options',
			', '.join(dropped),
		)
		return {key: value for key, value in options.items() if key not in _TOP_LEVEL_CHAT_KEYS}

	@overload
	async def ainvoke(
		self, messages: list[BaseMessage], output_format: None = None, **kwargs: Any
	) -> ChatInvokeCompletion[str]: ...

	@overload
	async def ainvoke(self, messages: list[BaseMessage], output_format: type[T], **kwargs: Any) -> ChatInvokeCompletion[T]: ...

	async def ainvoke(
		self, messages: list[BaseMessage], output_format: type[T] | None = None, **kwargs: Any
	) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
		ollama_messages = OllamaMessageSerializer.serialize_messages(messages)

		try:
			options = self._chat_options()
			if output_format is None:
				response = await self.get_client().chat(
					model=self.model,
					messages=ollama_messages,
					options=options,
				)

				return ChatInvokeCompletion(completion=response.message.content or '', usage=None)

			schema = output_format.model_json_schema()
			response = await self.get_client().chat(
				model=self.model,
				messages=ollama_messages,
				format=schema,
				options=options,
			)

			completion = _unwrap_json_content(response.message.content or '')
			try:
				parsed = output_format.model_validate_json(completion)
			except ValidationError as e:
				raise ModelProviderError(
					message=f'Ollama returned invalid JSON for structured output: {e}',
					model=self.name,
				) from e

			return ChatInvokeCompletion(completion=parsed, usage=None)

		except ModelProviderError:
			raise
		except Exception as e:
			raise ModelProviderError(message=str(e), model=self.name) from e
