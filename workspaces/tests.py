from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from accounts.models import UserRole, ApprovalStatus
from workspaces.models import (
    Workspace, WorkspaceMembership, WorkspaceRole,
    WorkspaceInvitation, InvitationStatus, WorkspaceAccessRequest,
    AccessRequestStatus, MembershipStatus, WorkspaceStatus
)

User = get_user_model()


class WorkspaceRBACAndIsolationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        # User 1: Workspace Admin
        self.admin_user = User.objects.create_user(
            email="admin.ws@aetherspace.dev",
            password=self.password,
            full_name="Alice Admin"
        )

        # User 2: Manager (multi-workspace)
        self.manager_user = User.objects.create_user(
            email="manager.ws@aetherspace.dev",
            password=self.password,
            full_name="Bob Manager"
        )

        # User 3: Contributor
        self.contributor_user = User.objects.create_user(
            email="contrib.ws@aetherspace.dev",
            password=self.password,
            full_name="Charlie Contributor"
        )

        # User 4: External / Non-member
        self.external_user = User.objects.create_user(
            email="external.ws@aetherspace.dev",
            password=self.password,
            full_name="Dave External",
            role=UserRole.MANAGER,
            approval_status=ApprovalStatus.APPROVED
        )

        # Primary Workspace
        self.workspace1 = Workspace.objects.create(
            name="Smart Classroom",
            slug="smart-classroom",
            description="Agile education workspace",
            owner=self.admin_user
        )

        # Memberships in Workspace 1
        self.membership_admin = WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.admin_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.membership_manager = WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.manager_user,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        self.membership_contributor = WorkspaceMembership.objects.create(
            workspace=self.workspace1,
            user=self.contributor_user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Second Workspace (Flora AI)
        self.workspace2 = Workspace.objects.create(
            name="Flora AI",
            slug="flora-ai",
            description="GenAI flora recognition project",
            owner=self.manager_user
        )
        # Manager is Admin in Workspace 2
        WorkspaceMembership.objects.create(
            workspace=self.workspace2,
            user=self.manager_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_workspace_creation_sets_owner_and_admin(self):
        """Creating a workspace assigns creator as owner and creates ADMIN membership."""
        self.client.login(email=self.external_user.email, password=self.password)
        url = reverse('workspaces:create')
        response = self.client.post(url, {
            'name': 'Quantum Labs',
            'slug': 'quantum-labs',
            'description': 'Advanced computing workspace',
        })
        self.assertEqual(response.status_code, 302)
        ws = Workspace.objects.get(slug='quantum-labs')
        self.assertEqual(ws.owner, self.external_user)
        membership = WorkspaceMembership.objects.get(workspace=ws, user=self.external_user)
        self.assertEqual(membership.role, WorkspaceRole.ADMIN)
        self.assertTrue(membership.is_admin)

    def test_workspace_isolation_blocks_non_member(self):
        """User without membership receives 403 Forbidden when accessing workspace."""
        self.client.login(email=self.external_user.email, password=self.password)
        url = reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace1.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_manager_multi_workspace_access_and_master_dashboard(self):
        """Manager belonging to multiple workspaces can view both and access Master Dashboard."""
        self.client.login(email=self.manager_user.email, password=self.password)

        # Can view workspace 1
        url1 = reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace1.slug})
        resp1 = self.client.get(url1)
        self.assertEqual(resp1.status_code, 200)
        self.assertContains(resp1, "Smart Classroom")

        # Can view workspace 2
        url2 = reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace2.slug})
        resp2 = self.client.get(url2)
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, "Flora AI")

        # Master dashboard lists both
        master_url = reverse('workspaces:master_dashboard')
        master_resp = self.client.get(master_url)
        self.assertEqual(master_resp.status_code, 200)
        self.assertContains(master_resp, "Smart Classroom")
        self.assertContains(master_resp, "Flora AI")
        self.assertContains(master_resp, "Master Dashboard")

    def test_admin_can_invite_member(self):
        """Admin can issue an invitation with cryptographic token."""
        self.client.login(email=self.admin_user.email, password=self.password)
        url = reverse('workspaces:invite_member', kwargs={'slug': self.workspace1.slug})
        invite_email = "newhire@aetherspace.dev"
        response = self.client.post(url, {
            'email': invite_email,
            'role': WorkspaceRole.CONTRIBUTOR,
        })
        self.assertEqual(response.status_code, 302)
        invite = WorkspaceInvitation.objects.get(workspace=self.workspace1, email=invite_email)
        self.assertEqual(invite.status, InvitationStatus.PENDING)
        self.assertEqual(invite.role, WorkspaceRole.CONTRIBUTOR)
        self.assertEqual(len(invite.token), 43)  # secrets.token_urlsafe(32) base64 string length

    def test_accept_invitation_flow(self):
        """Invited user can accept tokenized invitation and become an active member."""
        invite = WorkspaceInvitation.objects.create(
            workspace=self.workspace1,
            email=self.external_user.email,
            role=WorkspaceRole.CONTRIBUTOR,
            invited_by=self.admin_user,
        )

        self.client.login(email=self.external_user.email, password=self.password)
        accept_url = reverse('workspaces:accept_invitation', kwargs={'token': invite.token})
        
        # GET renders acceptance prompt
        get_resp = self.client.get(accept_url)
        self.assertEqual(get_resp.status_code, 200)
        self.assertContains(get_resp, "Smart Classroom")

        # POST accepts and joins
        post_resp = self.client.post(accept_url)
        self.assertEqual(post_resp.status_code, 302)

        # Verify membership
        membership = WorkspaceMembership.objects.get(workspace=self.workspace1, user=self.external_user)
        self.assertEqual(membership.role, WorkspaceRole.CONTRIBUTOR)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)

        # Invite status updated
        invite.refresh_from_db()
        self.assertEqual(invite.status, InvitationStatus.ACCEPTED)

    def test_contributor_cannot_invite_or_edit_settings(self):
        """Contributors receive 403 when attempting administrative actions."""
        self.client.login(email=self.contributor_user.email, password=self.password)

        invite_url = reverse('workspaces:invite_member', kwargs={'slug': self.workspace1.slug})
        resp1 = self.client.post(invite_url, {'email': 'hacker@evil.com', 'role': 'ADMIN'})
        self.assertEqual(resp1.status_code, 403)

        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace1.slug})
        resp2 = self.client.get(settings_url)
        self.assertEqual(resp2.status_code, 403)

    def test_cannot_demote_or_remove_sole_admin(self):
        """A workspace's sole admin cannot be demoted or removed."""
        self.client.login(email=self.admin_user.email, password=self.password)

        # Try to demote self
        role_url = reverse('workspaces:update_member_role', kwargs={
            'slug': self.workspace1.slug,
            'member_id': self.membership_admin.id
        })
        self.client.post(role_url, {'role': WorkspaceRole.CONTRIBUTOR})
        self.membership_admin.refresh_from_db()
        self.assertEqual(self.membership_admin.role, WorkspaceRole.ADMIN)

        # Try to remove self
        remove_url = reverse('workspaces:remove_member', kwargs={
            'slug': self.workspace1.slug,
            'member_id': self.membership_admin.id
        })
        self.client.post(remove_url)
        self.assertTrue(WorkspaceMembership.objects.filter(id=self.membership_admin.id).exists())

    def test_request_access_flow(self):
        """Unauthorized user can submit access request."""
        self.client.login(email=self.external_user.email, password=self.password)
        url = reverse('workspaces:request_access', kwargs={'slug': self.workspace1.slug})
        response = self.client.post(url, {
            'message': 'Need to view biology lecture materials.',
        })
        self.assertEqual(response.status_code, 302)
        req = WorkspaceAccessRequest.objects.get(workspace=self.workspace1, user=self.external_user)
        self.assertEqual(req.status, AccessRequestStatus.PENDING)
        self.assertEqual(req.message, 'Need to view biology lecture materials.')

    def test_workspace_max_seats_default_and_properties(self):
        """Workspace defaults to 15 seats and calculates seat properties properly."""
        self.assertEqual(self.workspace1.max_seats, 15)
        # 3 active members (admin, manager, contributor)
        self.assertEqual(self.workspace1.seats_assigned, 3)
        self.assertEqual(self.workspace1.seats_remaining, 12)
        self.assertFalse(self.workspace1.is_seats_full)

    def test_admin_can_update_max_seats_in_settings(self):
        """Workspace admin can increase max seats via workspace settings."""
        self.client.login(email=self.admin_user.email, password=self.password)
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace1.slug})
        
        response = self.client.post(settings_url, {
            'name': self.workspace1.name,
            'description': self.workspace1.description,
            'status': self.workspace1.status,
            'max_seats': 30,
        })
        self.assertEqual(response.status_code, 302)
        self.workspace1.refresh_from_db()
        self.assertEqual(self.workspace1.max_seats, 30)
        self.assertEqual(self.workspace1.seats_remaining, 27)

    def test_cannot_lower_seats_below_current_member_count(self):
        """Admin cannot reduce seats below the count of active members."""
        self.client.login(email=self.admin_user.email, password=self.password)
        settings_url = reverse('workspaces:settings', kwargs={'slug': self.workspace1.slug})
        
        # 3 active members, attempt to set max_seats to 2
        response = self.client.post(settings_url, {
            'name': self.workspace1.name,
            'description': self.workspace1.description,
            'status': self.workspace1.status,
            'max_seats': 2,
        })
        self.assertEqual(response.status_code, 200)  # form re-rendered with error
        self.workspace1.refresh_from_db()
        self.assertEqual(self.workspace1.max_seats, 15)  # unchanged

    def test_invite_blocked_when_seats_full(self):
        """Inviting members is blocked when all seats are allocated."""
        self.workspace1.max_seats = 3
        self.workspace1.save()
        self.assertTrue(self.workspace1.is_seats_full)

        self.client.login(email=self.admin_user.email, password=self.password)
        invite_url = reverse('workspaces:invite_member', kwargs={'slug': self.workspace1.slug})
        response = self.client.post(invite_url, {
            'email': 'overflow@aetherspace.dev',
            'role': WorkspaceRole.CONTRIBUTOR,
        })
        self.assertEqual(response.status_code, 302)
        # Should not create invite
        self.assertFalse(WorkspaceInvitation.objects.filter(email='overflow@aetherspace.dev').exists())

    def test_workspace_dashboard_shows_real_bugs(self):
        """Workspace dashboard displays real database bugs and handles empty state."""
        from bugs.models import Bug, BugSeverity, BugStatus
        self.client.login(email=self.admin_user.email, password=self.password)
        dashboard_url = reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace1.slug})

        # Initially 0 bugs - displays professional empty state
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['open_bugs_count'], 0)
        self.assertContains(response, "Zero Active Bugs")

        # Create a real bug
        Bug.objects.create(
            bug_code='B-123456',
            workspace=self.workspace1,
            title='Production latency issue',
            severity=BugSeverity.SEV1,
            status=BugStatus.OPEN,
            reporter=self.admin_user
        )
        response2 = self.client.get(dashboard_url)
        self.assertEqual(response2.context['open_bugs_count'], 1)
        self.assertEqual(response2.context['high_severity_bugs_count'], 1)
        self.assertContains(response2, "B-123456")
        self.assertContains(response2, "Production latency issue")

    def test_workspace_dashboard_real_kpi_and_isolation(self):
        """Dashboard displays real KPIs and strictly enforces workspace isolation."""
        from tasks.models import Task, TaskStatus, TaskPriority, Sprint, SprintStatus
        from bugs.models import Bug, BugSeverity, BugStatus
        from meetings.models import Meeting, MeetingStatus
        from django.utils import timezone

        self.client.login(email=self.admin_user.email, password=self.password)
        dashboard_url_1 = reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace1.slug})

        # 1. Active task in Workspace 1
        Task.objects.create(
            workspace=self.workspace1,
            task_code='101001',
            title='Database Migration Core',
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            reporter=self.admin_user
        )
        # Task in Workspace 2 (isolated)
        Task.objects.create(
            workspace=self.workspace2,
            task_code='202002',
            title='Workspace 2 Private Task',
            status=TaskStatus.TODO,
            priority=TaskPriority.URGENT,
            reporter=self.admin_user
        )

        # 2. Meeting today in Workspace 1
        Meeting.objects.create(
            workspace=self.workspace1,
            meeting_code='meet-core-101',
            title='Daily Core Standup',
            host=self.admin_user,
            scheduled_start=timezone.now() + timezone.timedelta(hours=1),
            status=MeetingStatus.SCHEDULED
        )

        # 3. Active Sprint in Workspace 1
        Sprint.objects.create(
            workspace=self.workspace1,
            name='Sprint Delta',
            goal='UX and Performance Refinements',
            status=SprintStatus.ACTIVE,
            created_by=self.admin_user
        )

        resp = self.client.get(dashboard_url_1)
        self.assertEqual(resp.status_code, 200)

        # KPI Verification
        self.assertEqual(resp.context['active_tasks_count'], 1)
        self.assertEqual(resp.context['meetings_today_count'], 1)
        self.assertIsNotNone(resp.context['active_sprint'])
        self.assertEqual(resp.context['active_sprint'].name, 'Sprint Delta')

        # Isolation Verification: Workspace 2 task must NOT appear in Workspace 1 dashboard
        self.assertContains(resp, 'Database Migration Core')
        self.assertContains(resp, '#101001')
        self.assertNotContains(resp, 'Workspace 2 Private Task')
        self.assertNotContains(resp, '#202002')

        # Roster Verification: Shows real full name, not email
        self.assertContains(resp, self.admin_user.full_name)

    def test_delete_workspace_owner_only_with_name_confirmation(self):
        """Workspace can be permanently deleted by the owner after typing exact name."""
        self.client.login(email=self.admin_user.email, password=self.password)
        delete_url = reverse('workspaces:delete', kwargs={'slug': self.workspace1.slug})

        # Wrong name fails
        response = self.client.post(delete_url, {'confirm_workspace_name': 'Wrong Name'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Workspace.objects.filter(id=self.workspace1.id).exists())

        # Exact name deletes workspace
        response_correct = self.client.post(delete_url, {'confirm_workspace_name': self.workspace1.name})
        self.assertEqual(response_correct.status_code, 302)
        self.assertFalse(Workspace.objects.filter(id=self.workspace1.id).exists())

    def test_admin_can_update_member_functional_role_and_reporting_to(self):
        """Only workspace admin can assign functional role, role tag, and reporting manager."""
        self.client.login(email=self.admin_user.email, password=self.password)
        update_url = reverse('workspaces:update_member_role', kwargs={
            'slug': self.workspace1.slug,
            'member_id': self.membership_contributor.id
        })

        response = self.client.post(update_url, {
            'role': WorkspaceRole.CONTRIBUTOR,
            'functional_role': 'Frontend Developer',
            'role_tag': 'Frontend',
            'reporting_to': str(self.membership_manager.id),
        })
        self.assertEqual(response.status_code, 302)
        self.membership_contributor.refresh_from_db()
        self.assertEqual(self.membership_contributor.functional_role, 'Frontend Developer')
        self.assertEqual(self.membership_contributor.role_tag, 'Frontend')
        self.assertEqual(self.membership_contributor.reporting_to, self.membership_manager)
        self.assertEqual(self.membership_contributor.effective_reporting_to, self.membership_manager)
        self.assertEqual(self.membership_manager.direct_reports_count, 1)

    def test_non_admin_cannot_update_member_roles_or_hierarchy(self):
        """Managers or contributors cannot alter member roles, functional roles, or reporting hierarchy."""
        self.client.login(email=self.manager_user.email, password=self.password)
        update_url = reverse('workspaces:update_member_role', kwargs={
            'slug': self.workspace1.slug,
            'member_id': self.membership_contributor.id
        })

        response = self.client.post(update_url, {
            'role': WorkspaceRole.MANAGER,
            'functional_role': 'Backend Lead',
            'role_tag': 'Backend',
        })
        # Should be denied (workspace_admin_required decorator returns 403)
        self.assertEqual(response.status_code, 403)
        self.membership_contributor.refresh_from_db()
        self.assertEqual(self.membership_contributor.role, WorkspaceRole.CONTRIBUTOR)
        self.assertNotEqual(self.membership_contributor.functional_role, 'Backend Lead')

    def test_effective_reporting_to_defaults_to_owner(self):
        """If reporting_to is unset, effective_reporting_to defaults to workspace owner."""
        self.membership_contributor.reporting_to = None
        self.membership_contributor.save()

        # Contributor defaults to owner (Alice Admin)
        self.assertEqual(self.membership_contributor.effective_reporting_to, self.membership_admin)

        # The owner/admin themselves does not report to anyone
        self.assertIsNone(self.membership_admin.effective_reporting_to)

    def test_prevent_self_reporting_and_circular_reporting(self):
        """A member cannot report to themselves, and circular reporting is rejected by the form."""
        from workspaces.forms import WorkspaceMemberRoleForm

        # Self-reporting test
        form_self = WorkspaceMemberRoleForm(
            member=self.membership_manager,
            data={
                'role': WorkspaceRole.MANAGER,
                'functional_role': 'Manager',
                'reporting_to': str(self.membership_manager.id),
            }
        )
        self.assertFalse(form_self.is_valid())
        self.assertIn('reporting_to', form_self.errors)

        # Circular reporting: set Manager reports to Contributor, then try to have Contributor report to Manager
        self.membership_manager.reporting_to = self.membership_contributor
        self.membership_manager.save()

        form_cycle = WorkspaceMemberRoleForm(
            member=self.membership_contributor,
            data={
                'role': WorkspaceRole.CONTRIBUTOR,
                'functional_role': 'Developer',
                'reporting_to': str(self.membership_manager.id),
            }
        )
        self.assertFalse(form_cycle.is_valid())
        self.assertIn('reporting_to', form_cycle.errors)


class ProjectDetailsEditTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.admin = User.objects.create_user(
            email="admin.pd@aetherspace.dev",
            password=self.password,
            full_name="Admin PD"
        )
        self.contributor = User.objects.create_user(
            email="contrib.pd@aetherspace.dev",
            password=self.password,
            full_name="Contrib PD"
        )
        self.workspace = Workspace.objects.create(
            name="Original Project",
            slug="original-project",
            description="Original description",
            owner=self.admin
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_admin_can_edit_project_details(self):
        self.client.login(email="admin.pd@aetherspace.dev", password=self.password)
        url = reverse('workspaces:project_details', kwargs={'slug': self.workspace.slug})

        response = self.client.post(url, {
            'name': 'Updated Project Name',
            'description': 'Updated workspace summary',
            'tech_stack': 'Python, Django, PostgreSQL, TailwindCSS, Alpine.js',
            'project_scope': 'Production agile workspace engine',
            'architecture_notes': 'Django monolithic architecture with Supabase storage',
            'security_mode': 'STRICT_RBAC',
            'storage_provider': 'SUPABASE_S3'
        })
        self.assertEqual(response.status_code, 302)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, 'Updated Project Name')
        self.assertEqual(self.workspace.description, 'Updated workspace summary')
        self.assertEqual(self.workspace.security_mode, 'STRICT_RBAC')
        self.assertEqual(self.workspace.storage_provider, 'SUPABASE_S3')
        self.assertIn('PostgreSQL', self.workspace.tech_stack_list)

    def test_contributor_cannot_edit_project_details(self):
        self.client.login(email="contrib.pd@aetherspace.dev", password=self.password)
        url = reverse('workspaces:project_details', kwargs={'slug': self.workspace.slug})

        response = self.client.post(url, {
            'name': 'Hacked Name',
            'description': 'Hacked description',
        })
        self.assertEqual(response.status_code, 403)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, 'Original Project')


