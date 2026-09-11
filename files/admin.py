from django.contrib import admin
from .models import Folder, StoredFile, FileShare, FileVersion, FileComment, FileActivity


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'parent', 'created_by', 'created_at')
    list_filter = ('workspace', 'is_starred')
    search_fields = ('name', 'workspace__name', 'created_by__email')


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'workspace', 'folder', 'category', 'is_external_link', 'size_bytes', 'uploaded_by', 'updated_at')
    list_filter = ('workspace', 'category', 'is_external_link', 'is_starred', 'is_trashed')
    search_fields = ('name', 'original_name', 'description', 'tags', 'workspace__name', 'uploaded_by__email')


@admin.register(FileShare)
class FileShareAdmin(admin.ModelAdmin):
    list_display = ('file', 'shared_with', 'shared_by', 'access_level', 'created_at')
    list_filter = ('access_level',)
    search_fields = ('file__name', 'shared_with__email', 'shared_by__email')


@admin.register(FileVersion)
class FileVersionAdmin(admin.ModelAdmin):
    list_display = ('file', 'version_number', 'uploaded_by', 'size_bytes', 'created_at')
    search_fields = ('file__name', 'uploaded_by__email', 'note')


@admin.register(FileComment)
class FileCommentAdmin(admin.ModelAdmin):
    list_display = ('file', 'author', 'created_at')
    search_fields = ('file__name', 'author__email', 'comment')


@admin.register(FileActivity)
class FileActivityAdmin(admin.ModelAdmin):
    list_display = ('file', 'actor', 'action', 'details', 'created_at')
    list_filter = ('action',)
    search_fields = ('file__name', 'actor__email', 'details')
