from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from .forms import LoginForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm
from .models import User, UserProfile


def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:landing')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', 'core:landing')
            return redirect(next_url)
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {
        'form': form,
        'title': 'Sign In — AetherSpace',
    })


def logout_view(request):
    logout(request)
    messages.info(request, "You have been safely signed out.")
    return redirect('accounts:login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('core:landing')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name
            )
            UserProfile.objects.create(user=user)
            login(request, user)
            messages.success(request, f"Welcome to AetherSpace, {full_name}!")
            return redirect('core:landing')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'title': 'Create Your Workspace Account — AetherSpace',
    })


def forgot_password_view(request):
    submitted = False
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            submitted = True
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {
        'form': form,
        'submitted': submitted,
        'title': 'Password Recovery — AetherSpace',
    })


def reset_password_view(request):
    success = False
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            success = True
    else:
        form = ResetPasswordForm()

    return render(request, 'accounts/reset_password.html', {
        'form': form,
        'success': success,
        'title': 'Reset Your Password — AetherSpace',
    })


def verification_view(request):
    return render(request, 'accounts/verification.html', {
        'title': 'Account Verification — AetherSpace',
    })
