import uuid
from django.db import migrations, models
import django.db.models.deletion


def seed_default_workspace_modules(apps, schema_editor):
    Workspace = apps.get_model('workspaces', 'Workspace')
    WorkspaceModule = apps.get_model('workspaces', 'WorkspaceModule')

    default_modules = [
        ("Authentication", "User authentication, sessions, and access control"),
        ("Dashboard", "Workspace and master overview metrics"),
        ("Tasks", "Task management, kanban board, and backlog"),
        ("Bug Tracking", "Defect logging, severity triage, and bug lifecycle"),
        ("Files", "Document vault and cloud file storage"),
        ("Meetings", "Audio/video rooms and meeting scheduling"),
        ("Chat", "Direct messaging and workspace channels"),
        ("UI/UX", "User interface components, themes, and accessibility"),
        ("Settings", "Workspace configuration and member roles"),
        ("Other", "General miscellaneous defect tracking"),
    ]

    for workspace in Workspace.objects.all():
        for name, desc in default_modules:
            WorkspaceModule.objects.get_or_create(
                workspace=workspace,
                name=name,
                defaults={'description': desc, 'is_active': True}
            )


def reverse_seed_default_workspace_modules(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('workspaces', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkspaceModule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='modules', to='workspaces.workspace')),
            ],
            options={
                'verbose_name': 'Workspace Module',
                'verbose_name_plural': 'Workspace Modules',
                'ordering': ['name'],
            },
        ),
        migrations.AddConstraint(
            model_name='workspacemodule',
            constraint=models.UniqueConstraint(fields=('workspace', 'name'), name='unique_workspace_module_name'),
        ),
        migrations.RunPython(seed_default_workspace_modules, reverse_seed_default_workspace_modules),
    ]
