from django import forms
from django.core.exceptions import ValidationError
from accounts.models import User, UserRole
from workspaces.models import Workspace, WorkspaceRole, WorkspaceStatus

INPUT_CLASSES = 'w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-aether-blue focus:border-aether-blue transition-all'
SELECT_CLASSES = 'w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-aether-blue focus:border-aether-blue transition-all'
TEXTAREA_CLASSES = 'w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-zinc-800 bg-white dark:bg-[#0c1322] text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-aether-blue focus:border-aether-blue transition-all h-20 resize-none'


class AdminUserRoleForm(forms.Form):
    """Update platform-wide role for a user."""
    role = forms.ChoiceField(
        choices=UserRole.choices,
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )

    def __init__(self, *args, user_instance=None, **kwargs):
        self.user_instance = user_instance
        super().__init__(*args, **kwargs)
        if user_instance:
            self.fields['role'].initial = user_instance.role

    def clean_role(self):
        new_role = self.cleaned_data['role']
        if self.user_instance and self.user_instance.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            # Check if this user is the sole platform admin
            admin_count = User.objects.filter(role=UserRole.ADMIN, is_active=True).count()
            if admin_count <= 1:
                raise ValidationError(
                    "Cannot demote the sole active Platform Administrator. Assign another Admin first."
                )
        return new_role


class AdminWorkspaceQuotaForm(forms.Form):
    """Adjust maximum seats and storage quota for a workspace."""
    max_seats = forms.IntegerField(
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASSES})
    )
    storage_quota_mb = forms.IntegerField(
        min_value=5,
        max_value=102400,
        widget=forms.NumberInput(attrs={'class': INPUT_CLASSES})
    )

    def __init__(self, *args, workspace=None, **kwargs):
        self.workspace = workspace
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields['max_seats'].initial = workspace.max_seats
            self.fields['storage_quota_mb'].initial = workspace.storage_quota_mb or 50

    def clean_max_seats(self):
        seats = self.cleaned_data.get('max_seats')
        if self.workspace and seats is not None:
            active_members = self.workspace.seats_assigned
            if seats < active_members:
                raise ValidationError(
                    f"Cannot reduce seats to {seats}. The workspace currently has {active_members} active members."
                )
        return seats


class AdminWorkspaceStatusForm(forms.Form):
    """Update workspace operational status."""
    status = forms.ChoiceField(
        choices=WorkspaceStatus.choices,
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields['status'].initial = workspace.status


class AdminRequestDecisionForm(forms.Form):
    """Approve or reject a workspace access request."""
    DECISION_CHOICES = [
        ('APPROVE', 'Approve Access Request'),
        ('REJECT', 'Reject Access Request'),
    ]
    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect
    )
    role = forms.ChoiceField(
        choices=WorkspaceRole.choices,
        initial=WorkspaceRole.CONTRIBUTOR,
        widget=forms.Select(attrs={'class': SELECT_CLASSES})
    )
    admin_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': TEXTAREA_CLASSES,
            'placeholder': 'Optional reason or welcoming note...'
        })
    )
