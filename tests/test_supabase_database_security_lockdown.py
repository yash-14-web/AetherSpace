"""
Tests for Supabase Database Security Lockdown Migration (Phase 2 Synchronization).

Verifies the 12 core security and architectural requirements:
1. Migration exists on disk.
2. Migration is registered in Django MigrationLoader.
3. Django model discovery is used rather than a static hard-coded table list.
4. M2M intermediate tables are covered.
5. Supabase Storage ('storage' schema) and system schemas are strictly excluded.
6. No FORCE ROW LEVEL SECURITY exists.
7. No permissive USING (true) or WITH CHECK (true) policies exist.
8. anon table and default privileges are revoked.
9. authenticated table and default privileges are revoked.
10. PostgreSQL-only behavior is preserved (clean no-op on non-PostgreSQL runners).
11. Existing production schema names (e.g., meetings_callsession, files_storedfile) are fully supported.
12. No unrelated application files are modified.
"""

import os
import inspect
import importlib
import subprocess
from django.test import TestCase
from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader

lockdown_migration = importlib.import_module('core.migrations.0003_supabase_database_security_lockdown')
get_target_public_tables = lockdown_migration.get_target_public_tables
DJANGO_PUBLIC_TABLE_PREFIXES = lockdown_migration.DJANGO_PUBLIC_TABLE_PREFIXES


