import re
import json
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, UserRole, ApprovalStatus, generate_unique_contributor_id
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from meetings.models import Meeting, MeetingParticipant


class Phase15WorkflowAndCorrectionsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"
        
        # Create an admin user
        self.admin = User.objects.create_user(
            email="admin@aetherspace.dev",
            password=self.password,
            full_name="Admin Boss",
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            contributor_id="10001C"
        )
        
        # Create an approved contributor
        self.approved_user = User.objects.create_user(
            email="approved@aetherspace.dev",
            password=self.password,
            full_name="Approved Member",
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            contributor_id="20001C"
        )

        # Create a workspace
        self.workspace = Workspace.objects.create(
            name="Apollo Workspace",
            slug="apollo-space",
            owner=self.admin
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role=WorkspaceRole.ADMIN
        )

    def test_contributor_id_format(self):
        """Contributor ID must strictly format as 5 digits followed by 'C' (#####C)."""
        cid = generate_unique_contributor_id()
        self.assertTrue(re.match(r'^\d{5}C$', cid), f"Generated ID {cid} does not match #####C format")

    def test_user_registration_defaults_to_pending_and_redirects(self):
        """User registration sets role=CONTRIBUTOR, status=PENDING, generates ID, and redirects to pending approval."""
        reg_data = {
            'full_name': 'New Candidate',
            'email': 'candidate@aetherspace.dev',
            'password': 'ComplexPassword123!',
            'confirm_password': 'ComplexPassword123!',
            'agree_terms': True,
        }
        resp = self.client.post(reverse('accounts:register'), data=reg_data)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('accounts:pending_approval'))

        new_user = User.objects.get(email='candidate@aetherspace.dev')
        self.assertEqual(new_user.role, UserRole.CONTRIBUTOR)
        self.assertEqual(new_user.approval_status, ApprovalStatus.PENDING)
        self.assertTrue(re.match(r'^\d{5}C$', new_user.contributor_id))

        # Check pending approval screen renders the contributor ID
        resp_pending = self.client.get(reverse('accounts:pending_approval'))
        self.assertEqual(resp_pending.status_code, 200)
        self.assertContains(resp_pending, new_user.contributor_id)

    def test_pending_user_cannot_login(self):
        """A user with PENDING approval status cannot log in."""
        pending_user = User.objects.create_user(
            email="pending@aetherspace.dev",
            password=self.password,
            full_name="Waiting User",
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.PENDING,
            contributor_id="30001C"
        )
        login_data = {
            'contributor_id': pending_user.contributor_id,
            'password': self.password
        }
        resp = self.client.post(reverse('accounts:login'), data=login_data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "awaiting Admin/Manager approval")

    def test_approved_user_login_with_contributor_id(self):
        """An approved user can successfully log in using their Contributor ID and password."""
        login_data = {
            'contributor_id': self.approved_user.contributor_id,
            'password': self.password
        }
        resp = self.client.post(reverse('accounts:login'), data=login_data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('workspaces:dashboard'))

    def test_admin_approval_and_rejection_flow(self):
        """Admin can approve and reject users via the admin endpoints."""
        candidate = User.objects.create_user(
            email="toapprove@aetherspace.dev",
            password=self.password,
            full_name="Approve Me",
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.PENDING,
            contributor_id="40001C"
        )
        self.client.login(email=self.admin.email, password=self.password)

        # Approve user
        resp_approve = self.client.post(reverse('admin_panel:approve_user', kwargs={'user_id': candidate.id}))
        self.assertEqual(resp_approve.status_code, 302)
        candidate.refresh_from_db()
        self.assertEqual(candidate.approval_status, ApprovalStatus.APPROVED)
        self.assertEqual(candidate.approved_by, self.admin)

        # Reject user
        resp_reject = self.client.post(reverse('admin_panel:reject_user', kwargs={'user_id': candidate.id}))
        self.assertEqual(resp_reject.status_code, 302)
        candidate.refresh_from_db()
        self.assertEqual(candidate.approval_status, ApprovalStatus.REJECTED)

    def test_search_first_rule_api_people_search(self):
        """Empty search query strictly returns 0 records; queries matching Contributor ID return records."""
        self.client.login(email=self.admin.email, password=self.password)

        # Empty search
        resp_empty = self.client.get(reverse('admin_panel:api_people_search') + "?q=")
        self.assertEqual(resp_empty.status_code, 200)
        data = resp_empty.json()
        self.assertEqual(len(data.get('users', [])), 0)

        # Search by Contributor ID
        resp_cid = self.client.get(reverse('admin_panel:api_people_search') + f"?q={self.approved_user.contributor_id}")
        self.assertEqual(resp_cid.status_code, 200)
        data = resp_cid.json()
        self.assertEqual(len(data.get('users', [])), 1)
        self.assertEqual(data['users'][0]['contributor_id'], self.approved_user.contributor_id)

    def test_direct_add_workspace_member(self):
        """Workspace Admin can directly add an approved user without an invitation."""
        self.client.login(email=self.admin.email, password=self.password)
        direct_add_url = reverse('workspaces:direct_add_member', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(direct_add_url, data={
            'user_id': str(self.approved_user.id),
            'role': WorkspaceRole.CONTRIBUTOR
        })
        self.assertEqual(resp.status_code, 302)
        # Verify membership exists
        self.assertTrue(
            WorkspaceMembership.objects.filter(workspace=self.workspace, user=self.approved_user).exists()
        )

    def test_meeting_raise_hand_and_remove_participant(self):
        """Meeting API supports hand raising toggle and host participant removal."""
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.approved_user,
            role=WorkspaceRole.CONTRIBUTOR
        )
        meeting = Meeting.objects.create(
            workspace=self.workspace,
            title="Sprint Planning",
            host=self.admin,
            meeting_code="619-347"
        )
        participant = MeetingParticipant.objects.create(
            meeting=meeting,
            user=self.approved_user
        )

        # 1. Contributor raises hand via ping API
        self.client.login(email=self.approved_user.email, password=self.password)
        ping_url = reverse('meetings:meeting_ping_api', kwargs={'slug': self.workspace.slug, 'meeting_code': meeting.meeting_code})
        resp_raise = self.client.post(ping_url, data='{"action": "raise_hand"}', content_type='application/json')
        self.assertEqual(resp_raise.status_code, 200)
        participant.refresh_from_db()
        self.assertTrue(participant.is_hand_raised)

        # 2. Host removes participant
        self.client.login(email=self.admin.email, password=self.password)
        remove_url = reverse('meetings:meeting_remove_participant_api', kwargs={'slug': self.workspace.slug, 'meeting_code': meeting.meeting_code})
        resp_remove = self.client.post(remove_url, data=json.dumps({'user_id': str(self.approved_user.id)}), content_type='application/json')
        self.assertEqual(resp_remove.status_code, 200)
        participant.refresh_from_db()
        self.assertTrue(participant.is_removed)

        # 3. Contributor next ping receives removed status
        self.client.login(email=self.approved_user.email, password=self.password)
        resp_ping_removed = self.client.post(ping_url, data='{"action": "ping"}', content_type='application/json')
        self.assertEqual(resp_ping_removed.status_code, 200)
        self.assertEqual(resp_ping_removed.json().get('status'), 'removed')

    def test_about_page_renders_200(self):
        """The public /about/ page renders successfully with HTTP 200."""
        resp = self.client.get(reverse('core:about'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "The Contributor ID Architecture")
        self.assertContains(resp, "#####C")
