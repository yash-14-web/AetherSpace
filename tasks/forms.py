from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Task, TaskStatus, TaskPriority, CodeReviewRequest, CodeReviewStatus, TaskComment, Sprint, SprintStatus
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
            'sprint',
            'due_date',
            'tags',
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
            'sprint': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'placeholder': 'e.g. Sprint 01'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'placeholder': 'e.g. Design, UI/UX'
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


class CodeReviewRequestForm(forms.ModelForm):
    task_code_display = forms.CharField(
        label=_("Task ID"),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-slate-100 dark:bg-zinc-800 text-slate-500 dark:text-zinc-400 font-mono text-sm cursor-not-allowed',
            'readonly': 'readonly'
        })
    )
    task_title_display = forms.CharField(
        label=_("Task Title"),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-slate-100 dark:bg-zinc-800 text-slate-500 dark:text-zinc-400 text-sm cursor-not-allowed',
            'readonly': 'readonly'
        })
    )
    reviewer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Select Reviewer (Optional)",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition'
        })
    )

    class Meta:
        model = CodeReviewRequest
        fields = ['title', 'description', 'github_pr_url', 'reviewer']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'placeholder': 'e.g. Review WebRTC Container Connection Implementation',
                'required': 'required'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'rows': 4,
                'placeholder': 'Summary of changes, test instructions, or notes for the reviewer...'
            }),
            'github_pr_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm font-mono transition',
                'placeholder': 'https://github.com/org/repo/pull/123',
                'required': 'required'
            }),
        }

    def __init__(self, *args, task=None, requester=None, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task
        self.requester = requester
        self.workspace = workspace or (task.workspace if task else None)

        if self.workspace:
            member_user_ids = WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                status=MembershipStatus.ACTIVE
            ).values_list('user_id', flat=True)
            self.fields['reviewer'].queryset = User.objects.filter(id__in=member_user_ids).order_by('full_name', 'email')

        if task:
            self.fields['task_code_display'].initial = task.display_code
            self.fields['task_title_display'].initial = task.title
            if not self.initial.get('title'):
                self.fields['title'].initial = f"Code Review: {task.title}"

    def clean_github_pr_url(self):
        import re
        url = self.cleaned_data.get('github_pr_url', '').strip()
        pr_pattern = re.compile(r'^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/pull/\d+/?$')
        if not pr_pattern.match(url):
            raise forms.ValidationError(_("Please enter a valid GitHub Pull Request URL (e.g. https://github.com/owner/repo/pull/42)."))

        if self.task:
            existing = CodeReviewRequest.objects.filter(
                task=self.task,
                github_pr_url=url
            ).exclude(status__in=[CodeReviewStatus.CLOSED, CodeReviewStatus.MERGED])
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_("An active code review request for this pull request already exists on this task."))

        return url

    def clean_reviewer(self):
        reviewer = self.cleaned_data.get('reviewer')
        if reviewer and self.workspace:
            is_member = WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=reviewer,
                status=MembershipStatus.ACTIVE
            ).exists()
            if not is_member:
                raise forms.ValidationError(_("Selected reviewer is not an active member of this workspace."))
        return reviewer

    def clean(self):
        cleaned_data = super().clean()
        if not self.task:
            raise forms.ValidationError(_("Connected task does not exist."))

        if self.workspace and self.task.workspace_id != self.workspace.id:
            raise forms.ValidationError(_("Task does not belong to this workspace."))

        if self.requester and self.workspace:
            is_member = WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=self.requester,
                status=MembershipStatus.ACTIVE
            ).exists()
            if not is_member:
                raise forms.ValidationError(_("Requester is not an active member of this workspace."))

        return cleaned_data


class TaskCommentForm(forms.ModelForm):
    code_review = forms.ModelChoiceField(
        queryset=CodeReviewRequest.objects.none(),
        required=False,
        empty_label="General Task Comment",
        widget=forms.Select(attrs={
            'class': 'px-3 py-1.5 rounded-lg border border-slate-200 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-xs text-slate-700 dark:text-zinc-300 focus:outline-none focus:ring-1 focus:ring-aether-blue'
        })
    )

    class Meta:
        model = TaskComment
        fields = ['content', 'code_review']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue text-sm transition',
                'rows': 3,
                'placeholder': 'Write a comment or reviewer feedback (Markdown supported)...',
                'required': 'required'
            })
        }

    def __init__(self, *args, task=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.task = task
        if task:
            self.fields['code_review'].queryset = task.code_reviews.all().order_by('-created_at')

    def clean_content(self):
        content = self.cleaned_data.get('content', '').strip()
        if not content:
            raise forms.ValidationError(_("Comment content cannot be empty."))
        return content


class SprintForm(forms.ModelForm):
    """
    Form for creating and editing Sprints with full validation.
    """
    status = forms.ChoiceField(
        choices=SprintStatus.choices,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition'
        })
    )

    class Meta:
        model = Sprint
        fields = ['name', 'goal', 'status', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'placeholder': 'e.g. Sprint 04',
                'required': 'required'
            }),
            'goal': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'rows': 3,
                'placeholder': 'Key objective or description for this sprint...'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-300 dark:border-zinc-700 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue focus:border-transparent text-sm transition',
                'type': 'date'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['status'].initial = self.instance.status
        else:
            self.fields['status'].initial = SprintStatus.PLANNING

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError(_("Sprint name is required."))
        return name

    def clean_status(self):
        status = self.cleaned_data.get('status')
        if not status:
            if self.instance and self.instance.pk:
                return self.instance.status
            return SprintStatus.PLANNING
        if status not in dict(SprintStatus.choices):
            raise forms.ValidationError(_("Invalid sprint status."))
        return status

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError(_("End date cannot be earlier than start date."))
        return cleaned_data
