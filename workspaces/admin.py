from django.contrib import admin
from .models import Workspace, WorkspaceMembership, WorkspaceInvitation, WorkspaceAccessRequest


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'owner', 'status', 'member_count', 'created_at')
    search_fields = ('name', 'slug', 'owner__email')
    list_filter = ('status', 'created_at')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'workspace', 'role', 'status', 'joined_at')
    list_filter = ('role', 'status', 'workspace')
    search_fields = ('user__email', 'workspace__name')


@admin.register(WorkspaceInvitation)
class WorkspaceInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'workspace', 'role', 'status', 'invited_by', 'created_at', 'expires_at')
    list_filter = ('role', 'status', 'workspace')
    search_fields = ('email', 'workspace__name')


@admin.register(WorkspaceAccessRequest)
class WorkspaceAccessRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'workspace', 'status', 'created_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'workspace')
    search_fields = ('user__email', 'workspace__name')