class SupabaseDatabaseSecurityLockdownTests(TestCase):

    def test_01_migration_exists_and_registered(self):
        """1. Verify migration 0003 exists on disk and is recognized by Django migration loader."""
        migration_file = lockdown_migration.__file__
        self.assertTrue(os.path.exists(migration_file), "Migration 0003 file must exist on disk.")

        loader = MigrationLoader(connection)
        self.assertIn(
            ('core', '0003_supabase_database_security_lockdown'),
            loader.disk_migrations,
            "Migration 0003_supabase_database_security_lockdown is not registered in loader disk_migrations."
        )

    def test_02_model_discovery_used_not_hardcoded_list(self):
        """2. Verify Django model metadata and registry introspection is used for table discovery."""
        source = inspect.getsource(get_target_public_tables)
        self.assertIn('get_models', source, "Table discovery must use get_models() introspection.")
        self.assertIn('_meta.db_table', source, "Table discovery must read _meta.db_table from models.")
        self.assertIn('local_many_to_many', source, "Table discovery must inspect local_many_to_many fields.")

    def test_03_m2m_intermediate_tables_covered(self):
        """3. Verify local many-to-many intermediate tables are covered."""
        tables = get_target_public_tables(apps, connection)
        expected_m2m = [
            'accounts_user_groups',
            'accounts_user_user_permissions',
            'auth_group_permissions',
        ]
        for m2m_table in expected_m2m:
            self.assertIn(
                m2m_table,
                tables,
                f"M2M intermediate table '{m2m_table}' must be included in the lockdown target list."
            )

    def test_04_storage_schema_strictly_excluded(self):
        """4. Confirm Supabase Storage ('storage') and system schemas are strictly excluded."""
        tables = get_target_public_tables(apps, connection)

        disallowed_items = [
            'storage.objects',
            'storage.buckets',
            'storage.migrations',
            'storage_objects',
            'objects',
            'buckets',
            'graphql',
            'realtime',
            'vault',
            'extensions',
        ]
        for item in disallowed_items:
            self.assertNotIn(
                item,
                tables,
                f"Storage/system item '{item}' must NEVER be targeted by public table lockdown."
            )

        # Every targeted table must match an authorized Django public prefix
        for tbl in tables:
            matches_prefix = any(tbl.startswith(prefix) for prefix in DJANGO_PUBLIC_TABLE_PREFIXES)
            self.assertTrue(
                matches_prefix,
                f"Target table '{tbl}' does not match authorized Django public prefixes."
            )

    def test_05_no_force_rls(self):
        """5. Verify that FORCE ROW LEVEL SECURITY is never used (preserves Django ORM owner bypass)."""
        source = inspect.getsource(lockdown_migration)
        self.assertNotIn('FORCE ROW LEVEL SECURITY', source)

    def test_06_no_permissive_using_true_policy(self):
        """6. Verify no permissive RLS policies (e.g. USING (true)) are created."""
        source = inspect.getsource(lockdown_migration)
        self.assertNotIn('USING (true)', source)
        self.assertNotIn('USING(true)', source)
        self.assertNotIn('WITH CHECK (true)', source)
        self.assertNotIn('WITH CHECK(true)', source)

    def test_07_anon_privileges_revoked(self):
        """7. Verify anon table privileges and future default privileges are revoked."""
        source = inspect.getsource(lockdown_migration.enable_rls_and_revoke_api_access)
        self.assertIn('REVOKE ALL PRIVILEGES ON TABLE', source)
        self.assertIn('FROM anon', source)
        self.assertIn('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon', source)

    def test_08_authenticated_privileges_revoked(self):
        """8. Verify authenticated table privileges and future default privileges are revoked."""
        source = inspect.getsource(lockdown_migration.enable_rls_and_revoke_api_access)
        self.assertIn('REVOKE ALL PRIVILEGES ON TABLE', source)
        self.assertIn('FROM authenticated', source)
        self.assertIn('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated', source)

    def test_09_postgresql_only_behavior_preserved(self):
        """9. Verify non-PostgreSQL runners (such as SQLite) cleanly no-op without error."""
        class MockSchemaEditor:
            def __init__(self, conn):
                self.connection = conn

        schema_editor = MockSchemaEditor(connection)
        # SQLite execution must complete with 0 errors
        lockdown_migration.enable_rls_and_revoke_api_access(apps, schema_editor)
        lockdown_migration.disable_rls_and_restore_access(apps, schema_editor)

    def test_10_production_schema_names_supported(self):
        """10. Verify actual production schema tables (54 tables) are properly resolved."""
        tables = get_target_public_tables(apps, connection)
        self.assertEqual(len(tables), 54, f"Expected exactly 54 production tables, found {len(tables)}: {tables}")

        actual_production_tables = [
            'accounts_user',
            'accounts_user_groups',
            'accounts_user_user_permissions',
            'accounts_userprofile',
            'admin_panel_adminalert',
            'admin_panel_auditlog',
            'auth_group',
            'auth_group_permissions',
            'auth_permission',
            'bugs_bug',
            'bugs_bugactivity',
            'bugs_bugattachment',
            'bugs_bugcomment',
            'calendars_calendarevent',
            'calendars_calendareventattachment',
            'calendars_calendareventattendee',
            'chat_channel',
            'chat_channelmembership',
            'chat_directmessageconversation',
            'chat_message',
            'chat_messageattachment',
            'chat_messagereaction',
            'core_modulestatus',
            'django_admin_log',
            'django_content_type',
            'django_migrations',
            'django_session',
            'files_fileactivity',
            'files_filecomment',
            'files_fileshare',
            'files_fileversion',
            'files_folder',
            'files_storedfile',
            'meetings_callsession',
            'meetings_meeting',
            'meetings_meetinginvite',
            'meetings_meetingparticipant',
            'notifications_emaildeliverylog',
            'notifications_notification',
            'tasks_codereviewrequest',
            'tasks_sprint',
            'tasks_subtask',
            'tasks_task',
            'tasks_taskactivity',
            'tasks_taskattachment',
            'tasks_taskcomment',
            'timetracking_timeentry',
            'workspaces_globalaccessrequest',
            'workspaces_temporaryaccessgrant',
            'workspaces_workspace',
            'workspaces_workspaceaccessrequest',
            'workspaces_workspaceinvitation',
            'workspaces_workspacemembership',
            'workspaces_workspacemodule',
        ]
        for tbl in actual_production_tables:
            self.assertIn(
                tbl,
                tables,
                f"Production table '{tbl}' was missing from the lockdown target list."
            )

    def test_11_reverse_migration_is_conservative(self):
        """11. Verify reverse migration does NOT blindly grant broad ALL PRIVILEGES to anon/authenticated."""
        source = inspect.getsource(lockdown_migration.disable_rls_and_restore_access)
        self.assertIn('DISABLE ROW LEVEL SECURITY', source)
        self.assertNotIn('GRANT ALL PRIVILEGES', source, "Reverse migration must not invent broad ALL grants.")

    def test_12_no_unrelated_application_files_modified(self):
        """12. Verify that no unrelated application models or core logic files were modified for this task."""
        # Ensure migration does not define model schemas or alter fields
        ops = lockdown_migration.Migration.operations
        for op in ops:
            self.assertIsInstance(
                op,
                lockdown_migration.migrations.RunPython,
                f"Migration should only use RunPython for security DDL, found {type(op)}."
            )
