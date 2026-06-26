from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_NAME = 'browser-use'
DEFAULT_TARGET = 'claude'
TARGET_DIRS = {
	'claude': Path.home() / '.claude' / 'skills' / SKILL_NAME,
	'codex': Path.home() / '.codex' / 'skills' / SKILL_NAME,
	'agents': Path.home() / '.agents' / 'skills' / SKILL_NAME,
}


def _load_skill_text() -> str:
	from browser_use.skills.browser_use import skill_text

	return skill_text()


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		prog='browser-use skill',
		description='Print or install the Browser Use skill.',
	)
	subparsers = parser.add_subparsers(dest='command')

	subparsers.add_parser('show', help='Print the skill text to stdout')

	install = subparsers.add_parser('install', help='Install the skill')
	install.add_argument(
		'--target',
		choices=sorted(TARGET_DIRS),
		default=DEFAULT_TARGET,
		help='Assistant skill directory to install into',
	)
	install.add_argument(
		'--path',
		type=Path,
		help='Custom output directory or SKILL.md path',
	)
	install.add_argument('--force', action='store_true', help='Overwrite an existing SKILL.md')

	return parser


def _resolve_output_path(target: str, custom_path: Path | None) -> Path:
	if custom_path is None:
		return TARGET_DIRS[target] / 'SKILL.md'

	path = custom_path.expanduser()
	if path.name == 'SKILL.md':
		return path
	return path / 'SKILL.md'


def handle(argv: list[str]) -> int:
	parser = _build_parser()
	args = parser.parse_args(argv)

	command = args.command or 'show'

	try:
		text = _load_skill_text()
	except RuntimeError as exc:
		print(f'Error: {exc}', file=sys.stderr)
		return 1

	if command == 'show':
		print(text, end='')
		return 0

	if command == 'install':
		output_path = _resolve_output_path(args.target, args.path)
		if output_path.exists() and not args.force:
			print(f'Error: {output_path} already exists. Use --force to overwrite.', file=sys.stderr)
			return 1

		output_path.parent.mkdir(parents=True, exist_ok=True)
		output_path.write_text(text, encoding='utf-8')
		print(f'Installed Browser Use skill to {output_path}')
		return 0

	parser.print_help()
	return 1
