"""
AetherSpace Security Hardening: Supabase Database Security Lockdown.
Enables Row Level Security (RLS) on all Django-managed public tables and revokes
table-level and default privileges from PostgREST Data API roles ('anon', 'authenticated').

Architectural Guardrails:
- Does NOT force row-level security (preserves Django ORM table owner bypass).
- Does NOT create permissive RLS policies (such as blanket access policies) for API roles.
- Does NOT modify Supabase Storage ('storage' schema) or system schemas.
- Dynamically discovers all Django-managed tables (models, local M2M, framework tables).
- Idempotent and vendor-safe (executes PostgreSQL DDL only when running on PostgreSQL).
- Provides a conservative reverse migration that avoids granting broad API access.
"""

import re
import logging
from django.db import migrations

logger = logging.getLogger(__name__)

DJANGO_PUBLIC_TABLE_PREFIXES = (
    'accounts_',
    'workspaces_',
    'tasks_',
    'bugs_',
    'chat_',
    'meetings_',
    'calendars_',
    'files_',
    'notifications_',
    'timetracking_',
    'admin_panel_',
    'core_',
    'auth_',
    'django_',
)

EXCLUDED_SCHEMAS_AND_PATTERNS = (
    'storage.',
    'storage_',
    'vault.',
    'realtime.',
    'graphql.',
    'extensions.',
    'pg_',
    'information_schema.',
)


def get_target_public_tables(apps, connection):
    """
    Identifies all Django-managed public tables using Django migration-time metadata,
    app registry introspection, M2M intermediate table resolution, and database catalog inspection.
    Strictly filters to authorized Django application prefixes to protect third-party
    and Supabase-managed schemas (e.g., Supabase Storage).
    """
    target_tables = set()

    # 1. Discover models from the migration-time state apps passed to RunPython
    if apps and hasattr(apps, 'get_models'):
        for model in apps.get_models():
            if not model._meta.abstract and not model._meta.proxy and model._meta.managed:
                target_tables.add(model._meta.db_table)
                for field in getattr(model._meta, 'local_many_to_many', []):
                    target_tables.add(field.m2m_db_table())

    # 2. Discover models from global runtime apps registry (ensures any loaded Django apps are captured)
    try:
        from django.apps import apps as global_apps
        for model in global_apps.get_models():
            if not model._meta.abstract and not model._meta.proxy and model._meta.managed:
                target_tables.add(model._meta.db_table)
                for field in getattr(model._meta, 'local_many_to_many', []):
                    target_tables.add(field.m2m_db_table())
    except Exception:
        pass

    # 3. Add Django core framework tracking and session tables
    target_tables.update([
        'django_migrations',
        'django_content_type',
        'django_session',
        'django_admin_log',
    ])

    # 4. If connected to PostgreSQL, discover any existing public tables with authorized Django prefixes
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE';
            """)
            for (tname,) in cursor.fetchall():
                if any(tname.startswith(prefix) for prefix in DJANGO_PUBLIC_TABLE_PREFIXES):
                    target_tables.add(tname)

    # 5. Filter strictly: must start with an authorized prefix, must NOT match excluded schemas,
    # and must be a valid SQL identifier (lowercase alphanumeric + underscore)
    valid_tables = []
    for tbl in target_tables:
        if not re.match(r'^[a-z0-9_]+$', tbl):
            continue
        if any(tbl.startswith(pat) for pat in EXCLUDED_SCHEMAS_AND_PATTERNS):
            continue
        if any(tbl.startswith(prefix) for prefix in DJANGO_PUBLIC_TABLE_PREFIXES):
            valid_tables.append(tbl)

    return sorted(set(valid_tables))


def enable_rls_and_revoke_api_access(apps, schema_editor):
    """
    Forward operation:
    1. Enables RLS on all Django-managed public tables (without FORCE).
    2. Revokes all privileges from 'anon' and 'authenticated' roles.
    3. Revokes future default table privileges for 'anon' and 'authenticated' in public schema.
    4. Preserves table owner / postgres server-side Django connection privileges.
    """
    if schema_editor.connection.vendor != 'postgresql':
        logger.info("Non-PostgreSQL database detected (%s). Skipping RLS security hardening.", schema_editor.connection.vendor)
        return

    tables = get_target_public_tables(apps, schema_editor.connection)

    with schema_editor.connection.cursor() as cursor:
        for table in tables:
            # Check if table exists in schema 'public'
            cursor.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s;
            """, [table])
            if cursor.fetchone():
                # Step 2: Enable standard RLS (without FORCE)
                cursor.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY;')

                # Step 3: Revoke privileges from anon and authenticated if roles exist
                cursor.execute(f"""
                    DO $$
                    BEGIN
                        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                            REVOKE ALL PRIVILEGES ON TABLE public."{table}" FROM anon;
                        END IF;
                        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                            REVOKE ALL PRIVILEGES ON TABLE public."{table}" FROM authenticated;
                        END IF;
                    END $$;
                """)

        # Revoke default future table privileges in schema public for API roles
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated;
                END IF;
            END $$;
        """)


def disable_rls_and_restore_access(apps, schema_editor):
    """
    Conservative reverse operation:
    1. Disables RLS on Django-managed public tables.
    2. Does NOT blindly grant broad 'ALL' privileges to 'anon' or 'authenticated' roles
       to avoid introducing unintentional security vulnerabilities during rollback.
    """
    if schema_editor.connection.vendor != 'postgresql':
        return

    tables = get_target_public_tables(apps, schema_editor.connection)

    with schema_editor.connection.cursor() as cursor:
        for table in tables:
            cursor.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s;
            """, [table])
            if cursor.fetchone():
                cursor.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_seed_module_statuses'),
    ]

    operations = [
        migrations.RunPython(
            enable_rls_and_revoke_api_access,
            disable_rls_and_restore_access,
        ),
    ]
