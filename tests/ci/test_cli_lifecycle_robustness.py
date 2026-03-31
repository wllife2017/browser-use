"""Additional robustness tests for CLI daemon lifecycle helpers.

These tests are derived from the implementation in:
- browser_use/skill_cli/daemon.py
- browser_use/skill_cli/main.py
- browser_use/skill_cli/browser.py

They focus on edge cases and failure modes in helper logic without relying on
the existing lifecycle test suite.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_request_shutdown_is_idempotent(monkeypatch):
	"""Daemon should create exactly one shutdown task even if requested twice."""
	from browser_use.skill_cli.daemon import Daemon

	daemon = Daemon(headed=False, profile=None, session='default')

	created: list[object] = []

	def fake_create_task(coro):
		created.append(coro)
		coro.close()
		return 'task-token'

	monkeypatch.setattr(asyncio, 'create_task', fake_create_task)

	daemon._request_shutdown()
	daemon._request_shutdown()

	assert daemon._is_shutting_down is True
	assert daemon._shutdown_task == 'task-token'
	assert len(created) == 1


def test_probe_session_records_socket_pid(monkeypatch, tmp_path):
	"""Probe should keep file-based PID but also capture daemon PID from ping."""
	from browser_use.skill_cli import main as cli_main

	class DummySock:
		def close(self):
			return None

	monkeypatch.setenv('BROWSER_USE_HOME', str(tmp_path))
	monkeypatch.setattr(
		cli_main,
		'_read_session_state',
		lambda session: {'phase': 'running', 'updated_at': 123.0, 'pid': 111},
	)
	monkeypatch.setattr(cli_main, '_is_pid_alive', lambda pid: pid == 111)
	monkeypatch.setattr(cli_main, '_connect_to_daemon', lambda **_: DummySock())
	monkeypatch.setattr(cli_main, 'send_command', lambda *args, **kwargs: {'success': True, 'data': {'pid': 222}})

	probe = cli_main._probe_session('default')

	assert probe.phase == 'running'
	assert probe.updated_at == 123.0
	assert probe.pid == 111
	assert probe.pid_alive is True
	assert probe.socket_reachable is True
	assert probe.socket_pid == 222


def test_probe_session_falls_back_to_pid_file_when_state_pid_is_dead(monkeypatch, tmp_path):
	"""Probe should prefer a live PID file when the state-file PID is stale."""
	from browser_use.skill_cli import main as cli_main

	(tmp_path / 'default.state.json').write_text(json.dumps({'phase': 'running', 'updated_at': 123.0, 'pid': 111}))
	(tmp_path / 'default.pid').write_text('222')

	class DummySock:
		def close(self):
			return None

	monkeypatch.setenv('BROWSER_USE_HOME', str(tmp_path))
	monkeypatch.setattr(cli_main, '_is_pid_alive', lambda pid: pid == 222)
	monkeypatch.setattr(cli_main, '_connect_to_daemon', lambda **_: DummySock())
	monkeypatch.setattr(cli_main, 'send_command', lambda *args, **kwargs: {'success': True, 'data': {'pid': 222}})

	probe = cli_main._probe_session('default')

	assert probe.phase == 'running'
	assert probe.pid == 222
	assert probe.pid_alive is True
	assert probe.socket_pid == 222


def test_close_session_does_not_kill_non_daemon_process(monkeypatch):
	"""Direct PID fallback should not kill unrelated live processes."""
	from browser_use.skill_cli import main as cli_main

	probe = SimpleNamespace(
		name='default',
		phase='running',
		updated_at=1.0,
		pid=4321,
		pid_alive=True,
		socket_reachable=False,
		socket_pid=None,
	)

	cleaned: list[str] = []
	terminated: list[int] = []

	monkeypatch.setattr(cli_main, '_probe_session', lambda session: probe)
	monkeypatch.setattr(cli_main, '_is_daemon_process', lambda pid: False)
	monkeypatch.setattr(cli_main, '_terminate_pid', lambda pid: terminated.append(pid))
	monkeypatch.setattr(cli_main, '_clean_session_files', lambda session: cleaned.append(session))

	closed = cli_main._close_session('default')

	assert closed is False
	assert terminated == []
	assert cleaned == ['default']


def test_close_session_cleans_stale_files_when_only_artifacts_exist(monkeypatch):
	"""Stale files with no live process should be removed and reported as not closed."""
	from browser_use.skill_cli import main as cli_main

	probe = SimpleNamespace(
		name='default',
		phase='failed',
		updated_at=1.0,
		pid=4321,
		pid_alive=False,
		socket_reachable=False,
		socket_pid=None,
	)

	cleaned: list[str] = []

	monkeypatch.setattr(cli_main, '_probe_session', lambda session: probe)
	monkeypatch.setattr(cli_main, '_clean_session_files', lambda session: cleaned.append(session))

	closed = cli_main._close_session('default')

	assert closed is False
	assert cleaned == ['default']


def test_close_session_does_not_clean_files_when_pid_survives_shutdown(monkeypatch):
	"""Socket-path close must NOT clean files if PID is still alive after polling.

	Cleaning files for a still-running daemon would orphan it (no PID/socket to discover).
	"""
	from browser_use.skill_cli import main as cli_main

	probe = SimpleNamespace(
		name='default',
		phase='running',
		updated_at=1.0,
		pid=1234,
		pid_alive=True,
		socket_reachable=True,
		socket_pid=1234,
	)

	cleaned: list[str] = []
	sleep_calls: list[float] = []

	monkeypatch.setattr(cli_main, '_probe_session', lambda session: probe)
	monkeypatch.setattr(cli_main, 'send_command', lambda *args, **kwargs: {'success': True})
	monkeypatch.setattr(cli_main, '_is_pid_alive', lambda pid: True)
	monkeypatch.setattr(cli_main, '_clean_session_files', lambda session: cleaned.append(session))
	monkeypatch.setattr(cli_main.time, 'sleep', lambda interval: sleep_calls.append(interval))

	closed = cli_main._close_session('default')

	assert closed is True
	assert cleaned == []  # Files NOT cleaned — daemon still alive
	assert len(sleep_calls) == 150


def test_close_session_cleans_up_when_shutdown_command_raises(monkeypatch):
	"""Socket-path close should still clean files if daemon disconnects mid-shutdown."""
	from browser_use.skill_cli import main as cli_main

	probe = SimpleNamespace(
		name='default',
		phase='running',
		updated_at=1.0,
		pid=5678,
		pid_alive=True,
		socket_reachable=True,
		socket_pid=5678,
	)

	cleaned: list[str] = []

	monkeypatch.setattr(cli_main, '_probe_session', lambda session: probe)
	monkeypatch.setattr(cli_main, 'send_command', Mock(side_effect=RuntimeError('socket dropped')))
	monkeypatch.setattr(cli_main, '_clean_session_files', lambda session: cleaned.append(session))

	closed = cli_main._close_session('default')

	assert closed is True
	assert cleaned == ['default']


@pytest.mark.skipif('win32' in __import__('sys').platform, reason='POSIX-only signal escalation path')
def test_terminate_pid_escalates_to_sigkill_after_sigterm_timeout(monkeypatch):
	"""POSIX termination should escalate to SIGKILL after the SIGTERM grace window."""
	from browser_use.skill_cli import main as cli_main

	kill_calls: list[int] = []
	sleep_calls: list[float] = []
	alive_checks = {'count': 0}

	def fake_kill(pid: int, sig: int):
		kill_calls.append(sig)

	def fake_is_alive(pid: int) -> bool:
		alive_checks['count'] += 1
		# Stay alive through the SIGTERM polling loop, then die after SIGKILL.
		return alive_checks['count'] <= 50

	monkeypatch.setattr(cli_main.os, 'kill', fake_kill)
	monkeypatch.setattr(cli_main, '_is_pid_alive', fake_is_alive)
	monkeypatch.setattr(cli_main.time, 'sleep', lambda interval: sleep_calls.append(interval))

	assert cli_main._terminate_pid(9999) is True
	assert kill_calls[0] == signal.SIGTERM
	assert kill_calls[-1] == signal.SIGKILL
	assert len(sleep_calls) >= 50


def test_ensure_daemon_exits_on_config_mismatch_when_alive(monkeypatch, capsys):
	"""Explicit config should still fail fast when the live daemon config differs."""
	from browser_use.skill_cli import main as cli_main

	# ensure_daemon now uses _probe_session, not _is_daemon_alive
	probe = SimpleNamespace(
		name='default', phase='running', updated_at=1.0,
		pid=1234, pid_alive=True, socket_reachable=True, socket_pid=1234,
	)
	monkeypatch.setattr(cli_main, '_probe_session', lambda session: probe)
	monkeypatch.setattr(
		cli_main,
		'send_command',
		lambda *args, **kwargs: {
			'success': True,
			'data': {'headed': True, 'profile': 'Other', 'cdp_url': None, 'use_cloud': False},
		},
	)

	with pytest.raises(SystemExit) as excinfo:
		cli_main.ensure_daemon(False, None, session='default', explicit_config=True)

	assert excinfo.value.code == 1
	assert "already running with different config" in capsys.readouterr().err


def test_ensure_daemon_reuses_alive_daemon_when_ping_fails(monkeypatch):
	"""Alive daemon should be reused if config cannot be verified safely."""
	from browser_use.skill_cli import main as cli_main

	probe = SimpleNamespace(
		name='default', phase='running', updated_at=1.0,
		pid=1234, pid_alive=True, socket_reachable=True, socket_pid=1234,
	)
	monkeypatch.setattr(cli_main, '_probe_session', lambda session: probe)
	monkeypatch.setattr(cli_main, 'send_command', Mock(side_effect=RuntimeError('ping failed')))
	monkeypatch.setattr(cli_main.subprocess, 'Popen', Mock(side_effect=AssertionError('should not spawn')))

	cli_main.ensure_daemon(False, None, session='default', explicit_config=True)


def test_handle_close_all_deduplicates_state_and_pid_discovery(monkeypatch, tmp_path, capsys):
	"""close --all should process each discovered session name once."""
	from browser_use.skill_cli import main as cli_main

	(tmp_path / 'dup.pid').write_text('123')
	(tmp_path / 'dup.state.json').write_text('{}')
	(tmp_path / 'other.state.json').write_text('{}')

	calls: list[str] = []

	monkeypatch.setenv('BROWSER_USE_HOME', str(tmp_path))
	monkeypatch.setattr(cli_main, '_close_session', lambda session: calls.append(session) or True)

	rc = cli_main._handle_close_all(SimpleNamespace(json=False))

	assert rc == 0
	assert calls == ['dup', 'other']
	assert 'Closed 2 session(s)' in capsys.readouterr().out


def test_cli_browser_stop_cloud_cleans_remote_before_disconnect(monkeypatch):
	"""Cloud stop should stop the remote browser and still clear local state."""
	from browser_use.skill_cli.browser import CLIBrowserSession

	order: list[str] = []

	async def stop_browser():
		order.append('cloud-stop')

	async def cdp_stop():
		order.append('cdp-stop')

	async def clear_session_manager():
		order.append('session-clear')

	bs = CLIBrowserSession.model_construct()
	object.__setattr__(bs, 'browser_profile', SimpleNamespace(use_cloud=True))
	object.__setattr__(bs, '_cloud_browser_client', SimpleNamespace(current_session_id='session-1', stop_browser=stop_browser))
	object.__setattr__(bs, '_cdp_client_root', SimpleNamespace(stop=cdp_stop))
	object.__setattr__(bs, 'session_manager', SimpleNamespace(clear=clear_session_manager))
	object.__setattr__(bs, 'agent_focus_target_id', 'tab-1')
	object.__setattr__(bs, '_cached_selector_map', {1: 'x'})
	object.__setattr__(bs, '_intentional_stop', False)

	asyncio.run(bs.stop())

	assert order == ['cloud-stop', 'cdp-stop', 'session-clear']


def test_cli_browser_stop_cloud_cleanup_error_does_not_block_disconnect(monkeypatch):
	"""Cloud cleanup failures should not prevent websocket/session-manager teardown."""
	from browser_use.skill_cli.browser import CLIBrowserSession

	order: list[str] = []

	async def stop_browser():
		order.append('cloud-stop')
		raise RuntimeError('cloud cleanup failed')

	async def cdp_stop():
		order.append('cdp-stop')

	async def clear_session_manager():
		order.append('session-clear')

	bs = CLIBrowserSession.model_construct()
	object.__setattr__(bs, 'browser_profile', SimpleNamespace(use_cloud=True))
	object.__setattr__(bs, '_cloud_browser_client', SimpleNamespace(current_session_id='session-1', stop_browser=stop_browser))
	object.__setattr__(bs, '_cdp_client_root', SimpleNamespace(stop=cdp_stop))
	object.__setattr__(bs, 'session_manager', SimpleNamespace(clear=clear_session_manager))
	object.__setattr__(bs, 'agent_focus_target_id', 'tab-1')
	object.__setattr__(bs, '_cached_selector_map', {1: 'x'})
	object.__setattr__(bs, '_intentional_stop', False)

	asyncio.run(bs.stop())

	assert order == ['cloud-stop', 'cdp-stop', 'session-clear']


@pytest.mark.asyncio
async def test_daemon_shutdown_uses_stop_for_external_connection(monkeypatch, tmp_path):
	"""Daemon shutdown should disconnect, not kill, for external CDP/browser ownership."""
	from browser_use.skill_cli.daemon import Daemon

	monkeypatch.setenv('BROWSER_USE_HOME', str(tmp_path))

	daemon = Daemon(headed=False, profile=None, cdp_url='ws://example', session='default')
	calls: list[str] = []

	async def stop():
		calls.append('stop')

	async def kill():
		calls.append('kill')

	session = SimpleNamespace(browser_session=SimpleNamespace(stop=stop, kill=kill))
	daemon._session = session

	pid_path = tmp_path / 'default.pid'
	pid_path.write_text(str(os.getpid()))

	def fake_exit(code: int):
		raise SystemExit(code)

	monkeypatch.setattr(os, '_exit', fake_exit)

	with pytest.raises(SystemExit):
		await daemon._shutdown()

	assert calls == ['stop']
	state = json.loads((tmp_path / 'default.state.json').read_text())
	assert state['phase'] == 'stopped'


@pytest.mark.asyncio
async def test_daemon_shutdown_uses_kill_for_locally_owned_browser(monkeypatch, tmp_path):
	"""Daemon shutdown should kill a locally launched browser."""
	from browser_use.skill_cli.daemon import Daemon

	monkeypatch.setenv('BROWSER_USE_HOME', str(tmp_path))

	daemon = Daemon(headed=False, profile=None, session='default')
	calls: list[str] = []

	async def stop():
		calls.append('stop')

	async def kill():
		calls.append('kill')

	session = SimpleNamespace(browser_session=SimpleNamespace(stop=stop, kill=kill))
	daemon._session = session

	pid_path = tmp_path / 'default.pid'
	pid_path.write_text(str(os.getpid()))

	def fake_exit(code: int):
		raise SystemExit(code)

	monkeypatch.setattr(os, '_exit', fake_exit)

	with pytest.raises(SystemExit):
		await daemon._shutdown()

	assert calls == ['kill']
	state = json.loads((tmp_path / 'default.state.json').read_text())
	assert state['phase'] == 'stopped'


def test_daemon_main_writes_failed_state_on_crash(monkeypatch, tmp_path):
	"""Daemon main should write failed state if it crashes before shutdown starts."""
	from browser_use.skill_cli import daemon as daemon_mod

	monkeypatch.setenv('BROWSER_USE_HOME', str(tmp_path))

	async def boom(self):
		raise RuntimeError('boom')

	def fake_exit(code: int):
		raise SystemExit(code)

	monkeypatch.setattr(daemon_mod.Daemon, 'run', boom)
	monkeypatch.setattr(daemon_mod.os, '_exit', fake_exit)
	monkeypatch.setattr(sys, 'argv', ['daemon.py', '--session', 'default'])

	with pytest.raises(SystemExit):
		daemon_mod.main()

	state = json.loads((tmp_path / 'default.state.json').read_text())
	assert state['phase'] == 'failed'
