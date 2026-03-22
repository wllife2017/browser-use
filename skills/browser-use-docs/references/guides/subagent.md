# Guide: Browser-Use as a Subagent

Delegate entire web tasks to browser-use from your orchestrator. Task in, result out — browser-use handles all browsing autonomously.

## Table of Contents
- [When to Use This Pattern](#when-to-use-this-pattern)
- [Pick Your Integration](#pick-your-integration)
- [Shell Command Agents (CLI)](#shell-command-agents-cli)
- [Python Framework Agents](#python-framework-agents)
- [TypeScript/JS Agents](#typescriptjs-agents)
- [MCP-Native Agents](#mcp-native-agents)
- [HTTP / Workflow Engines](#http--workflow-engines)
- [Cross-Cutting Concerns](#cross-cutting-concerns)

---

## When to Use This Pattern

Your system has an orchestrator — some agent, pipeline, or workflow engine that coordinates multiple capabilities. At some point it decides "I need data from the web" or "I need to interact with a website." It delegates to browser-use, which autonomously navigates, clicks, extracts, and returns a result. The orchestrator never touches the browser.

**Use subagent when:**
- You want a black box: task in → result out
- The web task is self-contained (search, extract, fill a form)
- You don't need action-by-action control

**Use [tools integration](tools-integration.md) instead when:**
- Your agent needs to make individual browser decisions (click this, then check that)
- You want your agent's reasoning loop to drive the browser

## Pick Your Integration

| Your agent type | Best approach |
|----------------|---------------|
| CLI coding agent in sandbox (Claude Code, Codex, OpenCode, Cline, Windsurf, Cursor bg, Hermes, OpenClaw) | [CLI cloud passthrough](#shell-command-agents-cli) |
| Python framework (LangChain, CrewAI, AutoGen, PydanticAI, custom) | [Python Agent wrapper](#python-framework-agents) |
| TypeScript/JS (Vercel AI SDK, LangChain.js, custom) | [Cloud SDK](#typescriptjs-agents) |
| MCP client (Claude Desktop, Cursor with MCP) | [MCP browser_task tool](#mcp-native-agents) |
| Workflow engine (n8n, Make, Zapier, Temporal) or any HTTP client | [Cloud REST API](#http--workflow-engines) |

---

## Shell Command Agents (CLI)

**For:** Agents running in sandboxes/VMs with terminal access.

The agent delegates a complete task to the cloud via CLI commands. No Python imports needed.

```bash
# 1. Set API key (once)
browser-use cloud login $BROWSER_USE_API_KEY

# 2. Fire off a task
browser-use cloud v2 POST /tasks '{"task": "Find the top HN post and return title and URL"}'
# Returns: {"id": "<task-id>", "sessionId": "<session-id>"}

# 3. Poll until done (blocks)
browser-use cloud v2 poll <task-id>

# 4. Get the result
browser-use cloud v2 GET /tasks/<task-id>
# Returns full TaskView with output, steps, outputFiles
```

For structured output, pass a JSON schema:
```bash
browser-use cloud v2 POST /tasks '{
  "task": "Find the CEO of OpenAI",
  "structuredOutput": "{\"type\":\"object\",\"properties\":{\"name\":{\"type\":\"string\"},\"company\":{\"type\":\"string\"}},\"required\":[\"name\",\"company\"]}"
}'
```

---

## Python Framework Agents

**For:** LangChain, CrewAI, AutoGen, PydanticAI, Semantic Kernel, or custom Python agents.

### Basic: Wrap Agent as a function

```python
from browser_use import Agent, ChatBrowserUse

async def browse(task: str) -> str:
    """Delegate a web task to browser-use. Returns extracted text."""
    agent = Agent(task=task, llm=ChatBrowserUse())
    try:
        history = await agent.run()
        return history.final_result() or ""
    finally:
        await agent.close()
```

Register this as a tool in your framework (LangChain `@tool`, CrewAI tool, etc.).

### Structured output

```python
from pydantic import BaseModel

class SearchResult(BaseModel):
    title: str
    url: str
    summary: str

async def browse_structured(task: str) -> SearchResult:
    agent = Agent(task=task, llm=ChatBrowserUse(), output_model_schema=SearchResult)
    history = await agent.run()
    return history.structured_output
```

### Multi-step with shared browser

```python
from browser_use import Agent, Browser, ChatBrowserUse

browser = Browser(keep_alive=True)
await browser.start()

agent = Agent(task="Log into GitHub", llm=ChatBrowserUse(), browser=browser)
await agent.run()

# Follow-up in same browser (cookies preserved)
agent.add_new_task("Navigate to my repos and list the top 5 by stars")
await agent.run()

await browser.close()
```

### Cloud subagent (no local browser needed)

```python
from browser_use_sdk import AsyncBrowserUse

client = AsyncBrowserUse()
result = await client.run(
    "Find the top HN post",
    output_schema=SearchResult,
    session_settings={"proxy_country_code": "us"},
)
print(result.output)  # SearchResult instance
```

---

## TypeScript/JS Agents

**For:** Vercel AI SDK, LangChain.js, or custom TypeScript agents.

```typescript
import { BrowserUse } from "browser-use-sdk";
import { z } from "zod";

const client = new BrowserUse();

// Simple
async function browse(task: string): Promise<string> {
  const result = await client.run(task);
  return result.output;
}

// Structured
const SearchResult = z.object({
  title: z.string(),
  url: z.string(),
});

async function browseStructured(task: string) {
  const result = await client.run(task, { schema: SearchResult });
  return result.output; // { title: string, url: string }
}
```

Multi-step with `keepAlive`:
```typescript
const session = await client.sessions.create({ proxyCountryCode: "us" });
await client.run("Log into site", { sessionId: session.id, keepAlive: true });
const result = await client.run("Extract data", { sessionId: session.id });
await client.sessions.stop(session.id);
```

---

## MCP-Native Agents

**For:** Claude Desktop, Cursor with MCP enabled, any MCP client.

### Cloud MCP (entire task delegation)

Add to MCP config:
```json
{
  "mcpServers": {
    "browser-use": {
      "url": "https://api.browser-use.com/mcp",
      "headers": { "X-Browser-Use-API-Key": "YOUR_KEY" }
    }
  }
}
```

The agent gets a `browser_task` tool. It calls it with a task description, gets back the result.

### Local MCP (free, open-source)

The `retry_with_browser_use_agent` tool delegates an entire task to the local Agent:

```bash
uvx --from 'browser-use[cli]' browser-use --mcp
```

---

## HTTP / Workflow Engines

**For:** n8n, Make, Zapier, Temporal, serverless functions, any HTTP client.

### Create task → Poll → Get result

```bash
# 1. Create task
curl -X POST https://api.browser-use.com/api/v2/tasks \
  -H "X-Browser-Use-API-Key: $BROWSER_USE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"task": "Find the top HN post and return title+URL"}'
# → {"id": "task-uuid", "sessionId": "session-uuid"}

# 2. Poll status
curl https://api.browser-use.com/api/v2/tasks/<task-id>/status \
  -H "X-Browser-Use-API-Key: $BROWSER_USE_API_KEY"
# → {"status": "finished"}

# 3. Get result
curl https://api.browser-use.com/api/v2/tasks/<task-id> \
  -H "X-Browser-Use-API-Key: $BROWSER_USE_API_KEY"
# → Full TaskView with output, steps, outputFiles
```

Or use webhooks for event-driven workflows (see `references/cloud/features.md`).

---

## Cross-Cutting Concerns

### Structured output (all integrations)

- **Local Python:** `output_model_schema=MyPydanticModel` → `history.structured_output`
- **Cloud SDK Python:** `output_schema=MyModel` → `result.output` (typed)
- **Cloud SDK TypeScript:** `{ schema: ZodSchema }` → `result.output` (typed)
- **Cloud REST:** `"structuredOutput": "<json-schema-string>"` → `output` in response

### Error handling

```python
# Local
agent = Agent(task=task, llm=llm, max_failures=5, fallback_llm=backup_llm)
history = await agent.run()
if not history.is_successful():
    errors = history.errors()

# Cloud SDK
try:
    result = await client.run(task, max_cost_usd=0.10)
except TimeoutError:
    pass  # Polling timed out (5 min default)
except BrowserUseError as e:
    pass  # API error
```

### Cost control

- **Local:** `max_steps=50`, `calculate_cost=True` → check `history.usage`
- **Cloud v2:** Per-step pricing. Use `max_steps` to limit.
- **Cloud v3:** `max_cost_usd=0.10` caps spending. Check `result.total_cost_usd`.

### Cleanup

Always close resources in `try/finally`:
```python
browser = Browser(keep_alive=True)
try:
    agent = Agent(task=task, llm=llm, browser=browser)
    await agent.run()
finally:
    await browser.close()
```
