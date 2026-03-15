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
	cdp_url: str | None
	browser_session: BrowserSession
	python_session: PythonSession = field(default_factory=PythonSession)
	use_cloud: bool = False


async def create_browser_session(
	headed: bool,
	profile: str | None,
	cdp_url: str | None = None,
	use_cloud: bool = False,
	cloud_timeout: int | None = None,
	cloud_proxy_country_code: str | None = None,
	cloud_profile_id: str | None = None,
) -> BrowserSession:
	"""Create BrowserSession based on connection mode.

	- CDP URL: Connect to existing browser (cdp_url takes precedence)
	- Cloud: Provision a cloud browser via BrowserSession(use_cloud=True)
	- With profile: User's real Chrome with the specified profile
	- No profile: Playwright-managed Chromium (default)
	"""
	if cdp_url is not None:
		return BrowserSession(cdp_url=cdp_url)

	if use_cloud:
		kwargs: dict = {'use_cloud': True}
		if cloud_timeout is not None:
			kwargs['cloud_timeout'] = cloud_timeout
		if cloud_proxy_country_code is not None:
			kwargs['cloud_proxy_country_code'] = cloud_proxy_country_code
		if cloud_profile_id is not None:
			kwargs['cloud_profile_id'] = cloud_profile_id
		return BrowserSession(**kwargs)

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
