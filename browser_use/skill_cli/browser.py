"""Lightweight BrowserSession subclass for the CLI daemon.

Skips watchdogs, event bus handlers, and auto-reconnect.
Uses connect() directly for CDP setup. All inherited methods
(get_element_by_index, take_screenshot, cdp_client_for_node, etc.)
work because this IS a BrowserSession.
"""

from __future__ import annotations

import logging

from browser_use.browser.session import BrowserSession

logger = logging.getLogger('browser_use.skill_cli.browser')


class CLIBrowserSession(BrowserSession):
	"""BrowserSession that connects to CDP without loading watchdogs or event bus handlers.

	Overrides start/stop/kill to be lightweight:
	- start() calls connect() directly (no attach_all_watchdogs)
	- stop() closes the websocket directly (no BrowserStopEvent chain)
	- kill() sends Browser.close + closes websocket (no event bus)
	"""

	async def start(self) -> None:
		"""Connect CDP without watchdogs or event bus handlers."""
		await self.connect()
		# Prevent monitoring on future tabs (existing tabs already got it during connect)
		if self.session_manager:

			async def _noop(cdp_session: object) -> None:
				pass

			self.session_manager._enable_page_monitoring = _noop  # type: ignore[assignment]
		# Disable auto-reconnect — daemon should die when CDP drops
		self._intentional_stop = True

	async def stop(self) -> None:
		"""Close the websocket without the BrowserStopEvent chain.

		For --connect mode: Chrome stays alive, we just disconnect.
		"""
		self._intentional_stop = True
		if self._cdp_client_root:
			try:
				await self._cdp_client_root.stop()
			except Exception as e:
				logger.debug(f'Error closing CDP client: {e}')
			self._cdp_client_root = None  # type: ignore[assignment]
		if self.session_manager:
			try:
				await self.session_manager.clear()
			except Exception as e:
				logger.debug(f'Error clearing session manager: {e}')
			self.session_manager = None
		self.agent_focus_target_id = None
		self._cached_selector_map.clear()

	async def kill(self) -> None:
		"""Send Browser.close to kill the browser process, then disconnect.

		For managed Chromium: kills the browser and cleans up.
		"""
		if self._cdp_client_root:
			try:
				await self._cdp_client_root.send.Browser.close()
			except Exception:
				pass
		await self.stop()
