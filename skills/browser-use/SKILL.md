---
name: browser-use
description: Automates browser interactions for web testing, form filling, screenshots, and data extraction. Use when the user needs to navigate websites, interact with web pages, fill forms, take screenshots, or extract information from web pages.
allowed-tools: Bash(browser-use:*)
---

# Browser Automation with browser-use CLI

The `browser-use` command provides fast, persistent browser automation. It maintains browser sessions across commands, enabling complex multi-step workflows.

## Prerequisites

Before using this skill, `browser-use` must be installed and configured. Run diagnostics to verify:

```bash
browser-use doctor
```

For more information, see https://github.com/browser-use/browser-use/blob/main/browser_use/skill_cli/README.md

## Core Workflow

1. **Navigate**: `browser-use open <url>` - Opens URL (starts browser if needed)
2. **Inspect**: `browser-use state` - Returns clickable elements with indices
3. **Interact**: Use indices from state to interact (`browser-use click 5`, `browser-use input 3 "text"`)
4. **Verify**: `browser-use state` or `browser-use screenshot` to confirm actions
5. **Repeat**: Browser stays open between commands

## Browser Modes

```bash
browser-use open <url>                         # Default: headless Chromium
browser-use --headed open <url>                # Visible Chromium window
browser-use --profile open <url>               # Real Chrome with Default profile
browser-use --profile "Profile 1" open <url>   # Real Chrome with named profile
```

- **Default (no --profile)**: Fast, isolated Chromium, headless by default
- **With --profile**: Uses your real Chrome binary with the specified profile (cookies, logins, extensions). Bare `--profile` uses "Default".

## Essential Commands

```bash
# Navigation
browser-use open <url>                    # Navigate to URL
browser-use back                          # Go back
browser-use scroll down                   # Scroll down (--amount N for pixels)

# Page State (always run state first to get element indices)
browser-use state                         # Get URL, title, clickable elements
browser-use screenshot                    # Take screenshot (base64)
browser-use screenshot path.png           # Save screenshot to file

# Interactions (use indices from state)
browser-use click <index>                 # Click element
browser-use type "text"                   # Type into focused element
browser-use input <index> "text"          # Click element, then type
browser-use keys "Enter"                  # Send keyboard keys
browser-use select <index> "option"       # Select dropdown option

# Data Extraction
browser-use eval "document.title"         # Execute JavaScript
browser-use get text <index>              # Get element text
browser-use get html --selector "h1"      # Get scoped HTML

# Wait
browser-use wait selector "h1"            # Wait for element
browser-use wait text "Success"           # Wait for text

# Session
browser-use close                         # Close browser session

# AI Agent
browser-use run "Fill the contact form"   # Run local agent
browser-use run "task" --llm gpt-4o       # Specify model
```

## Commands

### Navigation & Tabs
```bash
browser-use open <url>                    # Navigate to URL
browser-use back                          # Go back in history
browser-use scroll down                   # Scroll down
browser-use scroll up                     # Scroll up
browser-use scroll down --amount 1000     # Scroll by specific pixels (default: 500)
browser-use switch <tab>                  # Switch to tab by index
browser-use close-tab                     # Close current tab
browser-use close-tab <tab>              # Close specific tab
```

### Page State
```bash
browser-use state                         # Get URL, title, and clickable elements
browser-use screenshot                    # Take screenshot (outputs base64)
browser-use screenshot path.png           # Save screenshot to file
browser-use screenshot --full path.png    # Full page screenshot
```

### Interactions
```bash
browser-use click <index>                 # Click element
browser-use type "text"                   # Type text into focused element
browser-use input <index> "text"          # Click element, then type text
browser-use keys "Enter"                  # Send keyboard keys
browser-use keys "Control+a"              # Send key combination
browser-use select <index> "option"       # Select dropdown option
browser-use hover <index>                 # Hover over element (triggers CSS :hover)
browser-use dblclick <index>              # Double-click element
browser-use rightclick <index>            # Right-click element (context menu)
```

Use indices from `browser-use state`.

### JavaScript & Data
```bash
browser-use eval "document.title"         # Execute JavaScript, return result
browser-use get title                     # Get page title
browser-use get html                      # Get full page HTML
browser-use get html --selector "h1"      # Get HTML of specific element
browser-use get text <index>              # Get text content of element
browser-use get value <index>             # Get value of input/textarea
browser-use get attributes <index>        # Get all attributes of element
browser-use get bbox <index>              # Get bounding box (x, y, width, height)
```

### Cookies
```bash
browser-use cookies get                   # Get all cookies
browser-use cookies get --url <url>       # Get cookies for specific URL
browser-use cookies set <name> <value>    # Set a cookie
browser-use cookies set name val --domain .example.com --secure --http-only
browser-use cookies set name val --same-site Strict  # SameSite: Strict, Lax, or None
browser-use cookies set name val --expires 1735689600  # Expiration timestamp
browser-use cookies clear                 # Clear all cookies
browser-use cookies clear --url <url>     # Clear cookies for specific URL
browser-use cookies export <file>         # Export all cookies to JSON file
browser-use cookies export <file> --url <url>  # Export cookies for specific URL
browser-use cookies import <file>         # Import cookies from JSON file
```

