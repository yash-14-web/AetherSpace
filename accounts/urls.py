from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/<str:uidb64>/<str:token>/', views.reset_password_confirm_view, name='reset_password_confirm'),
    path('reset-password/', views.forgot_password_view, name='reset_password'),
    path('verify/', views.verification_view, name='verification'),
    path('verify/<str:uidb64>/<str:token>/', views.verify_email_confirm_view, name='verify_email_confirm'),

    # Phase 12 — Profile Routes
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/tasks/', views.profile_tasks_view, name='profile_tasks'),
    path('profile/bugs/', views.profile_bugs_view, name='profile_bugs'),
    path('profile/activity/', views.profile_activity_view, name='profile_activity'),
    path('profile/roles/', views.profile_roles_view, name='profile_roles'),
    path('profile/avatar/remove/', views.profile_avatar_remove_view, name='profile_avatar_remove'),
    path('profile/banner/remove/', views.profile_banner_remove_view, name='profile_banner_remove'),
    path('profile/u/<uuid:user_id>/', views.public_profile_view, name='public_profile'),
]

