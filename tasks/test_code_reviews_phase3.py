from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied

from accounts.models import User
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskPriority, TaskStatus, CodeReviewRequest, CodeReviewStatus, TaskComment, TaskActivity
from notifications.models import Notification, NotificationCategory, NotificationType
from tasks.services import create_task, create_code_review_request, submit_code_review_decision


class CodeReviewsPhase3DecisionTests(TestCase):
    def setUp(self):
        # 1. Users
        self.password = "Secr3tP@ssw0rd!"
        self.author = User.objects.create_user(
            email="author@alpha.dev",
            password=self.password,
            full_name="Alice Author"
        )
        self.reviewer = User.objects.create_user(
            email="reviewer@alpha.dev",
            password=self.password,
            full_name="Bob Reviewer"
        )
        self.manager = User.objects.create_user(
            email="manager@alpha.dev",
            password=self.password,
            full_name="Mary Manager"
        )
        self.contributor = User.objects.create_user(
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
            owner=self.manager
        )
        self.workspace_b = Workspace.objects.create(
            name="Beta Workspace",
            slug="beta-workspace",
            owner=self.dan_beta
        )

        # 3. Memberships
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.author,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.reviewer,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_a,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace_b,
            user=self.dan_beta,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # 4. Task in Workspace A
        self.task_1 = Task.objects.create(
            workspace=self.workspace_a,
            task_code="400001",
            title="Implement OAuth2 Token Refresh Flow",
            priority=TaskPriority.HIGH,
            status=TaskStatus.IN_PROGRESS,
            due_date=timezone.now().date() + timedelta(days=2),
            reporter=self.author,
            assignee=self.author
        )

        # 5. Code Review in Workspace A
        self.cr = create_code_review_request(
            task=self.task_1,
            requester=self.author,
            reviewer=self.reviewer,
            title="OAuth2 Token Storage & Expiry Handling",
            description="Inspect refresh token rotation logic and security header compliance.",
            status=CodeReviewStatus.IN_REVIEW
        )

    def test_reviewer_can_approve_review_with_valid_message(self):
        """Assigned reviewer can approve review with a meaningful decision message."""
        self.client.login(email="reviewer@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.APPROVED,
            'message': 'Architecture meets security requirements. Ready for merge.'
        })
        self.assertEqual(resp.status_code, 302)

        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.APPROVED)

        # Verify linked task is NOT marked done automatically
        self.task_1.refresh_from_db()
        self.assertEqual(self.task_1.status, TaskStatus.IN_PROGRESS)

    def test_reviewer_can_request_changes(self):
        """Assigned reviewer can request revisions with feedback message."""
        self.client.login(email="reviewer@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.CHANGES_REQUESTED,
            'message': 'Please add regression tests for token expiry and handle 401 response explicitly.'
        })
        self.assertEqual(resp.status_code, 302)

        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.CHANGES_REQUESTED)

    def test_reviewer_can_reject_review(self):
        """Assigned reviewer can reject review with rationale message."""
        self.client.login(email="reviewer@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.REJECTED,
            'message': 'Current architecture conflicts with centralized auth service. Approach discarded.'
        })
        self.assertEqual(resp.status_code, 302)

        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.REJECTED)

    def test_admin_manager_override_permission(self):
        """Workspace Manager can submit decision even if not assigned reviewer."""
        self.client.login(email="manager@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.APPROVED,
            'message': 'Manager sign-off approved after audit.'
        })
        self.assertEqual(resp.status_code, 302)

        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.APPROVED)

    def test_unauthorized_contributor_cannot_submit_decision(self):
        """Unassigned regular contributor is rejected when trying to submit a review decision."""
        self.client.login(email="charlie@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.APPROVED,
            'message': 'Unauthorized attempt to approve review.'
        })
        # Should redirect back with error message and status should remain unchanged
        self.assertEqual(resp.status_code, 302)
        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.IN_REVIEW)

        # Direct service call raises PermissionDenied
        with self.assertRaises(PermissionDenied):
            submit_code_review_decision(
                code_review_id=self.cr.id,
                actor=self.contributor,
                decision=CodeReviewStatus.APPROVED,
                message='Direct service call bypass attempt.'
            )

    def test_empty_or_short_decision_message_fails(self):
        """Submitting an empty or trivial message fails validation without altering status."""
        self.client.login(email="reviewer@alpha.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.APPROVED,
            'message': '  '
        })
        self.assertEqual(resp.status_code, 302)
        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.IN_REVIEW)

        # Service validation test
        with self.assertRaises(ValidationError):
            submit_code_review_decision(
                code_review_id=self.cr.id,
                actor=self.reviewer,
                decision=CodeReviewStatus.APPROVED,
                message='ok'  # less than 3 chars
            )

    def test_invalid_status_transition_rejected(self):
        """Submitting a decision on a finalized review is rejected."""
        # Finalize review
        submit_code_review_decision(
            code_review_id=self.cr.id,
            actor=self.reviewer,
            decision=CodeReviewStatus.APPROVED,
            message='Initial approval.'
        )
        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.APPROVED)

        # Attempt to decide on already approved review
        with self.assertRaises(ValidationError):
            submit_code_review_decision(
                code_review_id=self.cr.id,
                actor=self.reviewer,
                decision=CodeReviewStatus.REJECTED,
                message='Attempting to reject already approved review.'
            )

    def test_duplicate_decision_rejected(self):
        """Submitting the exact same status as current status is rejected as duplicate."""
        with self.assertRaises(ValidationError):
            submit_code_review_decision(
                code_review_id=self.cr.id,
                actor=self.reviewer,
                decision=CodeReviewStatus.IN_REVIEW,  # Already IN_REVIEW
                message='Attempt duplicate transition.'
            )

    def test_review_history_and_task_activity_persistence(self):
        """Decision creates system comment on review, discussion entry, and TaskActivity on linked task."""
        decision_msg = "Comprehensive security review completed. Code meets high standards."
        submit_code_review_decision(
            code_review_id=self.cr.id,
            actor=self.reviewer,
            decision=CodeReviewStatus.APPROVED,
            message=decision_msg
        )

        # 1. System audit TaskComment on the review
        sys_comment = TaskComment.objects.filter(
            code_review=self.cr,
            comment_type=TaskComment.CommentType.SYSTEM,
            system_event_type=TaskComment.SystemEventType.CODE_REVIEW_STATUS_CHANGED
        ).latest('created_at')
        self.assertIn("Review decision submitted: Approved", sys_comment.content)
        self.assertEqual(sys_comment.metadata.get('decision'), CodeReviewStatus.APPROVED)
        self.assertEqual(sys_comment.metadata.get('reviewer_name'), "Bob Reviewer")

        # 2. Discussion TaskComment on the review
        user_comment = TaskComment.objects.filter(
            code_review=self.cr,
            comment_type=TaskComment.CommentType.USER
        ).latest('created_at')
        self.assertIn("**Review Decision: Approved**", user_comment.content)
        self.assertIn(decision_msg, user_comment.content)

        # 3. TaskActivity on linked task
        activity = TaskActivity.objects.filter(
            task=self.task_1,
            actor=self.reviewer
        ).latest('created_at')
        self.assertEqual(activity.new_value, "Approved")
        self.assertIn(self.cr.review_code, activity.message)
        self.assertIn("Bob Reviewer", activity.message)
        self.assertIn(decision_msg, activity.message)
        expected_url = reverse('tasks:code_review_detail', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        self.assertIn(expected_url, activity.message)

    def test_notification_dispatched_to_requester(self):
        """Requester receives an in-app notification when reviewer submits a decision."""
        decision_msg = "Please fix error handling on edge cases."
        submit_code_review_decision(
            code_review_id=self.cr.id,
            actor=self.reviewer,
            decision=CodeReviewStatus.CHANGES_REQUESTED,
            message=decision_msg
        )

        notif = Notification.objects.filter(recipient=self.author, workspace=self.workspace_a).latest('created_at')
        self.assertIsNotNone(notif)
        self.assertIn(self.cr.review_code, notif.title)
        self.assertIn("Changes Requested", notif.title)
        self.assertIn("Bob Reviewer", notif.body)
        self.assertIn(decision_msg, notif.body)
        expected_url = reverse('tasks:code_review_detail', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        self.assertEqual(notif.action_url, expected_url)

    def test_suppress_self_notification_when_requester_is_actor(self):
        """No notification is dispatched if the actor who decides is also the requester."""
        # Create a review where manager requested and manager approves
        manager_cr = create_code_review_request(
            task=self.task_1,
            requester=self.manager,
            reviewer=self.manager,
            title="Manager Self-Review",
            status=CodeReviewStatus.IN_REVIEW
        )
        initial_notif_count = Notification.objects.filter(recipient=self.manager).count()

        submit_code_review_decision(
            code_review_id=manager_cr.id,
            actor=self.manager,
            decision=CodeReviewStatus.APPROVED,
            message="Self-approved as workspace manager."
        )

        # Notification count should not have increased
        new_notif_count = Notification.objects.filter(recipient=self.manager).count()
        self.assertEqual(initial_notif_count, new_notif_count)

    def test_workspace_isolation_blocks_cross_workspace_decision(self):
        """User from Workspace B cannot submit a decision on Workspace A review."""
        self.client.login(email="dan@beta.dev", password=self.password)
        url = reverse('tasks:code_review_decision', kwargs={
            'slug': self.workspace_a.slug,
            'review_code': self.cr.review_code
        })
        resp = self.client.post(url, {
            'decision': CodeReviewStatus.APPROVED,
            'message': 'Cross-workspace attack attempt.'
        })
        self.assertEqual(resp.status_code, 403)
        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, CodeReviewStatus.IN_REVIEW)

    def test_locking_query_avoids_outer_joins_for_update(self):
        """
        Verify that CodeReviewRequest select_for_update queryset does NOT introduce
        nullable outer joins (e.g. LEFT OUTER JOIN on reviewer) which causes PostgreSQL
        error: 'FOR UPDATE cannot be applied to the nullable side of an outer join'.
        """
        from django.db import connection, transaction
        with transaction.atomic():
            qs = CodeReviewRequest.objects.select_for_update().filter(pk=self.cr.id)
            compiler = qs.query.get_compiler('default')
            sql, params = compiler.as_sql()
            self.assertTrue(qs.query.select_for_update)
            if connection.features.has_select_for_update:
                self.assertIn("FOR UPDATE", sql)
            self.assertNotIn("LEFT OUTER JOIN", sql)
            self.assertNotIn("JOIN", sql)

    def test_submit_each_supported_decision(self):
        """
        Submitting each supported decision (APPROVED, CHANGES_REQUESTED, REJECTED)
        succeeds without database locking errors and persists all side-effects correctly.
        """
        decisions_to_test = [
            (CodeReviewStatus.CHANGES_REQUESTED, "Please revise tests and documentation."),
            (CodeReviewStatus.APPROVED, "All review comments addressed, LGTM!"),
            (CodeReviewStatus.REJECTED, "Architecture approach not acceptable."),
        ]

        for idx, (decision, msg) in enumerate(decisions_to_test):
            task = create_task(
                workspace=self.workspace_a,
                reporter=self.author,
                title=f"Decision Test Task {idx}",
                status=TaskStatus.IN_PROGRESS
            )
            cr = create_code_review_request(
                task=task,
                requester=self.author,
                reviewer=self.reviewer,
                title=f"Review for Task {idx}",
                status=CodeReviewStatus.IN_REVIEW
            )

            updated = submit_code_review_decision(
                code_review_id=cr.id,
                actor=self.reviewer,
                decision=decision,
                message=msg
            )
            self.assertEqual(updated.status, decision)
            cr.refresh_from_db()
            self.assertEqual(cr.status, decision)

            # 1. System audit comment
            sys_comment = TaskComment.objects.filter(
                code_review=cr,
                comment_type=TaskComment.CommentType.SYSTEM,
                system_event_type=TaskComment.SystemEventType.CODE_REVIEW_STATUS_CHANGED
            ).latest('created_at')
            self.assertIn(cr.get_status_display(), sys_comment.content)
            self.assertEqual(sys_comment.metadata.get('decision'), decision)

            # 2. Discussion comment
            user_comment = TaskComment.objects.filter(
                code_review=cr,
                comment_type=TaskComment.CommentType.USER
            ).latest('created_at')
            self.assertIn(msg, user_comment.content)

            # 3. TaskActivity
            activity = TaskActivity.objects.filter(task=task, actor=self.reviewer).latest('created_at')
            self.assertEqual(activity.new_value, cr.get_status_display())
            self.assertIn(msg, activity.message)

            # 4. Notification to requester
            notif = Notification.objects.filter(recipient=self.author, workspace=self.workspace_a).latest('created_at')
            self.assertIn(cr.review_code, notif.title)
            self.assertIn(cr.get_status_display(), notif.title)

    def test_transaction_rollback_on_failure_preserves_state(self):
        """
        Verify that an unhandled error inside transaction rolls back status change,
        preventing partial persistence of comments, activities, or review status.
        """
        initial_status = self.cr.status
        initial_comment_count = TaskComment.objects.filter(code_review=self.cr).count()
        initial_activity_count = TaskActivity.objects.filter(task=self.task_1).count()

        from unittest.mock import patch
        with patch('tasks.services.TaskActivity.objects.create', side_effect=RuntimeError("Simulated database failure")):
            with self.assertRaises(RuntimeError):
                submit_code_review_decision(
                    code_review_id=self.cr.id,
                    actor=self.reviewer,
                    decision=CodeReviewStatus.APPROVED,
                    message="Valid decision message."
                )

        self.cr.refresh_from_db()
        self.assertEqual(self.cr.status, initial_status)
        self.assertEqual(TaskComment.objects.filter(code_review=self.cr).count(), initial_comment_count)
        self.assertEqual(TaskActivity.objects.filter(task=self.task_1).count(), initial_activity_count)

