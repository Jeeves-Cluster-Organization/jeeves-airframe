# Gateway API Reference

Base URL: `http://{API_HOST}:{API_PORT}` (default `http://0.0.0.0:8000`)

## Diagnostics

### GET `/health`
Liveness probe. Returns 200 if the gateway process is alive.

```json
{ "status": "healthy", "service": "{service_id}-gateway" }
```

### GET `/ready`
Readiness probe. Returns 200 when all backend services are initialized, 503 otherwise.

```json
{
  "status": "ready",
  "flow_service": "initialized",
  "interrupt_service": "initialized"
}
```

### GET `/`
API root with version and endpoint listing.

### GET `/metrics`
Prometheus metrics endpoint.

---

## Chat API — `/api/v1/chat`

### POST `/api/v1/chat/messages`
Send a message and receive the final response.

**Query:** `user_id` (required, 1-255 chars)

**Body:**
```json
{
  "message": "string (1-10000 chars, required)",
  "session_id": "string (optional)",
  "mode": "string (optional)",
  "repo_path": "string (optional)"
}
```

**Response (200):** `MessageResponse` — contains `request_id`, `session_id`, `status`, `response`, and optional `clarification_question` / `confirmation_message`.

**Errors:** 500, 503 (flow service not configured)

### GET `/api/v1/chat/stream`
Stream flow events via Server-Sent Events.

**Query:** `user_id` (required), `message` (required, 1-10000 chars), `session_id`, `mode`, `repo_path` (all optional)

**Response (200):** `text/event-stream` with events: `flow_started`, `tool_started`, `tool_completed`, `agent_started`, `agent_completed`, `response_ready`, `clarification`, `confirmation`, `error`, etc.

**Errors:** 500, 503

### POST `/api/v1/chat/sessions`
Create a new chat session.

**Query/Body:** `user_id` (required), `title` (optional)

**Response (200):** `SessionResponse` — `session_id`, `user_id`, `title`, `message_count`, `status`, `created_at`.

**Errors:** 400 (missing user_id), 500, 503

### GET `/api/v1/chat/sessions`
List sessions for a user.

**Query:** `user_id` (required), `limit` (1-200, default 50), `offset` (default 0), `include_deleted` (default false)

**Response (200):** `{ "sessions": [...], "total": int }`

**Errors:** 500, 503

### GET `/api/v1/chat/sessions/{session_id}`
Get a specific session.

**Query:** `user_id` (required)

**Response (200):** `SessionResponse`

**Errors:** 404, 500, 503

### GET `/api/v1/chat/sessions/{session_id}/messages`
List messages in a session.

**Query:** `user_id` (required), `limit` (1-500, default 100), `offset` (default 0)

**Response (200):** `{ "messages": [...], "total": int }`

**Errors:** 500, 503

### DELETE `/api/v1/chat/sessions/{session_id}`
Delete a session.

**Query:** `user_id` (required)

**Response:** 204 No Content

**Errors:** 404, 500, 503

---

## Governance API — `/api/v1/governance`

### GET `/api/v1/governance/dashboard`
System health dashboard with tools, agents, memory layers, and config.

**Response (200):** `DashboardResponse` — arrays of tool health, agent info, memory layer status, and runtime config.

**Errors:** 503 (health service not configured)

### GET `/api/v1/governance/health`
Aggregated health summary across all registered tools.

**Response (200):** `HealthSummaryResponse` — `overall_status`, tool counts by health state, per-tool details.

**Errors:** 500, 503

### GET `/api/v1/governance/tools/{tool_name}`
Detailed health for a specific tool.

**Response (200):** `ToolHealthResponse` — call counts, success rate, latency, last error.

**Errors:** 404 (tool not found), 500, 503

---

## Interrupts API — `/api/v1/interrupts`

### GET `/api/v1/interrupts/`
List interrupts for a user.

**Query:** `user_id` (required), `session_id` (optional), `status_filter` (default `pending`), `kind` (optional), `limit` (1-200, default 50)

**Response (200):** `{ "interrupts": [...], "total": int }`

**Errors:** 400 (invalid kind), 503

### GET `/api/v1/interrupts/{interrupt_id}`
Get interrupt details.

**Query:** `user_id` (required)

**Response (200):** `InterruptDetail` — `id`, `kind`, `question`/`message`, `status`, timestamps.

**Errors:** 403 (wrong user), 404, 503

### POST `/api/v1/interrupts/{interrupt_id}/respond`
Respond to a pending interrupt.

**Query:** `user_id` (required)

**Body:**
```json
{
  "text": "string (for clarification, optional)",
  "approved": "boolean (for confirmation, optional)",
  "decision": "approve|reject|modify (for agent_review, optional)",
  "data": "object (extensible, optional)"
}
```

**Response (200):** `{ "success": true, "interrupt": {...}, "request_can_resume": true }`

**Errors:** 400 (missing required field), 403, 404, 409 (not pending), 500, 503

### DELETE `/api/v1/interrupts/{interrupt_id}`
Cancel a pending interrupt.

**Query:** `user_id` (required), `reason` (optional)

**Response:** 204 No Content

**Errors:** 403, 404, 409 (already resolved), 503

---

## Global Behavior

- **CORS:** Configurable origins, all methods/headers allowed, credentials enabled. Wildcard + credentials rejected at startup.
- **Body limit:** 1 MB default (configurable via `MAX_REQUEST_BODY_BYTES`). Returns 413 if exceeded.
- **503 pattern:** All endpoints return 503 if their backing service is not registered in `app.state`.
- **Error responses:** Internal errors return sanitized messages (`"Internal server error"`) — no stack traces leaked.
