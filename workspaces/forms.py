from django import forms
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from .models import Workspace, WorkspaceRole, WorkspaceStatus, WorkspaceMembership, MembershipStatus


INPUT_CLASSES = 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-aether-blue focus:border-aether-blue transition-all'
TEXTAREA_CLASSES = 'w-full px-3.5 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-aether-blue focus:border-aether-blue transition-all h-24 resize-none'


class WorkspaceCreateForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        help_text="Custom URL slug (e.g. smart-classroom). Auto-generated from name if left blank.",
        widget=forms.TextInput(attrs={
            'placeholder': 'smart-classroom',
            'class': INPUT_CLASSES,
            'autocomplete': 'off',
        })
    )

    class Meta:
        model = Workspace
        fields = ['name', 'slug', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g. Smart Classroom or Flora AI',
                'class': INPUT_CLASSES,
                'autocomplete': 'off',
                'required': 'required',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Brief description of the workspace purpose and team focus...',
                'class': TEXTAREA_CLASSES,
                'rows': 3,
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if len(name) < 2:
            raise ValidationError("Workspace name must be at least 2 characters long.")
        return name

    def clean_slug(self):
        slug = self.cleaned_data.get('slug', '').strip()
        if slug:
            slug = slugify(slug)
            if Workspace.objects.filter(slug=slug).exists():
                raise ValidationError("A workspace with this URL slug already exists. Please choose another.")
        return slug

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        slug = cleaned_data.get('slug')
        if not slug and name:
            base_slug = slugify(name) or 'workspace'
            candidate = base_slug
            counter = 1
            while Workspace.objects.filter(slug=candidate).exists():
                candidate = f"{base_slug}-{counter}"
                counter += 1
            cleaned_data['slug'] = candidate
        return cleaned_data


class WorkspaceUpdateForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ['name', 'description', 'status']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'required': 'required',
            }),
            'description': forms.Textarea(attrs={
                'class': TEXTAREA_CLASSES,
                'rows': 3,
            }),
            'status': forms.Select(attrs={
                'class': INPUT_CLASSES,
            }),
        }


class WorkspaceInviteForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'colleague@aetherspace.dev',
            'class': INPUT_CLASSES,
            'autocomplete': 'email',
        })
    )
    role = forms.ChoiceField(
        choices=WorkspaceRole.choices,
        initial=WorkspaceRole.CONTRIBUTOR,
        widget=forms.Select(attrs={
            'class': INPUT_CLASSES,
        })
    )

    def clean_email(self):
        return self.cleaned_data['email'].lower().strip()


class WorkspaceMemberRoleForm(forms.Form):
    role = forms.ChoiceField(
        choices=WorkspaceRole.choices,
        widget=forms.Select(attrs={
            'class': 'w-full px-2.5 py-1 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue',
        })
    )

    def __init__(self, *args, member=None, **kwargs):
        self.member = member
        super().__init__(*args, **kwargs)

    def clean_role(self):
        new_role = self.cleaned_data['role']
        if self.member and self.member.is_admin and new_role != WorkspaceRole.ADMIN:
            # Check if this member is the sole admin
            admin_count = WorkspaceMembership.objects.filter(
                workspace=self.member.workspace,
                role=WorkspaceRole.ADMIN,
                status=MembershipStatus.ACTIVE
            ).count()
            if admin_count <= 1:
                raise ValidationError("Cannot demote the only administrator in this workspace.")
        return new_role


class WorkspaceAccessRequestForm(forms.Form):
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': 'Tell the workspace admin why you need access...',
            'class': TEXTAREA_CLASSES,
            'rows': 2,
        })
    )
