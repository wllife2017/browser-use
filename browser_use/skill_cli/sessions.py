"""Session data — SessionInfo dataclass and browser session factory."""

import logging
from dataclasses import dataclass, field

from browser_use.browser.session import BrowserSession
from browser_use.skill_cli.python_session import PythonSession

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
	"""Information about a browser session."""

	name: str
	browser_mode: str
	headed: bool
	profile: str | None
	browser_session: BrowserSession
	python_session: PythonSession = field(default_factory=PythonSession)


async def create_browser_session(
	mode: str,
	headed: bool,
	profile: str | None,
) -> BrowserSession:
	"""Create BrowserSession based on mode.

	Modes:
	- chromium: Playwright-managed Chromium (default)
	- real: User's Chrome with profile

	Raises:
		RuntimeError: If the requested mode is not available based on installation config
	"""
	from browser_use.skill_cli.install_config import get_mode_unavailable_error, is_mode_available

	# Validate mode is available based on installation config
	if not is_mode_available(mode):
		raise RuntimeError(get_mode_unavailable_error(mode))

	if mode == 'chromium':
		return BrowserSession(
			headless=not headed,
		)

	elif mode == 'real':
		from browser_use.skill_cli.utils import find_chrome_executable, get_chrome_profile_path

		chrome_path = find_chrome_executable()
		if not chrome_path:
			raise RuntimeError('Could not find Chrome executable. Please install Chrome or specify --browser chromium')

		# Always get the Chrome user data directory (not the profile subdirectory)
		user_data_dir = get_chrome_profile_path(None)
		# Profile directory defaults to 'Default', or use the specified profile name
		profile_directory = profile if profile else 'Default'

		return BrowserSession(
			executable_path=chrome_path,
			user_data_dir=user_data_dir,
			profile_directory=profile_directory,
			headless=not headed,  # Headless by default, --headed for visible
		)

	else:
		raise ValueError(f'Unknown browser mode: {mode}')
