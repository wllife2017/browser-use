import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BROWSER_USE_REPO_SKILL_URL = 'https://raw.githubusercontent.com/browser-use/browser-use/main/skills/browser-use/SKILL.md'


def test_docs_install_browser_use_skill_from_package_alias():
	readme = (ROOT / 'README.md').read_text(encoding='utf-8')
	cli_readme = (ROOT / 'browser_use' / 'skill_cli' / 'README.md').read_text(encoding='utf-8')
	combined = readme + '\n' + cli_readme

	assert 'browser-use skill install' in combined
	assert 'mkdir -p ~/.claude/skills/browser-use' not in combined
	assert 'uv run --with "browser-use[browser-harness]" python -c' not in combined
	assert 'from browser_use.skills import browser_use_skill_text' not in combined
	assert BROWSER_USE_REPO_SKILL_URL not in combined
	assert 'raw.githubusercontent.com/browser-use/browser-harness/main/SKILL.md' not in combined


def test_browser_use_repo_does_not_carry_a_copied_browser_harness_skill():
	assert not (ROOT / 'skills' / 'browser-use' / 'SKILL.md').exists()
	assert not (ROOT / 'scripts' / 'sync_browser_use_skill.py').exists()


def test_browser_use_skill_alias_reads_browser_harness_package(monkeypatch, tmp_path):
	package_dir = tmp_path / 'browser_harness'
	package_dir.mkdir()
	(package_dir / '__init__.py').write_text('', encoding='utf-8')
	(package_dir / 'SKILL.md').write_text(
		'---\nname: browser-harness\ndescription: "Always use browser-harness."\n---\n\n# browser-harness\n',
		encoding='utf-8',
	)
	monkeypatch.syspath_prepend(str(tmp_path))

	from browser_use.skills import browser_use_skill_text

	assert browser_use_skill_text() == (
		'---\n'
		'name: browser-use\n'
		'description: "Direct browser control via CDP for web interaction: automation, scraping, testing, screenshots, and site/app work."\n'
		'---\n\n'
		'# Browser Use\n'
	)


def test_browser_use_skill_cli_installs_browser_harness_package_skill(tmp_path):
	package_dir = tmp_path / 'browser_harness'
	package_dir.mkdir()
	(package_dir / '__init__.py').write_text('', encoding='utf-8')
	(package_dir / 'SKILL.md').write_text('---\nname: browser-harness\n---\n\n# Browser Harness\n', encoding='utf-8')

	home = tmp_path / 'home'
	env = os.environ.copy()
	env['HOME'] = str(home)
	env['PYTHONPATH'] = os.pathsep.join(part for part in (str(tmp_path), str(ROOT), env.get('PYTHONPATH', '')) if part)

	result = subprocess.run(
		[sys.executable, '-m', 'browser_use.skill_cli.main', 'skill', 'install'],
		cwd=ROOT,
		env=env,
		capture_output=True,
		text=True,
		timeout=10,
	)

	assert result.returncode == 0, result.stderr
	installed = home / '.claude' / 'skills' / 'browser-use' / 'SKILL.md'
	assert installed.read_text(encoding='utf-8') == (
		'---\n'
		'name: browser-use\n'
		'description: "Direct browser control via CDP for web interaction: automation, scraping, testing, screenshots, and site/app work."\n'
		'---\n\n'
		'# Browser Use\n'
	)


def test_browser_use_skill_cli_uses_real_subcommand_index_when_session_is_named_skill(tmp_path):
	package_dir = tmp_path / 'browser_harness'
	package_dir.mkdir()
	(package_dir / '__init__.py').write_text('', encoding='utf-8')
	(package_dir / 'SKILL.md').write_text('---\nname: browser-harness\n---\n\n# browser-harness\n', encoding='utf-8')

	env = os.environ.copy()
	env['HOME'] = str(tmp_path / 'home')
	env['PYTHONPATH'] = os.pathsep.join(part for part in (str(tmp_path), str(ROOT), env.get('PYTHONPATH', '')) if part)

	result = subprocess.run(
		[sys.executable, '-m', 'browser_use.skill_cli.main', '--session', 'skill', 'skill', 'show'],
		cwd=ROOT,
		env=env,
		capture_output=True,
		text=True,
		timeout=10,
	)

	assert result.returncode == 0, result.stderr
	assert result.stdout == (
		'---\n'
		'name: browser-use\n'
		'description: "Direct browser control via CDP for web interaction: automation, scraping, testing, screenshots, and site/app work."\n'
		'---\n\n'
		'# Browser Use\n'
	)


def test_browser_use_cli_does_not_treat_session_value_named_skill_as_skill_command(tmp_path):
	env = os.environ.copy()
	env['HOME'] = str(tmp_path / 'home')
	env['PYTHONPATH'] = os.pathsep.join(part for part in (str(ROOT), env.get('PYTHONPATH', '')) if part)

	result = subprocess.run(
		[sys.executable, '-m', 'browser_use.skill_cli.main', '--session', 'skill', 'sessions'],
		cwd=ROOT,
		env=env,
		capture_output=True,
		text=True,
		timeout=10,
	)

	assert result.returncode == 0, result.stderr
	assert 'No active sessions' in result.stdout
