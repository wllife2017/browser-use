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
	headed: bool
	profile: str | None
	browser_session: BrowserSession
	python_session: PythonSession = field(default_factory=PythonSession)


async def create_browser_session(
	headed: bool,
	profile: str | None,
) -> BrowserSession:
	"""Create BrowserSession based on whether a profile is specified.

	- No profile: Playwright-managed Chromium (default)
	- With profile: User's real Chrome with the specified profile
	"""
	if profile is None:
		return BrowserSession(
			headless=not headed,
		)

	from browser_use.skill_cli.utils import find_chrome_executable, get_chrome_profile_path

	chrome_path = find_chrome_executable()
	if not chrome_path:
		raise RuntimeError('Could not find Chrome executable. Please install Chrome or omit --profile to use Chromium.')

	# Always get the Chrome user data directory (not the profile subdirectory)
	user_data_dir = get_chrome_profile_path(None)
	# Profile directory defaults to 'Default', or use the specified profile name
	profile_directory = profile

	return BrowserSession(
		executable_path=chrome_path,
		user_data_dir=user_data_dir,
		profile_directory=profile_directory,
		headless=not headed,
	)
