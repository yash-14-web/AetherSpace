from django import forms
from django.utils import timezone
from datetime import datetime, time
from django.contrib.auth import get_user_model
from .models import Meeting, MeetingType

User = get_user_model()


class StartMeetingForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=True,
        initial='Quick Sync Meeting',
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Sprint Kickoff, Design Huddle...',
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    meeting_type = forms.ChoiceField(
        choices=MeetingType.choices,
        required=False,
        initial=MeetingType.INSTANT,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    is_audio_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 rounded text-aether-blue focus:ring-aether-blue border-slate-300 dark:border-zinc-700 bg-white dark:bg-zinc-900'
        })
    )


class ScheduleMeetingForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Sprint 03 Review & Retrospective',
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Add meeting agenda, key topics to discuss, or required preparation...',
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    meeting_type = forms.ChoiceField(
        choices=MeetingType.choices,
        initial=MeetingType.GENERAL,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    scheduled_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    scheduled_time = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    duration_minutes = forms.ChoiceField(
        choices=[
            (15, '15 minutes'),
            (30, '30 minutes'),
            (45, '45 minutes'),
            (60, '1 hour'),
            (90, '1.5 hours'),
            (120, '2 hours'),
        ],
        initial=30,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 text-xs sm:text-sm rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition'
        })
    )
    invitees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple()
    )
    is_audio_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 rounded text-aether-blue focus:ring-aether-blue border-slate-300 dark:border-zinc-700 bg-white dark:bg-zinc-900'
        })
    )

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            # Only allow inviting active members of the same workspace
            self.fields['invitees'].queryset = User.objects.filter(
                workspace_memberships__workspace=workspace,
                workspace_memberships__status='ACTIVE'
            ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('scheduled_date')
        t = cleaned_data.get('scheduled_time')

        if date and t:
            combined = datetime.combine(date, t)
            # Make timezone aware
            current_tz = timezone.get_current_timezone()
            aware_dt = timezone.make_aware(combined, current_tz)
            cleaned_data['scheduled_start'] = aware_dt

            # Check future
            if aware_dt < timezone.now() - timezone.timedelta(minutes=5):
                self.add_error('scheduled_date', "Meeting cannot be scheduled in the past.")

        return cleaned_data


class JoinMeetingForm(forms.Form):
    meeting_code = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter code (e.g. meet-k7xp-2m9q)',
            'class': 'w-full px-4 py-3 text-sm font-mono rounded-xl bg-white dark:bg-[#0c1322] border border-slate-300 dark:border-zinc-700 text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:ring-2 focus:ring-aether-blue focus:border-transparent outline-none transition uppercase'
        })
    )

    def clean_meeting_code(self):
        code = self.cleaned_data.get('meeting_code', '').strip().lower()
        # Strip URL prefix if full URL pasted
        if '/' in code:
            code = code.split('/')[-1] or code.split('/')[-2]
        return code
