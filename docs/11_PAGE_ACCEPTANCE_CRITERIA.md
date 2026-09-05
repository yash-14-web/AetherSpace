# AetherSpace Page Acceptance Criteria

Every page must satisfy these baseline requirements.

## Global

-   AetherSpace branding
-   global navigation
-   workspace context where relevant
-   responsive layout
-   light/dark theme
-   consistent typography
-   accessible controls
-   breadcrumbs where useful
-   loading/empty/error states

## Dashboard Pages

Must show real database-backed information.

Never use permanent hard-coded fake metrics.

## List Pages

Must include: - search where useful - filters where useful -
pagination - empty state - permission handling

## Detail Pages

Must include: - object identity - metadata - primary action -
activity/history where relevant - related content - permission-aware
actions

## Form Pages

Must include: - labels - validation - helpful errors - CSRF - success
feedback - cancel/back navigation

## File Pages

Must include: - upload validation - file metadata - access control -
clear upload progress where practical

## Admin Pages

Must use real application data or clearly state when a metric is not
configured.

## Error Pages

Must not expose implementation details in production.
