# Browser Use Cloud API Reference

## Table of Contents

- [Overview](#overview)
- [Core Concepts](#core-concepts)
- [Authentication](#authentication)
- [Quickstart](#quickstart)
- [API Endpoints](#api-endpoints)
  - [Billing](#billing)
  - [Tasks](#tasks)
  - [Sessions](#sessions)
  - [Browsers](#browsers)
  - [Files](#files)
  - [Profiles](#profiles)
- [Enums Reference](#enums-reference)
- [Response Schemas](#response-schemas)

---

## Overview

Browser Use Cloud is the fully hosted product by Browser Use for automating web-based tasks. Users submit tasks as prompts (text, optionally files and images) and remote browsers + agents are spun up to complete them on-demand. Pricing is usage-based via API keys. Account management, live session viewing, and task results are at https://cloud.browser-use.com/.

## Core Concepts

- **Session** — Infrastructure package containing one Browser. Sessions are limited to 15 minutes (free) or 4 hours (paid). Users can run Agents sequentially within a Session.
- **Browser** — Chromium fork running on cloud infrastructure, controllable via CDP URL. Optimized for speed, stealth (undetectable as bots), with built-in adblockers.
- **Agent** — Framework enabling an LLM to interact with a Browser through iterative steps. Each step: observe page state (including screenshot) → call tools → repeat until done. An independent judge verifies completion.
- **Model** — The LLM powering an Agent. Best option: `browser-use-llm` (ChatBrowserUse) — routes to the best frontier model with speed/cost optimizations.
- **Browser Profile** — Persistent browser data (cookies, localStorage, passwords) saved across sessions. Upload from local Chrome for authentication.
- **Task** — User prompt (text + optional files/images) given to an Agent.
- **Profile Sync** — Upload local cookies: `export BROWSER_USE_API_KEY=<key> && curl -fsSL https://browser-use.com/profile.sh | sh`

## Authentication

- **Header:** `X-Browser-Use-API-Key: <your-api-key>`
- **Base URL:** `https://api.browser-use.com/api/v2/`
- **Get key:** https://cloud.browser-use.com/new-api-key

All endpoints require the `X-Browser-Use-API-Key` header.

## Quickstart

### 1. Create a Task

```bash
curl -X POST https://api.browser-use.com/api/v2/tasks \
     -H "X-Browser-Use-API-Key: <apiKey>" \
     -H "Content-Type: application/json" \
     -d '{
  "task": "Search for the top Hacker News post and return the title and url."
}'
```

Response: `{"id": "<task-id>", "sessionId": "<session-id>"}`

### 2. Watch the Live Stream

```bash
curl https://api.browser-use.com/api/v2/sessions/<sessionId> \
     -H "X-Browser-Use-API-Key: <apiKey>"
```

The response contains a `"liveUrl"` — open it to watch the agent work.

### 3. Stop the Session

```bash
curl -X PATCH https://api.browser-use.com/api/v2/sessions/<session_id> \
     -H "X-Browser-Use-API-Key: <apiKey>" \
     -H "Content-Type: application/json" \
     -d '{"action": "stop"}'
```

---

## API Endpoints

### Billing

#### GET /billing/account

Get account info including credit balances.

**Response (200):**

```
{
  name: string | null,
  monthlyCreditsBalanceUsd: number,
  additionalCreditsBalanceUsd: number,
  totalCreditsBalanceUsd: number,
  rateLimit: integer,
  planInfo: {
    planName: string,
    subscriptionStatus: string | null,
    subscriptionId: string | null,
    subscriptionCurrentPeriodEnd: string | null,
    subscriptionCanceledAt: string | null
  },
  projectId: uuid
}
```

---

### Tasks

#### GET /tasks

Get paginated list of tasks with optional filtering.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| pageSize | integer | no | Items per page |
| pageNumber | integer | no | Page number |
| sessionId | uuid | no | Filter by session |
| filterBy | TaskStatus | no | Filter by status |
| after | datetime | no | Tasks after this time |
| before | datetime | no | Tasks before this time |

**Response (200):** `{ items: TaskItemView[], totalItems, pageNumber, pageSize }`

#### POST /tasks

Create a new task. Auto-creates a session, or runs in an existing one.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| task | string | **yes** | The task prompt |
| llm | SupportedLLMs | no | Model to use (default: `browser-use-llm`) |
| startUrl | string | no | Initial URL to navigate to |
| maxSteps | integer | no | Max agent steps |
| structuredOutput | string | no | JSON schema for structured output |
| sessionId | uuid | no | Run in existing session |
| metadata | object | no | Key-value metadata (string values) |
| secrets | object | no | Sensitive key-value data (string values) |
| allowedDomains | string[] | no | Restrict navigation domains |
| opVaultId | string | no | 1Password vault ID |
| highlightElements | boolean | no | Highlight interactive elements |
| flashMode | boolean | no | Fast mode (skip evaluation/thinking) |
| thinking | boolean | no | Enable thinking |
| vision | boolean \| "auto" | no | Vision mode |
| systemPromptExtension | string | no | Extend system prompt |

**Response (202):** `{ id: uuid, sessionId: uuid }`

**Errors:** 400 (session busy/stopped), 404 (session not found), 422 (validation), 429 (rate limit)

#### GET /tasks/{task_id}

Get detailed task info including status, steps, and output files.

**Response (200):** TaskView (see [Response Schemas](#response-schemas))

**Errors:** 404 (not found)

#### PATCH /tasks/{task_id}

Control task execution.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| action | TaskUpdateAction | **yes** | `stop`, `pause`, `resume`, or `stop_task_and_session` |

**Response (200):** TaskView

**Errors:** 404 (not found), 422 (validation)

#### GET /tasks/{task_id}/logs

Get download URL for task execution logs.

**Response (200):** `{ downloadUrl: string }`

**Errors:** 404 (not found), 500 (failed to generate URL)

---

### Sessions

#### GET /sessions

Get paginated list of sessions.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| pageSize | integer | no | Items per page |
| pageNumber | integer | no | Page number |
| filterBy | SessionStatus | no | Filter by status |

**Response (200):** `{ items: SessionItemView[], totalItems, pageNumber, pageSize }`

#### POST /sessions

Create a new session.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| profileId | uuid | no | Browser profile to use |
| proxyCountryCode | ProxyCountryCode | no | Proxy location |
| startUrl | string | no | Initial URL |

**Response (201):** SessionItemView

**Errors:** 404 (profile not found), 422 (validation), 429 (too many concurrent)

#### GET /sessions/{session_id}

Get detailed session info including tasks and share URL.

**Response (200):** SessionView (see [Response Schemas](#response-schemas))

**Errors:** 404 (not found)

#### PATCH /sessions/{session_id}

Stop a session and all its running tasks.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| action | SessionUpdateAction | **yes** | `stop` |

**Response (200):** SessionView

**Errors:** 404 (not found), 422 (validation)

#### GET /sessions/{session_id}/public-share

Get public share info including URL and view count.

**Response (200):** ShareView (see [Response Schemas](#response-schemas))

**Errors:** 404 (session or share not found)

#### POST /sessions/{session_id}/public-share

Create or return existing public share for a session.

**Response (201):** ShareView

**Errors:** 404 (session not found)

#### DELETE /sessions/{session_id}/public-share

Remove public share.

**Response:** 204 (no content)

**Errors:** 404 (session not found)

---

### Browsers

#### GET /browsers

Get paginated list of browser sessions.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| pageSize | integer | no | Items per page |
| pageNumber | integer | no | Page number |
| filterBy | BrowserSessionStatus | no | Filter by status |

**Response (200):** `{ items: BrowserSessionItemView[], totalItems, pageNumber, pageSize }`

#### POST /browsers

Create a new browser session.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| profileId | uuid | no | Browser profile to use |
| proxyCountryCode | ProxyCountryCode | no | Proxy location |
| timeout | integer | no | Session timeout in minutes |

**Pricing:** $0.05/hour. Billed upfront, unused time refunded on stop. Ceil to nearest minute (minimum 1 minute).

**Session Limits:** Free users: max 15 minutes. Paid subscribers: up to 4 hours.

**Response (201):** BrowserSessionItemView (includes `cdpUrl` and `liveUrl`)

**Errors:** 403 (timeout limit for free users), 404 (profile not found), 422 (validation), 429 (too many concurrent)

#### GET /browsers/{session_id}

Get detailed browser session info.

**Response (200):** BrowserSessionView

**Errors:** 404 (not found)

#### PATCH /browsers/{session_id}

Stop a browser session. Unused time is automatically refunded.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| action | BrowserSessionUpdateAction | **yes** | `stop` |

**Response (200):** BrowserSessionView

**Errors:** 404 (not found), 422 (validation)

---

### Files

#### POST /files/sessions/{session_id}/presigned-url

Generate a presigned URL for uploading files to a session.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| fileName | string | **yes** | Name of the file |
| contentType | UploadFileRequestContentType | **yes** | MIME type |
| sizeBytes | integer | **yes** | File size in bytes |

**Response (200):**

```
{
  url: string,
  method: "POST",
  fields: { [key: string]: string },
  fileName: string,
  expiresIn: integer
}
```

**Errors:** 400 (unsupported content type), 404 (session not found), 500 (failed)

#### POST /files/browsers/{session_id}/presigned-url

Same as above but for browser sessions. Same request/response format.

#### GET /files/tasks/{task_id}/output-files/{file_id}

Get download URL for a task output file.

**Response (200):** `{ id: uuid, fileName: string, downloadUrl: string }`

**Errors:** 404 (task or file not found), 500 (failed)

---

### Profiles

#### GET /profiles

Get paginated list of profiles.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| pageSize | integer | no | Items per page |
| pageNumber | integer | no | Page number |

**Response (200):** `{ items: ProfileView[], totalItems, pageNumber, pageSize }`

#### POST /profiles

Create a new profile. Profiles preserve browser state (cookies, localStorage, passwords) between tasks. Typically one profile per user.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | no | Profile name |

**Response (201):** ProfileView

**Errors:** 402 (subscription required for additional profiles), 422 (validation)

#### GET /profiles/{profile_id}

Get profile details.

**Response (200):** ProfileView

**Errors:** 404 (not found)

#### DELETE /profiles/{profile_id}

Permanently delete a profile.

**Response:** 204 (no content)

**Errors:** 422 (validation)

#### PATCH /profiles/{profile_id}

Update a profile's name.

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | no | New name |

**Response (200):** ProfileView

**Errors:** 404 (not found), 422 (validation)

---

## Enums Reference

| Enum | Values |
|------|--------|
| TaskStatus | `started`, `paused`, `finished`, `stopped` |
| TaskUpdateAction | `stop`, `pause`, `resume`, `stop_task_and_session` |
| SessionStatus | `active`, `stopped` |
| SessionUpdateAction | `stop` |
| BrowserSessionStatus | `active`, `stopped` |
| BrowserSessionUpdateAction | `stop` |
| ProxyCountryCode | `us`, `uk`, `fr`, `it`, `jp`, `au`, `de`, `fi`, `ca`, `in` |
| SupportedLLMs | `browser-use-llm`, `gpt-4.1`, `gpt-4.1-mini`, `o4-mini`, `o3`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-flash-latest`, `gemini-flash-lite-latest`, `claude-sonnet-4-20250514`, `gpt-4o`, `gpt-4o-mini`, `llama-4-maverick-17b-128e-instruct`, `claude-3-7-sonnet-20250219` |
| UploadFileRequestContentType | `image/jpg`, `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `image/svg+xml`, `application/pdf`, `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `text/plain`, `text/csv`, `text/markdown` |

---

## Response Schemas

### TaskItemView

| Field | Type | Required |
|-------|------|----------|
| id | uuid | yes |
| sessionId | uuid | yes |
| llm | string | yes |
| task | string | yes |
| status | TaskStatus | yes |
| startedAt | datetime | yes |
| finishedAt | datetime | no |
| metadata | object | no |
| output | string | no |
| browserUseVersion | string | no |
| isSuccess | boolean | no |

### TaskView

Extends TaskItemView with:

| Field | Type | Required |
|-------|------|----------|
| steps | TaskStepView[] | yes |
| outputFiles | FileView[] | yes |

### TaskStepView

| Field | Type | Required |
|-------|------|----------|
| number | integer | yes |
| memory | string | yes |
| evaluationPreviousGoal | string | yes |
| nextGoal | string | yes |
| url | string | yes |
| screenshotUrl | string | no |
| actions | string[] | yes |

### FileView

| Field | Type | Required |
|-------|------|----------|
| id | uuid | yes |
| fileName | string | yes |

### SessionItemView

| Field | Type | Required |
|-------|------|----------|
| id | uuid | yes |
| status | SessionStatus | yes |
| liveUrl | string | no |
| startedAt | datetime | yes |
| finishedAt | datetime | no |

### SessionView

Extends SessionItemView with:

| Field | Type | Required |
|-------|------|----------|
| tasks | TaskItemView[] | yes |
| publicShareUrl | string | no |

### BrowserSessionItemView

| Field | Type | Required |
|-------|------|----------|
| id | uuid | yes |
| status | BrowserSessionStatus | yes |
| liveUrl | string | no |
| cdpUrl | string | no |
| timeoutAt | datetime | yes |
| startedAt | datetime | yes |
| finishedAt | datetime | no |

### BrowserSessionView

Same fields as BrowserSessionItemView.

### ProfileView

| Field | Type | Required |
|-------|------|----------|
| id | uuid | yes |
| name | string | no |
| lastUsedAt | datetime | no |
| createdAt | datetime | yes |
| updatedAt | datetime | yes |
| cookieDomains | string[] | no |

### ShareView

| Field | Type | Required |
|-------|------|----------|
| shareToken | string | yes |
| shareUrl | string | yes |
| viewCount | integer | yes |
| lastViewedAt | datetime | no |

### AccountView

| Field | Type | Required |
|-------|------|----------|
| name | string | no |
| monthlyCreditsBalanceUsd | number | yes |
| additionalCreditsBalanceUsd | number | yes |
| totalCreditsBalanceUsd | number | yes |
| rateLimit | integer | yes |
| planInfo | PlanInfo | yes |
| projectId | uuid | yes |
