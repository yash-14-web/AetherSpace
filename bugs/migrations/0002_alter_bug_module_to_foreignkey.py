from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_bug_modules(apps, schema_editor):
    Bug = apps.get_model('bugs', 'Bug')
    WorkspaceModule = apps.get_model('workspaces', 'WorkspaceModule')

    for bug in Bug.objects.all():
        old_module_name = getattr(bug, 'module', None)
        if not old_module_name:
            continue

        mod = WorkspaceModule.objects.filter(
            workspace_id=bug.workspace_id,
            name__iexact=str(old_module_name).strip()
        ).first()

        if not mod:
            mod, _ = WorkspaceModule.objects.get_or_create(
                workspace_id=bug.workspace_id,
                name=str(old_module_name).strip() or 'Other',
                defaults={'is_active': True, 'description': 'Migrated defect module'}
            )

        bug.module_ref = mod
        bug.save(update_fields=['module_ref'])


def reverse_migrate_existing_bug_modules(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bugs', '0001_initial'),
        ('workspaces', '0002_workspacemodule'),
    ]

    operations = [
        migrations.AddField(
            model_name='bug',
            name='module_ref',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bugs',
                to='workspaces.workspacemodule',
            ),
        ),
        migrations.RunPython(migrate_existing_bug_modules, reverse_migrate_existing_bug_modules),
        migrations.RemoveField(
            model_name='bug',
            name='module',
        ),
        migrations.RenameField(
            model_name='bug',
            old_name='module_ref',
            new_name='module',
        ),
        migrations.AddIndex(
            model_name='bug',
            index=models.Index(fields=['workspace', 'module'], name='bugs_bug_workspa_mod_idx'),
        ),
    ]
