"""Run one Browser Use Cloud API V4 task."""

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv('BROWSER_USE_API_URL', 'https://api.browser-use.com/api/v4').rstrip('/')
API_KEY = os.getenv('BROWSER_USE_API_KEY')
if not API_KEY:
	raise RuntimeError('Set BROWSER_USE_API_KEY or add it to .env')

HEADERS = {'X-Browser-Use-API-Key': API_KEY}
TERMINAL_STATUSES = {'completed', 'failed', 'cancelled'}


def create_run(task: str) -> str:
	response = requests.post(f'{API_URL}/runs', headers=HEADERS, json={'task': task}, timeout=30)
	response.raise_for_status()
	return response.json()['id']


def wait_for_run(run_id: str, poll_seconds: float = 2) -> dict[str, Any]:
	while True:
		response = requests.get(f'{API_URL}/runs/{run_id}/status', headers=HEADERS, timeout=30)
		response.raise_for_status()
		status = response.json()['status']
		print(f'Status: {status}')

		if status in TERMINAL_STATUSES:
			break

		time.sleep(poll_seconds)

	response = requests.get(f'{API_URL}/runs/{run_id}', headers=HEADERS, timeout=30)
	response.raise_for_status()
	return response.json()


def main() -> None:
	run_id = create_run('Find the top story on Hacker News and summarize it in one sentence.')
	print(f'Run: {run_id}')

	run = wait_for_run(run_id)
	if run['status'] != 'completed':
		raise RuntimeError(run.get('error') or f'Run {run["status"]}')

	print(f'Result: {run["result"]}')
	print(f'Cost: ${run["totalCostUsd"]}')


if __name__ == '__main__':
	main()
