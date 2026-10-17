# AetherSpace HTTP Endpoints & WebSocket Reference

This document enumerates the HTTP endpoints and real-time WebSocket channels active in the AetherSpace codebase.

---

## 1. WebSocket Routes & Channel Consumers

Real-time communication in AetherSpace is orchestrated via Daphne ASGI and Django Channels 4.

```
URLRouter Configuration (aetherspace/asgi.py):
chat.routing.websocket_urlpatterns + meetings.routing.websocket_urlpatterns
```

### 1.1 `GlobalCallConsumer`
* **Route**: `ws/calls/global/`
* **Auth Requirement**: Authenticated user session (`AuthMiddlewareStack`).
* **Purpose**: Universal real-time incoming call signaling, ringing modal dispatch, and call state transitions across *any* active page of the platform.
* **Channel Group**: `user_calls_<uuid:user_id>`
* **Handled Client Actions**:
  | Action | Payload Fields | Description | Server Response / Broadcast |
  |---|---|---|---|
  | `initiate` | `recipient_id`, `call_mode` ('AUDIO'/'VIDEO'), `workspace_slug` | Starts a 1-on-1 call session. | Emits `call_outgoing` to caller, `call_incoming` to recipient. |
  | `accept` | `call_id` | Recipient accepts ringing call. | Updates DB status to `ACCEPTED`; broadcasts `call_accepted` with `room_url`. |
  | `decline` | `call_id` | Recipient declines ringing call. | Updates DB status to `DECLINED`; broadcasts `call_declined` to caller. |
  | `cancel` | `call_id` | Caller cancels unanswered call. | Updates DB status to `CANCELLED`; broadcasts `call_cancelled` to callee. |
  | `timeout` | `call_id` | Ringing expires without answer. | Updates DB status to `MISSED`; broadcasts `call_missed` to both peers. |
  | `connected`| `call_id` | Both peers entered meeting room. | Updates DB status to `CONNECTED`. |
  | `end` | `call_id` | Either peer hangs up call. | Updates DB status to `ENDED`; broadcasts `call_ended`. |
* **Server Broadcast Events**:
  - `call_incoming`: Triggers synthesized Web Audio ringtone and incoming call modal on callee's browser.
  - `call_accepted`: Closes ringing modal and redirects both browsers to `/meetings/w/<slug>/room/<code/>`.
  - `call_declined` / `call_cancelled` / `call_missed`: Plays busy tone and dismisses modals.
  - `call_error`: Shows warning notice on outgoing modal for 3.0s prior to dismissal.

### 1.2 `ChatConsumer`
* **Routes**:
  - `ws/chat/c/<uuid:channel_id>/` (Channel messages)
  - `ws/chat/dm/<uuid:conversation_id>/` (1-on-1 Direct messages)
* **Auth Requirement**: Authenticated workspace member with access to the channel/conversation.
* **Purpose**: Real-time team chat message exchange, typing indicators, and emoji reaction synchronization.
* **Channel Group**: `chat_<uuid:channel_id>` or `dm_<uuid:conversation_id>`
* **Handled Client Events**:
  - `chat_message`: Persists `Message` record and broadcasts to group.
  - `typing_indicator`: Relays ephemeral typing banner (`"Alex Chen is typing..."`).
  - `reaction_add` / `reaction_remove`: Toggles `MessageReaction` and updates counts.

### 1.3 `MeetingSignalingConsumer`
* **Route**: `ws/meetings/<slug>/<meeting_code>/`
* **Auth Requirement**: Authenticated workspace member.
* **Purpose**: Attendance tracking, hand-raising events, and meeting termination signals.

---

## 2. Key HTTP API & Asynchronous View Endpoints

AetherSpace utilizes server-side rendered Django views with targeted JSON API endpoints for dynamic interactions:

### 2.1 Workspace Endpoints (`workspaces/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/workspaces/dashboard/` | GET | Master Dashboard (cross-workspace) | Authenticated | 200, 302 |
| `/workspaces/w/<slug>/` | GET | Workspace Tactical Dashboard | `@workspace_member_required` | 200, 403, 404 |
| `/workspaces/w/<slug>/team/` | GET | Workspace Team Directory | `@workspace_member_required` | 200, 403 |
| `/workspaces/w/<slug>/settings/` | GET, POST | Workspace Settings & Quotas | Workspace Admin Only | 200, 302, 403 |
| `/workspaces/w/<slug>/invite/` | POST | Send Member Email Invitation | Workspace Admin Only | 302, 400, 403 |
| `/workspaces/w/<slug>/api/request-access/` | POST | Submit Access Request | Authenticated User | 200, 400 |

