from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tasks.models import Task
from .models import TimeEntry, TimeEntryType


CATEGORY_CHOICES = [
    ('Development', _('Task / Development')),
    ('Bug fixes', _('Bug Fix')),
    ('Documentation', _('Documentation')),
    ('Meeting', _('Meeting')),
    ('Research', _('Research')),
    ('Code review', _('Code Review')),
    ('Design', _('Design')),
    ('API integration', _('API Integration')),
    ('Other', _('Other')),
]


class ManualTimeEntryForm(forms.Form):
    """
    Form for manual hour logging on workspace tasks, bugs, or general sprint effort.
    Supports both start_time/end_time calculation and explicit hours/minutes.
    """
    task = forms.ModelChoiceField(
        queryset=Task.objects.none(),
        required=False,
        empty_label=_("General Workspace Effort (No Task)"),
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-task-select'
        })
    )
    bug_code = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'manual-bug-code'})
    )
    date = forms.DateField(
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-date'
        })
    )
    start_time = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '09:00 AM',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-start-time'
        })
    )
    end_time = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': '11:30 AM',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-end-time'
        })
    )
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        required=False,
        initial='Development',
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-category'
        })
    )
    is_billable = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-slate-300 dark:border-zinc-700 text-aether-blue focus:ring-aether-blue',
            'id': 'manual-billable'
        })
    )
    hours = forms.IntegerField(
        min_value=0,
        max_value=24,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'placeholder': '0',
            'id': 'manual-hours'
        })
    )
    minutes = forms.IntegerField(
        min_value=0,
        max_value=59,
        required=False,
        initial=30,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'placeholder': '30',
            'id': 'manual-minutes'
        })
    )
    description = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'placeholder': 'Worked on implementing authentication backend and integrated with the new API endpoints...',
            'id': 'manual-desc'
        })
    )

    def __init__(self, workspace, *args, user=None, is_privileged=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        self.user = user
        self.is_privileged = is_privileged

        task_qs = Task.objects.filter(workspace=workspace).exclude(status='DONE')
        if not is_privileged and user:
            task_qs = task_qs.filter(assignee=user)
        self.fields['task'].queryset = task_qs.order_by('-created_at')

    def clean(self):
        cleaned_data = super().clean()

        # Server-side Task authorization
        task = cleaned_data.get('task')
        if task and not self.is_privileged and self.user:
            if task.assignee != self.user:
                raise forms.ValidationError(_("You can only log time against tasks assigned to you."))

        # Server-side Defect Bug authorization
        bug_code = (cleaned_data.get('bug_code') or '').strip()
        if bug_code:
            from bugs.models import Bug, BugStatus
            bug_qs = Bug.objects.filter(workspace=self.workspace, bug_code=bug_code).exclude(status=BugStatus.CLOSED)
            if not self.is_privileged and self.user:
                bug_qs = bug_qs.filter(assignee=self.user)
            bug = bug_qs.first()
            if not bug:
                if not self.is_privileged:
                    raise forms.ValidationError(_("Selected defect is not assigned to you or does not exist in this workspace."))
                raise forms.ValidationError(_("Selected defect does not belong to this workspace."))
            cleaned_data['validated_bug'] = bug

        # Sanitize description HTML using bleach
        import bleach
        from core.templatetags.rich_text import ALLOWED_TAGS, ALLOWED_ATTRIBUTES, ALLOWED_PROTOCOLS
        raw_desc = (cleaned_data.get('description') or '').strip()
        if raw_desc:
            cleaned_data['description'] = bleach.clean(
                raw_desc,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                protocols=ALLOWED_PROTOCOLS,
                strip=True
            )

        start_time_str = (cleaned_data.get('start_time') or '').strip()
        end_time_str = (cleaned_data.get('end_time') or '').strip()

        # Parse start_time and end_time if provided
        if start_time_str and end_time_str:
            from datetime import datetime
            parsed_start = None
            parsed_end = None
            for fmt in ['%I:%M %p', '%H:%M', '%I:%M%p']:
                if not parsed_start:
                    try:
                        parsed_start = datetime.strptime(start_time_str, fmt).time()
                    except ValueError:
                        pass
                if not parsed_end:
                    try:
                        parsed_end = datetime.strptime(end_time_str, fmt).time()
                    except ValueError:
                        pass

            if parsed_start and parsed_end:
                start_mins = parsed_start.hour * 60 + parsed_start.minute
                end_mins = parsed_end.hour * 60 + parsed_end.minute
                if end_mins < start_mins:
                    # Overnight duration
                    dur_mins = (24 * 60 - start_mins) + end_mins
                else:
                    dur_mins = end_mins - start_mins

                if dur_mins <= 0:
                    raise forms.ValidationError(_("End time must be after start time."))

                cleaned_data['hours'] = dur_mins // 60
                cleaned_data['minutes'] = dur_mins % 60
                cleaned_data['calculated_duration_seconds'] = dur_mins * 60
                cleaned_data['parsed_start_time'] = parsed_start
                cleaned_data['parsed_end_time'] = parsed_end
                return cleaned_data

        # Fallback to hours and minutes
        hours = cleaned_data.get('hours') or 0
        minutes = cleaned_data.get('minutes') or 0
        if hours == 0 and minutes == 0:
            raise forms.ValidationError(_("Duration must be at least 1 minute."))
        cleaned_data['calculated_duration_seconds'] = (hours * 3600) + (minutes * 60)
        return cleaned_data

