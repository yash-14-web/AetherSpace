import io
import uuid
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from files.models import (
    Folder,
    StoredFile,
    FileCategory,
    FileShare,
    FileShareAccess,
    FileVersion,
    FileComment,
    FileActivity,
)
from files.services import (
    SupabaseStorageService,
    compute_sha256,
    detect_file_category,
    detect_external_provider,
    get_workspace_storage_metrics,
    MAX_FILE_SIZE_BYTES,
)

User = get_user_model()


class FilesModuleTests(TestCase):
    def setUp(self):
        # Users
        self.owner = User.objects.create_user(
            email='owner@aetherspace.dev',
            password='TestPassword123!',
            full_name='Alice Owner'
        )
        self.manager = User.objects.create_user(
            email='manager@aetherspace.dev',
            password='TestPassword123!',
            full_name='Mark Manager'
        )
        self.contributor = User.objects.create_user(
            email='dev@aetherspace.dev',
            password='TestPassword123!',
            full_name='Dave Dev'
        )
        self.other_user = User.objects.create_user(
            email='stranger@aetherspace.dev',
            password='TestPassword123!',
            full_name='Sam Stranger'
        )

        # Workspace A
        self.workspace_a = Workspace.objects.create(
            name='Alpha Workspace',
            slug='alpha-workspace',
            owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.owner,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Workspace B (isolated)
        self.workspace_b = Workspace.objects.create(
            name='Beta Workspace',
            slug='beta-workspace',
            owner=self.other_user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_b,
            user=self.other_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        self.client = Client()

    def test_category_and_provider_detection(self):
        """Test file category and external cloud link provider detection."""
        self.assertEqual(detect_file_category('doc.pdf'), FileCategory.DOCUMENT)
        self.assertEqual(detect_file_category('sheet.xlsx'), FileCategory.SPREADSHEET)
        self.assertEqual(detect_file_category('slides.pptx'), FileCategory.PRESENTATION)
        self.assertEqual(detect_file_category('photo.png'), FileCategory.IMAGE)
        self.assertEqual(detect_file_category('script.py'), FileCategory.CODE)
        self.assertEqual(detect_file_category('archive.zip'), FileCategory.ARCHIVE)
        self.assertEqual(detect_file_category('notes.md'), FileCategory.CODE)
        self.assertEqual(detect_file_category('anything', is_url=True), FileCategory.URL_LINK)

        self.assertEqual(detect_external_provider('https://www.figma.com/file/123/design'), 'Figma Design')
        self.assertEqual(detect_external_provider('https://drive.google.com/drive/folders/456'), 'Google Drive')
        self.assertEqual(detect_external_provider('https://github.com/aetherspace/repo'), 'GitHub')
        self.assertEqual(detect_external_provider('https://notion.so/workspace/doc'), 'Notion')
        self.assertEqual(detect_external_provider('https://example.com/asset.pdf'), 'Web Resource')

    def test_folder_hierarchy_and_breadcrumbs(self):
        """Test creating nested folders and retrieving ancestors."""
        parent_folder = Folder.objects.create(
            workspace=self.workspace_a,
            name='Project Docs',
            created_by=self.owner
        )
        sub_folder = Folder.objects.create(
            workspace=self.workspace_a,
            parent=parent_folder,
            name='Sprint 02',
            created_by=self.manager
        )

        ancestors = sub_folder.get_ancestors()
        self.assertEqual(len(ancestors), 1)
        self.assertEqual(ancestors[0], parent_folder)
        self.assertEqual(parent_folder.subfolders.count(), 1)

    def test_file_upload_direct_and_local_fallback(self):
        """Test uploading a file directly with SHA-256 calculation and version creation."""
        self.client.force_login(self.contributor)
        file_content = b"Hello, AetherSpace file management!"
        upload_file = SimpleUploadedFile("readme.txt", file_content, content_type="text/plain")

        response = self.client.post(
            reverse('files:file_upload', kwargs={'slug': self.workspace_a.slug}),
            {
                'upload_type': 'file',
                'file': upload_file,
                'name': 'Custom Readme',
                'description': 'Important guidelines',
                'tags': 'guide, docs'
            },
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        stored = StoredFile.objects.filter(workspace=self.workspace_a, name='Custom Readme').first()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.original_name, 'readme.txt')
        self.assertEqual(stored.size_bytes, len(file_content))
        self.assertEqual(stored.category, FileCategory.CODE)
        self.assertEqual(stored.uploaded_by, self.contributor)
        self.assertTrue(stored.checksum)
        self.assertEqual(stored.versions.count(), 1)
        self.assertEqual(stored.tag_list, ['guide', 'docs'])

    def test_file_upload_cloud_link(self):
        """Test adding an external URL link (e.g. Figma / Drive) to save storage quota."""
        self.client.force_login(self.manager)
        figma_url = "https://www.figma.com/file/abc123xyz/AetherSpace-UI"

        response = self.client.post(
            reverse('files:file_upload', kwargs={'slug': self.workspace_a.slug}),
            {
                'upload_type': 'link',
                'external_url': figma_url,
                'name': 'Design System Figma',
                'description': 'Main UI components library',
                'tags': 'ui, figma'
            },
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        stored = StoredFile.objects.filter(workspace=self.workspace_a, is_external_link=True).first()
        self.assertIsNotNone(stored)
        self.assertEqual(stored.external_url, figma_url)
        self.assertEqual(stored.size_bytes, 0)
        self.assertEqual(stored.formatted_size, 'External Link')
        self.assertEqual(stored.category, FileCategory.URL_LINK)

    def test_file_size_limit_enforcement(self):
        """Files exceeding 20 MB must be rejected with validation error."""
        self.client.force_login(self.contributor)
        oversized_content = b"x" * (MAX_FILE_SIZE_BYTES + 1024)
        oversized_file = SimpleUploadedFile("huge_file.zip", oversized_content, content_type="application/zip")

        response = self.client.post(
            reverse('files:file_upload', kwargs={'slug': self.workspace_a.slug}),
            {
                'upload_type': 'file',
                'file': oversized_file,
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exceeds maximum allowed limit of 20 MB")
        self.assertFalse(StoredFile.objects.filter(name='huge_file.zip').exists())

    def test_workspace_isolation(self):
        """User in Workspace A cannot view, download, or delete files belonging to Workspace B."""
        # Create file in Workspace B
        secret_file = StoredFile.objects.create(
            workspace=self.workspace_b,
            uploaded_by=self.other_user,
            name='Secret Beta File.pdf',
            original_name='Secret Beta File.pdf',
            storage_path='workspaces/beta/secret.pdf',
            mime_type='application/pdf',
            size_bytes=1024,
        )

        # Contributor from Workspace A tries to access file in Workspace B
        self.client.force_login(self.contributor)

        # Access detail view in Workspace B
        response = self.client.get(
            reverse('files:file_detail', kwargs={'slug': self.workspace_b.slug, 'file_id': secret_file.id})
        )
        self.assertEqual(response.status_code, 403)

        # Download file from Workspace B
        download_resp = self.client.get(
            reverse('files:file_download', kwargs={'slug': self.workspace_b.slug, 'file_id': secret_file.id})
        )
        self.assertEqual(download_resp.status_code, 403)

    def test_rbac_file_deletion(self):
        """
        Contributor can delete own files.
        Contributor CANNOT delete files uploaded by others unless they have manager/admin role.
        """
        file_by_owner = StoredFile.objects.create(
            workspace=self.workspace_a,
            uploaded_by=self.owner,
            name='Owner Specs.docx',
            original_name='Owner Specs.docx',
            size_bytes=2048,
        )

        file_by_contributor = StoredFile.objects.create(
            workspace=self.workspace_a,
            uploaded_by=self.contributor,
            name='Dev Notes.txt',
            original_name='Dev Notes.txt',
            size_bytes=512,
        )

        # Contributor attempts to delete owner's file -> 403 Forbidden
        self.client.force_login(self.contributor)
        resp = self.client.post(
            reverse('files:file_delete', kwargs={'slug': self.workspace_a.slug, 'file_id': file_by_owner.id})
        )
        self.assertEqual(resp.status_code, 403)
        file_by_owner.refresh_from_db()
        self.assertFalse(file_by_owner.is_trashed)

        # Contributor deletes own file -> 200 / 302 OK
        resp_own = self.client.post(
            reverse('files:file_delete', kwargs={'slug': self.workspace_a.slug, 'file_id': file_by_contributor.id})
        )
        self.assertEqual(resp_own.status_code, 302)
        file_by_contributor.refresh_from_db()
        self.assertTrue(file_by_contributor.is_trashed)

        # Manager CAN delete owner's file
        self.client.force_login(self.manager)
        resp_mgr = self.client.post(
            reverse('files:file_delete', kwargs={'slug': self.workspace_a.slug, 'file_id': file_by_owner.id})
        )
        self.assertEqual(resp_mgr.status_code, 302)
        file_by_owner.refresh_from_db()
        self.assertTrue(file_by_owner.is_trashed)

    def test_people_search_api_rule(self):
        """
        CRITICAL PEOPLE SEARCH RULE:
        - Empty query (q='') MUST return zero users ([]).
        - Query with text must return matching workspace members.
        """
        self.client.force_login(self.owner)

        # 1. Empty query
        resp_empty = self.client.get(
            reverse('files:member_search_api', kwargs={'slug': self.workspace_a.slug}),
            {'q': ''}
        )
        self.assertEqual(resp_empty.status_code, 200)
        data_empty = resp_empty.json()
        self.assertEqual(data_empty.get('results'), [], "Empty query must return 0 users")

        # 2. Whitespace only query
        resp_space = self.client.get(
            reverse('files:member_search_api', kwargs={'slug': self.workspace_a.slug}),
            {'q': '   '}
        )
        self.assertEqual(resp_space.json().get('results'), [], "Whitespace query must return 0 users")

        # 3. Typed query matching 'Mark'
        resp_match = self.client.get(
            reverse('files:member_search_api', kwargs={'slug': self.workspace_a.slug}),
            {'q': 'Mark'}
        )
        self.assertEqual(resp_match.status_code, 200)
        results = resp_match.json().get('results')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['email'], 'manager@aetherspace.dev')

    def test_file_sharing_and_access(self):
        """Test sharing a file with another user with VIEW and EDIT permissions."""
        test_file = StoredFile.objects.create(
            workspace=self.workspace_a,
            uploaded_by=self.owner,
            name='Shared Specs.pdf',
            original_name='Shared Specs.pdf',
            size_bytes=4096,
        )

        self.client.force_login(self.owner)
        share_resp = self.client.post(
            reverse('files:file_share', kwargs={'slug': self.workspace_a.slug, 'file_id': test_file.id}),
            {
                'user_id': str(self.contributor.id),
                'access_level': 'EDIT',
            },
            follow=True
        )
        self.assertEqual(share_resp.status_code, 200)

        share = FileShare.objects.filter(file=test_file, shared_with=self.contributor).first()
        self.assertIsNotNone(share)
        self.assertEqual(share.access_level, FileShareAccess.EDIT)

    def test_all_files_views_render(self):
        """Verify all 6 Files views render successfully (HTTP 200)."""
        self.client.force_login(self.owner)

        folder = Folder.objects.create(
            workspace=self.workspace_a,
            name='General Docs',
            created_by=self.owner
        )

        stored = StoredFile.objects.create(
            workspace=self.workspace_a,
            folder=folder,
            uploaded_by=self.owner,
            name='Overview.pdf',
            original_name='Overview.pdf',
            size_bytes=1024,
            category=FileCategory.DOCUMENT
        )

        # 1. Files Home (Screen 46)
        resp_home = self.client.get(reverse('files:files_home', kwargs={'slug': self.workspace_a.slug}))
        self.assertEqual(resp_home.status_code, 200)
        self.assertContains(resp_home, "Files")
        self.assertContains(resp_home, "General Docs")

        # 2. Folder View (Screen 47)
        resp_folder = self.client.get(reverse('files:folder_view', kwargs={'slug': self.workspace_a.slug, 'folder_id': folder.id}))
        self.assertEqual(resp_folder.status_code, 200)
        self.assertContains(resp_folder, "General Docs")

        # 3. File Detail (Screen 48)
        resp_detail = self.client.get(reverse('files:file_detail', kwargs={'slug': self.workspace_a.slug, 'file_id': stored.id}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, "Overview.pdf")

        # 4. Upload File Page (Screen 49)
        resp_upload = self.client.get(reverse('files:file_upload', kwargs={'slug': self.workspace_a.slug}))
        self.assertEqual(resp_upload.status_code, 200)
        self.assertContains(resp_upload, "Upload Files")

        # 5. Recent Files (Screen 50)
        resp_recent = self.client.get(reverse('files:recent_files', kwargs={'slug': self.workspace_a.slug}))
        self.assertEqual(resp_recent.status_code, 200)
        self.assertContains(resp_recent, "Recent Files")

        # 6. Shared Files (Screen 51)
        resp_shared = self.client.get(reverse('files:shared_files', kwargs={'slug': self.workspace_a.slug}))
        self.assertEqual(resp_shared.status_code, 200)
        self.assertContains(resp_shared, "Shared Files")
