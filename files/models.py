import os
import uuid
from django.db import models
from django.conf import settings
from django.urls import reverse
from workspaces.models import Workspace


class FileCategory(models.TextChoices):
    DOCUMENT = 'DOCUMENT', 'Document'
    IMAGE = 'IMAGE', 'Image'
    SPREADSHEET = 'SPREADSHEET', 'Spreadsheet'
    PRESENTATION = 'PRESENTATION', 'Presentation'
    CODE = 'CODE', 'Code / Text'
    ARCHIVE = 'ARCHIVE', 'Archive'
    AUDIO = 'AUDIO', 'Audio'
    VIDEO = 'VIDEO', 'Video'
    URL_LINK = 'URL_LINK', 'External Link'
    OTHER = 'OTHER', 'Other'


class Folder(models.Model):
    """
    Hierarchical folder structure scoped to a Workspace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='folders'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subfolders'
    )
    name = models.CharField(max_length=150)
    color = models.CharField(max_length=30, default='amber')
    is_starred = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_folders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'parent', 'name'],
                name='unique_folder_per_parent'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.workspace.name})"

    @property
    def file_count(self):
        return self.files.filter(is_trashed=False).count()

    @property
    def total_size_bytes(self):
        total = self.files.filter(is_trashed=False).aggregate(models.Sum('size_bytes'))['size_bytes__sum']
        return total or 0

    @property
    def formatted_size(self):
        size = self.total_size_bytes
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def get_ancestors(self):
        """Returns list of parent folders from root to current parent."""
        ancestors = []
        curr = self.parent
        while curr:
            ancestors.insert(0, curr)
            curr = curr.parent
        return ancestors


class StoredFile(models.Model):
    """
    Metadata for files stored in Supabase Cloud Object Storage (or local storage fallback),
    as well as External Cloud Links (Figma, Drive, GitHub, Notion, Web URLs) to save quota.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='files'
    )
    folder = models.ForeignKey(
        Folder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='files'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='uploaded_files'
    )
    name = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    storage_path = models.CharField(max_length=500, blank=True, default='')
    external_url = models.URLField(max_length=1000, blank=True, default='')
    is_external_link = models.BooleanField(default=False)
    mime_type = models.CharField(max_length=120, blank=True, default='application/octet-stream')
    category = models.CharField(
        max_length=20,
        choices=FileCategory.choices,
        default=FileCategory.OTHER
    )
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default='')
    description = models.TextField(blank=True, default='')
    tags = models.CharField(max_length=255, blank=True, default='')
    is_starred = models.BooleanField(default=False)
    is_trashed = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(auto_now_add=True)
    last_accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_accessed_files'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['workspace', 'is_trashed', '-updated_at']),
            models.Index(fields=['workspace', 'folder', 'is_trashed']),
            models.Index(fields=['workspace', 'category']),
        ]

    def __str__(self):
        return f"{self.name} ({self.workspace.name})"

    @property
    def extension(self):
        if self.is_external_link:
            return 'link'
        _, ext = os.path.splitext(self.original_name)
        return ext.lstrip('.').lower()

    @property
    def formatted_size(self):
        if self.is_external_link:
            return 'External Link'
        size = self.size_bytes
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    @property
    def tag_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    @property
    def is_image(self):
        return self.category == FileCategory.IMAGE or self.mime_type.startswith('image/')

    @property
    def is_pdf(self):
        return self.mime_type == 'application/pdf' or self.extension == 'pdf'

    @property
    def is_text_or_code(self):
        return self.category == FileCategory.CODE or self.mime_type.startswith('text/') or self.extension in [
            'txt', 'md', 'py', 'js', 'html', 'css', 'json', 'yml', 'yaml', 'sql', 'sh', 'ts'
        ]

    @property
    def is_previewable(self):
        return self.is_image or self.is_pdf or self.is_text_or_code or self.is_external_link

    @property
    def badge_theme(self):
        """Returns visual styling classes for the file extension badge."""
        ext = self.extension
        if self.is_external_link:
            return {
                'bg': 'bg-indigo-500/10 dark:bg-indigo-500/20',
                'text': 'text-indigo-600 dark:text-indigo-400',
                'border': 'border-indigo-500/20 dark:border-indigo-500/30',
                'label': 'LINK'
            }
        if ext in ['pdf']:
            return {
                'bg': 'bg-rose-500/10 dark:bg-rose-500/20',
                'text': 'text-rose-600 dark:text-rose-400',
                'border': 'border-rose-500/20 dark:border-rose-500/30',
                'label': 'PDF'
            }
        elif ext in ['doc', 'docx', 'odt']:
            return {
                'bg': 'bg-blue-500/10 dark:bg-blue-500/20',
                'text': 'text-blue-600 dark:text-blue-400',
                'border': 'border-blue-500/20 dark:border-blue-500/30',
                'label': 'DOC'
            }
        elif ext in ['xls', 'xlsx', 'csv']:
            return {
                'bg': 'bg-emerald-500/10 dark:bg-emerald-500/20',
                'text': 'text-emerald-600 dark:text-emerald-400',
                'border': 'border-emerald-500/20 dark:border-emerald-500/30',
                'label': 'XLS'
            }
        elif ext in ['ppt', 'pptx']:
            return {
                'bg': 'bg-amber-500/10 dark:bg-amber-500/20',
                'text': 'text-amber-600 dark:text-amber-400',
                'border': 'border-amber-500/20 dark:border-amber-500/30',
                'label': 'PPT'
            }
        elif ext in ['zip', 'rar', 'tar', 'gz', '7z']:
            return {
                'bg': 'bg-yellow-500/10 dark:bg-yellow-500/20',
                'text': 'text-yellow-600 dark:text-yellow-400',
                'border': 'border-yellow-500/20 dark:border-yellow-500/30',
                'label': 'ZIP'
            }
        elif self.is_image:
            return {
                'bg': 'bg-purple-500/10 dark:bg-purple-500/20',
                'text': 'text-purple-600 dark:text-purple-400',
                'border': 'border-purple-500/20 dark:border-purple-500/30',
                'label': ext.upper() if ext else 'IMG'
            }
        elif self.is_text_or_code:
            return {
                'bg': 'bg-cyan-500/10 dark:bg-cyan-500/20',
                'text': 'text-cyan-600 dark:text-cyan-400',
                'border': 'border-cyan-500/20 dark:border-cyan-500/30',
                'label': ext.upper() if ext else 'CODE'
            }
        return {
            'bg': 'bg-slate-500/10 dark:bg-zinc-500/20',
            'text': 'text-slate-600 dark:text-zinc-400',
            'border': 'border-slate-500/20 dark:border-zinc-500/30',
            'label': ext.upper() if ext else 'FILE'
        }


