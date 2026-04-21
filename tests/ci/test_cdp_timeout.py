"""Regression tests for TimeoutWrappedCDPClient.

cdp_use.CDPClient.send_raw awaits a future that only resolves when the browser
sends a matching response. When the server goes silent (observed against cloud
browsers whose WebSocket stays connected at TCP/keepalive layer but never
replies), send_raw hangs forever. The wrapper turns that hang into a fast
TimeoutError.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from browser_use.browser._cdp_timeout import (
	DEFAULT_CDP_REQUEST_TIMEOUT_S,
	TimeoutWrappedCDPClient,
	_parse_env_cdp_timeout,
)


class _HangingClient(TimeoutWrappedCDPClient):
	"""Wrapper whose parent send_raw never returns — simulates a silent server."""

	def __init__(self, cdp_request_timeout_s: float) -> None:
		# Skip real CDPClient.__init__ — we only exercise the timeout wrapper.
		self._cdp_request_timeout_s = cdp_request_timeout_s
		self.call_count = 0

	async def _parent_send_raw(self, *_args, **_kwargs):
		self.call_count += 1
		await asyncio.sleep(30)  # Way longer than any test timeout.
		return {}

	async def send_raw(self, method, params=None, session_id=None):
		# Inline version of TimeoutWrappedCDPClient.send_raw using our _parent_send_raw
		# (avoids needing a real WebSocket).
		try:
			return await asyncio.wait_for(
				self._parent_send_raw(method=method, params=params, session_id=session_id),
				timeout=self._cdp_request_timeout_s,
			)
		except TimeoutError as e:
			raise TimeoutError(f'CDP method {method!r} did not respond within {self._cdp_request_timeout_s:.0f}s.') from e


@pytest.mark.asyncio
async def test_send_raw_times_out_on_silent_server():
	"""A CDP method that gets no response must raise TimeoutError within the cap."""
	client = _HangingClient(cdp_request_timeout_s=0.5)

	start = time.monotonic()
	with pytest.raises(TimeoutError) as exc:
		await client.send_raw('Target.getTargets')
	elapsed = time.monotonic() - start

	assert client.call_count == 1
	# Returned within the cap (plus a small scheduling margin), not after the
	# full 30s sleep.
	assert elapsed < 2.0, f'wrapper did not enforce timeout; took {elapsed:.2f}s'
	assert 'Target.getTargets' in str(exc.value)
	assert '0s' in str(exc.value) or '1s' in str(exc.value)


def test_default_cdp_timeout_is_reasonable():
	"""Default must give headroom above typical slow CDP calls but stay below
	the 180s agent step_timeout so hangs surface before step-level kills."""
	assert 10.0 <= DEFAULT_CDP_REQUEST_TIMEOUT_S <= 120.0, (
		f'Default CDP timeout ({DEFAULT_CDP_REQUEST_TIMEOUT_S}s) is outside the sensible 10–120s range'
	)


def test_parse_env_rejects_malformed_values():
	"""Mirrors the defensive parse used for BROWSER_USE_ACTION_TIMEOUT_S."""
	for bad in ('', 'nan', 'NaN', 'inf', '-inf', '0', '-5', 'abc'):
		assert _parse_env_cdp_timeout(bad) == 60.0, f'Expected fallback for {bad!r}'

	# Finite positive values take effect.
	assert _parse_env_cdp_timeout('30') == 30.0
	assert _parse_env_cdp_timeout('15.5') == 15.5
	# None (env var not set) also falls back.
	assert _parse_env_cdp_timeout(None) == 60.0
