# Guide: Adding Browser-Use Tools to Your Agent

Add individual browser actions to your existing agent's tool set. Your agent stays in control and drives the browser action by action.

## Table of Contents
- [When to Use This Pattern](#when-to-use-this-pattern)
- [Pick Your Integration](#pick-your-integration)
- [Shell Command Agents (CLI)](#shell-command-agents-cli)
- [Python: Actor API](#python-actor-api)
- [Python: Tools Registry](#python-tools-registry)
- [Python: MCP Client](#python-mcp-client)
- [TypeScript/JS: CDP + Playwright](#typescriptjs-cdp--playwright)
- [MCP-Native Agents](#mcp-native-agents)
- [Existing Playwright/Puppeteer/Selenium](#existing-playwrightpuppeteerselenium)
- [Decision Summary](#decision-summary)

---

## When to Use This Pattern

Your agent already has tools (search, code execution, file I/O, etc.) and its own reasoning loop. You want to add browser capabilities — navigate, click, type, extract — as tools your agent can call. You don't want to hand off to browser-use's Agent; your agent makes the decisions.

**Use tools integration when:**
- Your agent needs action-by-action browser control
- You want browser actions alongside your other tools
- Your agent's reasoning should drive what gets clicked/typed

**Use [subagent](subagent.md) instead when:**
- You want to delegate an entire web task as a black box
- You don't need control over individual browser actions

## Pick Your Integration

| Your agent type | Best approach | Control level |
|----------------|---------------|--------------|
| CLI coding agent in sandbox | [CLI commands](#shell-command-agents-cli) | Per-command |
| Python + wants fine control | [Actor API](#python-actor-api) | Page/Element/Mouse |
| Python + wants built-in actions | [Tools Registry](#python-tools-registry) | Action registry |
| Python + wants auto-discovery | [MCP Client](#python-mcp-client) | MCP tools |
| TypeScript/JS | [CDP + Playwright](#typescriptjs-cdp--playwright) | Playwright API |
| MCP client (Claude Desktop, Cursor) | [Local MCP server](#mcp-native-agents) | MCP tools |
| Existing Playwright/Puppeteer/Selenium | [CDP WebSocket (stealth)](#existing-playwrightpuppeteerselenium) | Your existing API |

---

## Shell Command Agents (CLI)

**For:** Claude Code, Codex, OpenCode, Cline, Windsurf, Cursor background agents, Hermes, OpenClaw — any coding agent running in a VM/container with terminal access.

**Setup:** Install the CLI and load the browser-use SKILL.md into the agent's context. The agent calls browser commands as shell tool invocations.

```bash
uv pip install 'browser-use[cli]'
```

**Core workflow** — the agent calls these commands one at a time, reading output between each:

```bash
# 1. Navigate
browser-use open https://example.com

# 2. Observe — ALWAYS run state first to get element indices
browser-use state
# Output: URL, title, list of clickable elements with indices
# e.g. [0] <input type="search" placeholder="Search...">
#      [1] <button>Submit</button>
#      [2] <a href="/about">About</a>

# 3. Interact — use indices from state
browser-use input 0 "search query"    # Type into element 0
browser-use click 1                   # Click element 1

# 4. Verify — re-run state to see result
browser-use state

# 5. Extract data
browser-use get text 3               # Get element text
browser-use get html --selector "h1" # Get scoped HTML
browser-use eval "document.title"    # Execute JavaScript
browser-use screenshot result.png    # Capture visual state

# 6. Wait for dynamic content
browser-use wait selector ".results" # Wait for element
browser-use wait text "Success"      # Wait for text

# 7. Cleanup
browser-use close
```

**Key details:**
- Background daemon keeps browser alive between commands (~50ms latency per call)
- Agent's reasoning loop decides which command to call next
- `state` output is the agent's "eyes" — it reads element indices and decides what to click
- Commands can be chained with `&&` when intermediate output isn't needed
- `--json` flag for machine-readable output
- `--headed` for visible browser (debugging)
- `--profile "Default"` for authenticated browsing with saved Chrome logins

---

## Python: Actor API

**For:** Python agents that want direct, fine-grained browser control. No LLM overhead from browser-use's side — your agent provides all reasoning.

```python
from browser_use import Browser

browser = Browser()
await browser.start()

# Page management
page = await browser.new_page("https://example.com")
pages = await browser.get_pages()

# Element finding
elements = await page.get_elements_by_css_selector("input[type='text']")
# Or use LLM to find elements by description:
element = await page.must_get_element_by_prompt("search box", llm=your_llm)

# Interactions
await element.fill("search query")
await element.click()
await page.press("Enter")

# JavaScript
title = await page.evaluate('() => document.title')
data = await page.evaluate('() => JSON.stringify([...document.querySelectorAll("h2")].map(e => e.textContent))')

# Screenshots
screenshot_b64 = await page.screenshot()

# LLM-powered extraction
from pydantic import BaseModel
class Product(BaseModel):
    name: str
    price: float

product = await page.extract_content("Extract product info", Product, llm=your_llm)

# Mouse operations
mouse = page.mouse
await mouse.click(x=100, y=200)
await mouse.scroll(delta_y=-500)

# Cleanup
await browser.stop()
```

**Key details:**
- Built on CDP, not Playwright — similar API but not identical
- `get_elements_by_css_selector()` returns immediately (no visibility wait)
- `evaluate()` requires arrow function format: `() => { ... }`
- Use `asyncio.sleep()` after navigation-triggering actions
- Always `browser.stop()` in `finally`

---

## Python: Tools Registry

**For:** Python agents that want browser-use's built-in actions as callable functions without the Agent loop.

```python
from browser_use import Tools, Browser, BrowserSession

browser = Browser()
await browser.start()

tools = Tools()

# Call built-in actions programmatically
await tools.registry.execute_action(
    'navigate', {'url': 'https://example.com'}, browser_session=browser
)

state = await tools.registry.execute_action(
    'get_state', {}, browser_session=browser
)

await tools.registry.execute_action(
    'click', {'index': 5}, browser_session=browser
)

await tools.registry.execute_action(
    'input_text', {'index': 3, 'text': 'hello'}, browser_session=browser
)

result = await tools.registry.execute_action(
    'extract', {'query': 'Extract all product names'}, browser_session=browser
)

await browser.stop()
```

**Available actions:** navigate, click, input_text, scroll, find_text, send_keys, screenshot, extract, go_back, switch_tab, close_tab, evaluate, dropdown_options, select_dropdown, upload_file, write_file, read_file, done.

You can also register custom actions:
```python
@tools.registry.action('My custom browser action')
async def custom_action(browser_session: BrowserSession):
    page = await browser_session.must_get_current_page()
    # ... your logic
    return ActionResult(extracted_content="result")
```

---

## Python: MCP Client

**For:** Python agents that want browser tools auto-discovered from an MCP server.

```python
from browser_use import Tools
from browser_use.mcp.client import MCPClient

tools = Tools()

# Connect to browser-use's own MCP server
mcp = MCPClient(
    server_name="browser",
    command="uvx",
    args=["--from", "browser-use[cli]", "browser-use", "--mcp"]
)

# All MCP tools auto-registered into Tools registry
await mcp.register_to_tools(tools)

# Now your agent can call: browser_navigate, browser_click,
# browser_type, browser_get_state, browser_extract_content,
# browser_screenshot, browser_scroll, browser_go_back,
# browser_list_tabs, browser_switch_tab, browser_close_tab, etc.
```

Also works with any external MCP server (filesystem, GitHub, Slack, etc.).

---

## TypeScript/JS: CDP + Playwright

**For:** TypeScript agents that need browser primitives. Connect Playwright to a cloud stealth browser.

```typescript
import { chromium } from "playwright";

// Connect to cloud stealth browser (no local Chrome needed)
const browser = await chromium.connectOverCDP(
  "wss://connect.browser-use.com?apiKey=YOUR_KEY&proxyCountryCode=us"
);
const page = browser.contexts()[0].pages()[0];

// Your agent calls these as tools:
await page.goto("https://example.com");
await page.fill("#search", "query");
await page.click("button[type=submit]");
const text = await page.textContent(".result");
const screenshot = await page.screenshot();

await browser.close();
// Browser auto-stops when WebSocket disconnects
```

For local browser (no cloud):
```typescript
import { chromium } from "playwright";

const browser = await chromium.launch();
const page = await browser.newPage();
// ... same Playwright API
await browser.close();
```

---

## MCP-Native Agents

**For:** Claude Desktop, Cursor with MCP, any MCP client that discovers tools via protocol.

Start the local MCP server:
```bash
uvx --from 'browser-use[cli]' browser-use --mcp
```

The agent gets individual browser tools:
- `browser_navigate(url)` — go to URL
- `browser_click(index)` — click element by index
- `browser_type(index, text)` — type into element
- `browser_get_state(include_screenshot)` — get page state with element indices
- `browser_extract_content(query)` — LLM-powered extraction
- `browser_screenshot(full_page)` — capture page
- `browser_scroll(direction)` — scroll up/down
- `browser_go_back()` — browser back
- `browser_list_tabs()`, `browser_switch_tab(id)`, `browser_close_tab(id)` — tab management

The agent calls these one at a time, using its own reasoning to decide the next action.

---

## Existing Playwright/Puppeteer/Selenium

**For:** You already have browser automation scripts and want to run them on stealth infrastructure (anti-fingerprinting, CAPTCHA handling, residential proxies).

Zero code changes — just change the connection URL:

### Playwright
```python
# Before: local browser
browser = await playwright.chromium.launch()

# After: cloud stealth browser
browser = await playwright.chromium.connect_over_cdp(
    "wss://connect.browser-use.com?apiKey=KEY&proxyCountryCode=us"
)
# Rest of your code stays exactly the same
```

### Puppeteer
```javascript
// Before
const browser = await puppeteer.launch();

// After
const browser = await puppeteer.connect({
  browserWSEndpoint: "wss://connect.browser-use.com?apiKey=KEY&proxyCountryCode=us"
});
```

Browser auto-starts on connect, auto-stops on disconnect. Pricing: $0.05/hour.

---

## Decision Summary

| Condition | Best option |
|-----------|------------|
| Agent has terminal access (sandbox/VM) | CLI commands |
| Python, wants fine-grained control | Actor API |
| Python, wants built-in action set | Tools Registry |
| Python, wants auto-discovery | MCPClient |
| TypeScript/JS | CDP WebSocket + Playwright |
| MCP client (Claude Desktop, Cursor) | Local MCP server |
| HTTP only / any language | Cloud REST: `POST /browsers` → CDP URL |
| Existing Playwright/Puppeteer scripts | CDP WebSocket (stealth cloud browser) |
