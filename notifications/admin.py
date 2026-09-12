from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'category', 'notification_type', 'is_read', 'workspace', 'created_at')
    list_filter = ('category', 'notification_type', 'is_read', 'workspace', 'created_at')
    search_fields = ('title', 'body', 'recipient__email', 'recipient__full_name')
    readonly_fields = ('id', 'created_at', 'read_at')