import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile


class WorkspaceLogoAndStorageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.admin = User.objects.create_user(
            email="admin.logo@aetherspace.dev",
            password=self.password,
            full_name="Logo Admin"
        )
        self.contributor = User.objects.create_user(
            email="contrib.logo@aetherspace.dev",
            password=self.password,
            full_name="Logo Contributor"
        )
        self.workspace = Workspace.objects.create(
            name="Aether Logo Team",
            slug="aether-logo-team",
            description="Testing logo storage",
            owner=self.admin
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def _create_test_image(self, size=(200, 200), color=(50, 100, 200), format='PNG'):
        image = Image.new('RGB', size, color=color)
        buf = io.BytesIO()
        image.save(buf, format=format)
        buf.seek(0)
        return buf.getvalue()

    def test_workspace_settings_contains_real_logo_upload_ui(self):
        self.client.login(email="admin.logo@aetherspace.dev", password=self.password)
        url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Ensure no placeholder alert remains
        self.assertNotContains(response, "File upload to Supabase Storage will be enabled with the files module.")
        # Ensure real upload inputs and Supabase indicator are present
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'workspace-logo-file-input')
        self.assertContains(response, 'Supabase Storage')

    def test_workspace_logo_upload_file_success(self):
        self.client.login(email="admin.logo@aetherspace.dev", password=self.password)
        url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})

        img_bytes = self._create_test_image()
        upload_file = SimpleUploadedFile("team_logo.png", img_bytes, content_type="image/png")

        response = self.client.post(url, {
            'name': 'Aether Logo Team',
            'description': 'Updated description',
            'max_seats': 15,
            'storage_quota_mb': 50,
            'status': 'ACTIVE',
            'logo_file': upload_file
        })
        self.assertEqual(response.status_code, 302)

        self.workspace.refresh_from_db()
        self.assertTrue(bool(self.workspace.logo))
        self.assertTrue(bool(self.workspace.logo_url))

    def test_workspace_logo_upload_large_file_rejected(self):
        self.client.login(email="admin.logo@aetherspace.dev", password=self.password)
        url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})

        # > 2 MB payload
        large_bytes = b"x" * (2 * 1024 * 1024 + 1024)
        upload_file = SimpleUploadedFile("huge_logo.png", large_bytes, content_type="image/png")

        response = self.client.post(url, {
            'name': 'Aether Logo Team',
            'description': 'Updated description',
            'max_seats': 15,
            'storage_quota_mb': 50,
            'status': 'ACTIVE',
            'logo_file': upload_file
        }, follow=True)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, '')
        self.assertContains(response, "exceeds the maximum allowed limit of 2 MB")

    def test_workspace_logo_external_url_success(self):
        self.client.login(email="admin.logo@aetherspace.dev", password=self.password)
        url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})

        test_url = "https://images.unsplash.com/photo-1579546929518-9e396f3cc809"
        response = self.client.post(url, {
            'name': 'Aether Logo Team',
            'description': 'Updated description',
            'max_seats': 15,
            'storage_quota_mb': 50,
            'status': 'ACTIVE',
            'logo_url': test_url
        })
        self.assertEqual(response.status_code, 302)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, test_url)
        self.assertEqual(self.workspace.logo_url, test_url)

    def test_workspace_logo_remove_resets_to_default(self):
        self.workspace.logo = "https://example.com/logo.png"
        self.workspace.save(update_fields=['logo'])

        self.client.login(email="admin.logo@aetherspace.dev", password=self.password)
        url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})

        response = self.client.post(url, {
            'action': 'remove_logo'
        })
        self.assertEqual(response.status_code, 302)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, '')
        self.assertEqual(self.workspace.logo_url, '')

    def test_contributor_cannot_update_workspace_logo(self):
        self.client.login(email="contrib.logo@aetherspace.dev", password=self.password)
        url = reverse('workspaces:settings', kwargs={'slug': self.workspace.slug})

        img_bytes = self._create_test_image()
        upload_file = SimpleUploadedFile("hacked_logo.png", img_bytes, content_type="image/png")

        response = self.client.post(url, {
            'name': 'Hacked Workspace',
            'logo_file': upload_file
        })
        self.assertEqual(response.status_code, 403)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.logo, '')


class GlobalAccessRequestSubmissionTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.contributor = User.objects.create_user(
            email="ramu.test@example.com",
            password=self.password,
            full_name="Ramu Contributor",
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED
        )

        self.admin = User.objects.create_user(
            email="admin.test@example.com",
            password=self.password,
            full_name="Admin User",
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED
        )

        self.workspace = Workspace.objects.create(
            name="AetherSpace Core",
            slug="aetherspace-core",
            owner=self.admin
        )

        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_submit_access_request_ajax_resilient_workspace_slug(self):
        """Even if the user types 'aetherspace  core' with spaces, it resolves cleanly and returns JSON."""
        self.client.login(email=self.contributor.email, password=self.password)
        url = reverse('workspaces:submit_access_request')

        response = self.client.post(
            url,
            {
                'workspace_slug': 'aetherspace  core',
                'action': 'task.create',
                'reason': 'For assigning tasks to team members',
                'goal_description': 'Create deliverables for sprint',
                'urgency': 'URGENT',
                'requested_duration': 'TODAY'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertIn('Access request for', data.get('message', ''))

    def test_submit_access_request_validation_error_returns_json_400(self):
        """Missing reason returns clean 400 JSON instead of HTML redirect."""
        self.client.login(email=self.contributor.email, password=self.password)
        url = reverse('workspaces:submit_access_request')

        response = self.client.post(
            url,
            {
                'workspace_slug': 'aetherspace-core',
                'action': 'task.create',
                'reason': '',  # Empty reason
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data.get('status'), 'error')
        self.assertIn('justification reason is required', data.get('message', ''))