class FileShareAccess(models.TextChoices):
    VIEW = 'VIEW', 'Can View'
    EDIT = 'EDIT', 'Can Edit'


class FileShare(models.Model):
    """
    Direct user-to-user sharing permissions within a workspace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        StoredFile,
        on_delete=models.CASCADE,
        related_name='shares'
    )
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_file_shares'
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='granted_file_shares'
    )
    access_level = models.CharField(
        max_length=10,
        choices=FileShareAccess.choices,
        default=FileShareAccess.VIEW
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['file', 'shared_with'],
                name='unique_file_user_share'
            )
        ]

    def __str__(self):
        return f"{self.file.name} shared with {self.shared_with.email} ({self.access_level})"


class FileVersion(models.Model):
    """
    Version history for stored files.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        StoredFile,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.PositiveIntegerField(default=1)
    storage_path = models.CharField(max_length=500, blank=True, default='')
    external_url = models.URLField(max_length=1000, blank=True, default='')
    size_bytes = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    checksum = models.CharField(max_length=64, blank=True, default='')
    note = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.file.name} v{self.version_number}"

    @property
    def formatted_size(self):
        if self.file.is_external_link:
            return 'External Link'
        size = self.size_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class FileComment(models.Model):
    """
    Discussion comments attached to a specific file.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        StoredFile,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.author.email} on {self.file.name}"


class FileActivity(models.Model):
    """
    Audit log of actions performed on a file.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        StoredFile,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )
    action = models.CharField(max_length=50)
    details = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.actor.email} {self.action} on {self.file.name}"
