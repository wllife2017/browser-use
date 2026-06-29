from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path


def find_chrome_executable() -> str | None:
	"""Find Chrome/Chromium executable on the system."""
	system = platform.system()

	if system == 'Darwin':
		for path in (
			'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
			'/Applications/Chromium.app/Contents/MacOS/Chromium',
			'/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
		):
			if os.path.exists(path):
				return path

	elif system == 'Linux':
		for cmd in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
			try:
				result = subprocess.run(['which', cmd], capture_output=True, text=True)
				if result.returncode == 0:
					return result.stdout.strip()
			except Exception:
				pass

	elif system == 'Windows':
		for path in (
			os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
			os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
			os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
		):
			if os.path.exists(path):
				return path

	return None


def get_chrome_profile_path(profile: str | None) -> str | None:
	"""Get Chrome user data directory, or return a specific profile directory name."""
	if profile is not None:
		return profile

	system = platform.system()
	if system == 'Darwin':
		return str(Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome')
	if system == 'Linux':
		base = Path.home() / '.config'
		for name in ('google-chrome', 'chromium'):
			if (base / name).is_dir():
				return str(base / name)
		return str(base / 'google-chrome')
	if system == 'Windows':
		return os.path.expandvars(r'%LocalAppData%\Google\Chrome\User Data')

	return None


def list_chrome_profiles() -> list[dict[str, str]]:
	"""List available Chrome profiles with their display names."""
	user_data_dir = get_chrome_profile_path(None)
	if user_data_dir is None:
		return []

	local_state_path = Path(user_data_dir) / 'Local State'
	if not local_state_path.exists():
		return []

	try:
		with open(local_state_path, encoding='utf-8') as f:
			local_state = json.load(f)

		info_cache = local_state.get('profile', {}).get('info_cache', {})
		return sorted(
			[
				{
					'directory': directory,
					'name': info.get('name', directory),
				}
				for directory, info in info_cache.items()
			],
			key=lambda profile: profile['directory'],
		)
	except (json.JSONDecodeError, KeyError, OSError):
		return []
