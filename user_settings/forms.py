from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from accounts.models import UserProfile
from workspaces.models import Workspace

User = get_user_model()

COMMON_TIMEZONES = [
    ('UTC', 'UTC (Coordinated Universal Time)'),
    ('America/New_York', 'America/New_York (Eastern Time)'),
    ('America/Chicago', 'America/Chicago (Central Time)'),
    ('America/Denver', 'America/Denver (Mountain Time)'),
    ('America/Los_Angeles', 'America/Los_Angeles (Pacific Time)'),
    ('Europe/London', 'Europe/London (GMT/BST)'),
    ('Europe/Paris', 'Europe/Paris (CET/CEST)'),
    ('Europe/Berlin', 'Europe/Berlin (CET/CEST)'),
    ('Asia/Dubai', 'Asia/Dubai (GST)'),
    ('Asia/Kolkata', 'Asia/Kolkata (IST - Indian Standard Time)'),
    ('Asia/Singapore', 'Asia/Singapore (SGT)'),
    ('Asia/Tokyo', 'Asia/Tokyo (JST)'),
    ('Australia/Sydney', 'Australia/Sydney (AEST/AEDT)'),
]

THEME_CHOICES = [
    ('obsidian', 'Obsidian Dark (Default)'),
    ('slate', 'Slate Light'),
    ('system', 'System Default (Matches OS)'),
]

DENSITY_CHOICES = [
    ('comfortable', 'Comfortable (Standard spacing)'),
    ('compact', 'Compact (High information density)'),
]

EMAIL_FREQUENCY_CHOICES = [
    ('immediate', 'Immediate (Instant email upon mention or assignment)'),
    ('daily', 'Daily Digest (Aggregated summary once per day)'),
    ('weekly', 'Weekly Digest (Summary every Monday morning)'),
    ('disabled', 'Disabled (No automated emails)'),
]


class AccountDetailsForm(forms.ModelForm):
    timezone = forms.ChoiceField(
        choices=COMMON_TIMEZONES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all'
        })
    )

    class Meta:
        model = User
        fields = ['full_name', 'email', 'timezone']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'placeholder': 'Your full name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-slate-100 dark:bg-zinc-900/50 text-slate-500 dark:text-zinc-400 text-sm cursor-not-allowed',
                'readonly': 'readonly',
                'title': 'Email is authoritative identity and cannot be edited directly'
            }),
        }

    def clean_email(self):
        # Email cannot be changed here for strict authentication security
        return self.instance.email


class ProfileDetailsForm(forms.ModelForm):
    avatar_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
            'placeholder': 'https://example.com/avatar.png'
        })
    )

    class Meta:
        model = UserProfile
        fields = ['headline', 'phone', 'bio']
        widgets = {
            'headline': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'placeholder': 'e.g. Senior Full-Stack Engineer / Product Lead'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'placeholder': '+1 (555) 000-0000'
            }),
            'bio': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'placeholder': 'Write a short professional bio describing your focus and expertise...'
            }),
        }


class SecurityPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all'
            })


class AppearancePreferencesForm(forms.Form):
    theme = forms.ChoiceField(
        choices=THEME_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'sr-only'}),
        required=True
    )
    ui_density = forms.ChoiceField(
        choices=DENSITY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all'
        }),
        required=True
    )
    sidebar_collapsed = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-slate-300 text-aether-blue focus:ring-aether-blue dark:border-zinc-700 dark:bg-zinc-800'
        })
    )


class NotificationPreferencesForm(forms.Form):
    email_frequency = forms.ChoiceField(
        choices=EMAIL_FREQUENCY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all'
        }),
        required=True
    )
    task_alerts = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'sr-only peer'
        })
    )
    bug_alerts = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'sr-only peer'
        })
    )
    chat_mentions = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'sr-only peer'
        })
    )
    meeting_reminders = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'sr-only peer'
        })
    )


class WorkspaceSettingsForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ['name', 'description', 'max_seats', 'storage_quota_mb']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'placeholder': 'Workspace Name'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'placeholder': 'Team objectives, focus areas, and guidelines...'
            }),
            'max_seats': forms.NumberInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'min': 1,
                'max': 100
            }),
            'storage_quota_mb': forms.NumberInput(attrs={
                'class': 'w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-aether-blue transition-all',
                'min': 10,
                'max': 2048
            }),
        }
