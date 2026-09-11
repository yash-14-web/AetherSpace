from django.urls import path
from . import views

app_name = 'calendars'

urlpatterns = [
    # Global entry router
    path('', views.calendar_router, name='calendar_router'),

    # Workspace scoped views
    path('w/<slug:slug>/', views.calendar_view, name='calendar_view'),
    path('w/<slug:slug>/agenda/', views.agenda_view, name='agenda_view'),
    path('w/<slug:slug>/deadlines/', views.upcoming_deadlines_view, name='upcoming_deadlines'),
    path('w/<slug:slug>/events/create/', views.event_create_view, name='event_create'),
    path('w/<slug:slug>/events/<uuid:event_id>/', views.event_detail_view, name='event_detail'),
    path('w/<slug:slug>/events/<uuid:event_id>/edit/', views.event_edit_view, name='event_edit'),
    path('w/<slug:slug>/events/<uuid:event_id>/delete/', views.event_delete_view, name='event_delete'),

    # Asynchronous feed API
    path('w/<slug:slug>/api/feed/', views.calendar_feed_api, name='calendar_feed_api'),
]
