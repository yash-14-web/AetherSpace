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
]
