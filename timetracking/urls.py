from django.urls import path
from . import views

app_name = 'timetracking'

urlpatterns = [
    path('', views.time_tracking_router, name='router'),
    path('w/<slug:slug>/', views.workspace_timesheet, name='workspace_timesheet'),
    path('w/<slug:slug>/timer/start/', views.api_timer_start, name='api_timer_start'),
    path('w/<slug:slug>/timer/pause/', views.api_timer_pause, name='api_timer_pause'),
    path('w/<slug:slug>/timer/resume/', views.api_timer_resume, name='api_timer_resume'),
    path('w/<slug:slug>/timer/stop/', views.api_timer_stop, name='api_timer_stop'),
    path('w/<slug:slug>/timer/status/', views.api_timer_status, name='api_timer_status'),
    path('w/<slug:slug>/manual/', views.manual_time_entry, name='manual_time_entry'),
    path('w/<slug:slug>/delete/<uuid:entry_id>/', views.delete_time_entry, name='delete_time_entry'),
    path('w/<slug:slug>/export/', views.export_timesheet_csv, name='export_timesheet_csv'),
]
