from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, UserRole, ApprovalStatus
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskStatus, TaskPriority
from timetracking.models import TimeEntry, TimeEntryType


class TimeTrackingTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            username='admin_user',
            password='Password123!',
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        self.member_user = User.objects.create_user(
            email='member@example.com',
            username='member_user',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        self.outsider_user = User.objects.create_user(
            email='outsider@example.com',
            username='outsider_user',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )

        # Workspace
        self.workspace = Workspace.objects.create(
            name='Alpha Workspace',
            slug='alpha-workspace',
            owner=self.admin_user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Task
        self.task = Task.objects.create(
            task_code='619347',
            workspace=self.workspace,
            reporter=self.admin_user,
            title='Test Task',
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH
        )

    def test_time_entry_formatting_and_stop(self):
        """Test formatting helpers and timer stopping logic."""
        now = timezone.now()
        entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            entry_type=TimeEntryType.TIMER,
            started_at=now - timedelta(hours=2, minutes=30),
            is_running=True
        )
        self.assertTrue(entry.is_running)

        # Stop timer
        entry.stop()
        self.assertFalse(entry.is_running)
        self.assertIsNotNone(entry.ended_at)
        self.assertGreaterEqual(entry.duration_seconds, 8900)  # ~2.5 hrs = 9000s
        self.assertIn("2h 30m", entry.duration_formatted)
        self.assertAlmostEqual(entry.hours_decimal, 2.5, places=1)

    def test_api_timer_start_and_stop(self):
        """Test starting and stopping timer via AJAX endpoints."""
        self.client.force_login(self.member_user)

        # Start timer
        start_url = reverse('timetracking:api_timer_start', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(start_url, {'task_id': self.task.id, 'description': 'Working on test task'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['is_running'])
        self.assertEqual(data['task_code'], '#619347')

        running_entry = TimeEntry.objects.filter(workspace=self.workspace, user=self.member_user, is_running=True).first()
        self.assertIsNotNone(running_entry)

        # Stop timer
        stop_url = reverse('timetracking:api_timer_stop', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(stop_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['is_running'])

        running_entry.refresh_from_db()
        self.assertFalse(running_entry.is_running)
        self.assertGreaterEqual(running_entry.duration_seconds, 0)

    def test_manual_time_entry(self):
        """Test logging manual time entry."""
        self.client.force_login(self.member_user)
        url = reverse('timetracking:manual_time_entry', kwargs={'slug': self.workspace.slug})
        today = timezone.localdate()

        resp = self.client.post(url, {
            'date': today.strftime('%Y-%m-%d'),
            'hours': '3',
            'minutes': '15',
            'description': 'Manual sprint testing',
            'task': self.task.id
        })
        self.assertEqual(resp.status_code, 302)

        entry = TimeEntry.objects.filter(user=self.member_user, entry_type=TimeEntryType.MANUAL).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.duration_seconds, (3 * 3600) + (15 * 60))
        self.assertEqual(entry.duration_formatted, '3h 15m')
        self.assertEqual(entry.description, 'Manual sprint testing')

    def test_timesheet_csv_export(self):
        """Test exporting workspace timesheet to CSV."""
        self.client.force_login(self.admin_user)
        # Create a sample entry
        TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            entry_type=TimeEntryType.MANUAL,
            started_at=timezone.now(),
            duration_seconds=7200,
            description='CSV test entry',
            is_running=False
        )

        export_url = reverse('timetracking:export_timesheet_csv', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(export_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        content = resp.content.decode('utf-8')
        self.assertIn('Date,Member Name,Contributor ID,Email,Task ID,Task Title', content)
        self.assertIn('619347', content)
        self.assertIn('CSV test entry', content)

    def test_workspace_isolation_outsider_denied(self):
        """Ensure users not in the workspace cannot access time tracking or endpoints."""
        self.client.force_login(self.outsider_user)
        url = reverse('timetracking:workspace_timesheet', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        # workspace_member_required returns 403 or redirects
        self.assertIn(resp.status_code, [302, 403])