### 2.2 Task Endpoints (`tasks/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/tasks/w/<slug>/` | GET | Sprint Kanban & Backlog | `@workspace_member_required` | 200, 403 |
| `/tasks/w/<slug>/<task_code>/` | GET | Task Cockpit & Subtasks | `@workspace_member_required` | 200, 404 |
| `/tasks/w/<slug>/create/` | GET, POST | Create 6-Digit Task (`######`) | `@workspace_member_required` | 200, 302, 400 |
| `/tasks/w/<slug>/<task_code>/status/` | POST | Transition Status (Kanban API) | `@workspace_member_required` | 200, 400, 403 |
| `/tasks/w/<slug>/<task_code>/subtask/toggle/`| POST | Toggle Subtask Completion | `@workspace_member_required` | 200, 400 |
| `/tasks/w/<slug>/<task_code>/review/` | POST | Submit PR Code Review (`CR-######`)| `@workspace_member_required` | 200, 302 |

### 2.3 Bug Endpoints (`bugs/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/bugs/w/<slug>/` | GET | Defect Triage Register | `@workspace_member_required` | 200, 403 |
| `/bugs/w/<slug>/<bug_code>/` | GET | Defect Details & Repro Steps | `@workspace_member_required` | 200, 404 |
| `/bugs/w/<slug>/create/` | GET, POST | Raise Defect (`B-######`) | `@workspace_member_required` | 200, 302, 400 |
| `/bugs/w/<slug>/<bug_code>/status/` | POST | Transition Bug Status | `@workspace_member_required` | 200, 400 |

### 2.4 Meet Hub Endpoints (`meetings/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/meetings/w/<slug>/` | GET | Meet Hub Standup Dashboard | `@workspace_member_required` + Gated | 200, 503 |
| `/meetings/w/<slug>/room/<code/>` | GET | Jitsi Media Room | `@workspace_member_required` + Gated | 200, 403, 503 |
| `/meetings/w/<slug>/call/initiate/` | POST | Initiate 1-on-1 Call Session | `@workspace_member_required` + Gated | 200, 400 |
| `/meetings/w/<slug>/call/chat-call/`| POST | In-Chat Call Form Handler | `@workspace_member_required` + Gated | 302, 400 |
| `/meetings/w/<slug>/api/<code/>/end/` | POST | Host End Meeting for All | Host / Lead Admin Only | 200, 403 |
| `/meetings/w/<slug>/api/<code/>/ping/`| POST | Participant Presence Heartbeat| Room Participant Only | 200, 400 |

### 2.5 File Storage Endpoints (`files/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/files/w/<slug>/` | GET | Folder & File Directory | `@workspace_member_required` | 200, 403 |
| `/files/w/<slug>/upload/` | POST | Upload File to Supabase | `@workspace_member_required` | 302, 400 |
| `/files/w/<slug>/file/<id>/download/`| GET | Authenticated File Stream | `@workspace_member_required` | 200, 403, 404 |
| `/files/w/<slug>/file/<id>/preview/` | GET | In-Browser Document Preview | `@workspace_member_required` | 200, 403, 404 |

### 2.6 Time Tracking Endpoints (`timetracking/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/timetracking/w/<slug>/` | GET | Time Tracking Dashboard | `@workspace_member_required` | 200, 403 |
| `/timetracking/w/<slug>/timer/start/` | POST | Start Running Stopwatch | `@workspace_member_required` | 200, 400 |
| `/timetracking/w/<slug>/timer/pause/` | POST | Pause Active Stopwatch | Entry Owner Only | 200, 400 |
| `/timetracking/w/<slug>/timer/resume/`| POST | Resume Paused Stopwatch | Entry Owner Only | 200, 400 |
| `/timetracking/w/<slug>/timer/stop/` | POST | Finalize Labor Entry | Entry Owner Only | 200, 400 |

### 2.7 Administration Endpoints (`admin_panel/urls.py`)
| Endpoint | Method | Purpose | Auth & RBAC | Status Codes |
|---|:---:|---|---|:---:|
| `/admin-panel/` | GET | Admin Governance Cockpit | Platform Admin Only | 200, 403 |
| `/admin-panel/approvals/` | GET | User Registration Queue | Platform Admin Only | 200, 403 |
| `/admin-panel/approvals/<id>/decide/` | POST | Approve / Reject User | Platform Admin Only | 200, 400, 403 |
| `/admin-panel/modules/` | GET, POST | Feature Gate Toggles | Platform Admin Only | 200, 302, 403 |
| `/admin-panel/backups/export/` | POST | Full JSON/CSV DB Backup | Platform Admin Only | 200, 403 |
