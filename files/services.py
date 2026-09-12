import os
import re
import mimetypes
import hashlib
import logging
from urllib.parse import urlparse
from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import requests

from .models import StoredFile, Folder, FileCategory, FileShare, FileActivity

logger = logging.getLogger(__name__)

# Max upload limits per free-tier architecture (docs/05_FREE_TIER_ARCHITECTURE.md)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB max general limit
DEFAULT_STORAGE_QUOTA_MB = 50  # 50 MB default quota for Supabase Free Tier
DEFAULT_STORAGE_QUOTA_BYTES = DEFAULT_STORAGE_QUOTA_MB * 1024 * 1024

DANGEROUS_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'com', 'msi', 'scr', 'vbs', 'vbe', 'wsf', 'wsh', 'ps1'
}


def sanitize_filename(filename):
    """Clean filename to avoid directory traversal or dangerous characters."""
    clean = re.sub(r'[^a-zA-Z0-9_.\- ]', '_', filename)
    clean = clean.strip().lstrip('.')
    return clean or 'unnamed_file'


def compute_sha256(file_obj):
    """Calculate SHA256 checksum of an uploaded file."""
    sha = hashlib.sha256()
    file_obj.seek(0)
    for chunk in file_obj.chunks(chunk_size=65536):
        sha.update(chunk)
    file_obj.seek(0)
    return sha.hexdigest()


def detect_file_category(filename, mime_type='', is_url=False):
    """Categorize file for filtering and icon display."""
    if is_url:
        return FileCategory.URL_LINK

    ext = os.path.splitext(filename)[1].lstrip('.').lower()

    if ext in ['pdf']:
        return FileCategory.DOCUMENT
    if ext in ['doc', 'docx', 'odt', 'rtf', 'pages']:
        return FileCategory.DOCUMENT
    if ext in ['xls', 'xlsx', 'csv', 'tsv', 'ods', 'numbers']:
        return FileCategory.SPREADSHEET
    if ext in ['ppt', 'pptx', 'odp', 'key']:
        return FileCategory.PRESENTATION
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico'] or mime_type.startswith('image/'):
        return FileCategory.IMAGE
    if ext in ['mp4', 'webm', 'mov', 'avi', 'mkv'] or mime_type.startswith('video/'):
        return FileCategory.VIDEO
    if ext in ['mp3', 'wav', 'ogg', 'm4a', 'flac'] or mime_type.startswith('audio/'):
        return FileCategory.AUDIO
    if ext in ['zip', 'rar', 'tar', 'gz', '7z', 'bz2']:
        return FileCategory.ARCHIVE
    if ext in ['py', 'js', 'ts', 'jsx', 'tsx', 'html', 'css', 'json', 'md', 'txt', 'sql', 'sh', 'yml', 'yaml', 'xml']:
        return FileCategory.CODE
    return FileCategory.OTHER


def detect_external_provider(url):
    """Identify cloud platform if the URL is an external link."""
    domain = urlparse(url).netloc.lower()
    if 'figma.com' in domain:
        return 'Figma Design'
    if 'drive.google.com' in domain or 'docs.google.com' in domain:
        return 'Google Drive'
    if 'github.com' in domain:
        return 'GitHub'
    if 'notion.so' in domain or 'notion.site' in domain:
        return 'Notion'
    if 'dropbox.com' in domain:
        return 'Dropbox'
    if 'box.com' in domain:
        return 'Box'
    if 'loom.com' in domain:
        return 'Loom Video'
    if 'youtube.com' in domain or 'youtu.be' in domain:
        return 'YouTube'
    return 'Web Resource'


