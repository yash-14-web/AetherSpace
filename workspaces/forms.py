from django import forms
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from .models import Workspace, WorkspaceRole, WorkspaceStatus, WorkspaceMembership, MembershipStatus


class WorkspaceCreateForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        help_text="Custom URL slug (e.g. smart-classroom). Auto-generated from name if left blank.",
        widget=forms.TextInput(attrs={
            'placeholder': 'smart-classroom',
            'class': 'aether-input',
            'autocomplete': 'off',
        })
    )

    class Meta:
        model = Workspace
        fields = ['name', 'slug', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g. Smart Classroom or Flora AI',
                'class': 'aether-input',
                'autocomplete': 'off',
                'required': 'required',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Brief description of the workspace purpose and team focus...',
                'class': 'aether-input h-24 resize-none',
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
                'class': 'aether-input',
                'required': 'required',
            }),
            'description': forms.Textarea(attrs={
                'class': 'aether-input h-24 resize-none',
                'rows': 3,
            }),
            'status': forms.Select(attrs={
                'class': 'aether-input',
            }),
        }


class WorkspaceInviteForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'colleague@aetherspace.dev',
            'class': 'aether-input',
            'autocomplete': 'email',
        })
    )
    role = forms.ChoiceField(
        choices=WorkspaceRole.choices,
        initial=WorkspaceRole.CONTRIBUTOR,
        widget=forms.Select(attrs={
            'class': 'aether-input',
        })
    )

    def clean_email(self):
        return self.cleaned_data['email'].lower().strip()


class WorkspaceMemberRoleForm(forms.Form):
    role = forms.ChoiceField(
        choices=WorkspaceRole.choices,
        widget=forms.Select(attrs={
            'class': 'aether-input !py-1 !text-xs',
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
            'class': 'aether-input h-20 resize-none',
            'rows': 2,
        })
    )
