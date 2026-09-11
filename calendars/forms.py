from datetime import datetime, time
from django import forms
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from workspaces.models import WorkspaceMembership, MembershipStatus
from tasks.models import Task
from bugs.models import Bug
from meetings.models import Meeting
from .models import (
    CalendarEvent, CalendarEventType, CalendarCategory,
    EventRepeat, EventStatus
)

User = get_user_model()


class CalendarEventForm(forms.ModelForm):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
        })
    )
    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
        })
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
        })
    )
    end_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
        })
    )
    invitees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = CalendarEvent
        fields = [
            'title', 'event_type', 'calendar_category', 'is_all_day',
            'repeat', 'location', 'meeting_link', 'description',
            'linked_task', 'linked_bug', 'linked_meeting'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'Enter event title',
                'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
            }),
            'event_type': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
            }),
            'calendar_category': forms.HiddenInput(),
            'is_all_day': forms.CheckboxInput(attrs={
                'class': 'rounded border-slate-300 text-blue-600 focus:ring-blue-500'
            }),
            'repeat': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
            }),
            'location': forms.TextInput(attrs={
                'placeholder': 'Add location or meeting link',
                'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
            }),
            'meeting_link': forms.URLInput(attrs={
                'placeholder': 'https://...',
                'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Add event description...',
                'class': 'w-full px-3.5 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition'
            }),
            'linked_task': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100'
            }),
            'linked_bug': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100'
            }),
            'linked_meeting': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-800 dark:text-zinc-100'
            }),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        self.workspace = workspace
        super().__init__(*args, **kwargs)

        if 'repeat' in self.fields:
            self.fields['repeat'].required = False
            self.fields['repeat'].initial = EventRepeat.NONE
        if 'calendar_category' in self.fields:
            self.fields['calendar_category'].required = False
            self.fields['calendar_category'].initial = CalendarCategory.WORKSPACE

        if self.workspace:
            # Scope linked options strictly to current workspace
            self.fields['linked_task'].queryset = Task.objects.filter(
                workspace=self.workspace
            ).order_by('-created_at')
            self.fields['linked_task'].empty_label = "Select task (optional)"

            self.fields['linked_bug'].queryset = Bug.objects.filter(
                workspace=self.workspace
            ).order_by('-created_at')
            self.fields['linked_bug'].empty_label = "Select bug (optional)"

            self.fields['linked_meeting'].queryset = Meeting.objects.filter(
                workspace=self.workspace
            ).order_by('-created_at')
            self.fields['linked_meeting'].empty_label = "Select meeting (optional)"

            member_ids = WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                status=MembershipStatus.ACTIVE
            ).values_list('user_id', flat=True)
            self.fields['invitees'].queryset = User.objects.filter(
                id__in=member_ids
            ).order_by('first_name', 'username')

        # If editing existing instance, populate date and time inputs
        if self.instance and self.instance.pk:
            current_tz = timezone.get_current_timezone()
            if self.instance.start_at:
                local_start = self.instance.start_at.astimezone(current_tz)
                self.fields['start_date'].initial = local_start.date()
                self.fields['start_time'].initial = local_start.time().strftime('%H:%M')
            if self.instance.end_at:
                local_end = self.instance.end_at.astimezone(current_tz)
                self.fields['end_date'].initial = local_end.date()
                self.fields['end_time'].initial = local_end.time().strftime('%H:%M')

            # Populate invitees
            attending_user_ids = self.instance.attendees.values_list('user_id', flat=True)
            self.fields['invitees'].initial = attending_user_ids

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        start_time = cleaned_data.get('start_time')
        end_date = cleaned_data.get('end_date')
        end_time = cleaned_data.get('end_time')
        is_all_day = cleaned_data.get('is_all_day', False)

        if not start_date or not end_date:
            raise ValidationError("Both start date and end date are required.")

        current_tz = timezone.get_current_timezone()

        if is_all_day:
            t_start = time(0, 0, 0)
            t_end = time(23, 59, 59)
        else:
            t_start = start_time or time(9, 0, 0)
            t_end = end_time or time(10, 0, 0)

        dt_start = datetime.combine(start_date, t_start)
        dt_end = datetime.combine(end_date, t_end)

        start_at = timezone.make_aware(dt_start, current_tz)
        end_at = timezone.make_aware(dt_end, current_tz)

        if end_at < start_at:
            raise ValidationError("End date and time must be after the start date and time.")

        cleaned_data['computed_start_at'] = start_at
        cleaned_data['computed_end_at'] = end_at

        if not cleaned_data.get('calendar_category'):
            cleaned_data['calendar_category'] = CalendarCategory.WORKSPACE

        return cleaned_data