class SupabaseStorageService:
    """
    Handles storage interactions.
    Prioritizes Supabase Cloud Storage if credentials and bucket are configured;
    falls back cleanly to Django media storage for offline development and testing.
    """

    @classmethod
    def is_supabase_configured(cls):
        """
        Returns True only when Supabase is enabled and the bucket is ready.
        Bypasses during unit tests or when user hasn't created the bucket yet.
        """
        import sys
        if 'test' in sys.argv:
            return False

        if os.environ.get('DISABLE_SUPABASE_STORAGE', '').lower() in ['true', '1']:
            return False

        # Configured when bucket is ready in Supabase project
        bucket_ready = (
            getattr(settings, 'SUPABASE_STORAGE_READY', False) or 
            os.environ.get('SUPABASE_STORAGE_READY', '').lower() in ['true', '1']
        )
        if not bucket_ready:
            return False

        url = getattr(settings, 'SUPABASE_URL', '')
        key = getattr(settings, 'SUPABASE_SECRET_KEY', '') or getattr(settings, 'SUPABASE_PUBLISHABLE_KEY', '')
        bucket = getattr(settings, 'SUPABASE_STORAGE_BUCKET', '')
        return bool(url and key and bucket and not url.startswith('http://test') and not url.startswith('https://example'))

    @classmethod
    def upload_file(cls, file_obj, workspace_id, filename, content_type='application/octet-stream'):
        """
        Uploads a file to storage and returns relative storage_path.
        """
        import uuid
        unique_prefix = uuid.uuid4().hex[:12]
        sanitized = sanitize_filename(filename)
        storage_path = f"workspaces/{workspace_id}/{unique_prefix}_{sanitized}"

        # If Supabase credentials exist, try uploading via REST API
        if cls.is_supabase_configured():
            try:
                base_url = settings.SUPABASE_URL.rstrip('/')
                bucket = settings.SUPABASE_STORAGE_BUCKET
                api_url = f"{base_url}/storage/v1/object/{bucket}/{storage_path}"
                headers = {
                    'Authorization': f"Bearer {settings.SUPABASE_SECRET_KEY or settings.SUPABASE_PUBLISHABLE_KEY}",
                    'Content-Type': content_type,
                    'x-upsert': 'true'
                }
                file_obj.seek(0)
                resp = requests.post(api_url, headers=headers, data=file_obj.read(), timeout=15)
                file_obj.seek(0)
                if resp.status_code in [200, 201]:
                    return storage_path
                else:
                    logger.warning(f"Supabase upload returned {resp.status_code}: {resp.text}. Falling back to local storage.")
            except Exception as e:
                logger.warning(f"Supabase upload failed ({str(e)}). Falling back to local storage.")
                file_obj.seek(0)

        # Fallback to local storage
        file_obj.seek(0)
        saved_name = default_storage.save(storage_path, ContentFile(file_obj.read()))
        file_obj.seek(0)
        return saved_name

    @classmethod
    def get_file_content(cls, storage_path):
        """
        Retrieve raw file bytes and content type.
        """
        if cls.is_supabase_configured():
            try:
                base_url = settings.SUPABASE_URL.rstrip('/')
                bucket = settings.SUPABASE_STORAGE_BUCKET
                api_url = f"{base_url}/storage/v1/object/authenticated/{bucket}/{storage_path}"
                headers = {
                    'Authorization': f"Bearer {settings.SUPABASE_SECRET_KEY or settings.SUPABASE_PUBLISHABLE_KEY}",
                }
                resp = requests.get(api_url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    content_type = resp.headers.get('Content-Type', 'application/octet-stream')
                    return resp.content, content_type
            except Exception as e:
                logger.warning(f"Supabase download failed ({str(e)}). Checking local storage.")

        if default_storage.exists(storage_path):
            with default_storage.open(storage_path, 'rb') as f:
                content = f.read()
                mime, _ = mimetypes.guess_type(storage_path)
                return content, (mime or 'application/octet-stream')

        return None, None

    @classmethod
    def delete_file(cls, storage_path):
        """
        Delete file from storage.
        """
        if not storage_path:
            return

        if cls.is_supabase_configured():
            try:
                base_url = settings.SUPABASE_URL.rstrip('/')
                bucket = settings.SUPABASE_STORAGE_BUCKET
                api_url = f"{base_url}/storage/v1/object/{bucket}/{storage_path}"
                headers = {
                    'Authorization': f"Bearer {settings.SUPABASE_SECRET_KEY or settings.SUPABASE_PUBLISHABLE_KEY}",
                }
                requests.delete(api_url, headers=headers, timeout=10)
            except Exception as e:
                logger.warning(f"Supabase delete failed: {str(e)}")

        if default_storage.exists(storage_path):
            try:
                default_storage.delete(storage_path)
            except Exception as e:
                logger.warning(f"Local storage delete failed: {str(e)}")

    @classmethod
    def get_download_url(cls, stored_file):
        """
        Generates appropriate download URL:
        - If external link -> external_url
        - Otherwise returns workspace-protected view URL
        """
        if stored_file.is_external_link:
            return stored_file.external_url
        from django.urls import reverse
        return reverse('files:file_download', kwargs={'slug': stored_file.workspace.slug, 'file_id': stored_file.id})


def log_file_activity(stored_file, actor, action, details=''):
    """Record an audit entry for a file."""
    try:
        FileActivity.objects.create(
            file=stored_file,
            actor=actor,
            action=action,
            details=details
        )
    except Exception as e:
        logger.error(f"Failed to log file activity: {e}")


def get_workspace_storage_metrics(workspace, user=None):
    """
    Computes storage metrics for a workspace:
    - Total files count
    - Total folders count
    - Total shared with user count
    - Storage used in bytes and formatted
    - Storage quota percentage (out of 100 GB)
    """
    files_qs = StoredFile.objects.filter(workspace=workspace, is_trashed=False)
    total_files = files_qs.count()
    total_folders = Folder.objects.filter(workspace=workspace).count()

    total_bytes = 0
    for f in files_qs:
        if not f.is_external_link:
            total_bytes += f.size_bytes

    shared_with_me = 0
    if user and user.is_authenticated:
        shared_with_me = FileShare.objects.filter(
            file__workspace=workspace,
            file__is_trashed=False,
            shared_with=user
        ).count()

    # Formatted strings
    used_size = total_bytes
    formatted_used = "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if used_size < 1024.0:
            formatted_used = f"{used_size:.1f} {unit}" if unit != 'B' else f"{int(used_size)} {unit}"
            break
        used_size /= 1024.0

    # Storage quota calculation based on workspace allocation (defaults to 50 MB)
    quota_mb = getattr(workspace, 'storage_quota_mb', DEFAULT_STORAGE_QUOTA_MB) or DEFAULT_STORAGE_QUOTA_MB
    quota_bytes = quota_mb * 1024 * 1024
    percentage = min(100.0, (total_bytes / quota_bytes) * 100) if quota_bytes else 0
    quota_label = f"{quota_mb} MB" if quota_mb < 1024 else f"{quota_mb / 1024:.1f} GB"
    remaining_bytes = max(0, quota_bytes - total_bytes)

    return {
        'total_files': total_files,
        'total_folders': total_folders,
        'shared_with_me': shared_with_me,
        'total_bytes': total_bytes,
        'quota_bytes': quota_bytes,
        'remaining_bytes': remaining_bytes,
        'formatted_used': formatted_used,
        'quota_label': quota_label,
        'percentage': round(percentage, 1),
    }
