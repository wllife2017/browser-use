# Browser Use Open-Source Library Reference

## Table of Contents

- [Installation](#installation)
- [Quickstart](#quickstart)
- [Production Deployment](#production-deployment)
- [Agent](#agent)
  - [Basic Usage](#agent-basic-usage)
  - [All Parameters](#agent-all-parameters)
  - [Output Format](#agent-output-format)
  - [Structured Output](#structured-output)
  - [Prompting Guide](#prompting-guide)
- [Browser](#browser)
  - [Basic Usage](#browser-basic-usage)
  - [All Parameters](#browser-all-parameters)
  - [Real Browser Connection](#real-browser-connection)
  - [Remote / Cloud Browser](#remote--cloud-browser)
- [Tools](#tools)
  - [Basics](#tools-basics)
  - [Adding Custom Tools](#adding-custom-tools)
  - [Available Default Tools](#available-default-tools)
  - [Removing Tools](#removing-tools)
  - [Tool Response](#tool-response)
- [Local Development Setup](#local-development-setup)
- [Telemetry](#telemetry)

---

## Installation

```bash
pip install uv
uv venv --python 3.12
source .venv/bin/activate
# On Windows: .venv\Scripts\activate
```

```bash
uv pip install browser-use
uvx browser-use install
```

---

## Quickstart

Create a `.env` file with your API key, then run your first agent.

### Environment Variables

```bash
# Browser Use (recommended) — get key at https://cloud.browser-use.com/new-api-key
BROWSER_USE_API_KEY=

# Google — get free key at https://aistudio.google.com/app/u/1/apikey
GOOGLE_API_KEY=

# OpenAI
OPENAI_API_KEY=

# Anthropic
ANTHROPIC_API_KEY=
```

### ChatBrowserUse (Recommended)

`ChatBrowserUse` is optimized for browser automation — highest accuracy, fastest speed, lowest token cost.

```python
from browser_use import Agent, ChatBrowserUse
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def main():
    llm = ChatBrowserUse()
    agent = Agent(task="Find the number 1 post on Show HN", llm=llm)
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Google Gemini

```python
from browser_use import Agent, ChatGoogle
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def main():
    llm = ChatGoogle(model="gemini-flash-latest")
    agent = Agent(task="Find the number 1 post on Show HN", llm=llm)
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### OpenAI

```python
from browser_use import Agent, ChatOpenAI
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def main():
    llm = ChatOpenAI(model="gpt-4.1-mini")
    agent = Agent(task="Find the number 1 post on Show HN", llm=llm)
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Anthropic

```python
from browser_use import Agent, ChatAnthropic
from dotenv import load_dotenv
import asyncio

load_dotenv()

async def main():
    llm = ChatAnthropic(model='claude-sonnet-4-0', temperature=0.0)
    agent = Agent(task="Find the number 1 post on Show HN", llm=llm)
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

See [Supported Models](https://docs.browser-use.com/supported-models#supported-models) for more providers.

---

## Production Deployment

Sandboxes are the easiest way to run Browser-Use in production. The agent runs right next to the browser, so latency is minimal.

### Basic Deployment

```python
from browser_use import Browser, sandbox, ChatBrowserUse
from browser_use.agent.service import Agent
import asyncio

@sandbox()
async def my_task(browser: Browser):
    agent = Agent(task="Find the top HN post", browser=browser, llm=ChatBrowserUse())
    await agent.run()

asyncio.run(my_task())
```

### Add Proxies for Stealth

Use country-specific proxies to bypass captchas, Cloudflare, and geo-restrictions:

```python
@sandbox(cloud_proxy_country_code='us')
async def stealth_task(browser: Browser):
    agent = Agent(task="Your task", browser=browser, llm=ChatBrowserUse())
    await agent.run()
```

### Sync Local Cookies to Cloud

1. Create an API key at [cloud.browser-use.com/new-api-key](https://cloud.browser-use.com/new-api-key)
2. Sync your local cookies:

```bash
export BROWSER_USE_API_KEY=your_key && curl -fsSL https://browser-use.com/profile.sh | sh
```

This opens a browser where you log into your accounts. You'll get a `profile_id`.

3. Use the profile in production:

```python
@sandbox(cloud_profile_id='your-profile-id')
async def authenticated_task(browser: Browser):
    agent = Agent(task="Your authenticated task", browser=browser, llm=ChatBrowserUse())
    await agent.run()
```

See [Going to Production](https://docs.browser-use.com/production) and [Sandbox Quickstart](https://docs.browser-use.com/legacy/sandbox/quickstart) for more.

---

## Agent

### Agent Basic Usage

```python
from browser_use import Agent, ChatBrowserUse

agent = Agent(
    task="Search for latest news about AI",
    llm=ChatBrowserUse(),
)

async def main():
    history = await agent.run(max_steps=100)
```

* `task`: The task you want to automate.
* `llm`: Your LLM. See [Supported Models](https://docs.browser-use.com/customize/agent/supported-models).
* `max_steps` (default: `100`): Maximum number of steps an agent can take.

### Agent All Parameters

See all parameters at [docs.browser-use.com/customize/agent/all-parameters](https://docs.browser-use.com/customize/agent/all-parameters).

#### Core Settings

* `tools`: Registry of tools the agent can call. [Example](https://docs.browser-use.com/customize/tools/basics)
* `browser`: Browser object for browser settings.
* `output_model_schema`: Pydantic model class for structured output validation. [Example](https://github.com/browser-use/browser-use/blob/main/examples/features/custom_output.py)

#### Vision & Processing

* `use_vision` (default: `"auto"`): `"auto"` includes screenshot tool but only uses vision when requested, `True` always includes screenshots, `False` never includes screenshots
* `vision_detail_level` (default: `'auto'`): Screenshot detail level — `'low'`, `'high'`, or `'auto'`
* `page_extraction_llm`: Separate LLM for page content extraction (default: same as `llm`)

#### Actions & Behavior

* `initial_actions`: List of actions to run before the main task without LLM. [Example](https://github.com/browser-use/browser-use/blob/main/examples/features/initial_actions.py)
* `max_actions_per_step` (default: `3`): Maximum actions per step
* `max_failures` (default: `3`): Maximum retries for steps with errors
* `final_response_after_failure` (default: `True`): Attempt one final model call with intermediate output after max_failures
* `use_thinking` (default: `True`): Enable explicit reasoning steps
* `flash_mode` (default: `False`): Fast mode — skips evaluation, next goal, and thinking; uses memory only. Overrides `use_thinking`. [Example](https://github.com/browser-use/browser-use/blob/main/examples/getting_started/05_fast_agent.py)

#### System Messages

* `override_system_message`: Completely replace the default system prompt
* `extend_system_message`: Add additional instructions to the default system prompt. [Example](https://github.com/browser-use/browser-use/blob/main/examples/features/custom_system_prompt.py)

#### File & Data Management

* `save_conversation_path`: Path to save complete conversation history
* `save_conversation_path_encoding` (default: `'utf-8'`): Encoding for saved conversations
* `available_file_paths`: List of file paths the agent can access
* `sensitive_data`: Dictionary of sensitive data to handle carefully. [Example](https://github.com/browser-use/browser-use/blob/main/examples/features/sensitive_data.py)

#### Visual Output

* `generate_gif` (default: `False`): Generate GIF of agent actions. Set to `True` or string path
* `include_attributes`: List of HTML attributes to include in page analysis

#### Performance & Limits

* `max_history_items`: Maximum last steps to keep in LLM memory (`None` = keep all)
* `llm_timeout` (default: `90`): Timeout in seconds for LLM calls
* `step_timeout` (default: `120`): Timeout in seconds for each step
* `directly_open_url` (default: `True`): Auto-open URLs detected in the task

#### Advanced Options

* `calculate_cost` (default: `False`): Calculate and track API costs
* `display_files_in_done_text` (default: `True`): Show file information in completion messages

#### Backwards Compatibility

* `controller`: Alias for `tools`
* `browser_session`: Alias for `browser`

### Agent Output Format

The `run()` method returns an `AgentHistoryList` object:

```python
history = await agent.run()

# Access useful information
history.urls()                    # List of visited URLs
history.screenshot_paths()        # List of screenshot paths
history.screenshots()             # List of screenshots as base64 strings
history.action_names()            # Names of executed actions
history.extracted_content()       # List of extracted content from all actions
history.errors()                  # List of errors (None for steps without errors)
history.model_actions()           # All actions with their parameters
history.model_outputs()           # All model outputs from history
history.last_action()             # Last action in history

# Analysis methods
history.final_result()            # Final extracted content (last step)
history.is_done()                 # Check if agent completed successfully
history.is_successful()           # Check if successful (None if not done)
history.has_errors()              # Check if any errors occurred
history.model_thoughts()          # Agent's reasoning (AgentBrain objects)
history.action_results()          # All ActionResult objects
history.action_history()          # Truncated action history
history.number_of_steps()         # Number of steps
history.total_duration_seconds()  # Total duration in seconds
```

See [AgentHistoryList source](https://github.com/browser-use/browser-use/blob/main/browser_use/agent/views.py#L301).

### Structured Output

Use `output_model_schema` with a Pydantic model. [Example](https://github.com/browser-use/browser-use/blob/main/examples/features/custom_output.py).

Access via `history.structured_output`.

### Prompting Guide

Prompting can drastically improve performance. See [full guide](https://docs.browser-use.com).

#### Be Specific vs Open-Ended

```python
# Good — specific
task = """
1. Go to https://quotes.toscrape.com/
2. Use extract action with the query "first 3 quotes with their authors"
3. Save results to quotes.csv using write_file action
4. Do a google search for the first quote and find when it was written
"""

# Bad — too vague
task = "Go to web and make money"
```

#### Name Actions Directly

```python
task = """
1. Use search action to find "Python tutorials"
2. Use click to open first result in a new tab
3. Use scroll action to scroll down 2 pages
4. Use extract to extract the names of the first 5 items
5. Wait for 2 seconds if the page is not loaded, refresh it and wait 10 sec
6. Use send_keys action with "Tab Tab ArrowDown Enter"
"""
```

#### Handle Interaction Problems via Keyboard

Sometimes buttons can't be clicked. Work around it with keyboard navigation:

```python
task = """
If the submit button cannot be clicked:
1. Use send_keys action with "Tab Tab Enter" to navigate and activate
2. Or use send_keys with "ArrowDown ArrowDown Enter" for form submission
"""
```

#### Custom Actions Integration

```python
@controller.action("Get 2FA code from authenticator app")
async def get_2fa_code():
    pass

task = """
Login with 2FA:
1. Enter username/password
2. When prompted for 2FA, use get_2fa_code action
3. NEVER try to extract 2FA codes from the page manually
4. ALWAYS use the get_2fa_code action for authentication codes
"""
```

#### Error Recovery

```python
task = """
Robust data extraction:
1. Go to openai.com to find their CEO
2. If navigation fails due to anti-bot protection:
   - Use google search to find the CEO
3. If page times out, use go_back and try alternative approach
"""
```

---

## Browser

### Browser Basic Usage

```python
from browser_use import Agent, Browser, ChatBrowserUse

browser = Browser(
    headless=False,
    window_size={'width': 1000, 'height': 700},
)

agent = Agent(
    task='Search for Browser Use',
    browser=browser,
    llm=ChatBrowserUse(),
)

async def main():
    await agent.run()
```

> **Note:** `Browser` is an alias for `BrowserSession` — they are the same class. Use `Browser` for cleaner code.

### Browser All Parameters

See all parameters at [docs.browser-use.com/customize/browser/all-parameters](https://docs.browser-use.com/customize/browser/all-parameters).

The `Browser` instance also provides all [Actor](https://docs.browser-use.com/legacy/actor/all-parameters) methods for direct browser control.

#### Core Settings

* `cdp_url`: CDP URL for connecting to existing browser (e.g., `"http://localhost:9222"`)

#### Display & Appearance

* `headless` (default: `None`): Run without UI. Auto-detects based on display availability
* `window_size`: Browser window size. Dict `{'width': 1920, 'height': 1080}` or `ViewportSize`
* `window_position` (default: `{'width': 0, 'height': 0}`): Window position from top-left
* `viewport`: Content area size, same format as `window_size`
* `no_viewport` (default: `None`): Disable viewport emulation
* `device_scale_factor`: DPI. Set `2.0` or `3.0` for high-res screenshots

#### Browser Behavior

* `keep_alive` (default: `None`): Keep browser running after agent completes
* `allowed_domains`: Restrict navigation. Patterns:
  * `'example.com'` — matches `https://example.com/*`
  * `'*.example.com'` — matches domain and subdomains
  * `'http*://example.com'` — matches http and https
  * `'chrome-extension://*'` — matches extensions
  * Wildcards in TLD (e.g., `example.*`) are **not allowed**
* `prohibited_domains`: Block domains. Same patterns. When both set, `allowed_domains` takes precedence
* `enable_default_extensions` (default: `True`): Load uBlock Origin, cookie handlers, ClearURLs
* `cross_origin_iframes` (default: `False`): Enable cross-origin iframe support
* `is_local` (default: `True`): Whether local browser. `False` for remote

#### User Data & Profiles

* `user_data_dir` (default: auto temp): Browser profile data directory. `None` for incognito
* `profile_directory` (default: `'Default'`): Chrome profile name (`'Profile 1'`, `'Work Profile'`)
* `storage_state`: Browser storage (cookies, localStorage). File path or dict

#### Network & Security

* `proxy`: `ProxySettings(server='http://host:8080', bypass='localhost,127.0.0.1', username='user', password='pass')`
* `permissions` (default: `['clipboardReadWrite', 'notifications']`): e.g., `['camera', 'microphone', 'geolocation']`
* `headers`: Additional HTTP headers (remote browsers only)

#### Browser Launch

* `executable_path`: Path to browser executable:
  * macOS: `'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`
  * Windows: `'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'`
  * Linux: `'/usr/bin/google-chrome'`
* `channel`: `'chromium'`, `'chrome'`, `'chrome-beta'`, `'msedge'`, etc.
* `args`: Additional CLI args: `['--disable-gpu', '--custom-flag=value']`
* `env`: Environment vars: `{'DISPLAY': ':0', 'LANG': 'en_US.UTF-8'}`
* `chromium_sandbox` (default: `True` except Docker): Chromium sandboxing
* `devtools` (default: `False`): Open DevTools (requires `headless=False`)
* `ignore_default_args`: Args to disable, or `True` for all

#### Timing & Performance

* `minimum_wait_page_load_time` (default: `0.25`): Min wait before capturing state (seconds)
* `wait_for_network_idle_page_load_time` (default: `0.5`): Wait for network idle (seconds)
* `wait_between_actions` (default: `0.5`): Wait between actions (seconds)

#### AI Integration

* `highlight_elements` (default: `True`): Highlight interactive elements for AI vision
* `paint_order_filtering` (default: `True`): Optimize DOM tree by removing hidden elements

#### Downloads & Files

* `accept_downloads` (default: `True`): Auto-accept downloads
* `downloads_path`: Download directory
* `auto_download_pdfs` (default: `True`): Download PDFs instead of viewing

#### Device Emulation

* `user_agent`: Custom user agent string
* `screen`: Screen size, same format as `window_size`

#### Recording & Debugging

* `record_video_dir`: Save video recordings as `.mp4`
* `record_video_size` (default: ViewportSize): Video frame size
* `record_video_framerate` (default: `30`): Video framerate
* `record_har_path`: Save network traces as `.har`
* `traces_dir`: Save complete trace files
* `record_har_content` (default: `'embed'`): `'omit'`, `'embed'`, `'attach'`
* `record_har_mode` (default: `'full'`): `'full'`, `'minimal'`

#### Advanced

* `disable_security` (default: `False`): **NOT RECOMMENDED** — disables all browser security
* `deterministic_rendering` (default: `False`): **NOT RECOMMENDED** — forces consistent rendering

### Real Browser Connection

Connect your existing Chrome to preserve authentication:

```python
from browser_use import Agent, Browser, ChatOpenAI

browser = Browser(
    executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    user_data_dir='~/Library/Application Support/Google/Chrome',
    profile_directory='Default',
)

agent = Agent(
    task='Visit https://duckduckgo.com and search for "browser-use founders"',
    browser=browser,
    llm=ChatOpenAI(model='gpt-4.1-mini'),
)

async def main():
    await agent.run()
```

> **Note:** You need to fully close Chrome before running this. Google blocks this approach, so use DuckDuckGo instead.

#### Platform Paths

| Platform | executable_path | user_data_dir |
|----------|----------------|---------------|
| macOS | `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` | `~/Library/Application Support/Google/Chrome` |
| Windows | `C:\Program Files\Google\Chrome\Application\chrome.exe` | `%LOCALAPPDATA%\Google\Chrome\User Data` |
| Linux | `/usr/bin/google-chrome` | `~/.config/google-chrome` |

### Remote / Cloud Browser

#### Browser-Use Cloud (Recommended)

```python
from browser_use import Agent, Browser, ChatBrowserUse

# Simple
browser = Browser(use_cloud=True)

# Advanced — bypasses captchas
browser = Browser(
    cloud_profile_id='your-profile-id',
    cloud_proxy_country_code='us',  # us, uk, fr, it, jp, au, de, fi, ca, in
    cloud_timeout=30,  # minutes (free: max 15, paid: max 240)
)

agent = Agent(task="Your task", llm=ChatBrowserUse(), browser=browser)
```

**Prerequisites:** Get API key from [cloud.browser-use.com](https://cloud.browser-use.com/new-api-key), set `BROWSER_USE_API_KEY` env var.

#### CDP URL (Any Provider)

```python
browser = Browser(cdp_url="http://remote-server:9222")
```

#### With Proxy

```python
from browser_use.browser import ProxySettings

browser = Browser(
    headless=False,
    proxy=ProxySettings(
        server="http://proxy-server:8080",
        username="proxy-user",
        password="proxy-pass"
    ),
    cdp_url="http://remote-server:9222"
)
```

---

## Tools

Tools are the functions the agent uses to interact with the world.

### Tools Basics

```python
from browser_use import Tools, ActionResult, BrowserSession

tools = Tools()

@tools.action('Ask human for help with a question')
async def ask_human(question: str, browser_session: BrowserSession) -> ActionResult:
    answer = input(f'{question} > ')
    return ActionResult(extracted_content=f'The human responded with: {answer}')

agent = Agent(task='Ask human for help', llm=llm, tools=tools)
```

> **Warning:** The parameter must be named exactly `browser_session` with type `BrowserSession` (not `browser: Browser`). The agent injects parameters by name matching — using the wrong name will cause your tool to fail silently.

Use `browser_session` for deterministic [Actor](https://docs.browser-use.com/legacy/actor/basics) actions.

### Adding Custom Tools

```python
from browser_use import Tools, Agent, ActionResult

tools = Tools()

@tools.action(description='Ask human for help with a question')
async def ask_human(question: str) -> ActionResult:
    answer = input(f'{question} > ')
    return ActionResult(extracted_content=f'The human responded with: {answer}')

agent = Agent(task='...', llm=llm, tools=tools)
```

* `description` *(required)* — What the tool does; the LLM uses this to decide when to call it
* `allowed_domains` — List of domains where tool can run (e.g., `['*.example.com']`), defaults to all

The Agent fills function parameters based on names, type hints, and defaults.

### Available Default Tools

Source: [tools/service.py](https://github.com/browser-use/browser-use/blob/main/browser_use/tools/service.py)

#### Navigation & Browser Control
* `search` — Search queries (DuckDuckGo, Google, Bing)
* `navigate` — Navigate to URLs
* `go_back` — Go back in browser history
* `wait` — Wait for specified seconds

#### Page Interaction
* `click` — Click elements by index
* `input` — Input text into form fields
* `upload_file` — Upload files to file inputs
* `scroll` — Scroll page up/down
* `find_text` — Scroll to specific text on page
* `send_keys` — Send special keys (Enter, Escape, etc.)

#### JavaScript Execution
* `evaluate` — Execute custom JavaScript (shadow DOM, custom selectors, data extraction)

#### Tab Management
* `switch` — Switch between tabs
* `close` — Close tabs

#### Content Extraction
* `extract` — Extract data from webpages using LLM

#### Visual Analysis
* `screenshot` — Request screenshot for visual confirmation

#### Form Controls
* `dropdown_options` — Get dropdown option values
* `select_dropdown` — Select dropdown options

#### File Operations
* `write_file` — Write content to files
* `read_file` — Read file contents
* `replace_file` — Replace text in files

#### Task Completion
* `done` — Complete the task (always available)

### Removing Tools

```python
from browser_use import Tools

tools = Tools(exclude_actions=['search', 'wait'])
agent = Agent(task='...', llm=llm, tools=tools)
```

### Tool Response

Tools return `ActionResult` or simple strings:

```python
@tools.action('My tool')
def my_tool() -> str:
    return "Task completed successfully"

@tools.action('Advanced tool')
def advanced_tool() -> ActionResult:
    return ActionResult(
        extracted_content="Main result",
        long_term_memory="Remember this info",
        error="Something went wrong",
        is_done=True,
        success=True,
        attachments=["file.pdf"],
    )
```

---

## Local Development Setup

```bash
git clone https://github.com/browser-use/browser-use
cd browser-use
uv sync --all-extras --dev
```

Configuration:

```bash
cp .env.example .env
# set BROWSER_USE_LOGGING_LEVEL=debug if needed
```

Helper scripts:

```bash
./bin/setup.sh   # Complete setup (uv, venv, deps)
./bin/lint.sh    # Pre-commit hooks (formatting, linting, type checking)
./bin/test.sh    # Core CI test suite
```

Run examples:

```bash
uv run examples/simple.py
```

---

## Telemetry

Browser Use collects anonymous usage data via PostHog to improve the library.

### Opting Out

```bash
# In .env
ANONYMIZED_TELEMETRY=false
```

Or in Python:

```python
import os
os.environ["ANONYMIZED_TELEMETRY"] = "false"
```

Telemetry has zero performance impact. Source: [telemetry service](https://github.com/browser-use/browser-use/tree/main/browser_use/telemetry).

---

## Getting Help

1. [GitHub Issues](https://github.com/browser-use/browser-use/issues)
2. [Discord community](https://link.browser-use.com/discord)
3. Enterprise support: [support@browser-use.com](mailto:support@browser-use.com)
