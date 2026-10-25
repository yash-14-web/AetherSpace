from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskPriority, TaskStatus, CodeReviewRequest, CodeReviewStatus, TaskComment
from tasks.services import create_code_review_request, update_code_review_status


class CodeReviewsPhase2DetailTests(TestCase):
    def setUp(self):
        # 1. Users
        self.password = "Secr3tP@ssw0rd!"
        self.alice = User.objects.create_user(
            email="alice@alpha.dev",
            password=self.password,
            full_name="Alice Alpha"
        )
        self.bob = User.objects.create_user(
            email="bob@alpha.dev",
            password=self.password,
            full_name="Bob Reviewer"
        )
        self.charlie = User.objects.create_user(
            email="charlie@alpha.dev",
            password=self.password,
            full_name="Charlie Contributor"
        )
        self.dan_beta = User.objects.create_user(
            email="dan@beta.dev",
            password=self.password,
            full_name="Dan Beta"
        )

        # 2. Workspaces
        self.workspace_a = Workspace.objects.create(
            name="Alpha Workspace",
            slug="alpha-workspace",
            owner=self.alice
        )
        self.workspace_b = Workspace.objects.create(
            name="Beta Workspace",
            slug="beta-workspace",
            owner=self.dan_beta
        )

        # 3. Memberships
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.alice,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.bob,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.charlie,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_b,
            user=self.dan_beta,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # 4. Tasks in Workspace A
        self.task_1 = Task.objects.create(
            workspace=self.workspace_a,
            task_code="300001",
            title="Implement User Authentication Flow",
            priority=TaskPriority.HIGH,
            due_date=timezone.now().date() + timedelta(days=3),
            reporter=self.alice,
            assignee=self.alice
        )

        # 5. Code Review in Workspace A
        self.cr = create_code_review_request(
            task=self.task_1,
            requester=self.alice,
            reviewer=self.bob,
            title="Authentication Middleware & Token Refresh",
            description="Please inspect token expiry, session cleanup, and security headers.",
            status=CodeReviewStatus.REQUESTED
        )

    def test_overview_tab_renders_successfully(self):
        """Review detail page renders overview tab with all required attributes."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_detail', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Check content
        self.assertContains(resp, self.cr.review_code)
        self.assertContains(resp, "Authentication Middleware")
        self.assertContains(resp, "#300001")
        self.assertContains(resp, "Bob Reviewer")
        self.assertContains(resp, "Review Quality Checklist")
        self.assertEqual(resp.context['active_tab'], 'overview')

    def test_comments_tab_renders_and_lists_comments(self):
        """Comments & Decision tab lists discussion comments and renders decision panel UI."""
        # Create an existing comment
        TaskComment.objects.create(
            task=self.task_1,
            author=self.bob,
            comment_type=TaskComment.CommentType.USER,
            code_review=self.cr,
            content="Initial review looks solid. Please check header parsing."
        )

        self.client.login(email="alice@alpha.dev", password=self.password)
        url = f"{reverse('tasks:code_review_detail', kwargs={'slug': self.workspace_a.slug, 'review_code': self.cr.review_code})}?tab=comments"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.context['active_tab'], 'comments')
        self.assertContains(resp, "Initial review looks solid. Please check header parsing.")
        self.assertContains(resp, "Review Decision")
        self.assertContains(resp, "Submit Decision")

    def test_activity_and_history_tab_renders_timeline(self):
        """Activity & History tab displays chronological audit trail."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        url = f"{reverse('tasks:code_review_detail', kwargs={'slug': self.workspace_a.slug, 'review_code': self.cr.review_code})}?tab=history"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.context['active_tab'], 'history')
        self.assertContains(resp, "Audit Trail & Activity Timeline")
        self.assertContains(resp, "Code Review Requested")
        self.assertGreaterEqual(resp.context['history_count'], 1)

    def test_post_comment_on_code_review(self):
        """Posting a comment adds a TaskComment associated with the review and redirects to comments tab."""
        self.client.login(email="bob@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_comment_add', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {'content': 'LGTM pending test coverage.'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('tab=comments', resp.url)

        # Check in DB
        comment = TaskComment.objects.filter(code_review=self.cr, author=self.bob, comment_type=TaskComment.CommentType.USER).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.content, 'LGTM pending test coverage.')
        self.assertEqual(comment.comment_type, TaskComment.CommentType.USER)

    def test_post_empty_comment_fails(self):
        """Submitting an empty comment creates no record."""
        self.client.login(email="bob@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_comment_add', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {'content': '   '})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TaskComment.objects.filter(code_review=self.cr, comment_type=TaskComment.CommentType.USER).count(), 0)

    def test_start_review_transitions_to_in_review(self):
        """Assigned reviewer can transition review from REQUESTED to IN_REVIEW."""
        self.client.login(email="bob@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_start', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.IN_REVIEW)

    def test_unauthorized_user_cannot_start_review(self):
        """Unrelated contributor (Charlie) cannot start Bob's review."""
        self.client.login(email="charlie@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_start', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)

    def test_workspace_isolation_on_detail_page(self):
        """Dan from Workspace B cannot view review detail in Workspace A."""
        self.client.login(email="dan@beta.dev", password=self.password)
        url = reverse('tasks:code_review_detail', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)
