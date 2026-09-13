from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from .models import User, ApprovalStatus


class LoginForm(forms.Form):
    contributor_id = forms.CharField(
        label=_("Contributor ID"),
        widget=forms.TextInput(attrs={
            'id': 'login-contributor-id',
            'placeholder': 'e.g. 26457C',
            'autocomplete': 'username',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 uppercase',
        })
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'id': 'login-password',
            'placeholder': '••••••••••••',
            'autocomplete': 'current-password',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Remember me"),
        widget=forms.CheckboxInput(attrs={
            'id': 'remember-me',
            'class': 'h-4 w-4 rounded border-slate-300 text-aether-blue focus:ring-aether-blue dark:border-zinc-700 dark:bg-zinc-900',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        contributor_id = cleaned_data.get('contributor_id')
        password = cleaned_data.get('password')

        if contributor_id and password:
            cid_clean = str(contributor_id).strip().upper()
            
            # Check user existence and credentials securely without exposing user existence
            user = authenticate(username=cid_clean, password=password)
            
            if user is None:
                # Also check if user exists with matching credentials but is unapproved/suspended
                potential_user = User.objects.filter(contributor_id__iexact=cid_clean).first()
                if not potential_user and '@' in cid_clean:
                    potential_user = User.objects.filter(email__iexact=cid_clean).first()
                    
                if potential_user and potential_user.check_password(password):
                    if potential_user.approval_status == ApprovalStatus.PENDING:
                        raise forms.ValidationError(
                            _("Your account (Contributor ID: %(cid)s) is awaiting Admin/Manager approval. Login will become available once approved."),
                            params={'cid': potential_user.contributor_id or cid_clean}
                        )
                    elif potential_user.approval_status in [ApprovalStatus.REJECTED, ApprovalStatus.SUSPENDED]:
                        raise forms.ValidationError(
                            _("This account has been suspended or rejected. Please contact an administrator.")
                        )
                    elif not potential_user.is_active:
                        raise forms.ValidationError(
                            _("This account is currently disabled. Please contact your workspace administrator.")
                        )
                raise forms.ValidationError(_("Invalid Contributor ID or password."))
            
            # Verify approval status for authenticated user
            if user.approval_status == ApprovalStatus.PENDING:
                raise forms.ValidationError(
                    _("Your account (Contributor ID: %(cid)s) is awaiting Admin/Manager approval. Login will become available once approved."),
                    params={'cid': user.contributor_id or cid_clean}
                )
            elif user.approval_status in [ApprovalStatus.REJECTED, ApprovalStatus.SUSPENDED]:
                raise forms.ValidationError(
                    _("This account has been suspended or rejected. Please contact an administrator.")
                )
            elif not user.is_active:
                raise forms.ValidationError(
                    _("This account is currently disabled. Please contact your workspace administrator.")
                )

            self.user_cache = user

        return cleaned_data

    def get_user(self):
        return getattr(self, 'user_cache', None)


class RegisterForm(forms.Form):
    full_name = forms.CharField(
        max_length=255,
        label=_("Full name"),
        widget=forms.TextInput(attrs={
            'id': 'register-fullname',
            'placeholder': 'Yaswanth M',
            'autocomplete': 'name',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={
            'id': 'register-email',
            'placeholder': 'yaswanth@example.com',
            'autocomplete': 'email',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'id': 'register-password',
            'placeholder': '••••••••••••',
            'autocomplete': 'new-password',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    confirm_password = forms.CharField(
        label=_("Confirm password"),
        widget=forms.PasswordInput(attrs={
            'id': 'register-confirm-password',
            'placeholder': '••••••••••••',
            'autocomplete': 'new-password',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    agree_terms = forms.BooleanField(
        required=True,
        label=_("I agree to the Terms of Service and Privacy Policy"),
        error_messages={
            'required': _("You must agree to the Terms of Service and Privacy Policy to create an account.")
        },
        widget=forms.CheckboxInput(attrs={
            'id': 'agree-terms',
            'class': 'h-4 w-4 rounded border-slate-300 text-aether-blue focus:ring-aether-blue dark:border-zinc-700 dark:bg-zinc-900',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email').lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email address already exists."))
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', _("Passwords do not match."))
            else:
                validate_password(password)
        return cleaned_data


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={
            'id': 'forgot-email',
            'placeholder': 'yaswanth@example.com',
            'autocomplete': 'email',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )

    def clean_email(self):
        return self.cleaned_data.get('email').lower().strip()


class ResetPasswordForm(forms.Form):
    password = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(attrs={
            'id': 'reset-password',
            'placeholder': '••••••••••••',
            'autocomplete': 'new-password',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    confirm_password = forms.CharField(
        label=_("Confirm new password"),
        widget=forms.PasswordInput(attrs={
            'id': 'reset-confirm-password',
            'placeholder': '••••••••••••',
            'autocomplete': 'new-password',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', _("Passwords do not match."))
            else:
                validate_password(password)
        return cleaned_data


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={
            'id': 'resend-email',
            'placeholder': 'yaswanth@example.com',
            'autocomplete': 'email',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )

    def clean_email(self):
        return self.cleaned_data.get('email').lower().strip()


TIMEZONE_CHOICES = [
    ('UTC', 'UTC (Coordinated Universal Time)'),
    ('America/New_York', 'Eastern Time (US & Canada) (UTC-5)'),
    ('America/Chicago', 'Central Time (US & Canada) (UTC-6)'),
    ('America/Denver', 'Mountain Time (US & Canada) (UTC-7)'),
    ('America/Los_Angeles', 'Pacific Time (US & Canada) (UTC-8)'),
    ('Europe/London', 'London, Dublin (UTC+0)'),
    ('Europe/Paris', 'Paris, Berlin, Rome (UTC+1)'),
    ('Asia/Dubai', 'Dubai, Abu Dhabi (UTC+4)'),
    ('Asia/Kolkata', 'India Standard Time (IST) (UTC+5:30)'),
    ('Asia/Singapore', 'Singapore, Hong Kong (UTC+8)'),
    ('Asia/Tokyo', 'Tokyo, Seoul (UTC+9)'),
    ('Australia/Sydney', 'Sydney, Melbourne (UTC+10)'),
]


class ProfileUpdateForm(forms.Form):
    """Form to update primary user information and profile details."""
    full_name = forms.CharField(
        max_length=255,
        required=True,
        label=_("Full name"),
        widget=forms.TextInput(attrs={
            'id': 'profile-fullname',
            'placeholder': 'Yaswanth M',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    headline = forms.CharField(
        max_length=255,
        required=False,
        label=_("Professional headline"),
        widget=forms.TextInput(attrs={
            'id': 'profile-headline',
            'placeholder': 'Senior Full-Stack Engineer & Agile Architect',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    bio = forms.CharField(
        required=False,
        label=_("About / Bio"),
        widget=forms.Textarea(attrs={
            'id': 'profile-bio',
            'rows': 4,
            'placeholder': 'Share a few words about your background, focus areas, and technical expertise...',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    phone = forms.CharField(
        max_length=32,
        required=False,
        label=_("Phone number"),
        widget=forms.TextInput(attrs={
            'id': 'profile-phone',
            'placeholder': '+1 (555) 000-0000',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES,
        required=False,
        label=_("Timezone"),
        widget=forms.Select(attrs={
            'id': 'profile-timezone',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100',
        })
    )


class AvatarUploadForm(forms.Form):
    """
    KB-only Avatar upload and linking form:
    Enforces maximum 500 KB upload limit, image extensions, or external URL.
    """
    avatar_file = forms.FileField(
        required=False,
        label=_("Upload profile picture (Max 500 KB)"),
        widget=forms.FileInput(attrs={
            'id': 'avatar-file-input',
            'accept': 'image/png,image/jpeg,image/webp,image/gif',
            'class': 'hidden',
        })
    )
    avatar_url = forms.URLField(
        required=False,
        label=_("Or link external image URL (0 KB storage)"),
        widget=forms.URLInput(attrs={
            'id': 'avatar-url-input',
            'placeholder': 'https://avatars.githubusercontent.com/u/...',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
        })
    )
    preset_color = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'avatar-preset-input'})
    )

    def clean_avatar_file(self):
        file_obj = self.cleaned_data.get('avatar_file')
        if file_obj:
            from .services import MAX_AVATAR_SIZE_BYTES, ALLOWED_AVATAR_EXTENSIONS
            import os
            if file_obj.size > MAX_AVATAR_SIZE_BYTES:
                size_kb = round(file_obj.size / 1024)
                raise forms.ValidationError(
                    _(f"File size ({size_kb} KB) exceeds the 500 KB maximum limit. Please choose a smaller photo.")
                )
            ext = os.path.splitext(file_obj.name)[1].lstrip('.').lower()
            if ext not in ALLOWED_AVATAR_EXTENSIONS:
                raise forms.ValidationError(
                    _(f"Unsupported format '.{ext}'. Allowed formats: JPG, PNG, WEBP, GIF.")
                )
        return file_obj

