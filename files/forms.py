import os
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import Folder, StoredFile, FileCategory, FileShare, FileShareAccess, FileVersion
from .services import MAX_FILE_SIZE_BYTES, DANGEROUS_EXTENSIONS

User = get_user_model()


class FileUploadForm(forms.Form):
    UPLOAD_TYPE_CHOICES = [
        ('file', 'Upload File (Direct)'),
        ('link', 'Add Cloud Link (Figma, Drive, GitHub, etc.)'),
    ]

    upload_type = forms.ChoiceField(
        choices=UPLOAD_TYPE_CHOICES,
        initial='file',
        widget=forms.RadioSelect(attrs={'class': 'sr-only'})
    )
    file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'hidden',
            'id': 'file-input-field'
        })
    )
    external_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'placeholder': 'https://www.figma.com/file/... or https://drive.google.com/...',
            'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
        })
    )
    name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Custom file or resource title (optional)',
            'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
        })
    )
    folder = forms.ModelChoiceField(
        queryset=Folder.objects.none(),
        required=False,
        empty_label='Root (Workspace Files)',
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Add description or context for your team...',
            'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue resize-none'
        })
    )
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'overview, planning, sprint-02 (comma separated)',
            'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
        })
    )

    def __init__(self, workspace, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        self.fields['folder'].queryset = Folder.objects.filter(workspace=workspace).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        upload_type = cleaned_data.get('upload_type')
        uploaded_file = cleaned_data.get('file')
        external_url = cleaned_data.get('external_url')

        if upload_type == 'file':
            if not uploaded_file:
                self.add_error('file', "Please select a file to upload.")
            else:
                if uploaded_file.size > MAX_FILE_SIZE_BYTES:
                    size_mb = uploaded_file.size / (1024 * 1024)
                    self.add_error('file', f"File size ({size_mb:.1f} MB) exceeds maximum allowed limit of 20 MB.")

                ext = os.path.splitext(uploaded_file.name)[1].lstrip('.').lower()
                if ext in DANGEROUS_EXTENSIONS:
                    self.add_error('file', f"File extension '.{ext}' is restricted for security reasons.")

        elif upload_type == 'link':
            if not external_url:
                self.add_error('external_url', "Please enter a valid external link / URL.")
            elif not (external_url.startswith('http://') or external_url.startswith('https://')):
                self.add_error('external_url', "URL must start with http:// or https://")

        return cleaned_data


class FolderForm(forms.ModelForm):
    COLOR_CHOICES = [
        ('amber', 'Amber Yellow'),
        ('blue', 'Sapphire Blue'),
        ('purple', 'Violet Purple'),
        ('emerald', 'Emerald Green'),
        ('rose', 'Rose Red'),
        ('indigo', 'Indigo'),
        ('cyan', 'Cyan Teal'),
    ]

    color = forms.ChoiceField(
        choices=COLOR_CHOICES,
        initial='amber',
        widget=forms.Select(attrs={
            'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
        })
    )

    class Meta:
        model = Folder
        fields = ['name', 'parent', 'color']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Folder name (e.g. Design Assets, Meeting Notes)',
                'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue',
                'required': True
            }),
            'parent': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
            })
        }

    def __init__(self, workspace, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        self.fields['parent'].queryset = Folder.objects.filter(workspace=workspace).order_by('name')
        self.fields['parent'].empty_label = 'None (Root Level)'
        if self.instance and self.instance.pk:
            # Prevent folder from selecting itself or subfolders as parent
            self.fields['parent'].queryset = self.fields['parent'].queryset.exclude(pk=self.instance.pk)

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise ValidationError("Folder name is required.")
        parent = self.cleaned_data.get('parent')
        qs = Folder.objects.filter(workspace=self.workspace, parent=parent, name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A folder named '{name}' already exists in this location.")
        return name


class FileEditForm(forms.ModelForm):
    class Meta:
        model = StoredFile
        fields = ['name', 'folder', 'description', 'tags']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
            }),
            'folder': forms.Select(attrs={
                'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue resize-none'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'w-full px-3.5 py-2 text-sm rounded-xl border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800/60 text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-aether-blue/30 focus:border-aether-blue'
            })
        }

    def __init__(self, workspace, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['folder'].queryset = Folder.objects.filter(workspace=workspace).order_by('name')
        self.fields['folder'].empty_label = 'Root (Workspace Files)'


class FileShareForm(forms.Form):
    user_id = forms.CharField(
        widget=forms.HiddenInput(attrs={'id': 'share-user-id-input'})
    )
    access_level = forms.ChoiceField(
        choices=FileShareAccess.choices,
        initial=FileShareAccess.VIEW,
        widget=forms.Select(attrs={
            'class': 'px-3 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 text-slate-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-aether-blue/30'
        })
    )


class FileVersionUploadForm(forms.Form):
    file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'w-full text-xs'})
    )
    external_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'placeholder': 'New URL link (if updating cloud asset)',
            'class': 'w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 text-slate-900 dark:text-zinc-100'
        })
    )
    note = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. Updated layout according to sprint feedback',
            'class': 'w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-700 bg-slate-50 dark:bg-zinc-800 text-slate-900 dark:text-zinc-100'
        })
    )
