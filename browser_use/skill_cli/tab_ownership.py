"""Tab locking for multi-agent browser sharing.

All agents can see all tabs. A tab becomes locked to an agent when the agent
mutates it (click, type, navigate, etc.). If another agent tries to mutate a
locked tab, it gets an error. Read-only commands (state, screenshot) work on
any tab regardless of locks.

Agent identity comes from --connect <index>, assigned by 'browser-use register'.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from browser_use.browser.session import BrowserSession

logger = logging.getLogger('browser_use.skill_cli.tab_ownership')

SHARED_CONTEXT = '__shared__'
AGENT_EXPIRY_SECONDS = 300  # 5 minutes


@dataclass
class CallerContext:
	"""Per-agent state."""

	agent_id: str
	locked_target_ids: set[str] = field(default_factory=set)
	focused_target_id: str | None = None
	cached_selector_map: dict[int, Any] = field(default_factory=dict)
	last_active: float = field(default_factory=time.time)


class TabOwnershipManager:
	"""Tab locking for multi-agent browser sharing.

	All agents see all tabs. Tabs become locked to an agent when the agent
	mutates them. Locks prevent other agents from mutating the same tab.
	Read-only commands bypass locks entirely.
	"""

	def __init__(self, browser_session: BrowserSession) -> None:
		self._browser_session = browser_session
		self._contexts: dict[str, CallerContext] = {}
		self._tab_locks: dict[str, str] = {}  # target_id → agent_id that holds the lock
		self._agents_file: Path | None = None

	def set_agents_file(self, path: Path) -> None:
		"""Set the path to the agents registry file."""
		self._agents_file = path

	def get_or_create_context(self, agent_id: str) -> CallerContext:
		"""Get or create a CallerContext for the given agent."""
		if agent_id not in self._contexts:
			self._contexts[agent_id] = CallerContext(agent_id=agent_id)
		ctx = self._contexts[agent_id]
		ctx.last_active = time.time()
		return ctx

	def lock_tab(self, agent_id: str, target_id: str) -> None:
		"""Lock a tab for an agent."""
		ctx = self.get_or_create_context(agent_id)
		ctx.locked_target_ids.add(target_id)
		self._tab_locks[target_id] = agent_id
		logger.debug(f'Locked tab {target_id[:8]}... for agent {agent_id}')

	def unlock_tab(self, target_id: str) -> None:
		"""Release a lock on a tab."""
		agent_id = self._tab_locks.pop(target_id, None)
		if agent_id is None:
			return
		ctx = self._contexts.get(agent_id)
		if ctx is None:
			return
		ctx.locked_target_ids.discard(target_id)

	def check_lock(self, agent_id: str, target_id: str | None) -> str | None:
		"""Check if a tab is locked by another agent.

		Returns an error message if locked by someone else, None if OK.
		"""
		if target_id is None:
			return None
		lock_holder = self._tab_locks.get(target_id)
		if lock_holder is not None and lock_holder != agent_id:
			return 'Tab is currently in use by another agent. Navigate your own tab with `open <url>`, or run `browser-use register` to get a new agent index.'
		return None

	def resolve_tab_index(self, index: int) -> str | None:
		"""Map a global tab index to a TargetID.

		All agents see all tabs — indices are global, not scoped per-agent.
		Returns None if the index is out of range.
		"""
		all_targets = self._browser_session.session_manager.get_all_page_targets() if self._browser_session.session_manager else []
		if index < 0 or index >= len(all_targets):
			return None
		return all_targets[index].target_id

	async def ensure_caller_has_tab(self, agent_id: str) -> CallerContext:
		"""Ensure an agent has a focused tab.

		On first connect, adopts the browser's current focused tab if it's
		unlocked. Only creates a new tab if nothing is available.
		"""
		ctx = self.get_or_create_context(agent_id)

		# If caller already has a valid focused tab, we're good
		if ctx.focused_target_id:
			all_target_ids = set()
			if self._browser_session.session_manager:
				all_target_ids = {t.target_id for t in self._browser_session.session_manager.get_all_page_targets()}
			if ctx.focused_target_id in all_target_ids:
				return ctx
			ctx.focused_target_id = None

		# Try to adopt the browser's current focused tab if it's unlocked
		existing_focus = self._browser_session.agent_focus_target_id
		if existing_focus and self.check_lock(agent_id, existing_focus) is None:
			ctx.focused_target_id = existing_focus
			self.lock_tab(agent_id, existing_focus)
			return ctx

		# Try to adopt any unlocked tab
		if self._browser_session.session_manager:
			for t in self._browser_session.session_manager.get_all_page_targets():
				if self.check_lock(agent_id, t.target_id) is None:
					ctx.focused_target_id = t.target_id
					self.lock_tab(agent_id, t.target_id)
					return ctx

		# No unlocked tabs available — create a new one
		target_id = await self._browser_session._cdp_create_new_page('about:blank')
		ctx.focused_target_id = target_id
		logger.info(f'Created new tab {target_id[:8]}... for agent {agent_id}')
		return ctx

	def on_tab_created(self, target_id: str) -> None:
		"""Handle a new tab being created. New tabs start unlocked."""
		if target_id in self._tab_locks:
			return
		logger.debug(f'New tab {target_id[:8]}... starts unlocked')

	def on_tab_closed(self, target_id: str) -> None:
		"""Handle a tab being closed. Release its lock and clear any agent's focus."""
		self.unlock_tab(target_id)
		for ctx in self._contexts.values():
			if ctx.focused_target_id == target_id:
				ctx.focused_target_id = None

	async def cleanup_stale_agents(self) -> None:
		"""Remove contexts for agents that haven't been active for 5+ minutes.

		Also updates the agents.json registry file to remove expired entries.
		"""
		now = time.time()
		stale_agents = []
		for agent_id, ctx in self._contexts.items():
			if agent_id == SHARED_CONTEXT:
				continue
			if now - ctx.last_active > AGENT_EXPIRY_SECONDS:
				stale_agents.append(agent_id)

		for agent_id in stale_agents:
			ctx = self._contexts.pop(agent_id, None)
			if ctx:
				for target_id in list(ctx.locked_target_ids):
					self._tab_locks.pop(target_id, None)
				logger.info(f'Cleaned up stale agent {agent_id} ({len(ctx.locked_target_ids)} locks released)')

		# Update agents.json to remove expired entries
		if self._agents_file and self._agents_file.exists():
			try:
				agents = json.loads(self._agents_file.read_text())
				agents = {k: v for k, v in agents.items() if now - v.get('last_active', 0) < AGENT_EXPIRY_SECONDS}
				self._agents_file.write_text(json.dumps(agents))
			except (json.JSONDecodeError, OSError):
				pass
