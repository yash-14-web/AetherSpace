# AetherSpace Error Pages & Global Error Handling

## Visual Source of Truth
Modeled directly after `AetherSpace_Designs/a_high_resolution_dark_ui_graphic_design_showcase.png`.

All error pages:
- Inherit from `templates/errors/base_error.html`
- Support **Obsidian Dark** (`#09090b` / `#18181b`) and **Clean Slate Light** (`#f8fafc` / `#ffffff`) modes
- Feature bespoke glowing vector SVG illustrations and prominent colored status code numbers
- Provide accessible dual-action recovery paths (`[ Primary Action ]` + `[ Secondary / Back ]`)
- Never expose stack traces, Python exceptions, SQL queries, database credentials, or secret keys
- Include safe correlation Error IDs on 500 errors (e.g. `ERR-500-XXXXXXXX`)
- Automatically format AJAX / API error responses (`X-Requested-With: XMLHttpRequest` or `Accept: application/json`) into structured JSON `{ "error": ..., "status_code": ... }` via `AetherSpaceGlobalErrorMiddleware`

---

## Django Configuration

In `aetherspace/urls.py`:
```python
handler400 = 'core.views.error_400'
handler403 = 'core.views.error_403'
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'
```

In `aetherspace/settings.py`:
```python
MIDDLEWARE = [
    ...
    'core.middleware.AetherSpaceGlobalErrorMiddleware',
]
```

---

## Error Catalog

### 400 — Bad Request
- **Title**: `400 — Bad Request`
- **Headline**: `Invalid Request`
- **Accent**: Amber (`#f59e0b`)
- **Graphic**: Terminal window syntax error with parameter wrench
- **Copy**: `The request could not be processed due to invalid parameters. Please verify the query and try again.`
- **Actions**: `[ Go Back ]`, `[ Go to Dashboard ]`

### 401 — Authentication Required
- **Title**: `401 — Authentication Required`
- **Headline**: `Authentication Required`
- **Accent**: Cyan (`#06b6d4`)
- **Graphic**: Security keycard with biometric lock
- **Copy**: `Please sign in with your AetherSpace credentials to access this workspace and its resources.`
- **Actions**: `[ Sign In ]`, `[ Go Back ]`

### 403 — Access Restricted / Permission Denied
- **Title**: `403 — Access Restricted`
- **Headline**: `Access Restricted`
- **Accent**: Violet / Purple (`#8b5cf6` / `#a855f7`)
- **Graphic**: Glowing purple shield with padlock and ambient gems
- **Copy**: `You don't have permission to access this page. Your current role doesn't have the required permission for this workspace or resource.`
- **Actions**:
  - `[ Request Access ]` (renders when legitimate workspace exists and user is authenticated but not a member)
  - `[ Go to Dashboard ]`
  - `[ Go Back ]`
- **Workflow**:
  - Clicking `[ Request Access ]` opens a CSRF-protected modal submitting to `workspaces:request_access`.
  - Creates a `WorkspaceAccessRequest` record with status `PENDING`.
  - Admin approves or rejects via `admin_panel:workspace_requests`.

### 404 — Page Not Found
- **Title**: `404 — Page Not Found`
- **Headline**: `Page Not Found`
- **Accent**: Electric Blue (`#3b82f6`)
- **Graphic**: UFO spacecraft beaming tractor light onto document
- **Copy**: `The page you're looking for doesn't exist or may have been moved.`
- **Actions**: `[ Go to Dashboard ]`, `[ Go Back ]`

### 408 — Request Timed Out
- **Title**: `408 — Request Timed Out`
- **Headline**: `Request Timed Out`
- **Accent**: Orange (`#f97316`)
- **Graphic**: Stopwatch latency dial with timeout threshold mark
- **Copy**: `The request took too long to complete. Network conditions or server latency caused a timeout. Please try again.`
- **Actions**: `[ Try Again ]`, `[ Go to Dashboard ]`

### 429 — Too Many Requests
- **Title**: `429 — Too Many Requests`
- **Headline**: `Too Many Requests`
- **Accent**: Magenta / Pink (`#ec4899`)
- **Graphic**: Tachometer velocity gauge pushed into redline
- **Copy**: `You've made too many requests in a short period. Rate limits protect system stability for your team. Please wait a moment and try again.`
- **Headers**: Includes HTTP `Retry-After: 60`
- **Actions**: `[ Try Again ]`, `[ Go to Dashboard ]`

### 500 — Internal Server Error
- **Title**: `500 — Internal Server Error`
- **Headline**: `Something Went Wrong`
- **Accent**: Crimson Red (`#ef4444`)
- **Graphic**: Damaged sparking robot satellite with loose debris
- **Copy**: `Something went wrong on our end. Our engineering team has been notified. Please try again.`
- **Badge**: `Error ID: ERR-500-XXXXXXXX` (Safe correlation ID)
- **Security**: Strict zero-leakage guarantee. No stack traces, file paths, or env secrets exposed.
- **Actions**: `[ Try Again ]`, `[ Go to Dashboard ]`

