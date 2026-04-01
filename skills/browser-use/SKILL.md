---
name: browser-use
description: Automates browser interactions for web testing, form filling, screenshots, and data extraction. Use when the user needs to navigate websites, interact with web pages, fill forms, take screenshots, or extract information from web pages.
allowed-tools: Bash(browser-use:*)
---

# Browser Automation with browser-use CLI

The `browser-use` command provides fast, persistent browser automation. A background daemon keeps the browser open across commands, giving ~50ms latency per call.

## Prerequisites

```bash
browser-use doctor    # Verify installation
```

For setup details, see https://github.com/browser-use/browser-use/blob/main/browser_use/skill_cli/README.md

## Core Workflow

**Default: connect to the user's existing Chrome browser.** This preserves their logins, cookies, and open tabs.

1. **Register**: `INDEX=$(browser-use register)` — get an agent index (once per session)
2. **Navigate**: `browser-use --connect $INDEX open <url>` — opens in a new tab in the user's Chrome
3. **Inspect**: `browser-use --connect $INDEX state` — returns clickable elements with indices
4. **Interact**: use indices from state (`browser-use --connect $INDEX click 5`, `browser-use --connect $INDEX input 3 "text"`)
5. **Verify**: `browser-use --connect $INDEX state` or `browser-use --connect $INDEX screenshot` to confirm
6. **Repeat**: browser stays open between commands

If `--connect` fails (Chrome not running with remote debugging), fall back to `browser-use --headed open <url>` which launches a fresh Chromium.

## Browser Modes

```bash
# Preferred: connect to user's existing Chrome (requires remote debugging enabled)
INDEX=$(browser-use register)
browser-use --connect $INDEX open <url>        # Connect to running Chrome with agent index

# Fallback: launch a new browser
browser-use --headed open <url>                # Visible Chromium window
browser-use open <url>                         # Headless Chromium

# Other modes
browser-use --profile "Default" open <url>      # Real Chrome with Default profile
browser-use --cdp-url ws://localhost:9222/... open <url>  # Connect via explicit CDP URL
```

`--connect`, `--cdp-url`, and `--profile` are mutually exclusive.

## Commands

```bash
# Navigation
browser-use open <url>                    # Navigate to URL
browser-use back                          # Go back in history
browser-use scroll down                   # Scroll down (--amount N for pixels)
browser-use scroll up                     # Scroll up
browser-use tab list                      # List all tabs with lock status
browser-use tab new [url]                 # Open a new tab (blank or with URL)
browser-use tab switch <index>            # Switch to tab by index
browser-use tab close <index> [index...]  # Close one or more tabs

# Page State — always run state first to get element indices
browser-use state                         # URL, title, clickable elements with indices
browser-use screenshot [path.png]         # Screenshot (base64 if no path, --full for full page)

# Interactions — use indices from state
browser-use click <index>                 # Click element by index
browser-use click <x> <y>                 # Click at pixel coordinates
browser-use type "text"                   # Type into focused element
browser-use input <index> "text"          # Click element, then type
browser-use keys "Enter"                  # Send keyboard keys (also "Control+a", etc.)
browser-use select <index> "option"       # Select dropdown option
browser-use upload <index> <path>         # Upload file to file input
browser-use hover <index>                 # Hover over element
browser-use dblclick <index>              # Double-click element
browser-use rightclick <index>            # Right-click element

# Data Extraction
browser-use eval "js code"                # Execute JavaScript, return result
browser-use get title                     # Page title
browser-use get html [--selector "h1"]    # Page HTML (or scoped to selector)
browser-use get text <index>              # Element text content
browser-use get value <index>             # Input/textarea value
browser-use get attributes <index>        # Element attributes
browser-use get bbox <index>              # Bounding box (x, y, width, height)

# Wait
browser-use wait selector "css"           # Wait for element (--state visible|hidden|attached|detached, --timeout ms)
browser-use wait text "text"              # Wait for text to appear

# Cookies
browser-use cookies get [--url <url>]     # Get cookies (optionally filtered)
browser-use cookies set <name> <value>    # Set cookie (--domain, --secure, --http-only, --same-site, --expires)
browser-use cookies clear [--url <url>]   # Clear cookies
browser-use cookies export <file>         # Export to JSON
browser-use cookies import <file>         # Import from JSON

# Python — persistent session with browser access
browser-use python "code"                 # Execute Python (variables persist across calls)
browser-use python --file script.py       # Run file
browser-use python --vars                 # Show defined variables
browser-use python --reset                # Clear namespace

# Session
browser-use close                         # Close browser and stop daemon
browser-use sessions                      # List active sessions
browser-use close --all                   # Close all sessions
```

The Python `browser` object provides: `browser.url`, `browser.title`, `browser.html`, `browser.goto(url)`, `browser.back()`, `browser.click(index)`, `browser.type(text)`, `browser.input(index, text)`, `browser.keys(keys)`, `browser.upload(index, path)`, `browser.screenshot(path)`, `browser.scroll(direction, amount)`, `browser.wait(seconds)`.

### Raw CDP / Python session

The CLI commands handle most browser interactions. Use `browser-use python` with raw CDP access when you need to:
- Control which tab the user sees in Chrome (activate/focus a tab)
- Manipulate page internals the CLI doesn't expose (network, DOM, device emulation)
- Work with Chrome target IDs instead of element indices
- Chain multiple async browser operations in one call

Read `references/cdp-python.md` for the `browser._run()` pattern and copy-pasteable CDP recipes.

## Cloud API

