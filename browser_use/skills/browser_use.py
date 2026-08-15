"""Browser Use skill alias for Browser Harness"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path


def _canonical_skill_path() -> Path:
	return Path(__file__).resolve().parent / 'browser-use' / 'SKILL.md'


def _canonical_metadata_lines() -> list[str]:
	"""Read the metadata block from the canonical Browser Use skill."""
	skill_path = _canonical_skill_path()
	if not skill_path.exists():
		return []

	try:
		_, frontmatter, _ = skill_path.read_text(encoding='utf-8').split('---\n', 2)
	except ValueError:
		return []

	lines = frontmatter.splitlines()
	try:
		start = lines.index('metadata:')
	except ValueError:
		return []

	end = len(lines)
	for index in range(start + 1, len(lines)):
		if lines[index] and not lines[index][0].isspace():
			end = index
			break
	return lines[start:end]


def as_browser_use_skill(text: str) -> str:
	"""Expose the Browser Harness skill under the Browser Use skill identity."""
	if not text.startswith('---\n'):
		return text

	try:
		_, frontmatter, body = text.split('---\n', 2)
	except ValueError:
		return text

	lines = []
	saw_name = False
	saw_description = False
	for line in frontmatter.splitlines():
		if line.startswith('name:'):
			lines.append('name: browser-use')
			saw_name = True
		elif line.startswith('description:'):
			lines.append(
				'description: "Direct browser control via CDP for web interaction: automation, scraping, testing, screenshots, and site/app work."'
			)
			saw_description = True
		else:
			lines.append(line)

	if not saw_name:
		lines.insert(0, 'name: browser-use')
	if not saw_description:
		lines.insert(
			1,
			'description: "Direct browser control via CDP for web interaction: automation, scraping, testing, screenshots, and site/app work."',
		)
	if not any(line.startswith('homepage:') for line in lines):
		lines.append('homepage: https://browser-use.com')
	if not any(line.startswith('metadata:') for line in lines):
		lines.extend(_canonical_metadata_lines())

	body = body.replace('# browser-harness', '# Browser Use', 1).replace('# Browser Harness', '# Browser Use', 1)
	# Rebrand every mention except repo URLs (github.com/browser-use/browser-harness/...)
	body = re.sub(r'(?<!/)browser-harness', 'browser-use', body)
	body = body.replace('Browser Harness', 'Browser Use')
	frontmatter_text = '\n'.join(lines)
	return f'---\n{frontmatter_text}\n---\n{body}'


def skill_text() -> str:
	"""Return the canonical Browser Use skill."""
	skill_path = _canonical_skill_path()
	if skill_path.exists():
		return skill_path.read_text(encoding='utf-8')

	try:
		text = resources.files('browser_harness').joinpath('SKILL.md').read_text(encoding='utf-8')
	except ModuleNotFoundError as exc:
		raise RuntimeError(
			'The Browser Use skill relies on the browser-harness package. Install browser-use again or install `browser-harness`.'
		) from exc
	return as_browser_use_skill(text)
