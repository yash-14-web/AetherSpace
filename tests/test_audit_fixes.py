from django.test import TestCase, Client
from django.urls import reverse
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import User, UserRole, ApprovalStatus
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from tasks.models import Task, TaskStatus, TaskPriority, Subtask, TaskAttachment, TaskComment
from bugs.models import Bug, BugStatus, BugPriority, BugSeverity, BugEnvironment, BugAttachment, BugComment
from files.models import StoredFile, FileCategory
from core.templatetags.rich_text import render_rich_text
from notifications.email_backend import CleanConsoleEmailBackend
from notifications.models import Notification


class AuditFixesTestCase(TestCase):
    def setUp(self):
        # Create users
        self.admin = User.objects.create_superuser(
            email='admin@aetherspace.dev',
            password='testpassword123',
            full_name='Platform Admin'
        )
        self.manager = User.objects.create_user(
            email='manager@aetherspace.dev',
            password='testpassword123',
            full_name='Workspace Manager',
            role=UserRole.MANAGER,
            approval_status=ApprovalStatus.APPROVED
        )
        self.developer = User.objects.create_user(
            email='dev@aetherspace.dev',
            password='testpassword123',
            full_name='Lead Developer',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )
        self.outsider = User.objects.create_user(
            email='outsider@aetherspace.dev',
            password='testpassword123',
            full_name='Outsider User',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )

        # Create workspace
        self.workspace = Workspace.objects.create(
            name='Engineering Core',
            slug='engineering-core',
            owner=self.manager
        )

        # Memberships
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.developer,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Task
        self.task = Task.objects.create(
            workspace=self.workspace,
            task_code='619347',
            reporter=self.manager,
            assignee=self.developer,
            title='Implement Real-Time Presence',
            description='Detailed specs for **presence** indicator.',
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH
        )

        # Bug
        self.bug = Bug.objects.create(
            workspace=self.workspace,
            bug_code='B-882316',
            reporter=self.manager,
            assignee=self.developer,
            title='WebRTC Disconnect on Reload',
            description='WebRTC container drops stream.',
            steps_to_reproduce='1. Join call\n2. Press F5',
            expected_result='Stream reconnects automatically',
            actual_result='Socket errors out',
            status=BugStatus.OPEN,
            priority=BugPriority.HIGH,
            severity=BugSeverity.SEV2,
            environment=BugEnvironment.STAGING
        )

        self.client = Client()

    def test_clean_console_email_backend(self):
        """Test CleanConsoleEmailBackend renders without errors."""
        backend = CleanConsoleEmailBackend()
        email = mail.EmailMultiAlternatives(
            subject='Task Assigned: Real-Time Presence',
            body='You have been assigned to task T-100001.',
            from_email='notifications@aetherspace.dev',
            to=[self.developer.email]
        )
        email.attach_alternative('<html><body><h3>Task Assigned</h3><p>Hello</p></body></html>', 'text/html')
        sent = backend.send_messages([email])
        self.assertEqual(sent, 1)

    def test_render_rich_text_markdown_and_sanitization(self):
        """Test markdown rendering, HTML sanitization, and mention badges."""
        raw = "**Bold text** and [Link](https://example.com) <script>alert('xss')</script> @Lead Developer"
        rendered = render_rich_text(raw)
        
        # Markdown bold converted
        self.assertIn('<strong>Bold text</strong>', rendered)
        # Script tags stripped by bleach
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('</script>', rendered)
        # Link preserved
        self.assertIn('href="https://example.com"', rendered)
        # Mention converted to styled badge
        self.assertIn('@Lead Developer', rendered)
        self.assertIn('aether-mention', rendered)

    def test_workspace_members_search_api(self):
        """Test search-first behavior (0 on empty query, live query on typing, workspace scoped)."""
        self.client.force_login(self.developer)

        # Empty search query -> returns 0 results
        url = reverse('workspaces:api_workspace_members_search', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(len(data['members']), 0)

        # Query with match -> returns matching workspace member
        resp = self.client.get(f"{url}?q=Manager")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data['total'], 1)
        self.assertEqual(data['members'][0]['email'], self.manager.email)
        self.assertTrue('contributor_id' in data['members'][0])

        # Query for outsider -> should NOT return non-workspace member
        resp = self.client.get(f"{url}?q=Outsider")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 0)

    def test_user_hover_card_api(self):
        """Test user hover card data and workspace role resolution."""
        self.client.force_login(self.developer)

        url = reverse('accounts:api_user_hover_card', kwargs={'user_identifier': self.manager.id})
        resp = self.client.get(f"{url}?workspace={self.workspace.slug}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['email'], self.manager.email)
        self.assertEqual(data['full_name'], 'Workspace Manager')
        self.assertEqual(data['system_role'], 'Manager')
        self.assertEqual(data['workspace_role'], 'Manager')
        self.assertIsNotNone(data['dm_url'])
        self.assertEqual(data['mailto_url'], f"mailto:{self.manager.email}")

    def test_user_hover_card_permission_denied_for_outsider(self):
        """Outsider who doesn't share workspace with target user gets 403."""
        self.client.force_login(self.outsider)
        url = reverse('accounts:api_user_hover_card', kwargs={'user_identifier': self.manager.id})
        resp = self.client.get(f"{url}?workspace={self.workspace.slug}")
        self.assertEqual(resp.status_code, 403)

    def test_subtask_create_and_toggle_endpoints(self):
        """Test subtasks are persisted to PostgreSQL and toggled cleanly."""
        self.client.force_login(self.developer)

        # Create subtask
        create_url = reverse('tasks:subtask_create', kwargs={
            'slug': self.workspace.slug,
            'task_code': self.task.task_code
        })
        resp = self.client.post(create_url, {'title': 'Write unit tests'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        subtask_id = data['subtask']['id']

        # Verify DB persistence
        st = Subtask.objects.get(id=subtask_id)
        self.assertEqual(st.title, 'Write unit tests')
        self.assertFalse(st.is_completed)

        # Toggle subtask
        toggle_url = reverse('tasks:subtask_toggle', kwargs={
            'slug': self.workspace.slug,
            'task_code': self.task.task_code,
            'subtask_id': subtask_id
        })
        resp = self.client.post(toggle_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_completed'])

        st.refresh_from_db()
        self.assertTrue(st.is_completed)

    def test_task_and_bug_attachments(self):
        """Test TaskAttachment and BugAttachment database relationships with StoredFile."""
        # Create a StoredFile metadata record
        stored_file = StoredFile.objects.create(
            workspace=self.workspace,
            uploaded_by=self.developer,
            name='spec_doc.pdf',
            original_name='spec_doc.pdf',
            storage_path='engineering-core/spec_doc.pdf',
            mime_type='application/pdf',
            category=FileCategory.DOCUMENT,
            size_bytes=1048576,
            checksum='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        )

        # Attach to Task
        task_att = TaskAttachment.objects.create(
            task=self.task,
            file=stored_file
        )
        self.assertEqual(self.task.attachments.count(), 1)
        self.assertEqual(self.task.attachments.first().file.name, 'spec_doc.pdf')

        # Attach to Bug
        bug_att = BugAttachment.objects.create(
            bug=self.bug,
            file=stored_file
        )
        self.assertEqual(self.bug.attachments.count(), 1)
        self.assertEqual(self.bug.attachments.first().file.name, 'spec_doc.pdf')

    def test_comment_mentions_generate_notifications(self):
        """Test adding a comment with @mention notifies mentioned user."""
        self.client.force_login(self.manager)

        comment_url = reverse('tasks:task_comment_add', kwargs={
            'slug': self.workspace.slug,
            'task_code': self.task.task_code
        })
        # Post comment mentioning Lead Developer
        resp = self.client.post(comment_url, {
            'content': f"Hey @{self.developer.full_name}, please inspect this issue."
        })
        self.assertEqual(resp.status_code, 302)

        # Check in-app notification created for developer
        notif = Notification.objects.filter(
            recipient=self.developer,
            actor=self.manager
        ).first()
        self.assertIsNotNone(notif)
        self.assertIn('mentioned you', notif.title)

    def test_contributor_raise_bug_page_renders_without_variable_lookup_error(self):
        """Verify that a contributor accessing the bug creation page renders HTTP 200 without VariableDoesNotExist."""
        self.client.force_login(self.developer)
        bug_create_url = reverse('bugs:bug_create', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(bug_create_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Raise New Bug")

    def test_visual_organogram_hierarchy_page_renders(self):
        """Verify that the visual Organogram view renders with concentric tier nodes and legend."""
        self.client.force_login(self.manager)
        team_url = reverse('workspaces:team', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(team_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ORGANOGRAM")
        self.assertContains(resp, "Leadership")
        self.assertContains(resp, "Managers / Leads")
        self.assertContains(resp, "Contributors")

    def test_mentions_autocomplete_api_returns_people_and_files(self):
        """Verify that the mentions autocomplete API returns both People and Files sections matching Image 1."""
        self.client.force_login(self.developer)
        
        # Create a file in the workspace
        StoredFile.objects.create(
            workspace=self.workspace,
            uploaded_by=self.developer,
            name='roadmap_presentation.pdf',
            original_name='roadmap_presentation.pdf',
            storage_path='engineering-core/roadmap_presentation.pdf',
            mime_type='application/pdf',
            size_bytes=204800,
            checksum='a1b2c3d4e5f60000000000000000000000000000000000000000000000000000'
        )

        mentions_url = reverse('workspaces:api_workspace_mentions', kwargs={'slug': self.workspace.slug})

        # 1. Test empty query (default when typing '@')
        resp = self.client.get(mentions_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('people', data)
        self.assertIn('files', data)
        self.assertTrue(len(data['people']) > 0)
        self.assertTrue(len(data['files']) > 0)

        # Verify person structure
        person = data['people'][0]
        self.assertIn('full_name', person)
        self.assertIn('email', person)
        self.assertIn('contributor_id', person)

        # Verify file structure
        file_item = data['files'][0]
        self.assertEqual(file_item['name'], 'roadmap_presentation.pdf')
        self.assertIn('url', file_item)

        # 2. Test query filtering by person name
        resp_filtered = self.client.get(f"{mentions_url}?q=Lead")
        self.assertEqual(resp_filtered.status_code, 200)
        data_filtered = resp_filtered.json()
        self.assertTrue(any('Lead' in p['full_name'] for p in data_filtered['people']))

        # 3. Test query filtering by file name
        resp_file_search = self.client.get(f"{mentions_url}?q=roadmap")
        self.assertEqual(resp_file_search.status_code, 200)
        data_file_search = resp_file_search.json()
        self.assertTrue(any('roadmap' in f['name'].lower() for f in data_file_search['files']))

    def test_people_hover_card_renders_teleported_to_body(self):
        """Verify that the hover card is rendered with x-teleport to body so it cannot be clipped by comment overflow."""
        self.client.force_login(self.manager)
        task_url = reverse('tasks:task_detail', kwargs={'slug': self.workspace.slug, 'task_code': self.task.task_code})
        resp = self.client.get(task_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'x-teleport="body"')
        self.assertContains(resp, 'aether-hover-card fixed z-[99999]')

    def test_bug_form_renders_integrated_editor_and_textareas(self):
        """Verify bug create form renders integrated rich text editor with textarea and buttons."""
        self.client.force_login(self.developer)
        bug_create_url = reverse('bugs:bug_create', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(bug_create_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="description"')
        self.assertContains(resp, 'name="steps_to_reproduce"')
        self.assertContains(resp, 'Markdown supported')
        self.assertContains(resp, 'applyFormat')

    def test_profile_form_banner_and_avatar_urls(self):
        """Verify profile form accepts valid inputs and avatar form accepts image URLs."""
        from accounts.forms import ProfileUpdateForm, AvatarUploadForm
        
        profile_form = ProfileUpdateForm(data={
            'full_name': 'Developer Updated',
            'headline': 'Full Stack Engineer',
            'bio': 'Passionate about high-performance software.',
            'timezone': 'UTC',
        })
        self.assertTrue(profile_form.is_valid(), f"ProfileForm errors: {profile_form.errors}")

        avatar_form = AvatarUploadForm(data={
            'avatar_url': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200&q=80',
        })
        self.assertTrue(avatar_form.is_valid(), f"AvatarForm errors: {avatar_form.errors}")


