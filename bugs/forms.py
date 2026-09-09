from django import forms
from django.contrib.auth import get_user_model
from workspaces.models import WorkspaceMembership, MembershipStatus, WorkspaceModule
from tasks.models import Task
from .models import (
    Bug, BugStatus, BugPriority, BugSeverity, BugEnvironment
)

User = get_user_model()


class BugForm(forms.ModelForm):
    class Meta:
        model = Bug
        fields = [
            'title',
            'module',
            'linked_task',
            'priority',
            'severity',
            'environment',
            'browser_device',
            'status',
            'assignee',
            'reporter',
            'sprint',
            'due_date',
            'description',
            'steps_to_reproduce',
            'expected_result',
            'actual_result',
            'labels',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'Enter bug title e.g. Login issue on staging...',
                'required': True,
            }),
            'module': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'linked_task': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'severity': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'environment': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'browser_device': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'e.g. Chrome 124 / Windows 11',
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'assignee': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'reporter': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'sprint': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'e.g. Sprint 01',
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'Detailed explanation of the defect and symptoms...',
            }),
            'steps_to_reproduce': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': "1. Navigate to...\n2. Click on...\n3. Observe error...",
            }),
            'expected_result': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'What should have happened...',
            }),
            'actual_result': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'What actually occurred (e.g. 500 Internal Server Error)...',
            }),
            'labels': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs sm:text-sm rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'e.g. login, authentication, backend',
            }),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        self.fields['module'].required = False
        self.fields['linked_task'].required = False
        self.fields['assignee'].required = False
        self.fields['reporter'].required = False
        self.fields['due_date'].required = False
        self.fields['description'].required = False
        self.fields['steps_to_reproduce'].required = False
        self.fields['expected_result'].required = False
        self.fields['actual_result'].required = False
        self.fields['browser_device'].required = False
        self.fields['labels'].required = False

        if workspace:
            # Filter modules strictly to this workspace
            self.fields['module'].queryset = WorkspaceModule.objects.filter(
                workspace=workspace,
                is_active=True
            ).order_by('name')
            self.fields['module'].empty_label = "Select Module (Optional)"

            # Filter tasks strictly to this workspace
            tasks_qs = Task.objects.filter(workspace=workspace).order_by('-created_at')
            self.fields['linked_task'].queryset = tasks_qs
            self.fields['linked_task'].label_from_instance = lambda obj: f"#{obj.task_code} - {obj.title}"
            self.fields['linked_task'].empty_label = "No Linked Task (Optional)"

            # Filter assignees and reporters strictly to active workspace members
            active_user_ids = WorkspaceMembership.objects.filter(
                workspace=workspace,
                status=MembershipStatus.ACTIVE
            ).values_list('user_id', flat=True)
            active_users = User.objects.filter(id__in=active_user_ids)
            self.fields['assignee'].queryset = active_users
            self.fields['assignee'].empty_label = "Unassigned"
            self.fields['reporter'].queryset = active_users
            self.fields['reporter'].empty_label = "Select Reporter"
        else:
            self.fields['module'].queryset = WorkspaceModule.objects.none()
            self.fields['linked_task'].queryset = Task.objects.none()
            self.fields['assignee'].queryset = User.objects.none()
            self.fields['reporter'].queryset = User.objects.none()

    def clean_module(self):
        module = self.cleaned_data.get('module')
        if module and self.workspace and module.workspace_id != self.workspace.id:
            raise forms.ValidationError("Selected module does not belong to this workspace.")
        return module

    def clean_linked_task(self):
        task = self.cleaned_data.get('linked_task')
        if task and self.workspace and task.workspace_id != self.workspace.id:
            raise forms.ValidationError("Selected task does not belong to this workspace.")
        return task


class BugFilterForm(forms.Form):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(BugStatus.choices),
        required=False
    )
    priority = forms.ChoiceField(
        choices=[('', 'All Priorities')] + list(BugPriority.choices),
        required=False
    )
    severity = forms.ChoiceField(
        choices=[('', 'All Severities')] + list(BugSeverity.choices),
        required=False
    )
    module = forms.ModelChoiceField(
        queryset=WorkspaceModule.objects.none(),
        required=False,
        empty_label="All Modules"
    )
    environment = forms.ChoiceField(
        choices=[('', 'All Environments')] + list(BugEnvironment.choices),
        required=False
    )
    assignee = forms.CharField(required=False)

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields['module'].queryset = WorkspaceModule.objects.filter(
                workspace=workspace
            ).order_by('name')
