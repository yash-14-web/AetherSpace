from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from .models import User


class LoginForm(forms.Form):
    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={
            'id': 'login-email',
            'placeholder': 'yaswanth@example.com',
            'autocomplete': 'email',
            'class': 'w-full px-3.5 py-2.5 text-sm rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-aether-blue border-slate-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-slate-900 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500',
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
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            email_normalized = email.lower().strip()
            self.user_cache = authenticate(username=email_normalized, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(_("Invalid email address or password."))
            elif not self.user_cache.is_active:
                raise forms.ValidationError(_("This account is currently disabled. Please contact your workspace administrator."))
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
