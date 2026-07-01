from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_NAME = 'browser-use'
DEFAULT_TARGET = 'all'
TARGET_DIRS = {
	'agents': Path.home() / '.agents' / 'skills' / SKILL_NAME,
	'claude': Path.home() / '.claude' / 'skills' / SKILL_NAME,
	'codex': Path.home() / '.codex' / 'skills' / SKILL_NAME,
	'copilot': Path.home() / '.copilot' / 'skills' / SKILL_NAME,
	'cursor': Path.home() / '.cursor' / 'skills' / SKILL_NAME,
	'gemini': Path.home() / '.gemini' / 'skills' / SKILL_NAME,
	'opencode': Path.home() / '.config' / 'opencode' / 'skills' / SKILL_NAME,
}


def _load_skill_text_from_package() -> str:
	from browser_use.skills.browser_use import skill_text

	return skill_text()


def _browser_harness_executable() -> str | None:
	exe = shutil.which('browser-harness')
	if exe:
		return exe

	local_bin = Path.home() / '.local' / 'bin'
	for name in ('browser-harness', 'browser-harness.exe'):
		path = local_bin / name
		if path.exists():
			return str(path)
	return None


def _install_browser_use_tool() -> None:
	uv = shutil.which('uv')
	if not uv:
		raise RuntimeError('Installing the Browser Use skill requires `uv`. Install uv, then rerun `browser-use skill install`.')

	result = subprocess.run([uv, 'tool', 'install', '--python', '3.12', '--upgrade', '--force', 'browser-use'])
	if result.returncode != 0:
		raise RuntimeError('Failed to install browser-use with `uv tool install --python 3.12 --upgrade --force browser-use`.')


def _load_skill_text_from_browser_harness_cli() -> str:
	exe = _browser_harness_executable()
	if exe is None:
		return _load_skill_text_from_package()

	result = subprocess.run([exe, 'skill'], capture_output=True, text=True)
	if result.returncode != 0:
		error = result.stderr.strip() or result.stdout.strip() or 'unknown error'
		raise RuntimeError(f'Failed to read skill from `{exe} skill`: {error}')

	from browser_use.skills.browser_use import as_browser_use_skill

	return as_browser_use_skill(result.stdout)


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
		choices=sorted([*TARGET_DIRS, 'all']),
		default=DEFAULT_TARGET,
		help='Assistant skill directory to install into',
	)
	install.add_argument(
		'--path',
		type=Path,
		help='Custom output directory or SKILL.md path',
	)
	install.add_argument(
		'--force',
		action='store_true',
		help='Accepted for compatibility; install overwrites existing SKILL.md files by default',
	)
	install.add_argument(
		'--no-install',
		action='store_true',
		help='Skip uv tool install/upgrade and use the existing browser-use command or package',
	)

	return parser


def _resolve_output_paths(target: str, custom_path: Path | None) -> list[Path]:
	if custom_path is None:
		if target == 'all':
			return [path / 'SKILL.md' for path in TARGET_DIRS.values()]
		return [TARGET_DIRS[target] / 'SKILL.md']

	path = custom_path.expanduser()
	if path.name == 'SKILL.md':
		return [path]
	return [path / 'SKILL.md']


def _validate_output_paths(output_paths: list[Path]) -> None:
	for output_path in output_paths:
		if output_path.exists() and output_path.is_dir():
			raise RuntimeError(f'{output_path} is a directory, expected a SKILL.md file path.')
		ancestor = output_path.parent
		while not ancestor.exists():
			if ancestor.parent == ancestor:
				break
			ancestor = ancestor.parent
		if ancestor.exists() and not ancestor.is_dir():
			raise RuntimeError(f'{ancestor} is not a directory.')


def handle(argv: list[str]) -> int:
	parser = _build_parser()
	args = parser.parse_args(argv)

	command = args.command or 'show'

	if command == 'show':
		try:
			text = _load_skill_text_from_browser_harness_cli()
		except RuntimeError as exc:
			print(f'Error: {exc}', file=sys.stderr)
			return 1
		print(text, end='')
		return 0

	if command == 'install':
		try:
			output_paths = _resolve_output_paths(args.target, args.path)
			_validate_output_paths(output_paths)
			if not args.no_install:
				_install_browser_use_tool()
			text = _load_skill_text_from_browser_harness_cli()
		except RuntimeError as exc:
			print(f'Error: {exc}', file=sys.stderr)
			return 1

		for output_path in output_paths:
			output_path.parent.mkdir(parents=True, exist_ok=True)
			output_path.write_text(text, encoding='utf-8')
			print(f'Installed Browser Use skill to {output_path}')
		return 0

	parser.print_help()
	return 1
