"""Platform utilities for CLI and daemon."""

import os
import platform
import re
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path


def validate_session_name(session: str) -> None:
	"""Validate session name — reject path traversal and special characters.

	Raises ValueError on invalid name.
	"""
	if not re.match(r'^[a-zA-Z0-9_-]+$', session):
		raise ValueError(f'Invalid session name {session!r}: only letters, digits, hyphens, and underscores allowed')


def get_runtime_dir() -> Path:
	"""Get runtime directory for daemon socket/PID files.

	Priority: BROWSER_USE_RUNTIME_DIR > XDG_RUNTIME_DIR/browser-use > ~/.browser-use/run > tempdir/browser-use
	"""
	env_dir = os.environ.get('BROWSER_USE_RUNTIME_DIR')
	if env_dir:
		d = Path(env_dir)
		d.mkdir(parents=True, exist_ok=True)
		return d

	xdg = os.environ.get('XDG_RUNTIME_DIR')
	if xdg:
		d = Path(xdg) / 'browser-use'
		d.mkdir(parents=True, exist_ok=True)
		return d

	home_dir = Path.home() / '.browser-use' / 'run'
	try:
		home_dir.mkdir(parents=True, exist_ok=True)
		return home_dir
	except OSError:
		pass

	d = Path(tempfile.gettempdir()) / 'browser-use'
	d.mkdir(parents=True, exist_ok=True)
	return d


def get_socket_path(session: str = 'default') -> str:
	"""Get daemon socket path for a session.

	On Windows, returns a TCP address (tcp://127.0.0.1:PORT).
	On Unix, returns a Unix socket path.
	"""
	if sys.platform == 'win32':
		port = 49152 + zlib.adler32(session.encode()) % 16383
		return f'tcp://127.0.0.1:{port}'
	return str(get_runtime_dir() / f'browser-use-{session}.sock')


def get_pid_path(session: str = 'default') -> Path:
	"""Get PID file path for a session."""
	return get_runtime_dir() / f'browser-use-{session}.pid'


def is_daemon_alive(session: str = 'default') -> bool:
	"""Check daemon liveness by attempting socket connect.

	If socket file exists but nobody is listening, removes the stale file.
	"""
	import socket

	sock_path = get_socket_path(session)

	if sock_path.startswith('tcp://'):
		_, hostport = sock_path.split('://', 1)
		host, port_str = hostport.split(':')
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.settimeout(0.5)
			s.connect((host, int(port_str)))
			s.close()
			return True
		except OSError:
			return False
	else:
		sock_file = Path(sock_path)
		if not sock_file.exists():
			return False
		try:
			s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
			s.settimeout(0.5)
			s.connect(sock_path)
			s.close()
			return True
		except OSError:
			# Stale socket file — remove it
			sock_file.unlink(missing_ok=True)
			return False


def list_sessions() -> list[dict]:
	"""List active daemon sessions by scanning PID files.

	Returns list of {'name': str, 'pid': int, 'socket': str} for alive sessions.
	Cleans up stale PID/socket files for dead sessions.
	"""
	runtime_dir = get_runtime_dir()
	sessions: list[dict] = []

	for pid_file in sorted(runtime_dir.glob('browser-use-*.pid')):
		# Extract session name from filename: browser-use-<session>.pid
		stem = pid_file.stem  # browser-use-<session>
		session_name = stem[len('browser-use-') :]
		if not session_name:
			continue

		try:
			pid = int(pid_file.read_text().strip())
		except (OSError, ValueError):
			# Corrupt PID file — clean up
			pid_file.unlink(missing_ok=True)
			continue

		# Check if process is alive
		try:
			os.kill(pid, 0)
		except (OSError, ProcessLookupError):
			# Dead process — clean up stale files
			pid_file.unlink(missing_ok=True)
			sock_path = get_socket_path(session_name)
			if not sock_path.startswith('tcp://'):
				Path(sock_path).unlink(missing_ok=True)
			continue

		sessions.append(
			{
				'name': session_name,
				'pid': pid,
				'socket': get_socket_path(session_name),
			}
		)

	return sessions


def get_log_path() -> Path:
	"""Get log file path for the daemon."""
	return Path(tempfile.gettempdir()) / 'browser-use-cli.log'


def find_chrome_executable() -> str | None:
	"""Find Chrome/Chromium executable on the system."""
	system = platform.system()

	if system == 'Darwin':
		# macOS
		paths = [
			'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
			'/Applications/Chromium.app/Contents/MacOS/Chromium',
			'/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
		]
		for path in paths:
			if os.path.exists(path):
				return path

	elif system == 'Linux':
		# Linux: try common commands
		for cmd in ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']:
			try:
				result = subprocess.run(['which', cmd], capture_output=True, text=True)
				if result.returncode == 0:
					return result.stdout.strip()
			except Exception:
				pass

	elif system == 'Windows':
		# Windows: check common paths
		paths = [
			os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
			os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
			os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
		]
		for path in paths:
			if os.path.exists(path):
				return path

	return None


def get_chrome_profile_path(profile: str | None) -> str | None:
	"""Get Chrome user data directory for a profile.

	If profile is None, returns the default Chrome user data directory.
	"""
	if profile is None:
		# Use default Chrome profile location
		system = platform.system()
		if system == 'Darwin':
			return str(Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome')
		elif system == 'Linux':
			return str(Path.home() / '.config' / 'google-chrome')
		elif system == 'Windows':
			return os.path.expandvars(r'%LocalAppData%\Google\Chrome\User Data')
	else:
		# Return the profile name - Chrome will use it as a subdirectory
		# The actual path will be user_data_dir/profile
		return profile

	return None


def list_chrome_profiles() -> list[dict[str, str]]:
	"""List available Chrome profiles with their names.

	Returns:
		List of dicts with 'directory' and 'name' keys, ex:
		[{'directory': 'Default', 'name': 'Person 1'}, {'directory': 'Profile 1', 'name': 'Work'}]
	"""
	import json

	user_data_dir = get_chrome_profile_path(None)
	if user_data_dir is None:
		return []

	local_state_path = Path(user_data_dir) / 'Local State'
	if not local_state_path.exists():
		return []

	try:
		with open(local_state_path) as f:
			local_state = json.load(f)

		info_cache = local_state.get('profile', {}).get('info_cache', {})
		profiles = []
		for directory, info in info_cache.items():
			profiles.append(
				{
					'directory': directory,
					'name': info.get('name', directory),
				}
			)
		return sorted(profiles, key=lambda p: p['directory'])
	except (json.JSONDecodeError, KeyError, OSError):
		return []


def get_config_dir() -> Path:
	"""Get browser-use config directory."""
	if sys.platform == 'win32':
		base = Path(os.environ.get('APPDATA', Path.home()))
	else:
		base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
	return base / 'browser-use'


def get_config_path() -> Path:
	"""Get browser-use config file path."""
	return get_config_dir() / 'config.json'
