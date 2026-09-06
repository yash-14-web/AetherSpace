from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Task, TaskStatus, TaskPriority
from workspaces.models import WorkspaceMembership, MembershipStatus
from accounts.models import User


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            'title',
            'description',
            'status',
            'priority',
            'assignee',
            'due_date',
            'estimated_hours',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'placeholder': 'e.g. Implement WebRTC container connection',
                'required': 'required'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'rows': 4,
                'placeholder': 'Provide technical details, acceptance criteria, or context for this task...'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition'
            }),
            'priority': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition'
            }),
            'assignee': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'type': 'date'
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'placeholder': 'Hours (e.g. 4.5)',
                'step': '0.25',
                'min': '0'
            }),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        
        # Restrict assignee choices strictly to active members of this workspace
        if workspace:
            member_user_ids = WorkspaceMembership.objects.filter(
                workspace=workspace,
                status=MembershipStatus.ACTIVE
            ).values_list('user_id', flat=True)
            self.fields['assignee'].queryset = User.objects.filter(id__in=member_user_ids).order_by('full_name', 'email')
        else:
            self.fields['assignee'].queryset = User.objects.none()

        self.fields['assignee'].required = False
        self.fields['assignee'].empty_label = "Unassigned"
        self.fields['due_date'].required = False
        self.fields['estimated_hours'].required = False

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title:
            raise forms.ValidationError(_("Task title cannot be empty."))
        return title

    def clean_assignee(self):
        assignee = self.cleaned_data.get('assignee')
        if assignee and self.workspace:
            # Server-side validation: ensure user is really an active member of this workspace
            is_member = WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=assignee,
                status=MembershipStatus.ACTIVE
            ).exists()
            if not is_member:
                raise forms.ValidationError(_("Selected user is not an active member of this workspace."))
        return assignee


class TaskFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search by title, description, or #ID...',
            'class': 'w-full pl-9 pr-4 py-2 text-xs rounded-xl bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-zinc-800 text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition'
        })
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses')] + list(TaskStatus.choices),
        widget=forms.Select(attrs={
            'class': 'px-3 py-2 text-xs rounded-xl bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-zinc-800 text-slate-700 dark:text-zinc-300 focus:outline-none focus:ring-2 focus:ring-aether-blue'
        })
    )
    priority = forms.ChoiceField(
        required=False,
        choices=[('', 'All Priorities')] + list(TaskPriority.choices),
        widget=forms.Select(attrs={
            'class': 'px-3 py-2 text-xs rounded-xl bg-white dark:bg-[#0c1322] border border-slate-200 dark:border-zinc-800 text-slate-700 dark:text-zinc-300 focus:outline-none focus:ring-2 focus:ring-aether-blue'
        })
    )
    assignee = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
