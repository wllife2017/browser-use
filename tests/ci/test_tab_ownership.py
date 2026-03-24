"""Tests for tab locking and agent registration (TabOwnershipManager).

Validates that multiple agents can see all tabs but cannot mutate
tabs that are locked by another agent. Agent identity comes from
'browser-use register' which assigns numeric indices.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock

from browser_use.skill_cli.tab_ownership import AGENT_EXPIRY_SECONDS, SHARED_CONTEXT, TabOwnershipManager


def _make_target(target_id: str) -> MagicMock:
	t = MagicMock()
	t.target_id = target_id
	t.target_type = 'page'
	return t


def _make_browser_session(targets: list[MagicMock] | None = None) -> MagicMock:
	bs = MagicMock()
	bs.agent_focus_target_id = None
	bs.session_manager = MagicMock()
	bs.session_manager.get_all_page_targets.return_value = targets or []
	bs._cdp_create_new_page = AsyncMock(return_value='new-target-001')
	return bs


# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------


def test_get_or_create_context():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	ctx = mgr.get_or_create_context('1')
	assert ctx.agent_id == '1'
	assert ctx.locked_target_ids == set()
	assert ctx.focused_target_id is None
	assert mgr.get_or_create_context('1') is ctx


def test_context_updates_last_active():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	ctx = mgr.get_or_create_context('1')
	first_active = ctx.last_active
	import time as _time

	_time.sleep(0.01)
	mgr.get_or_create_context('1')
	assert ctx.last_active > first_active


# ---------------------------------------------------------------------------
# Tab locking
# ---------------------------------------------------------------------------


def test_lock_tab():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'target-A')
	ctx = mgr.get_or_create_context('1')
	assert 'target-A' in ctx.locked_target_ids
	assert mgr._tab_locks['target-A'] == '1'


def test_unlock_tab():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'target-A')
	mgr.unlock_tab('target-A')
	ctx = mgr.get_or_create_context('1')
	assert 'target-A' not in ctx.locked_target_ids
	assert 'target-A' not in mgr._tab_locks


# ---------------------------------------------------------------------------
# Lock checking
# ---------------------------------------------------------------------------


def test_check_lock_unlocked():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	assert mgr.check_lock('1', 'target-A') is None


def test_check_lock_own_tab():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'target-A')
	assert mgr.check_lock('1', 'target-A') is None


def test_check_lock_other_agent():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'target-A')
	err = mgr.check_lock('2', 'target-A')
	assert err is not None
	assert 'in use by another agent' in err


def test_check_lock_none_target():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	assert mgr.check_lock('1', None) is None


# ---------------------------------------------------------------------------
# Tab index resolution — ALL tabs visible
# ---------------------------------------------------------------------------


def test_resolve_tab_index_sees_all_tabs():
	t1 = _make_target('target-A')
	t2 = _make_target('target-B')
	t3 = _make_target('target-C')
	bs = _make_browser_session(targets=[t1, t2, t3])
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'target-A')

	assert mgr.resolve_tab_index(0) == 'target-A'
	assert mgr.resolve_tab_index(1) == 'target-B'
	assert mgr.resolve_tab_index(2) == 'target-C'
	assert mgr.resolve_tab_index(3) is None
	assert mgr.resolve_tab_index(-1) is None


# ---------------------------------------------------------------------------
# ensure_caller_has_tab
# ---------------------------------------------------------------------------


async def test_ensure_adopts_unlocked_tab():
	t1 = _make_target('existing-tab')
	bs = _make_browser_session(targets=[t1])
	bs.agent_focus_target_id = 'existing-tab'
	mgr = TabOwnershipManager(bs)

	ctx = await mgr.ensure_caller_has_tab('1')
	bs._cdp_create_new_page.assert_not_awaited()
	assert ctx.focused_target_id == 'existing-tab'


async def test_ensure_skips_locked_tab():
	t1 = _make_target('locked-tab')
	t2 = _make_target('free-tab')
	bs = _make_browser_session(targets=[t1, t2])
	bs.agent_focus_target_id = 'locked-tab'
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'locked-tab')

	ctx = await mgr.ensure_caller_has_tab('2')
	bs._cdp_create_new_page.assert_not_awaited()
	assert ctx.focused_target_id == 'free-tab'


async def test_ensure_creates_tab_when_all_locked():
	t1 = _make_target('locked-tab')
	bs = _make_browser_session(targets=[t1])
	bs.agent_focus_target_id = 'locked-tab'
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'locked-tab')

	ctx = await mgr.ensure_caller_has_tab('2')
	bs._cdp_create_new_page.assert_awaited_once_with('about:blank')
	assert ctx.focused_target_id == 'new-target-001'


async def test_ensure_reuses_own_tab():
	t1 = _make_target('my-tab')
	bs = _make_browser_session(targets=[t1])
	mgr = TabOwnershipManager(bs)
	ctx = mgr.get_or_create_context('1')
	ctx.focused_target_id = 'my-tab'

	result = await mgr.ensure_caller_has_tab('1')
	bs._cdp_create_new_page.assert_not_awaited()
	assert result.focused_target_id == 'my-tab'


# ---------------------------------------------------------------------------
# Tab lifecycle
# ---------------------------------------------------------------------------


def test_on_tab_created_starts_unlocked():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.on_tab_created('new-tab')
	assert 'new-tab' not in mgr._tab_locks


def test_on_tab_closed_releases_lock():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab('1', 'target-A')
	ctx = mgr.get_or_create_context('1')
	ctx.focused_target_id = 'target-A'

	mgr.on_tab_closed('target-A')
	assert 'target-A' not in mgr._tab_locks
	assert ctx.focused_target_id is None


# ---------------------------------------------------------------------------
# Timestamp-based cleanup
# ---------------------------------------------------------------------------


async def test_cleanup_stale_agents(tmp_path):
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)

	# Active agent
	mgr.lock_tab('1', 'target-live')

	# Stale agent (expired)
	ctx2 = mgr.get_or_create_context('2')
	ctx2.last_active = time.time() - AGENT_EXPIRY_SECONDS - 1
	mgr.lock_tab('2', 'target-stale')
	ctx2.last_active = time.time() - AGENT_EXPIRY_SECONDS - 1  # re-set after lock_tab touches it

	# Set up agents file
	agents_file = tmp_path / 'agents.json'
	agents_file.write_text(json.dumps({
		'1': {'last_active': time.time()},
		'2': {'last_active': time.time() - AGENT_EXPIRY_SECONDS - 1},
	}))
	mgr.set_agents_file(agents_file)

	await mgr.cleanup_stale_agents()

	# Active agent still tracked
	assert '1' in mgr._contexts
	assert 'target-live' in mgr._tab_locks

	# Stale agent cleaned up
	assert '2' not in mgr._contexts
	assert 'target-stale' not in mgr._tab_locks

	# Agents file updated
	agents = json.loads(agents_file.read_text())
	assert '1' in agents
	assert '2' not in agents


async def test_cleanup_never_removes_shared():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)
	mgr.lock_tab(SHARED_CONTEXT, 'target-shared')

	await mgr.cleanup_stale_agents()
	assert SHARED_CONTEXT in mgr._contexts


# ---------------------------------------------------------------------------
# Two agents: isolation
# ---------------------------------------------------------------------------


def test_two_agents_lock_different_tabs():
	bs = _make_browser_session()
	mgr = TabOwnershipManager(bs)

	mgr.lock_tab('1', 'tab-A')
	mgr.lock_tab('2', 'tab-B')

	assert mgr.check_lock('1', 'tab-A') is None
	assert mgr.check_lock('2', 'tab-B') is None
	assert mgr.check_lock('1', 'tab-B') is not None
	assert mgr.check_lock('2', 'tab-A') is not None
	assert mgr.check_lock('1', 'tab-unlocked') is None
	assert mgr.check_lock('2', 'tab-unlocked') is None


# ---------------------------------------------------------------------------
# Register command
# ---------------------------------------------------------------------------


def test_register_assigns_sequential_indices(tmp_path):
	"""Test that register assigns 1, 2, 3 etc."""
	agents_file = tmp_path / 'agents.json'

	# First register
	agents = {}
	now = time.time()
	next_idx = 1
	while str(next_idx) in agents:
		next_idx += 1
	agents[str(next_idx)] = {'last_active': now}
	agents_file.write_text(json.dumps(agents))
	assert next_idx == 1

	# Second register
	agents = json.loads(agents_file.read_text())
	next_idx = 1
	while str(next_idx) in agents:
		next_idx += 1
	agents[str(next_idx)] = {'last_active': now}
	agents_file.write_text(json.dumps(agents))
	assert next_idx == 2


def test_register_reclaims_expired_indices(tmp_path):
	"""Test that expired indices get reclaimed."""
	agents_file = tmp_path / 'agents.json'
	now = time.time()
	agents = {
		'1': {'last_active': now - AGENT_EXPIRY_SECONDS - 1},  # expired
		'2': {'last_active': now},  # active
	}
	agents_file.write_text(json.dumps(agents))

	# Clean expired and find next
	agents = json.loads(agents_file.read_text())
	agents = {k: v for k, v in agents.items() if now - v.get('last_active', 0) < AGENT_EXPIRY_SECONDS}
	next_idx = 1
	while str(next_idx) in agents:
		next_idx += 1

	# Should reclaim index 1
	assert next_idx == 1
