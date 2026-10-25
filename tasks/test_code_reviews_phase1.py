import json
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskStatus, TaskPriority, CodeReviewRequest, CodeReviewStatus
from tasks.services import create_code_review_request, update_code_review_status
from tasks.forms import CodeReviewRequestForm, WorkspaceCodeReviewRequestForm


class CodeReviewsPhase1Tests(TestCase):
    def setUp(self):
        # 1. Create Users
        self.password = "Secr3tP@ssw0rd!"
        self.alice = User.objects.create_user(
            email="alice@alpha.dev",
            password=self.password,
            full_name="Alice Alpha"
        )
        self.bob = User.objects.create_user(
            email="bob@alpha.dev",
            password=self.password,
            full_name="Bob Alpha"
        )
        self.charlie = User.objects.create_user(
            email="charlie@beta.dev",
            password=self.password,
            full_name="Charlie Beta"
        )

        # 2. Create Workspace A
        self.workspace_a = Workspace.objects.create(
            name="Alpha Workspace",
            slug="alpha-workspace",
            owner=self.alice
        )

        # 3. Create Workspace B (Isolation testing)
        self.workspace_b = Workspace.objects.create(
            name="Beta Workspace",
            slug="beta-workspace",
            owner=self.charlie
        )

        # 4. Memberships
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
            workspace=self.workspace_b,
            user=self.charlie,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # 5. Create Tasks in Workspace A
        today = timezone.now().date()
        self.task_1 = Task.objects.create(
            workspace=self.workspace_a,
            task_code="100001",
            title="Implement Authentication",
            priority=TaskPriority.HIGH,
            due_date=today + timedelta(days=2),
            reporter=self.alice,
            assignee=self.alice
        )
        self.task_2 = Task.objects.create(
            workspace=self.workspace_a,
            task_code="100002",
            title="Design Dashboard UI",
            priority=TaskPriority.MEDIUM,
            due_date=today + timedelta(days=5),
            reporter=self.bob,
            assignee=self.bob
        )

        # 6. Create Task in Workspace B
        self.task_b = Task.objects.create(
            workspace=self.workspace_b,
            task_code="200001",
            title="Beta Database Setup",
            priority=TaskPriority.URGENT,
            reporter=self.charlie,
            assignee=self.charlie
        )

        # 7. Create Code Reviews in Workspace A
        self.cr_1 = create_code_review_request(
            task=self.task_1,
            requester=self.alice,
            reviewer=self.bob,
            title="Review Authentication Logic",
            description="Please check JWT tokens and session expiration",
            status=CodeReviewStatus.REQUESTED
        )
        self.cr_2 = create_code_review_request(
            task=self.task_2,
            requester=self.bob,
            reviewer=self.alice,
            title="Review Dashboard Components",
            description="Alpine widgets and Tailwind responsiveness",
            status=CodeReviewStatus.APPROVED
        )

        # 8. Create Code Review in Workspace B
        self.cr_b = create_code_review_request(
            task=self.task_b,
            requester=self.charlie,
            reviewer=self.charlie,
            title="Beta DB Migration Review",
            status=CodeReviewStatus.REQUESTED
        )

    def test_rejected_status_in_choices(self):
        """Verify REJECTED status choice exists and updates correctly."""
        self.assertIn('REJECTED', dict(CodeReviewStatus.choices))
        self.assertEqual(CodeReviewStatus.REJECTED, 'REJECTED')

        # Update status to REJECTED
        update_code_review_status(self.cr_1, actor=self.alice, new_status=CodeReviewStatus.REJECTED)
        self.cr_1.refresh_from_db()
        self.assertEqual(self.cr_1.status, CodeReviewStatus.REJECTED)
        self.assertFalse(self.cr_1.is_open)

    def test_workspace_isolation_on_list_page(self):
        """Alice can only see reviews in Workspace A, never Workspace B."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_list', kwargs={'slug': self.workspace_a.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # Shows Workspace A reviews
        self.assertContains(resp, self.cr_1.review_code)
        self.assertContains(resp, self.cr_2.review_code)
        # Does NOT show Workspace B review
        self.assertNotContains(resp, self.cr_b.review_code)

        # Charlie (Workspace B) cannot access Workspace A's review list
        self.client.login(email="charlie@beta.dev", password=self.password)
        resp_unauth = self.client.get(url)
        self.assertEqual(resp_unauth.status_code, 403)

    def test_summary_kpi_counts_on_list_page(self):
        """Summary card metrics reflect real authorized records in the workspace."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_list', kwargs={'slug': self.workspace_a.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        ctx = resp.context
        self.assertEqual(ctx['total_reviews'], 2)
        # cr_1 reviewer is bob, cr_2 reviewer is alice
        self.assertEqual(ctx['assigned_to_me_count'], 1)
        # cr_1 requester is alice, cr_2 requester is bob
        self.assertEqual(ctx['requested_by_me_count'], 1)
        self.assertEqual(ctx['pending_count'], 1)  # cr_1 is REQUESTED
        self.assertEqual(ctx['approved_count'], 1)  # cr_2 is APPROVED
        self.assertEqual(ctx['rejected_count'], 0)

    def test_assigned_to_me_filter_and_sub_panel(self):
        """Assigned to Me filter narrows records to user's assigned reviews."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        url = f"{reverse('tasks:code_review_list', kwargs={'slug': self.workspace_a.slug})}?filter=assigned_to_me"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        ctx = resp.context
        self.assertEqual(ctx['active_filter'], 'assigned_to_me')
        reviews = list(ctx['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_2.id)

        # Panel 2 counts check
        self.assertIsNotNone(ctx['panel_counts'])
        self.assertEqual(ctx['panel_counts']['assigned_to_me'], 1)
        self.assertEqual(ctx['panel_counts']['completed'], 1)

    def test_requested_by_me_filter(self):
        """Requested by Me filter shows only user's own requests."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        url = f"{reverse('tasks:code_review_list', kwargs={'slug': self.workspace_a.slug})}?filter=requested_by_me"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_1.id)

    def test_search_and_attribute_filters(self):
        """Search query and filters (status, priority, reviewer) filter list accurately."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        base_url = reverse('tasks:code_review_list', kwargs={'slug': self.workspace_a.slug})

        # 1. Search by task code
        resp = self.client.get(f"{base_url}?q=100001")
        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_1.id)

        # 2. Search by review code
        resp = self.client.get(f"{base_url}?q={self.cr_2.review_code}")
        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_2.id)

        # 3. Filter by status APPROVED
        resp = self.client.get(f"{base_url}?status={CodeReviewStatus.APPROVED}")
        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_2.id)

        # 3b. Filter by status=PENDING (mapped to REQUESTED)
        resp = self.client.get(f"{base_url}?status=PENDING")
        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_1.id)

        # 4. Filter by Priority HIGH
        resp = self.client.get(f"{base_url}?priority={TaskPriority.HIGH}")
        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_1.id)

        # 5. Filter by Reviewer Bob
        resp = self.client.get(f"{base_url}?reviewer={self.bob.id}")
        reviews = list(resp.context['reviews'])
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].id, self.cr_1.id)

    def test_workspace_level_review_request_form_success(self):
        """Workspace-level review request form successfully creates a review."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        create_url = reverse('tasks:code_review_request_workspace', kwargs={'slug': self.workspace_a.slug})

        # GET form page
        resp_get = self.client.get(create_url)
        self.assertEqual(resp_get.status_code, 200)

        # POST valid review request
        post_data = {
            'task': str(self.task_1.id),
            'title': 'New Code Review from Workspace Form',
            'reviewer': str(self.bob.id),
            'description': 'Workspace level review submission testing',
            'github_pr_url': ''
        }
        resp_post = self.client.post(create_url, post_data)
        self.assertEqual(resp_post.status_code, 302)

        # Verify created record
        cr_new = CodeReviewRequest.objects.filter(title='New Code Review from Workspace Form').first()
        self.assertIsNotNone(cr_new)
        self.assertEqual(cr_new.task, self.task_1)
        self.assertEqual(cr_new.requester, self.alice)
        self.assertEqual(cr_new.reviewer, self.bob)
        self.assertEqual(cr_new.status, CodeReviewStatus.REQUESTED)

    def test_workspace_level_review_request_cross_workspace_protection(self):
        """Requester cannot select a task or reviewer from another workspace."""
        form = WorkspaceCodeReviewRequestForm(
            data={
                'task': str(self.task_b.id),  # Task from Workspace B
                'title': 'Cross workspace attempt',
                'reviewer': str(self.charlie.id)  # User from Workspace B
            },
            workspace=self.workspace_a,
            requester=self.alice
        )
        self.assertFalse(form.is_valid())
        self.assertIn('task', form.errors)

    def test_task_level_review_request_flow_preserved(self):
        """Existing task-level code review creation continues to function smoothly."""
        self.client.login(email="alice@alpha.dev", password=self.password)
        task_create_url = reverse('tasks:code_review_create', kwargs={
            'slug': self.workspace_a.slug,
            'task_code': self.task_2.task_code
        })
        resp = self.client.post(task_create_url, {
            'title': 'Task Detail Level Review',
            'reviewer': str(self.bob.id),
            'description': 'Created via task detail modal',
            'github_pr_url': ''
        })
        self.assertEqual(resp.status_code, 302)

        cr = CodeReviewRequest.objects.filter(title='Task Detail Level Review').first()
        self.assertIsNotNone(cr)
        self.assertEqual(cr.task, self.task_2)
        self.assertEqual(cr.reviewer, self.bob)
