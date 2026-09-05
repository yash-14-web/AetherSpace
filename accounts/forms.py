from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from .models import User


class LoginForm(forms.Form):
    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={
            'placeholder': 'you@domain.com',
            'autocomplete': 'email',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            self.user_cache = authenticate(username=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(_("Invalid email address or password."))
            elif not self.user_cache.is_active:
                raise forms.ValidationError(_("This account is currently inactive."))
        return cleaned_data

    def get_user(self):
        return getattr(self, 'user_cache', None)


class RegisterForm(forms.Form):
    full_name = forms.CharField(
        max_length=255,
        label=_("Full Name"),
        widget=forms.TextInput(attrs={
            'placeholder': 'Jane Doe',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )
    email = forms.EmailField(
        label=_("Work Email"),
        widget=forms.EmailInput(attrs={
            'placeholder': 'you@company.com',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Minimum 8 characters',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )
    confirm_password = forms.CharField(
        label=_("Confirm Password"),
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Repeat your password',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
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
        label=_("Registered Email"),
        widget=forms.EmailInput(attrs={
            'placeholder': 'you@company.com',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )


class ResetPasswordForm(forms.Form):
    password = forms.CharField(
        label=_("New Password"),
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter new password',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )
    confirm_password = forms.CharField(
        label=_("Confirm New Password"),
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm new password',
            'class': 'w-full px-3 py-2 border rounded-lg focus:outline-none transition-colors dark:bg-zinc-900 dark:border-zinc-800 dark:text-zinc-100 bg-white border-slate-200 text-slate-900',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2:
            if p1 != p2:
                self.add_error('confirm_password', _("Passwords do not match."))
            else:
                validate_password(p1)
        return cleaned_data
