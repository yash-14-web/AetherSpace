from django import forms
from django.utils.text import slugify
from .models import Channel, PostingPermission, Message


class ChannelForm(forms.ModelForm):
    class Meta:
        model = Channel
        fields = ['name', 'topic', 'description', 'is_private', 'who_can_post']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'e.g. marketing-campaign, dev-discussion',
                'required': 'required',
            }),
            'topic': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition',
                'placeholder': 'Short channel focus or topic...',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition resize-none',
                'rows': 3,
                'placeholder': 'Describe what this channel is for, rules, or resources...',
            }),
            'who_can_post': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue transition cursor-pointer',
            }),
            'is_private': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 rounded text-aether-blue border-slate-300 dark:border-zinc-700 focus:ring-aether-blue cursor-pointer',
            }),
        }

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace

    def clean_name(self):
        raw_name = self.cleaned_data.get('name', '').lstrip('#').strip().lower()
        if not raw_name:
            raise forms.ValidationError("Channel name cannot be empty.")

        slug = slugify(raw_name)
        if not slug:
            raise forms.ValidationError("Enter a valid channel name containing letters or numbers.")

        if self.workspace:
            query = Channel.objects.filter(workspace=self.workspace, slug=slug)
            if self.instance and self.instance.pk:
                query = query.exclude(pk=self.instance.pk)
            if query.exists():
                raise forms.ValidationError(f"A channel named #{raw_name} already exists in this workspace.")

        return raw_name


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-aether-blue transition resize-none',
                'rows': 2,
                'placeholder': 'Type a message...',
            }),
        }
