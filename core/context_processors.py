def aetherspace_global_context(request):
    """Provides global branding and runtime context to all templates."""
    return {
        'APP_NAME': 'AetherSpace',
        'APP_TAGLINE': 'Next-Gen Agile Collaboration & Workspace Platform',
        'CURRENT_YEAR': 2026,
    }
