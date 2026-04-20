"""Per-action timeout regression test.

When a CDP WebSocket goes silent (common failure mode with remote / cloud browsers),
action handlers can await event-bus dispatches that never resolve — individual CDP
calls like Page.navigate() have their own timeouts, but the surrounding event
plumbing does not. Without a per-action cap, `tools.act()` hangs indefinitely and
agents never emit a step, producing empty history traces.

This test replaces `registry.execute_action` with a coroutine that sleeps longer
than the per-action cap, then asserts that `tools.act()` returns within the cap
with an ActionResult(error=...) instead of hanging.
"""

import asyncio
import time
from typing import Any

import pytest

from browser_use.agent.views import ActionModel, ActionResult
from browser_use.tools.service import Tools


class _StubActionModel(ActionModel):
	"""ActionModel with two arbitrary named slots for tools.act() plumbing tests.

	Tests target tools.act() behaviour (timeout wrapping, error handling), not any
	registered action — so we declare fixed slots here and stub out execute_action.
	"""

	hung_action: dict[str, Any] | None = None
	fast_action: dict[str, Any] | None = None


@pytest.mark.asyncio
async def test_act_enforces_per_action_timeout_on_hung_handler():
	"""tools.act() must return within action_timeout even if the handler hangs."""
	tools = Tools()

	# Replace the action executor with one that hangs far past the timeout.
	sleep_seconds = 30.0
	call_count = {'n': 0}

	async def _hanging_execute_action(**_kwargs):
		call_count['n'] += 1
		await asyncio.sleep(sleep_seconds)
		return ActionResult(extracted_content='should never be reached')

	tools.registry.execute_action = _hanging_execute_action  # type: ignore[assignment]

	# Build an ActionModel with a single slot — act() iterates model_dump(exclude_unset=True).
	action = _StubActionModel(hung_action={'url': 'https://example.com'})

	# Use a tight timeout so the test runs in under a second.
	action_timeout = 0.5
	start = time.monotonic()
	result = await tools.act(action=action, browser_session=None, action_timeout=action_timeout)  # type: ignore[arg-type]
	elapsed = time.monotonic() - start

	# Handler got invoked exactly once.
	assert call_count['n'] == 1

	# Returned well before the sleep would have finished.
	assert elapsed < sleep_seconds / 2, f'act() did not honor timeout; took {elapsed:.2f}s'
	# And returned close to the timeout itself (with a reasonable grace margin).
	assert elapsed < action_timeout + 2.0, f'act() overshot timeout; took {elapsed:.2f}s'

	# Returned a proper ActionResult describing the timeout.
	assert isinstance(result, ActionResult)
	assert result.error is not None
	assert 'timed out' in result.error.lower()
	assert 'hung_action' in result.error


@pytest.mark.asyncio
async def test_act_passes_through_fast_handler():
	"""When the handler finishes fast, act() returns its result unchanged."""
	tools = Tools()

	async def _fast_execute_action(**_kwargs):
		return ActionResult(extracted_content='done')

	tools.registry.execute_action = _fast_execute_action  # type: ignore[assignment]

	action = _StubActionModel(fast_action={'x': 1})
	result = await tools.act(action=action, browser_session=None, action_timeout=5.0)  # type: ignore[arg-type]

	assert isinstance(result, ActionResult)
	assert result.error is None
	assert result.extracted_content == 'done'


def test_default_action_timeout_accommodates_extract_action():
	"""The module-level default must sit above extract's 120s LLM inner cap."""
	from browser_use.tools.service import _DEFAULT_ACTION_TIMEOUT_S

	# extract action uses page_extraction_llm.ainvoke(..., timeout=120.0); the
	# outer per-action cap must not truncate it.
	assert _DEFAULT_ACTION_TIMEOUT_S >= 150.0, (
		f'Default action cap ({_DEFAULT_ACTION_TIMEOUT_S}s) is below the 120s '
		f'extract timeout + grace — slow but valid extractions would be killed.'
	)


def test_malformed_env_timeout_does_not_break_import(monkeypatch):
	"""Empty / non-numeric BROWSER_USE_ACTION_TIMEOUT_S must not crash import.

	Env-templating tools sometimes produce empty strings; that turning into a
	ValueError at module import would take out every tool call process-wide.
	"""
	import importlib

	import browser_use.tools.service as svc_module

	for bad_value in ('', 'not-a-number', 'abc'):
		monkeypatch.setenv('BROWSER_USE_ACTION_TIMEOUT_S', bad_value)
		# Re-import cleanly; this would have raised ValueError before the fix.
		reloaded = importlib.reload(svc_module)
		# Fell back to the hardcoded default (180s) without raising.
		assert reloaded._DEFAULT_ACTION_TIMEOUT_S == 180.0, (
			f'Expected fallback 180.0 for bad env {bad_value!r}, got {reloaded._DEFAULT_ACTION_TIMEOUT_S}'
		)

	# Numeric values still work.
	monkeypatch.setenv('BROWSER_USE_ACTION_TIMEOUT_S', '45')
	reloaded = importlib.reload(svc_module)
	assert reloaded._DEFAULT_ACTION_TIMEOUT_S == 45.0
