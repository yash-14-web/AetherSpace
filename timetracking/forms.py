from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from tasks.models import Task
from .models import TimeEntry, TimeEntryType


class ManualTimeEntryForm(forms.Form):
    """
    Form for manual hour logging on workspace tasks or general sprint effort.
    """
    task = forms.ModelChoiceField(
        queryset=Task.objects.none(),
        required=False,
        empty_label=_("General Workspace Effort (No Task)"),
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-task-select'
        })
    )
    date = forms.DateField(
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'id': 'manual-date'
        })
    )
    hours = forms.IntegerField(
        min_value=0,
        max_value=24,
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
        initial=30,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'placeholder': '30',
            'id': 'manual-minutes'
        })
    )
    description = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-aether-blue',
            'placeholder': 'Brief description of work done...',
            'id': 'manual-desc'
        })
    )

    def __init__(self, workspace, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        self.fields['task'].queryset = Task.objects.filter(workspace=workspace).order_by('-created_at')

    def clean(self):
        cleaned_data = super().clean()
        hours = cleaned_data.get('hours', 0) or 0
        minutes = cleaned_data.get('minutes', 0) or 0
        if hours == 0 and minutes == 0:
            raise forms.ValidationError(_("Duration must be at least 1 minute."))
        return cleaned_data
