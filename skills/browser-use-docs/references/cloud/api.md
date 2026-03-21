# Cloud API Reference (v2 + v3)

## Table of Contents
- [Authentication](#authentication)
- [Core Concepts](#core-concepts)
- [SDK Methods](#sdk-methods)
- [REST Endpoints (v2)](#rest-endpoints-v2)
- [V3 API](#v3-api)
- [Enums](#enums)
- [Response Schemas](#response-schemas)

---

## Authentication

- **Header:** `X-Browser-Use-API-Key: <key>`
- **Base URL:** `https://api.browser-use.com/api/v2/`
- **Get key:** https://cloud.browser-use.com/new-api-key

## Core Concepts

- **Session** — Infrastructure container (one Browser, sequential Agents). Max 15 min (free) or 4 hours (paid).
- **Browser** — Chromium fork, CDP-controllable, stealth-optimized, adblockers built-in.
- **Agent** — LLM-powered framework for iterative browser steps. Independent judge verifies completion.
- **Model** — Best: `browser-use-llm` (ChatBrowserUse) — fastest, cheapest, routes to best frontier model.
- **Browser Profile** — Persistent cookies/localStorage/passwords across sessions. Uploadable from local Chrome.
- **Task** — Prompt (text + optional files/images) given to Agent.
- **Workspace** — Persistent file storage across sessions (v3).
- **Profile Sync** — `export BROWSER_USE_API_KEY=<key> && curl -fsSL https://browser-use.com/profile.sh | sh`

## SDK Methods

### Python

```python
from browser_use_sdk import BrowserUse
client = BrowserUse()  # BROWSER_USE_API_KEY env var

# Tasks
result = await client.run("task", llm="browser-use-llm", output_schema=MyModel)
task = await client.tasks.get(task_id)

# Sessions
session = await client.sessions.create(profile_id="uuid", proxy_country_code="us")
session = await client.sessions.get(session_id)
await client.sessions.stop(session_id)
share = await client.sessions.create_share(session_id)

# Browsers
browser = await client.browsers.create(profile_id="uuid", proxy_country_code="us", timeout=60)
await client.browsers.stop(session_id)

# Profiles
profiles = await client.profiles.list()
profile = await client.profiles.create(name="my-profile")
await client.profiles.update(profile_id, name="new-name")
await client.profiles.delete(profile_id)

# Files
url = await client.files.session_url(session_id, file_name="doc.pdf", content_type="application/pdf", size_bytes=1024)
output = await client.files.task_output(task_id, file_id)

# Billing
account = await client.billing.account()

# Skills
skill = await client.skills.create(...)
result = await client.skills.execute(skill_id, params={})
await client.skills.refine(skill_id, feedback="...")
skills = await client.marketplace.list()
```

---

## REST Endpoints (v2)

### Billing

**GET /billing/account** — Account info and credit balances.
Response: `{ name?, monthlyCreditsBalanceUsd, additionalCreditsBalanceUsd, totalCreditsBalanceUsd, rateLimit, planInfo, projectId }`

### Tasks

**GET /tasks** — Paginated list.
Params: `pageSize`, `pageNumber`, `sessionId?`, `filterBy?` (TaskStatus), `after?`, `before?`

**POST /tasks** — Create task. Auto-creates session or uses existing.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| task | string | **yes** | Task prompt |
| llm | SupportedLLMs | no | Model (default: browser-use-llm) |
| startUrl | string | no | Initial URL |
| maxSteps | integer | no | Max agent steps |
| structuredOutput | string | no | JSON schema |
| sessionId | uuid | no | Existing session |
| metadata | object | no | Key-value metadata |
| secrets | object | no | Sensitive key-value data |
| allowedDomains | string[] | no | Domain restrictions |
| opVaultId | string | no | 1Password vault ID |
| highlightElements | boolean | no | Highlight elements |
| flashMode | boolean | no | Fast mode |
| thinking | boolean | no | Enable thinking |
| vision | boolean\|"auto" | no | Vision mode |
| systemPromptExtension | string | no | Extend system prompt |

Response (202): `{ id, sessionId }`
Errors: 400 (busy), 404 (not found), 422 (validation), 429 (rate limit)

**GET /tasks/{task_id}** — Detailed info with steps and output files.

**PATCH /tasks/{task_id}** — Control: `{ action: "stop"|"pause"|"resume"|"stop_task_and_session" }`

**GET /tasks/{task_id}/logs** — Download URL: `{ downloadUrl }`

### Sessions

**GET /sessions** — Paginated list. Params: `pageSize`, `pageNumber`, `filterBy?`

**POST /sessions** — Create. Body: `{ profileId?, proxyCountryCode?, startUrl? }`
Response (201): SessionItemView. Errors: 404, 429.

**GET /sessions/{id}** — Detailed info with tasks.

**PATCH /sessions/{id}** — Stop: `{ action: "stop" }`

**GET /sessions/{id}/public-share** — Share info.

**POST /sessions/{id}/public-share** — Create share (201).

**DELETE /sessions/{id}/public-share** — Remove share (204).

### Browsers

**GET /browsers** — Paginated list.

**POST /browsers** — Create. Body: `{ profileId?, proxyCountryCode?, timeout? }`
Pricing: $0.05/hr upfront, refund on stop, min 1 min. Free: 15 min max, Paid: 4 hrs.
Response (201): BrowserSessionItemView (has `cdpUrl`, `liveUrl`). Errors: 403, 404, 429.

**GET /browsers/{id}** — Detailed info.

**PATCH /browsers/{id}** — Stop: `{ action: "stop" }` (unused time refunded).

### Files

**POST /files/sessions/{id}/presigned-url** — Upload URL.
Body: `{ fileName, contentType, sizeBytes }`. Response: `{ url, method:"POST", fields, fileName, expiresIn }`

**POST /files/browsers/{id}/presigned-url** — Same for browser sessions.

**GET /files/tasks/{task_id}/output-files/{file_id}** — Download URL: `{ id, fileName, downloadUrl }`

### Profiles

**GET /profiles** — Paginated list.

**POST /profiles** — Create: `{ name? }`. Error: 402 (subscription needed).

**GET /profiles/{id}** — Details.

**DELETE /profiles/{id}** — Delete (204).

**PATCH /profiles/{id}** — Update: `{ name? }`

---

## V3 API

Experimental next-gen agent. Token-based billing, workspaces, session messages.

```python
from browser_use_sdk.v3 import AsyncBrowserUse

client = AsyncBrowserUse()

# Run task
result = await client.run("Find top HN post")

# Sessions with messages
session = await client.sessions.create(task="...", keep_alive=True)
messages = await client.sessions.messages(session.id)

# Workspaces (persistent files)
workspace = await client.workspaces.create(name="my-workspace")
await client.sessions.upload_files(session.id, workspace_id=workspace.id, files=[...])
files = await client.sessions.files(session.id)

# Cleanup
await client.sessions.stop(session.id)
await client.close()
```

---

## Enums

| Enum | Values |
|------|--------|
| TaskStatus | started, paused, finished, stopped |
| TaskUpdateAction | stop, pause, resume, stop_task_and_session |
| SessionStatus | active, stopped |
| BrowserSessionStatus | active, stopped |
| ProxyCountryCode | us, uk, fr, it, jp, au, de, fi, ca, in (+185 more) |
| SupportedLLMs | browser-use-llm, gpt-4.1, gpt-4.1-mini, o4-mini, o3, gemini-2.5-flash, gemini-2.5-pro, gemini-flash-latest, gemini-flash-lite-latest, claude-sonnet-4-20250514, gpt-4o, gpt-4o-mini, llama-4-maverick-17b-128e-instruct, claude-3-7-sonnet-20250219 |
| UploadContentType | image/jpg, jpeg, png, gif, webp, svg+xml, application/pdf, msword, vnd.openxmlformats*.document, vnd.ms-excel, vnd.openxmlformats*.sheet, text/plain, csv, markdown |

## Response Schemas

**TaskItemView:** id, sessionId, llm, task, status, startedAt, finishedAt?, metadata?, output?, browserUseVersion?, isSuccess?

**TaskView:** extends TaskItemView + steps: TaskStepView[], outputFiles: FileView[]

**TaskStepView:** number, memory, evaluationPreviousGoal, nextGoal, url, screenshotUrl?, actions[]

**FileView:** id, fileName

**SessionItemView:** id, status, liveUrl?, startedAt, finishedAt?

**SessionView:** extends SessionItemView + tasks: TaskItemView[], publicShareUrl?

**BrowserSessionItemView:** id, status, liveUrl?, cdpUrl?, timeoutAt, startedAt, finishedAt?

**ProfileView:** id, name?, lastUsedAt?, createdAt, updatedAt, cookieDomains?[]

**ShareView:** shareToken, shareUrl, viewCount, lastViewedAt?

**AccountView:** name?, monthlyCreditsBalanceUsd, additionalCreditsBalanceUsd, totalCreditsBalanceUsd, rateLimit, planInfo, projectId
