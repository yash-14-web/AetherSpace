# AetherSpace UI/UX Design System

## Design Direction

Minimalist, professional, modern SaaS interface.

The interface must not feel like a generic Bootstrap admin panel.

Use: - generous whitespace - rounded cards - subtle borders - clear
hierarchy - restrained blue accent - readable typography - consistent
iconography - responsive layouts

## Layout

Desktop: - Global icon rail on far left - Workspace tree beside the
rail - Universal header - Main content canvas

Application pages should favor stacked horizontal sections over cramped
multi-column layouts.

## Dark Theme

Background: - `#09090b` - `#0f172a`

Surface: - `#18181b` - `#1e293b`

Border: - zinc/slate dark borders

Text: - Primary `#f4f4f5` - Secondary `#a1a1aa`

Accent: - Blue `#2563eb` - Optional success green

## Light Theme

Background: - `#f8fafc` - `#f4f4f5`

Surface: - `#ffffff`

Border: - `#e2e8f0`

Text: - Primary `#0f172a` - Secondary `#64748b`

## Components

Create reusable components for:

-   Sidebar
-   Workspace tree
-   Header
-   Breadcrumbs
-   Page header
-   Cards
-   Stat cards
-   Tables
-   Tabs
-   Badges
-   Status pills
-   Buttons
-   Dropdowns
-   Modal
-   Drawer
-   Toast
-   Form controls
-   Empty states
-   Error states
-   Pagination
-   File cards
-   Activity timeline
-   Avatar/group avatar
-   Search/filter bar

## Status Semantics

Task priority: - Low - Medium - High - Urgent

Bug severity: - Low - Medium - High - Critical

Do not communicate status only through color. Include text/icon.

## Accessibility

-   Keyboard navigable controls
-   Visible focus states
-   Proper labels
-   Sufficient contrast
-   Semantic HTML
-   `aria-*` only where appropriate
-   Buttons must look and behave like buttons
-   Do not make entire cards clickable without accessible semantics

## Responsive Behavior

Mobile: - Collapse global rail - Workspace navigation becomes a drawer -
Tables become responsive cards or horizontal scroll - Forms become
single column - Avoid horizontal overflow - Keep primary actions easy to
reach

## Theme Persistence

Store theme preference client-side, preferably localStorage, while
allowing a system default.

Avoid flash of incorrect theme on page load where practical.
