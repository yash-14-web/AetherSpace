# AetherSpace Release & Verification Policy

## 1. Core Principle

**No sensitive, real-time, or mission-critical feature in AetherSpace may be released to general workspace contributors based solely on automated unit tests or UI mockups.**

Passing automated unit tests proves that database models, view dispatchers, and state transitions function in isolation under simulated request environments. However, automated tests **do not prove** that physical hardware interfaces (microphones, cameras, speakers), browser network policies, cross-device acoustic behavior, or third-party cloud engines operate correctly in the real world.

---

## 2. Release Status Taxonomy

Every feature, module, and subsystem in AetherSpace must be assigned one of the following authoritative statuses:

| Status | Definition | Criteria for Assignment |
|---|---|---|
| **Implemented** | Source code exists in the repository. | Implementation located in models, views, templates, or services. |
| **Implemented and Tested** | Source code and automated test coverage exist. | `python manage.py test <app>` passes 100% with dedicated test assertions. |
| **Manually Verified** | Real-world interactive verification has succeeded. | Formally documented test results conducted across two distinct physical devices or user sessions. |
| **Partially Implemented** | Foundational logic exists; key edge cases or sub-features remain unbuilt. | Code exists but specific workflows are stubbed or incomplete. |
| **Planned** | Proposed or architected in blueprints, but unwritten. | Documented in specs or issues; no source code exists. |
| **Gated / Coming Soon** | Intentionally restricted to administrators or disabled for all users. | Guarded server-side by `ModuleStatus` (`STATUS_COMING_SOON` or `STATUS_MAINTENANCE`). |
| **Unverified** | Implementation exists, but required manual or hardware verification is pending. | Code complete, but real-time or third-party behavior unconfirmed in production. |
| **Deprecated** | Intentionally superseded or disabled. | Documented rationale; superseded by hardened implementation. |

---

## 3. The Feature Gating Mechanism (`ModuleStatus`)

### Enforcement Protocol
1. **Server-Side Enforcement**: Gating is strictly enforced in Python view logic (e.g. `check_meetings_maintenance(request, slug)`). Attempting to navigate directly to a gated module URL or API endpoint returns a `503 Service Unavailable` maintenance page or redirects safely.
2. **UI Navigation Transparency**: Global navigation rails, workspace trees, and action buttons dynamically render maintenance or "Coming Soon" badges based on `ModuleStatus.objects.all()`.
3. **Admin Exemption**: Platform Administrators (`User.role == 'ADMIN'` or `User.is_superuser`) may access gated modules for testing and configuration purposes without exposing the feature to contributors.

---

## 4. Meet Hub Release Acceptance Criteria

Meet Hub is currently classified as **`Gated / Coming Soon`** and **`Implemented and Tested (Backend)`**. It may **NOT** be released to workspace contributors until the following criteria are fulfilled:

1. **Automated Backend Suite**: Historical audit reported 57/57 tests passing in `meetings` and `tests.test_meeting_webrtc_signaling` (Status: **REPORT-REPORTED PASSING**). Note: automated unit tests validate backend state machines and signaling; they do not prove physical audio/video functionality across physical hardware.
2. **System Check**: `python manage.py check` reports 0 issues (Status: **PASSING**).
3. **Owner Manual Two-User Verification**:
   - [ ] Successful bidirectional voice transmission between two distinct physical devices.
   - [ ] Successful bidirectional video transmission between two distinct physical devices.
   - [ ] Screen sharing verified with display-capture permissions.
   - [ ] Cross-page incoming call modal and synthesized ringtone verified across two active user sessions.
   - [ ] Accept and Decline actions verified between two live users.
   - [ ] Absence of acoustic feedback loops when testers use separate rooms or headphones.
4. **Third-Party Conference Provider Activation**:
   - [ ] JaaS (8x8 Jitsi as a Service) RS256 JWT signing activated, OR self-hosted Docker Jitsi Meet configured, eliminating the 8x8 5-minute timeout and moderator login prompts.
5. **Phase 19 Launch Readiness Sign-Off**:
   - [ ] Formal sign-off in the documentation audit register by the project owner.

---

## 5. Prohibition on Unauthorized Release

No developer, automated script, or AI coding assistant may:
- Set `ModuleStatus` for Meet Hub to `AVAILABLE` without explicit authorization.
- Remove `@workspace_member_required` or `check_meetings_maintenance` guards.
- Bypass authentication or RBAC to make pages viewable to unauthorized users.
- Claim that an unverified feature is production-ready.
