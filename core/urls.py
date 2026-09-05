from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('test/400/', views.error_400, name='test_400'),
    path('test/403/', views.error_403, name='test_403'),
    path('test/404/', views.error_404, name='test_404'),
    path('test/500/', views.error_500, name='test_500'),
]
