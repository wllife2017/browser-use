---
name: remote-browser
description: Controls a local browser from a sandboxed remote machine. Use when the agent is running in a sandbox (no GUI) and needs to navigate websites, interact with web pages, fill forms, take screenshots, or expose local dev servers via tunnels.
allowed-tools: Bash(browser-use:*)
---

# Browser Automation for Sandboxed Agents

This skill is for agents running on **sandboxed remote machines** (cloud VMs, CI, coding agents) that need to control a browser. Install `browser-use` and drive a headless Chromium browser.

## Prerequisites

Before using this skill, `browser-use` must be installed and configured. Run diagnostics to verify:

```bash
browser-use doctor
```

For more information, see https://github.com/browser-use/browser-use/blob/main/browser_use/skill_cli/README.md

## Browser Modes

```bash
browser-use open <url>                                    # Default: headless Chromium
browser-use cloud connect                                 # Provision cloud browser and connect
browser-use --connect open <url>                          # Auto-discover running Chrome via CDP
browser-use --cdp-url http://localhost:9222 open <url>    # Connect to existing browser via CDP
browser-use --cdp-url ws://localhost:9222/devtools/browser/... state  # WebSocket CDP URL
```

- **Default**: Launches headless Chromium
- **With cloud connect**: Provisions a cloud browser via Browser-Use Cloud API, connects via CDP, and prints a live URL. `browser-use close` disconnects AND stops the cloud browser. Requires API key (`BROWSER_USE_API_KEY` env var or `browser-use cloud login`).
- **With --connect**: Auto-discovers a running Chrome instance with remote debugging enabled. No manual URL needed.
- **With --cdp-url**: Connects to an already-running browser via CDP URL (http:// or ws://). Useful for Docker containers, remote debugging sessions, or cloud-provisioned browsers. `browser-use close` disconnects without killing the external browser.

## Core Workflow

```bash
# Step 1: Start session (headless Chromium by default)
browser-use open https://example.com

# Step 2+: All subsequent commands use the existing session
browser-use state                   # Get page elements with indices
browser-use click 5                 # Click element by index
browser-use type "Hello World"      # Type into focused element
browser-use input 3 "text"          # Click element, then type
browser-use screenshot              # Take screenshot (base64)
browser-use screenshot page.png     # Save screenshot to file

# Done: Close the session
browser-use close                   # Close browser and release resources
```

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
browser-use click <index>                 # Click element by index
browser-use click <x> <y>                 # Click at pixel coordinates
browser-use type "text"                   # Type into focused element
browser-use input <index> "text"          # Click element, then type
browser-use keys "Enter"                  # Send keyboard keys
browser-use select <index> "option"       # Select dropdown option
browser-use upload <index> <path>         # Upload file to file input

# Data Extraction
browser-use eval "document.title"         # Execute JavaScript
browser-use extract "query"               # Extract data with LLM (not yet implemented)
browser-use get text <index>              # Get element text
browser-use get html --selector "h1"      # Get scoped HTML

# Wait
browser-use wait selector "h1"            # Wait for element
browser-use wait text "Success"           # Wait for text

# Session
browser-use close                         # Close browser session
```

## Commands

### Navigation & Tabs
```bash
browser-use open <url>              # Navigate to URL
browser-use back                    # Go back in history
browser-use scroll down             # Scroll down
browser-use scroll up               # Scroll up
browser-use scroll down --amount 1000  # Scroll by specific pixels (default: 500)
browser-use switch <tab>            # Switch tab by index
browser-use close-tab               # Close current tab
browser-use close-tab <tab>         # Close specific tab
```

### Page State
```bash
browser-use state                   # Get URL, title, and clickable elements
browser-use screenshot              # Take screenshot (base64)
browser-use screenshot path.png     # Save screenshot to file
browser-use screenshot --full p.png # Full page screenshot
```

### Interactions
```bash
browser-use click <index>           # Click element by index
browser-use click <x> <y>          # Click at pixel coordinates
browser-use type "text"             # Type into focused element
browser-use input <index> "text"    # Click element, then type
browser-use keys "Enter"            # Send keyboard keys
browser-use keys "Control+a"        # Key combination
browser-use select <index> "option" # Select dropdown option
browser-use upload <index> <path>   # Upload file to file input
browser-use hover <index>           # Hover over element
browser-use dblclick <index>        # Double-click
browser-use rightclick <index>      # Right-click
```

Use indices from `browser-use state`.

### JavaScript & Data
```bash
browser-use eval "document.title"   # Execute JavaScript
browser-use extract "query"         # Extract data with LLM (not yet implemented)
browser-use get title               # Get page title
browser-use get html                # Get page HTML
browser-use get html --selector "h1"  # Scoped HTML
browser-use get text <index>        # Get element text
browser-use get value <index>       # Get input value
browser-use get attributes <index>  # Get element attributes
browser-use get bbox <index>        # Get bounding box (x, y, width, height)
```

### Cookies
```bash
browser-use cookies get             # Get all cookies
browser-use cookies get --url <url> # Get cookies for specific URL
browser-use cookies set <name> <val>  # Set a cookie
browser-use cookies set name val --domain .example.com --secure
browser-use cookies set name val --same-site Strict  # SameSite: Strict, Lax, None
browser-use cookies set name val --expires 1735689600  # Expiration timestamp
browser-use cookies clear           # Clear all cookies
browser-use cookies clear --url <url>  # Clear cookies for specific URL
browser-use cookies export <file>   # Export to JSON
browser-use cookies import <file>   # Import from JSON
```

### Wait Conditions
```bash
browser-use wait selector "h1"                         # Wait for element
browser-use wait selector ".loading" --state hidden    # Wait for element to disappear
browser-use wait text "Success"                        # Wait for text
browser-use wait selector "#btn" --timeout 5000        # Custom timeout (ms)
```

### Python Execution
```bash
browser-use python "x = 42"           # Set variable
browser-use python "print(x)"         # Access variable (prints: 42)
browser-use python "print(browser.url)"  # Access browser object
browser-use python --vars             # Show defined variables
browser-use python --reset            # Clear namespace
browser-use python --file script.py   # Run Python file
```

The Python session maintains state across commands. The `browser` object provides:
- `browser.url`, `browser.title`, `browser.html` — page info
- `browser.goto(url)`, `browser.back()` — navigation
- `browser.click(index)`, `browser.type(text)`, `browser.input(index, text)`, `browser.keys(keys)`, `browser.upload(index, path)` — interactions
- `browser.screenshot(path)`, `browser.scroll(direction, amount)` — visual
- `browser.wait(seconds)` — utilities

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
browser-use close                   # Close browser session
```

## Common Workflows

### Exposing Local Dev Servers

Use when you have a dev server on the remote machine and need the browser to reach it via tunnel.

**Core workflow:** Start dev server → create tunnel → browse the tunnel URL.

```bash
# 1. Start your dev server
python -m http.server 3000 &

# 2. Expose it via Cloudflare tunnel
browser-use tunnel 3000
# → url: https://abc.trycloudflare.com

# 3. Now the browser can reach your local server
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
| `--connect` | Auto-discover and connect to running Chrome via CDP |
| `--cdp-url <url>` | Connect to existing browser via CDP URL (`http://` or `ws://`) |
| `--session NAME` | Target a named session (default: "default") |
| `--json` | Output as JSON |

## Command Chaining

Commands can be chained with `&&` in a single shell invocation. The browser persists between commands via a background daemon, so chaining is safe and more efficient than separate calls.

```bash
# Chain open + state in one call
browser-use open https://example.com && browser-use state

# Chain multiple interactions
browser-use input 5 "user@example.com" && browser-use input 6 "password123" && browser-use click 7

# Fill and verify
browser-use input 3 "search query" && browser-use keys "Enter" && browser-use state
```

**When to chain:** Use `&&` when you don't need to read the output of an intermediate command before proceeding. Run commands separately when you need to parse the output first (e.g., `state` to discover indices, then interact using those indices).

## Tips

1. **Run `browser-use doctor`** to verify installation before starting
2. **Always run `state` first** to see available elements and their indices
3. **Sessions persist** across commands — the browser stays open until you close it
4. **Tunnels are independent** — they persist across `browser-use close`
5. **Use `--json`** for programmatic parsing
6. **`tunnel` is idempotent** — calling it again for the same port returns the existing URL

## Troubleshooting

**Browser won't start?**
- Run `browser-use doctor` to check configuration
- `browser-use close` then retry

**Tunnel not working?**
- Verify cloudflared is installed: `which cloudflared`
- `browser-use tunnel list` to check active tunnels
- `browser-use tunnel stop <port>` and retry

**Element not found?**
- Run `browser-use state` to see current elements
- `browser-use scroll down` then `browser-use state` — element might be below fold

## Cleanup

**Always close resources when done:**

```bash
browser-use close                     # Close browser session
browser-use tunnel stop --all         # Stop tunnels (if any)
```
