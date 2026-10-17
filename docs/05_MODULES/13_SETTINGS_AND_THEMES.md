# Module 13: Settings & Theme Engine

## 1. Purpose
Provides user preferences, notification threshold configuration, account security and password management, and seamless theme toggling between **Obsidian Dark** and **Clean Light** modes.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `user_settings/views.py`, `user_settings/forms.py`, `templates/base.html`, `user_settings/tests.py`.

## 3. Main User Workflows
1. **Theme Switching**:
   - User toggles theme via the global rail toggle or settings page.
   - Theme applies instantly to the DOM (`<html class="dark">`) without page reload.
   - Preference persists across sessions in `UserProfile.preferences['theme']` and browser `localStorage`.
2. **Account Security**:
   - User changes password; system enforces Django password validation rules.
   - User inspects active sessions.
3. **Notification Preferences**:
   - User configures email alerts for task assignments, mentions, and meetings.
4. **Timezone Configuration**:
   - User sets local timezone (e.g. `America/New_York`, `Asia/Kolkata`); dates throughout the platform render in their local time.

## 4. Theme System Design Tokens

AetherSpace enforces a strict design system across all pages per `AGENTS.md`:

### Obsidian Dark Mode (Default)
* **Background**: `#09090b` / `#0f172a` (`bg-[#09090b]`, `bg-zinc-950`)
* **Cards & Surfaces**: `#18181b` / `#1e293b` (`bg-zinc-900`, `bg-[#131314]`)
* **Borders**: `#27272a` (`border-zinc-800`, `border-zinc-800/60`)
* **Primary Text**: `#f4f4f5` (`text-zinc-100`, `text-white`)
* **Secondary Text**: `#a1a1aa` (`text-zinc-400`)
* **Brand Accent**: `#2563eb` (`bg-blue-600`, `text-blue-500`)

### Clean Light Mode
* **Background**: `#f8fafc` / `#f4f4f5` (`bg-slate-50`)
* **Cards & Surfaces**: `#ffffff` (`bg-white`)
* **Borders**: `#e2e8f0` (`border-slate-200`)
* **Primary Text**: `#0f172a` (`text-slate-900`)
* **Secondary Text**: `#64748b` (`text-slate-500`)
* **Brand Accent**: `#2563eb` (`bg-blue-600`)

## 5. Pages & Templates
* `templates/user_settings/settings_general.html`: Profile details, timezone, and language.
* `templates/user_settings/settings_appearance.html`: Theme selection and layout density.
* `templates/user_settings/settings_notifications.html`: Email and in-app alert thresholds.
* `templates/user_settings/settings_security.html`: Password change and session termination.

## 6. URLs, Views, Services & Models
* **URLs**: `user_settings/urls.py` (`settings_general`, `settings_appearance`, `settings_notifications`, `settings_security`).
* **Views**: `user_settings/views.py` (`settings_general_view`, `settings_appearance_view`, `settings_security_view`).
* **Forms**: `user_settings/forms.py` (`GeneralSettingsForm`, `AppearanceSettingsForm`, `PasswordChangeCustomForm`).
* **Models**: `accounts.User`, `accounts.UserProfile`.

## 7. Business Rules & Invariants
* Theme Persistence: Stored in `UserProfile.preferences['theme']` ('dark' | 'light') and cached locally to prevent white flashes upon page load.
* Password Security: Password updates invalidate other sessions and require current password verification.

## 8. Database Relationships
* Operates on `accounts.User` and `accounts.UserProfile`.

## 9. API & WebSocket Interactions
* `POST /settings/appearance/`: Saves theme preference asynchronously.

## 10. Notifications & Integrations
* Dispatches `PASSWORD_RESET` or security alert email upon credential modification.

## 11. Error States & Edge Cases
* Submitting mismatched passwords -> `ValidationError: "New passwords do not match."`
* Invalid timezone string -> Reverts to `UTC`.

## 12. Tests & Verification Evidence
* `user_settings/tests.py`: Unit tests for theme saving, preference serialization, and password modification.

## 13. Known Limitations
* System auto-detection (matching OS `prefers-color-scheme`) is secondary to explicit user preference stored in profile.

## 14. Future Work
* High-contrast accessibility theme preset.
