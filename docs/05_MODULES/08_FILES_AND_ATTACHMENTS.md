# Module 08: Files & Attachments

## 1. Purpose
Provides centralized asset management, hierarchical folder organization, file version history, direct peer sharing, external cloud resource links (Figma, GitHub, Notion), and cloud storage synchronization via Supabase Storage.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `files/models.py`, `files/views.py`, `core/supabase_storage.py`, `files/tests.py`.

## 3. Main User Workflows
1. **Folder Organization**: Users create nested folders (`Folder`) with custom color tags (amber, blue, purple, emerald) to categorize project documents.
2. **File Upload**: Users upload documents, images, PDFs, code files, or archives (`StoredFile`). System validates size against workspace quota, computes SHA-256 checksum, and streams the binary to Supabase Storage (`aetherspace-storage`).
3. **External Cloud Links**: To conserve storage quota, users link external design or doc assets (Figma, Notion, Google Drive). These consume 0 bytes of workspace storage.
4. **File Versioning**: Users upload new revisions (`FileVersion`), preserving historical versions with timestamps and uploader metadata.
5. **Direct Sharing**: Users grant specific team members view or edit access (`FileShare`).
6. **Trash & Recovery**: Files can be moved to Trash (`is_trashed = True`) and restored or permanently purged by Admins.

## 4. User Roles & Permissions
* **Workspace Admin**: Can manage storage quotas, purge trashed files permanently, and view all workspace folders.
* **Workspace Manager**: Can organize folders, share assets, and upload team deliverables.
* **Workspace Contributor**: Can upload files within quota limits, create folders, share their files, and link external resources.

## 5. Pages & Templates
* `templates/files/file_list.html`: Folder grid, file table, storage usage bar, and upload drag-and-drop zone.
* `templates/files/file_detail.html`: File inspection cockpit, metadata, version history, comments, and sharing permissions.
* `templates/files/file_preview.html`: In-browser preview modal for images, PDFs, audio, video, and syntax-highlighted code.
* `templates/files/trash.html`: Trashed file recovery console.

## 6. URLs, Views, Services & Models
* **URLs**: `files/urls.py` (`file_list`, `folder_detail`, `file_upload`, `file_detail`, `file_download`, `file_preview`, `file_trash`).
* **Views**: `files/views.py` (`file_list_view`, `file_upload_view`, `file_download_view`, `file_preview_view`).
* **Services**: `core/supabase_storage.py` (`SupabaseStorageClient`).
* **Models**: `Folder`, `StoredFile`, `FileShare`, `FileVersion`, `FileComment`, `FileActivity`.

## 7. Business Rules & Invariants
* Storage Quota Enforcement: Total active file bytes (`Sum('size_bytes')` where `is_trashed=False`) cannot exceed `workspace.storage_quota_bytes`. Over-quota uploads return a descriptive validation error.
* Binary File Isolation: Uploaded binaries are never stored in PostgreSQL columns; only metadata and storage paths are persisted in PostgreSQL.
* URL Sanitization: External link URLs are strictly validated via `core.utils.is_safe_external_url` to prevent `javascript:` execution.

## 8. Database Relationships
* `Folder` belongs to `Workspace` and optionally a parent `Folder` (CASCADE).
* `StoredFile` belongs to `Workspace` and optionally a `Folder` (SET_NULL).
* `StoredFile` has many `FileVersion`, `FileShare`, `FileComment`, `FileActivity` (CASCADE).

## 9. API & WebSocket Interactions
* `POST /files/w/<slug>/api/upload/`: Asynchronous chunked or multi-file upload endpoint.
* File downloads proxy through authenticated Django view (`files:file_download`), validating workspace membership before streaming.

## 10. Notifications & Integrations
* Dispatches `FILE_SHARED` notification when files are directly shared with team members.
* Integrated with Tasks, Bugs, Chat, and Calendars as linked attachments.

## 11. Error States & Edge Cases
* Exceeding storage quota -> `ValidationError: "Workspace storage quota exceeded. Upgrade quota or link external URLs."`
* Corrupted file download -> Returns `404 Not Found` if object is missing from storage bucket.

## 12. Tests & Verification Evidence
* `files/tests.py`: Unit tests for file upload validation, folder hierarchy, versioning, quota calculation, and trash recovery.

## 13. Known Limitations
* Direct browser-to-bucket S3 presigned URL uploads are not currently enabled; uploads pass through the Django backend proxy to enforce server-side quota checks.

## 14. Future Work
* Full-text search indexing of PDF and text document contents.
