# AetherSpace QA Checklist

## Authentication

-   Login success
-   Invalid credentials
-   Logout
-   Password reset
-   Invitation acceptance
-   Verification
-   Session expiry

## RBAC

Test each role against: - workspace access - task creation - task
editing - bug creation - bug editing - member management - workspace
settings - admin pages

Attempt unauthorized direct URLs and POST requests.

## Tasks

-   create
-   edit
-   delete where allowed
-   assign
-   filter
-   search
-   pagination
-   ID uniqueness
-   activity generation

## Bugs

-   raise
-   edit
-   severity
-   environment
-   attachments
-   ID uniqueness
-   activity

## Chat

-   channel creation
-   membership
-   message send
-   DM
-   attachment access
-   permission isolation

## Meetings

-   create
-   join
-   invalid code
-   scheduling
-   participant access

## Calendar

-   event creation
-   linked task
-   linked bug
-   linked meeting
-   date/time correctness

## Files

-   upload
-   validation
-   size limits
-   storage path
-   access control
-   download
-   deletion

## Notifications

-   generation
-   read/unread
-   categories
-   links

## Admin

-   unauthorized users cannot access
-   audit log integrity
-   storage metrics
-   security events
-   alerts
-   settings

## UI

-   light theme
-   dark theme
-   mobile
-   tablet
-   desktop
-   keyboard navigation
-   focus states
-   empty states
-   validation states
-   error states

## Security

-   CSRF
-   XSS
-   authorization bypass
-   file upload abuse
-   secret leakage
-   insecure direct object references
-   SQL injection through raw queries
-   sensitive data in logs

## Performance

Check: - N+1 queries - slow list pages - large file handling -
unnecessary client requests - pagination
