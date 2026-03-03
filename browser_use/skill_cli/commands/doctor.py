"""Doctor command - check installation and dependencies.

Validates that browser-use is properly installed and all dependencies
are available. Provides helpful diagnostic information and fixes.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

COMMANDS = {'doctor'}


async def handle() -> dict[str, Any]:
	"""Run health checks and return results."""
	checks: dict[str, dict[str, Any]] = {}

	# 1. Package installation
	checks['package'] = _check_package()

	# 2. Browser availability
	checks['browser'] = _check_browser()

	# 3. Network connectivity (basic check)
	checks['network'] = await _check_network()

	# Determine overall status
	all_ok = all(check.get('status') == 'ok' for check in checks.values())

	return {
		'status': 'healthy' if all_ok else 'issues_found',
		'checks': checks,
		'summary': _summarize_checks(checks),
	}


def _check_package() -> dict[str, Any]:
	"""Check if browser-use is installed."""
	try:
		import browser_use

		version = getattr(browser_use, '__version__', 'unknown')
		return {
			'status': 'ok',
			'message': f'browser-use {version}',
		}
	except ImportError:
		return {
			'status': 'error',
			'message': 'browser-use not installed',
			'fix': 'pip install browser-use',
		}


def _check_browser() -> dict[str, Any]:
	"""Check if browser is available."""
	try:
		from browser_use.browser.profile import BrowserProfile

		# Just check if we can import and create a profile
		profile = BrowserProfile(headless=True)
		return {
			'status': 'ok',
			'message': 'Browser profile available',
		}
	except Exception as e:
		return {
			'status': 'warning',
			'message': f'Browser may not be available: {e}',
			'note': 'Will be installed on first use',
		}


async def _check_network() -> dict[str, Any]:
	"""Check basic network connectivity."""
	try:
		import httpx

		async with httpx.AsyncClient(timeout=5.0) as client:
			# Just ping a reliable endpoint
			response = await client.head('https://api.github.com', follow_redirects=True)
			if response.status_code < 500:
				return {
					'status': 'ok',
					'message': 'Network connectivity OK',
				}
	except Exception as e:
		logger.debug(f'Network check failed: {e}')

	return {
		'status': 'warning',
		'message': 'Network connectivity check inconclusive',
		'note': 'Some features may not work offline',
	}


def _summarize_checks(checks: dict[str, dict[str, Any]]) -> str:
	"""Generate a summary of check results."""
	ok = sum(1 for c in checks.values() if c.get('status') == 'ok')
	warning = sum(1 for c in checks.values() if c.get('status') == 'warning')
	error = sum(1 for c in checks.values() if c.get('status') == 'error')
	missing = sum(1 for c in checks.values() if c.get('status') == 'missing')

	total = len(checks)

	parts = [f'{ok}/{total} checks passed']
	if warning > 0:
		parts.append(f'{warning} warnings')
	if error > 0:
		parts.append(f'{error} errors')
	if missing > 0:
		parts.append(f'{missing} missing')

	return ', '.join(parts)