### Wait Conditions
```bash
browser-use wait selector "h1"            # Wait for element to be visible
browser-use wait selector ".loading" --state hidden  # Wait for element to disappear
browser-use wait selector "#btn" --state attached    # Wait for element in DOM
browser-use wait text "Success"           # Wait for text to appear
browser-use wait selector "h1" --timeout 5000  # Custom timeout in ms
```

### Python Execution
```bash
browser-use python "x = 42"               # Set variable
browser-use python "print(x)"             # Access variable (outputs: 42)
browser-use python "print(browser.url)"   # Access browser object
browser-use python --vars                 # Show defined variables
browser-use python --reset                # Clear Python namespace
browser-use python --file script.py       # Execute Python file
```

The Python session maintains state across commands. The `browser` object provides:
- `browser.url`, `browser.title`, `browser.html` — page info
- `browser.goto(url)`, `browser.back()` — navigation
- `browser.click(index)`, `browser.type(text)`, `browser.input(index, text)`, `browser.keys(keys)` — interactions
- `browser.screenshot(path)`, `browser.scroll(direction, amount)` — visual
- `browser.wait(seconds)`, `browser.extract(query)` — utilities

### Agent Tasks
```bash
browser-use run "Fill the contact form with test data"   # AI agent
browser-use run "Extract all product prices" --max-steps 50
browser-use run "task" --llm gpt-4o                      # Specify LLM model
browser-use run "task" --llm claude-sonnet-4-20250514
```

### Cloud API
```bash
browser-use cloud login <api-key>                          # Save API key
browser-use cloud logout                                   # Remove API key
browser-use cloud v2 GET /browsers                         # List browsers
browser-use cloud v2 POST /tasks '{"task":"...","url":"https://..."}'  # Create task
browser-use cloud v3 POST /sessions '{"task":"...","model":"bu-mini"}' # Create session
browser-use cloud v2 GET /tasks/<task-id>                  # Get task status
browser-use cloud v2 poll <task-id>                        # Poll task until done
browser-use cloud v2 --help                                # Show API v2 endpoints
browser-use cloud v3 --help                                # Show API v3 endpoints
```

API key: env var `BROWSER_USE_API_KEY` or `browser-use cloud login`. Stored in `~/.config/browser-use/config.json`.

### Tunnels
```bash
browser-use tunnel <port>           # Start tunnel (returns URL)
browser-use tunnel <port>           # Idempotent - returns existing URL
browser-use tunnel list             # Show active tunnels
browser-use tunnel stop <port>      # Stop tunnel
browser-use tunnel stop --all       # Stop all tunnels
```

### Session Management
```bash
browser-use close                         # Close browser session
```

### Profile Management

#### Local Chrome Profiles
```bash
browser-use profile list                  # List local Chrome profiles
browser-use profile get "Default"         # Get profile details
browser-use profile cookies "Default"     # Show cookie domains in profile
```

## Common Workflows

### Authenticated Browsing with Profiles

Use when a task requires browsing a site the user is already logged into (e.g. Gmail, GitHub, internal tools).

**Core workflow:** Check existing profiles → ask user which profile → browse with that profile.

**Before browsing an authenticated site, the agent MUST:**
1. List available profiles
2. Ask which profile to use
3. Browse with the chosen profile

#### Step 1: Check existing profiles

```bash
browser-use profile list
# → Default: Person 1 (user@gmail.com)
# → Profile 1: Work (work@company.com)
```

#### Step 2: Browse with the chosen profile

```bash
# Real Chrome — uses existing login sessions from the chosen profile
browser-use --profile "Default" open https://github.com
```

The user is already authenticated — no login needed.

#### Check what cookies a profile has
```bash
browser-use profile cookies "Default"
# → youtube.com: 23
# → google.com: 18
# → github.com: 2
```

### Exposing Local Dev Servers

Use when you have a local dev server and need to expose it via tunnel.

```bash
# 1. Start your dev server
npm run dev &  # localhost:3000

# 2. Expose it via Cloudflare tunnel
browser-use tunnel 3000
# → url: https://abc.trycloudflare.com

# 3. Browse the tunnel URL
browser-use open https://abc.trycloudflare.com
browser-use state
browser-use screenshot
```

**Note:** Tunnels are independent of browser sessions. They persist across `browser-use close` and can be managed separately. Cloudflared must be installed — run `browser-use doctor` to check.

## Global Options

| Option | Description |
|--------|-------------|
| `--headed` | Show browser window |
| `--profile [NAME]` | Use real Chrome (bare `--profile` uses "Default") |
| `--json` | Output as JSON |
| `--mcp` | Run as MCP server via stdin/stdout |

## Tips

1. **Always run `browser-use state` first** to see available elements and their indices
2. **Use `--headed` for debugging** to see what the browser is doing
3. **Sessions persist** — the browser stays open between commands
4. **Use `--json`** for programmatic parsing
5. **Python variables persist** across `browser-use python` commands within a session
6. **CLI aliases**: `bu`, `browser`, and `browseruse` all work identically to `browser-use`

## Troubleshooting

**Run diagnostics first:**
```bash
browser-use doctor
```

**Browser won't start?**
```bash
browser-use close                     # Close browser session
browser-use --headed open <url>       # Try with visible window
```

**Element not found?**
```bash
browser-use state                     # Check current elements
browser-use scroll down               # Element might be below fold
browser-use state                     # Check again
```

## Cleanup

**Always close the browser when done:**

```bash
browser-use close                     # Close browser session
browser-use tunnel stop --all         # Stop tunnels (if any)
```