```bash
browser-use cloud connect                 # Provision cloud browser and connect (zero-config)
browser-use cloud login <api-key>         # Save API key (or set BROWSER_USE_API_KEY)
browser-use cloud logout                  # Remove API key
browser-use cloud v2 GET /browsers        # REST passthrough (v2 or v3)
browser-use cloud v2 POST /tasks '{"task":"...","url":"..."}'
browser-use cloud v2 poll <task-id>       # Poll task until done
browser-use cloud v2 --help               # Show API endpoints
```

`cloud connect` provisions a cloud browser with a persistent profile (auto-created on first use), connects via CDP, and prints a live URL. `browser-use close` disconnects AND stops the cloud browser. For custom browser settings (proxy, timeout, specific profile), use `cloud v2 POST /browsers` directly with the desired parameters.

### Agent Self-Registration

Only use this if you don't already have an API key (check `browser-use cloud login` status first). If already logged in, skip this entirely.

1. `browser-use cloud signup` — get a challenge
2. Solve the challenge
3. `browser-use cloud signup --verify <challenge-id> <answer>` — verify and save API key
4. `browser-use cloud signup --claim` — generate URL for a human to claim the account

## Tunnels

```bash
browser-use tunnel <port>                 # Start Cloudflare tunnel (idempotent)
browser-use tunnel list                   # Show active tunnels
browser-use tunnel stop <port>            # Stop tunnel
browser-use tunnel stop --all             # Stop all tunnels
```

## Profile Management

```bash
browser-use profile list                  # List detected browsers and profiles
browser-use profile sync --all            # Sync profiles to cloud
browser-use profile update                # Download/update profile-use binary
```

## Command Chaining

Commands can be chained with `&&`. The browser persists via the daemon, so chaining is safe and efficient.

```bash
browser-use open https://example.com && browser-use state
browser-use input 5 "user@example.com" && browser-use input 6 "password" && browser-use click 7
```

Chain when you don't need intermediate output. Run separately when you need to parse `state` to discover indices first.

## Common Workflows

### Authenticated Browsing

When a task requires an authenticated site (Gmail, GitHub, internal tools), use Chrome profiles:

```bash
browser-use profile list                           # Check available profiles
# Ask the user which profile to use, then:
browser-use --profile "Default" open https://github.com  # Already logged in
```

### Connecting to Existing Chrome

```bash
INDEX=$(browser-use register)                      # Get agent index first
browser-use --connect $INDEX open https://example.com  # Connect with agent index
```

Requires Chrome with remote debugging enabled. Falls back to probing ports 9222/9229.

### Exposing Local Dev Servers

```bash
browser-use tunnel 3000                            # → https://abc.trycloudflare.com
browser-use open https://abc.trycloudflare.com     # Browse the tunnel
```

## Multi-Agent (--connect mode)

Multiple agents can share one Chrome browser via `--connect`. Each agent gets its own tab — other agents can't interfere.

**Setup**: Register once, then pass the index with every `--connect` command:

```bash
INDEX=$(browser-use register)                    # → prints "1"
browser-use --connect $INDEX open <url>          # Navigate in agent's own tab
browser-use --connect $INDEX state               # Get state from agent's tab
browser-use --connect $INDEX click <element>     # Click in agent's tab
```

- **Tab locking**: When an agent mutates a tab (click, type, navigate), that tab is locked to it. Other agents get an error if they try to mutate the same tab.
- **Read-only access**: `state`, `screenshot`, `get`, and `wait` commands work on any tab regardless of locks.
- **Pre-existing tabs**: Tabs already open in Chrome start unlocked — any agent can claim them.
- **Agent sessions expire** after 5 minutes of inactivity. Run `browser-use register` again to get a new index.
- **If you get "Tab is currently in use by another agent"**: do NOT close sessions or force it. Just use `open` to navigate your own tab to the URL you need.
- **Never run `browser-use close --all`** when other agents are sharing the browser — it kills everything.

## Multiple Browser Sessions

Run different browsers simultaneously with `--session`:

```bash
browser-use --session cloud cloud connect         # Cloud browser
browser-use --session local --headed open <url>    # Local Chromium
browser-use --session work --profile "Default" open <url>  # Real Chrome

browser-use sessions                               # List all active
browser-use --session cloud close                  # Close one
browser-use close --all                            # Close all
```

Each session gets its own daemon, socket, and state. See `references/multi-session.md` for details.

## Configuration

```bash
browser-use config list                            # Show all config values
browser-use config set cloud_connect_proxy jp      # Set a value
browser-use config get cloud_connect_proxy         # Get a value
browser-use config unset cloud_connect_timeout     # Remove a value
browser-use doctor                                 # Shows config + diagnostics
browser-use setup                                  # Interactive post-install setup
```

Config stored in `~/.browser-use/config.json`.

## Global Options

| Option | Description |
|--------|-------------|
| `--headed` | Show browser window |
| `--profile [NAME]` | Use real Chrome (bare `--profile` uses "Default") |
| `--connect INDEX` | Connect to running Chrome via CDP with agent index (run `browser-use register` first) |
| `--cdp-url <url>` | Connect via CDP URL (`http://` or `ws://`) |
| `--session NAME` | Target a named session (default: "default") |
| `--json` | Output as JSON |
| `--mcp` | Run as MCP server via stdin/stdout |

## Tips

1. **Always run `state` first** to see available elements and their indices
2. **Use `--headed` for debugging** to see what the browser is doing
3. **Sessions persist** — browser stays open between commands
4. **CLI aliases**: `bu`, `browser`, and `browseruse` all work

## Troubleshooting

- **Browser won't start?** `browser-use close` then `browser-use --headed open <url>`
- **Element not found?** `browser-use scroll down` then `browser-use state`
- **Run diagnostics:** `browser-use doctor`

## Cleanup

```bash
browser-use close                         # Close browser session
browser-use tunnel stop --all             # Stop tunnels (if any)
```
