from .models import ModuleStatus


def aetherspace_global_context(request):
    """Provides global branding, runtime context, and module maintenance statuses to all templates."""
    module_statuses = ModuleStatus.get_all_statuses()
    maintenance_modules = [m for m in module_statuses.values() if m.is_under_maintenance]
    return {
        'APP_NAME': 'AetherSpace',
        'APP_TAGLINE': 'Next-Gen Agile Collaboration & Workspace Platform',
        'CURRENT_YEAR': 2026,
        'MODULE_STATUSES': module_statuses,
        'MODULE_STATUSES_LIST': list(module_statuses.values()),
        'ANY_MODULE_UNDER_MAINTENANCE': bool(maintenance_modules),
        'MAINTENANCE_MODULES_COUNT': len(maintenance_modules),
    }


