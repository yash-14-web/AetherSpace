from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, UserRole, ApprovalStatus
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskStatus, TaskPriority
from timetracking.models import TimeEntry, TimeEntryType, TimerStatus


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

    def test_timer_pause_and_resume_lifecycle(self):
        """Test transitioning timer between RUNNING, PAUSED, and COMPLETED states."""
        self.client.force_login(self.member_user)

        # 1. Start timer -> RUNNING
        start_url = reverse('timetracking:api_timer_start', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(start_url, {'task_id': self.task.id, 'description': 'Feature development'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['timer_status'], 'running')
        self.assertTrue(data['is_running'])

        timer = TimeEntry.objects.get(id=data['timer_id'])
        self.assertEqual(timer.status, TimerStatus.RUNNING)
        self.assertTrue(timer.is_running)

        # 2. Pause timer -> PAUSED
        pause_url = reverse('timetracking:api_timer_pause', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(pause_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['timer_status'], 'paused')
        self.assertFalse(data['is_running'])

        timer.refresh_from_db()
        self.assertEqual(timer.status, TimerStatus.PAUSED)
        self.assertFalse(timer.is_running)
        self.assertIsNotNone(timer.paused_at)
        self.assertIsNone(timer.ended_at)  # Not finalized!

        # 3. Resume timer -> RUNNING
        resume_url = reverse('timetracking:api_timer_resume', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(resume_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['timer_status'], 'running')
        self.assertTrue(data['is_running'])

        timer.refresh_from_db()
        self.assertEqual(timer.status, TimerStatus.RUNNING)
        self.assertTrue(timer.is_running)
        self.assertIsNone(timer.paused_at)

        # 4. Stop timer -> COMPLETED
        stop_url = reverse('timetracking:api_timer_stop', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(stop_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['timer_status'], 'completed')
        self.assertFalse(data['is_running'])

        timer.refresh_from_db()
        self.assertEqual(timer.status, TimerStatus.COMPLETED)
        self.assertFalse(timer.is_running)
        self.assertIsNotNone(timer.ended_at)

    def test_paused_duration_excluded_from_tracked_work(self):
        """Ensure time spent while paused is NOT counted as work duration."""
        now = timezone.now()
        # Create an entry that ran for 15 minutes (900 seconds) then paused
        timer = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            started_at=now - timedelta(minutes=45),
            last_resumed_at=now - timedelta(minutes=45),
            accumulated_seconds=900,  # 15 minutes
            paused_at=now - timedelta(minutes=30),  # paused 30 mins ago
            status=TimerStatus.PAUSED,
            is_running=False,
            entry_type=TimeEntryType.TIMER
        )

        # current_duration_seconds must be exactly 900 seconds, excluding the 30 paused minutes
        self.assertEqual(timer.current_duration_seconds, 900)

        # Finalize (stop)
        timer.stop()
        self.assertEqual(timer.duration_seconds, 900)

    def test_availability_away_automatically_pauses_running_timer(self):
        """Changing availability status to Away or OOO automatically pauses any running timer."""
        self.client.force_login(self.member_user)

        # Start timer
        start_url = reverse('timetracking:api_timer_start', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(start_url, {'task_id': self.task.id, 'description': 'Deep work'})
        timer_id = resp.json()['timer_id']

        timer = TimeEntry.objects.get(id=timer_id)
        self.assertEqual(timer.status, TimerStatus.RUNNING)

        # Update availability to 'away'
        status_url = reverse('accounts:update_availability_status')
        status_resp = self.client.post(
            status_url,
            data='{"status": "away", "status_message": "Stepped out for lunch"}',
            content_type='application/json'
        )
        self.assertEqual(status_resp.status_code, 200)

        # Verify timer automatically transitioned to PAUSED
        timer.refresh_from_db()
        self.assertEqual(timer.status, TimerStatus.PAUSED)
        self.assertFalse(timer.is_running)
        self.assertIsNone(timer.ended_at)  # Not finalized

        # Verify no duplicate TimeEntry was created
        user_timers = TimeEntry.objects.filter(user=self.member_user)
        self.assertEqual(user_timers.count(), 1)

        # Changing back to 'available' preserves PAUSED state with resume option
        status_resp2 = self.client.post(
            status_url,
            data='{"status": "available", "status_message": ""}',
            content_type='application/json'
        )
        self.assertEqual(status_resp2.status_code, 200)
        timer.refresh_from_db()
        self.assertEqual(timer.status, TimerStatus.PAUSED)

    def test_unauthorized_user_cannot_control_another_members_timer(self):
        """User A cannot pause, resume, or stop User B's timer."""
        # Member creates running timer
        timer = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            status=TimerStatus.RUNNING,
            is_running=True,
            entry_type=TimeEntryType.TIMER
        )

        # Outsider or another member cannot pause it via API
        another_member = User.objects.create_user(
            email='another@example.com',
            username='another_user',
            password='Password123!',
            role=UserRole.CONTRIBUTOR,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=another_member,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        self.client.force_login(another_member)
        pause_url = reverse('timetracking:api_timer_pause', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(pause_url)
        # Another member has no running timer, so returns 400 error
        self.assertEqual(resp.status_code, 400)

        # Member's timer is still running intact
        timer.refresh_from_db()
        self.assertEqual(timer.status, TimerStatus.RUNNING)

    def test_resume_or_start_timer_automatically_switches_away_to_available(self):
        """When user is Away and resumes or starts a timer, status auto-switches to Available."""
        # Set member to away
        from accounts.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.member_user)
        profile.preferences = {'status': 'away'}
        profile.save()
        self.assertEqual(self.member_user.availability_status, 'away')

        # Create paused timer
        timer = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            status=TimerStatus.PAUSED,
            is_running=False,
            accumulated_seconds=120,
            entry_type=TimeEntryType.TIMER
        )

        self.client.force_login(self.member_user)
        resume_url = reverse('timetracking:api_timer_resume', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(resume_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['user_availability'], 'available')

        # User's profile availability is now available!
        profile.refresh_from_db()
        self.assertEqual(profile.availability_status, 'available')

