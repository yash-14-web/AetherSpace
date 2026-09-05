# AetherSpace Error Pages

Configure Django handlers:

``` python
handler400 = "core.views.error_400"
handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"
```

## 400

Title: `Bad Request`

Message:
`Invalid Request — The request could not be processed due to invalid parameters.`

Actions: - Go Back - Return to Dashboard

## 403

Title: `Permission Denied`

Message:
`Access Restricted — You do not have the required permissions to view this workspace or resource.`

Action: - Request Access

## 404

Title: `Page Not Found`

Message:
`Page Not Found — The task, bug, or workspace you are looking for does not exist or has been moved.`

Actions: - Return to Dashboard - Go Back

## 500

Title: `Internal Server Error`

Message:
`Internal Server Error — Something went wrong on our end. Our engineering team has been notified.`

Actions: - Reload Page - Return to Dashboard

## Requirements

All error pages: - use the AetherSpace base design - support dark/light
mode - remain usable when the failing request occurs - do not expose
stack traces in production - provide useful navigation