### 503 — Service Temporarily Unavailable
- **Title**: `503 — Service Temporarily Unavailable`
- **Headline**: `Service Temporarily Unavailable`
- **Accent**: Amber (`#f59e0b`)
- **Graphic**: Deep space communication satellite radar dish
- **Copy**: `AetherSpace is temporarily unable to process your request. We are working to restore service. Please try again shortly.`
- **Actions**: `[ Try Again ]`, `[ Go to Dashboard ]`

### Network / Connection Failure State
- **Title**: `Connection Lost — AetherSpace`
- **Headline**: `Connection Lost`
- **Accent**: Coral Red (`#f43f5e`)
- **Graphic**: Broken wifi wave beacon with alert badge
- **Copy**: `We couldn't connect to AetherSpace. Check your internet connection and try again.`
- **Actions**: `[ Retry Connection ]`, `[ Go to Dashboard ]`

---

## Real Application Integrations (Phase 17 Correction)

### 1. Authoritative 403 Permission Interception
When an authenticated user attempts an unauthorized action (e.g. Contributor attempting workspace creation at `/workspaces/create/`):
- `AetherSpaceGlobalErrorMiddleware` intercepts plain-text `HttpResponseForbidden` responses on standard browser navigations.
- It transforms them into `core.views.error_403(request, message=reason)` while preserving the exact human-readable message (e.g. *"Permission Denied: Only Administrators and Managers can create workspaces."*).
- Renders the full designed 403 Access Restricted template with the reason prominently badged.

### 2. Vector Empty-State Library (`templates/components/empty_states.html`)
Directly implements the 5 vector graphics from Panel 2 of `a_high_resolution_dark_ui_graphic_design_showcase.png`:
1. `no_tasks`: Holographic clipboard with checkmarks & cyan/blue ambient glow.
2. `no_bugs`: Cybernetic purple ladybug beetle.
3. `no_files`: Glossy 3D indigo folder with documents & cloud badge.
4. `no_notifications`: Emerald green bell with checkmark badge.
5. `no_search_results`: Amber/orange magnifying glass with scanner radar rings.

Distinguishes zero-state conditions:
- **Tasks**: "No Tasks Yet" vs "No Tasks Match Filters" vs "No Tasks Assigned to You" vs "No Tasks Found" (search).
- **Bugs**: "No Bugs Found — All systems green" vs "No Bugs Match Filters" vs "No Bugs Found" (search).
- **Files**: "No Files Yet" vs "Trash is Empty" vs "No Starred Files" vs "No Files Found" (search).
- **Notifications**: "You're All Caught Up!" vs "No Task Alerts" vs "No Bug Alerts" vs "No Notifications Found" (search).
- **Omnibar Search**: Displays amber magnifying glass graphic with query string retained and "[ Clear Search ]" action.

### 3. Global Real Avatar & Initials Fallback (`templates/components/avatar.html`)
- If real profile image URL exists (`https://...`, `/media/avatars/...`, Supabase Storage): renders `<img>` with automatic `onerror` initials fallback.
- If preset gradient exists (`preset:color`): maps to curated gradient pill with user initials.
- If empty: renders clean initials fallback.
- Zero static stock photos; zero external placeholder avatars.

### 4. People Hover Card with Real Tagging Role
- Connects `WorkspaceMembership.role_tag` (e.g. `Frontend`, `Backend`, `DevOps`, `QA`, `Product`) and `WorkspaceMembership.functional_role`.
- Returns `tagging_role` in `/auth/api/user-card/<id>/` and displays a distinct purple badge pill.
- Accessible via keyboard navigation (`tabindex="0"`, `@focus`, `@blur`, `@keydown.escape`).
- Debounced hover timers and invisible hit area bridge eliminate flickering and stay open smoothly during cursor transit.

---

## Component-Level & Micro-Error States

Located in `templates/components/error_states.html`:
1. **Chart Error State**: `Unable to load chart`
2. **Table Error State**: `Unable to load data`
3. **API Inline Error Banner**: `Failed to fetch data`
4. **Widget Error State**: `Failed to load storage info`
5. **Action Error Toast**: `Failed to delete task`
6. **File Upload Errors**: `Upload Failed`, `File Too Large`, `Storage Reached`
7. **Calendar Errors**: `Event Creation Failed`, `Conflicting Event`
8. **Live Network Telemetry**: `templates/components/connection_status.html` provides Alpine.js `online`/`offline` listeners with an auto-updating top banner.
