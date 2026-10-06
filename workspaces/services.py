import os
import io
import re
import logging
from urllib.parse import urlparse, quote
from PIL import Image

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from files.services import SupabaseStorageService, sanitize_filename

logger = logging.getLogger(__name__)

# Upload constraints for workspace logo
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB hard limit
ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'svg', 'gif'}


def process_and_save_workspace_logo(workspace, file_obj=None, logo_url=None, remove_logo=False):
    """
    Process, validate, compress, and store the workspace logo:
    1. If remove_logo is True: Clears the workspace logo and restores default initials emblem.
    2. If logo_url is provided: Validates the external/cloud URL and updates workspace.logo.
    3. If file_obj is provided: Validates size (<= 2 MB) and format, optimizes raster images
       to a 256x256 square thumbnail (or sanitizes SVG), and stores in Supabase Storage
       (with local fallback).
    """
    if remove_logo:
        old_logo = workspace.logo
        if old_logo and not old_logo.startswith(('http://', 'https://')):
            try:
                if default_storage.exists(old_logo):
                    default_storage.delete(old_logo)
            except Exception as e:
                logger.warning(f"Failed deleting old logo {old_logo}: {e}")

        workspace.logo = ''
        workspace.save(update_fields=['logo'])
        return True, "Workspace logo removed. Default initials emblem restored."

    if logo_url:
        from core.utils import validate_image_url
        is_valid, clean_url, err_msg = validate_image_url(logo_url)
        if not is_valid:
            return False, err_msg or "Please enter a valid HTTP/HTTPS image URL."
        workspace.logo = clean_url
        workspace.save(update_fields=['logo'])
        return True, "Workspace logo URL updated successfully."

    if file_obj:
        # 1. Size constraint
        if file_obj.size > MAX_LOGO_SIZE_BYTES:
            size_kb = round(file_obj.size / 1024)
            return False, f"File size ({size_kb} KB) exceeds the maximum allowed limit of 2 MB."

        # 2. Extension check
        ext = os.path.splitext(file_obj.name)[1].lstrip('.').lower()
        if ext not in ALLOWED_LOGO_EXTENSIONS:
            return False, f"Unsupported file format '.{ext}'. Allowed formats: PNG, JPG, WEBP, SVG, GIF."

        try:
            content_type = 'image/png'
            filename = f"logo_{workspace.slug}.png"
            final_bytes = None

            if ext == 'svg':
                # SVG handling: read content and ensure no malicious script tags
                file_obj.seek(0)
                svg_content = file_obj.read()
                svg_text = svg_content.decode('utf-8', errors='ignore')
                if '<script' in svg_text.lower():
                    return False, "SVG files containing scripts are rejected for security."
                content_type = 'image/svg+xml'
                filename = f"logo_{workspace.slug}.svg"
                final_bytes = svg_content
            else:
                # Raster image: open with Pillow and resize/crop to 256x256 square
                file_obj.seek(0)
                image = Image.open(file_obj)

                # Keep transparency for PNG/WEBP/GIF if RGBA
                if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                    image = image.convert('RGBA')
                    save_format = 'PNG'
                    content_type = 'image/png'
                    filename = f"logo_{workspace.slug}.png"
                else:
                    image = image.convert('RGB')
                    save_format = 'JPEG'
                    content_type = 'image/jpeg'
                    filename = f"logo_{workspace.slug}.jpg"

                # Center crop to square
                width, height = image.size
                min_dim = min(width, height)
                left = (width - min_dim) / 2
                top = (height - min_dim) / 2
                right = (width + min_dim) / 2
                bottom = (height + min_dim) / 2
                image = image.crop((left, top, right, bottom))

                # Resize to max 256x256
                image.thumbnail((256, 256), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                if save_format == 'PNG':
                    image.save(buffer, format='PNG', optimize=True)
                else:
                    image.save(buffer, format='JPEG', quality=90, optimize=True)
                final_bytes = buffer.getvalue()

            # Upload using SupabaseStorageService (which checks Supabase configuration)
            storage_path = f"workspaces/{workspace.id}/{filename}"
            content_file = ContentFile(final_bytes)

            uploaded_storage_path = SupabaseStorageService.upload_file(
                file_obj=content_file,
                workspace_id=str(workspace.id),
                filename=filename,
                content_type=content_type
            )

            # Ensure local storage also has a copy for instant fallback & local development
            if default_storage.exists(uploaded_storage_path):
                default_storage.delete(uploaded_storage_path)
            saved_local = default_storage.save(uploaded_storage_path, ContentFile(final_bytes))

            # Determine public URL
            if SupabaseStorageService.is_supabase_configured():
                base_url = settings.SUPABASE_URL.rstrip('/')
                bucket = quote(settings.SUPABASE_STORAGE_BUCKET)
                public_url = f"{base_url}/storage/v1/object/public/{bucket}/{uploaded_storage_path}"
                workspace.logo = public_url
            else:
                workspace.logo = default_storage.url(saved_local)

            workspace.save(update_fields=['logo'])
            return True, "Workspace logo uploaded and updated successfully."

        except Exception as e:
            logger.error(f"Workspace logo processing error: {e}", exc_info=True)
            return False, f"Error processing image: {str(e)}"

    return False, "No image file or URL provided."
