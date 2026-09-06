import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse

from .forms import (
    LoginForm,
    RegisterForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    ResendVerificationForm,
)
from .models import User, UserProfile
from .tokens import account_verification_token

logger = logging.getLogger(__name__)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('workspaces:dashboard')

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Session expiration handling based on remember_me
            remember_me = form.cleaned_data.get('remember_me')
            if remember_me:
                # 14 days
                request.session.set_expiry(1209600)
            else:
                # Session expires on browser close
                request.session.set_expiry(0)

            # Validate redirect URL security
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('workspaces:dashboard')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {
        'form': form,
        'next_url': next_url,
        'title': 'Sign In — AetherSpace',
    })


def logout_view(request):
    logout(request)
    messages.info(request, "You have been safely signed out.")
    return redirect('accounts:login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('workspaces:dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                is_verified=False,
            )
            UserProfile.objects.create(user=user)

            # Generate email verification token
            token = account_verification_token.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            verify_url = request.build_absolute_uri(
                reverse('accounts:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': token})
            )
            logger.info("Verification URL generated for %s: %s", user.email, verify_url)

            # Store in session for easy testing/demo display
            request.session['pending_verification_email'] = user.email
            request.session['last_verify_url'] = verify_url

            # Sign user in
            login(request, user)
            messages.success(request, f"Welcome to AetherSpace, {full_name}! Please verify your email.")
            return redirect('accounts:verification')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'title': 'Create Your Workspace Account — AetherSpace',
    })


def forgot_password_view(request):
    submitted = False
    reset_url = None

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.filter(email=email).first()
            if user:
                token = default_token_generator.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                reset_url = request.build_absolute_uri(
                    reverse('accounts:reset_password_confirm', kwargs={'uidb64': uidb64, 'token': token})
                )
                logger.info("Password reset link generated for %s: %s", user.email, reset_url)
                request.session['last_reset_url'] = reset_url
            submitted = True
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {
        'form': form,
        'submitted': submitted,
        'reset_url': reset_url or request.session.get('last_reset_url'),
        'title': 'Forgot Password — AetherSpace',
    })


def reset_password_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    is_valid_token = user is not None and default_token_generator.check_token(user, token)

    if not is_valid_token:
        return render(request, 'accounts/reset_password.html', {
            'invalid_token': True,
            'title': 'Invalid or Expired Reset Link — AetherSpace',
        })

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['password']
            user.set_password(new_password)
            user.save()
            messages.success(request, "Your password has been reset successfully. Please sign in.")
            return redirect('accounts:login')
    else:
        form = ResetPasswordForm()

    return render(request, 'accounts/reset_password.html', {
        'form': form,
        'uidb64': uidb64,
        'token': token,
        'title': 'Reset Your Password — AetherSpace',
    })


def verification_view(request):
    email = request.session.get('pending_verification_email')
    if not email and request.user.is_authenticated:
        email = request.user.email

    resend_success = False

    if request.method == 'POST':
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            target_email = form.cleaned_data['email']
            user = User.objects.filter(email=target_email).first()
            if user and not user.is_verified:
                token = account_verification_token.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                verify_url = request.build_absolute_uri(
                    reverse('accounts:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': token})
                )
                request.session['last_verify_url'] = verify_url
                resend_success = True
                messages.success(request, f"A fresh verification link has been sent to {target_email}.")
    else:
        form = ResendVerificationForm(initial={'email': email or ''})

    return render(request, 'accounts/verification.html', {
        'email': email or 'your email address',
        'verify_url': request.session.get('last_verify_url'),
        'form': form,
        'resend_success': resend_success,
        'title': 'Verify Your Email — AetherSpace',
    })


def verify_email_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_verification_token.check_token(user, token):
        user.is_verified = True
        user.save()
        messages.success(request, "Your email has been verified! Welcome to AetherSpace.")
        return redirect('core:landing')
    else:
        return render(request, 'accounts/verification.html', {
            'invalid_token': True,
            'title': 'Invalid Verification Link — AetherSpace',
        })
