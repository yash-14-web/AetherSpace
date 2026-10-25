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
        from django.core.cache import cache
        from django.utils import timezone
        cache.set(f'user_last_seen_{self.member_user.id}', timezone.now().timestamp(), 300)
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

    def test_manual_time_entry_with_start_and_end_time(self):
        """Test logging manual time entry using start_time and end_time strings."""
        self.client.force_login(self.member_user)
        url = reverse('timetracking:manual_time_entry', kwargs={'slug': self.workspace.slug})
        today = timezone.localdate()

        resp = self.client.post(url, {
            'date': today.strftime('%Y-%m-%d'),
            'start_time': '09:00 AM',
            'end_time': '11:30 AM',
            'category': 'Development',
            'is_billable': 'on',
            'description': 'Working on auth backend and API integration',
            'task': self.task.id
        })
        self.assertEqual(resp.status_code, 302)

        entry = TimeEntry.objects.filter(user=self.member_user, entry_type=TimeEntryType.MANUAL).order_by('-created_at').first()
        self.assertIsNotNone(entry)
        # 9:00 AM to 11:30 AM is 2 hours 30 mins = 9000 seconds
        self.assertEqual(entry.duration_seconds, 9000)
        self.assertEqual(entry.duration_formatted, '2h 30m')
        self.assertEqual(entry.category, 'Development')
        self.assertTrue(entry.is_billable)
        self.assertEqual(entry.clean_description, 'Working on auth backend and API integration')

    def test_edit_time_entry_authorized(self):
        """Test author updating an existing time entry via edit_time_entry."""
        self.client.force_login(self.member_user)
        entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            duration_seconds=3600,
            accumulated_seconds=3600,
            description='Initial description',
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.MANUAL
        )

        edit_url = reverse('timetracking:edit_time_entry', kwargs={'slug': self.workspace.slug, 'entry_id': entry.id})
        today = timezone.localdate()
        resp = self.client.post(edit_url, {
            'date': today.strftime('%Y-%m-%d'),
            'hours': '2',
            'minutes': '45',
            'category': 'Bug fixes',
            'description': 'Updated bug fix notes',
            'task': self.task.id
        })
        self.assertEqual(resp.status_code, 302)

        entry.refresh_from_db()
        self.assertEqual(entry.duration_seconds, (2 * 3600) + (45 * 60))
        self.assertEqual(entry.category, 'Bug fixes')
        self.assertEqual(entry.clean_description, 'Updated bug fix notes')

    def test_edit_time_entry_unauthorized(self):
        """Another non-admin contributor cannot edit someone else's time entry."""
        entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.admin_user,
            task=self.task,
            duration_seconds=3600,
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.MANUAL
        )

        self.client.force_login(self.member_user)
        edit_url = reverse('timetracking:edit_time_entry', kwargs={'slug': self.workspace.slug, 'entry_id': entry.id})
        today = timezone.localdate()
        resp = self.client.post(edit_url, {
            'date': today.strftime('%Y-%m-%d'),
            'hours': '1',
            'minutes': '0',
            'description': 'Tampering with admin log',
            'task': self.task.id
        })
        self.assertEqual(resp.status_code, 403)

    def test_manual_entry_with_bug_association(self):
        """Test associating a defect (Bug) with a manual time log."""
        from bugs.models import Bug, BugSeverity, BugPriority
        bug = Bug.objects.create(
            bug_code='B-882316',
            workspace=self.workspace,
            title='Navigation drawer clips on mobile',
            severity=BugSeverity.SEV2,
            priority=BugPriority.HIGH,
            linked_task=self.task
        )

        self.client.force_login(self.member_user)
        url = reverse('timetracking:manual_time_entry', kwargs={'slug': self.workspace.slug})
        today = timezone.localdate()

        resp = self.client.post(url, {
            'date': today.strftime('%Y-%m-%d'),
            'start_time': '10:00 AM',
            'end_time': '11:30 AM',
            'category': 'Bug fixes',
            'bug_code': bug.bug_code,
            'description': 'Investigated viewport overflow in drawer',
            'task': ''
        })
        self.assertEqual(resp.status_code, 302)

        entry = TimeEntry.objects.filter(user=self.member_user, entry_type=TimeEntryType.MANUAL).order_by('-created_at').first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.linked_bug_code, 'B-882316')
        self.assertEqual(entry.task, self.task)  # Auto-associated from bug.linked_task!
        self.assertEqual(entry.category, 'Bug fixes')
        self.assertEqual(entry.entry_source_display, 'Manual Entry')
        self.assertIn('Investigated viewport overflow in drawer', entry.clean_description)
        self.assertNotIn('[Bug: B-882316]', entry.clean_description)

    def test_manual_entry_invalid_bug_from_other_workspace_rejected(self):
        """Defects from another workspace cannot be linked to this workspace's timesheet."""
        from bugs.models import Bug
        other_ws = Workspace.objects.create(name='Other Workspace', slug='other-ws', owner=self.admin_user)
        other_bug = Bug.objects.create(
            bug_code='B-999999',
            workspace=other_ws,
            title='Foreign Defect'
        )

        self.client.force_login(self.member_user)
        url = reverse('timetracking:manual_time_entry', kwargs={'slug': self.workspace.slug})
        today = timezone.localdate()

        resp = self.client.post(url, {
            'date': today.strftime('%Y-%m-%d'),
            'hours': '1',
            'minutes': '0',
            'bug_code': other_bug.bug_code,
            'description': 'Attempting cross-workspace bug link'
        })
        self.assertEqual(resp.status_code, 302)
        # Verify no entry was created with the foreign bug
        self.assertFalse(TimeEntry.objects.filter(workspace=self.workspace, description__icontains='B-999999').exists())

    def test_entry_source_distinction_timer_vs_manual(self):
        """Timer entries and manual entries are reliably distinguished on backend and display."""
        # 1. Start live timer
        self.client.force_login(self.member_user)
        start_url = reverse('timetracking:api_timer_start', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(start_url, {'task_id': self.task.id, 'description': 'Timer task'})
        timer_id = resp.json()['timer_id']
        timer_entry = TimeEntry.objects.get(id=timer_id)
        self.assertEqual(timer_entry.entry_type, TimeEntryType.TIMER)
        self.assertEqual(timer_entry.entry_source_display, 'Timer Entry')

        # 2. Stop timer
        stop_url = reverse('timetracking:api_timer_stop', kwargs={'slug': self.workspace.slug})
        self.client.post(stop_url)
        timer_entry.refresh_from_db()
        self.assertEqual(timer_entry.entry_type, TimeEntryType.TIMER)
        self.assertEqual(timer_entry.entry_source_display, 'Timer Entry')

        # 3. Manual entry
        manual_url = reverse('timetracking:manual_time_entry', kwargs={'slug': self.workspace.slug})
        today = timezone.localdate()
        self.client.post(manual_url, {
            'date': today.strftime('%Y-%m-%d'),
            'hours': '1',
            'minutes': '30',
            'category': 'Research',
            'description': 'Exploring LLM caching strategies'
        })
        manual_entry = TimeEntry.objects.filter(user=self.member_user, entry_type=TimeEntryType.MANUAL).order_by('-created_at').first()
        self.assertEqual(manual_entry.entry_type, TimeEntryType.MANUAL)
        self.assertEqual(manual_entry.entry_source_display, 'Manual Entry')

    def test_all_work_type_categories_support(self):
        """All 9 categories are cleanly categorized and clean_description handles them."""
        categories = [
            'Development', 'Bug fixes', 'Documentation', 'Meeting',
            'Research', 'Code review', 'Design', 'API integration', 'Other'
        ]
        for cat in categories:
            entry = TimeEntry(
                workspace=self.workspace,
                user=self.member_user,
                task=self.task,
                duration_seconds=3600,
                description=f"[{cat}] Completed work on module"
            )
            self.assertEqual(entry.category, cat)
            self.assertEqual(entry.clean_description, "Completed work on module")

    def test_rich_text_safe_rendering_and_sanitization(self):
        """Rich text descriptions render markdown safely and sanitize malicious HTML tags and attributes."""
        from core.templatetags.rich_text import render_rich_text
        markdown_desc = "**Bold work** and *italic review* with [Link](https://aetherspace.dev) <script>evilScript()</script><img src=x onerror='evilAttr()'>"
        safe_output = render_rich_text(markdown_desc)

        self.assertIn("<strong>Bold work</strong>", safe_output)
        self.assertIn("<em>italic review</em>", safe_output)
        self.assertIn('href="https://aetherspace.dev"', safe_output)
        self.assertNotIn("<script>", safe_output)
        self.assertNotIn("onerror", safe_output)

    def test_timesheet_hover_card_and_avatar_context(self):
        """Timesheet view attaches workspace memberships to entries to prevent N+1 queries in hover cards."""
        TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            duration_seconds=3600,
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.MANUAL
        )

        self.client.force_login(self.admin_user)
        url = reverse('timetracking:workspace_timesheet', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        logs = resp.context['logs_page']
        self.assertGreaterEqual(len(logs), 1)
        for e in logs:
            self.assertIsNotNone(e.workspace_member)
            self.assertEqual(e.workspace_member.workspace, self.workspace)
        self.assertIn('available_bugs', resp.context)
        # Check that hover card and avatar template components were rendered
        content = resp.content.decode('utf-8')
        self.assertIn('aether-hover-card', content)
        self.assertIn(self.member_user.email, content)

    def test_legacy_entry_display_compatibility(self):
        """Entries without tags or task associations fallback sensibly without error."""
        legacy_entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=None,
            duration_seconds=1800,
            description='',
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.TIMER
        )
        self.assertEqual(legacy_entry.category, 'Development')
        self.assertEqual(legacy_entry.clean_description, '')
        self.assertEqual(legacy_entry.entry_source_display, 'Timer Entry')
        self.assertEqual(legacy_entry.sprint_name, '—')
        self.assertEqual(legacy_entry.duration_formatted, '30m')

    def test_api_timer_start_with_bug_defect_association(self):
        """Starting timer on a bug defect associates bug code, Bug Fix category, and Timer Entry source."""
        from bugs.models import Bug, BugSeverity, BugStatus
        bug = Bug.objects.create(
            bug_code='B-882316',
            workspace=self.workspace,
            reporter=self.member_user,
            title='Null pointer in checkout',
            severity=BugSeverity.SEV2,
            status=BugStatus.OPEN,
            linked_task=self.task
        )

        self.client.force_login(self.member_user)
        start_url = reverse('timetracking:api_timer_start', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(start_url, {
            'task_id': '',
            'bug_code': bug.bug_code,
            'category': 'Bug fixes',
            'description': 'Investigating crash stack trace'
        })

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['bug_code'], 'B-882316')
        self.assertEqual(data['category'], 'Bug fixes')

        # Check DB entry
        entry = TimeEntry.objects.get(id=data['timer_id'])
        self.assertEqual(entry.entry_type, TimeEntryType.TIMER)
        self.assertEqual(entry.entry_source_display, 'Timer Entry')
        self.assertEqual(entry.linked_bug_code, 'B-882316')
        self.assertEqual(entry.category, 'Bug fixes')
        self.assertEqual(entry.clean_description, 'Investigating crash stack trace')
        self.assertEqual(entry.task, self.task)  # Linked through bug.linked_task

        # Check status API returns bug info
        status_url = reverse('timetracking:api_timer_status', kwargs={'slug': self.workspace.slug})
        status_resp = self.client.get(status_url)
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.json()
        self.assertEqual(status_data['bug_code'], 'B-882316')
        self.assertEqual(status_data['category'], 'Bug fixes')

    def test_timer_entry_vs_manual_entry_source_labels(self):
        """Timesheet clearly distinguishes Timer Entry vs Manual Entry in models and rendered UI."""
        now = timezone.now()
        timer_entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            description="Timer session work",
            started_at=now - timedelta(hours=1),
            ended_at=now,
            duration_seconds=3600,
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.TIMER
        )
        manual_entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            description="Manual offline work",
            started_at=now - timedelta(hours=3),
            ended_at=now - timedelta(hours=2),
            duration_seconds=3600,
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.MANUAL
        )

        self.assertEqual(timer_entry.entry_source_display, 'Timer Entry')
        self.assertEqual(manual_entry.entry_source_display, 'Manual Entry')

        self.client.force_login(self.admin_user)
        url = reverse('timetracking:workspace_timesheet', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn('⏱️ Timer Entry', content)
        self.assertIn('📝 Manual Entry', content)

    def test_view_day_date_filtering_and_banner(self):
        """View Day filters to today only, renders detailed day banner with navigation, and links to timesheet-section."""
        now = timezone.now()
        # Today's entry
        today_entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            description="Today effort",
            started_at=now,
            ended_at=now + timedelta(hours=1),
            duration_seconds=3600,
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.TIMER
        )
        # 3 days ago entry
        old_entry = TimeEntry.objects.create(
            workspace=self.workspace,
            user=self.member_user,
            task=self.task,
            description="Past effort",
            started_at=now - timedelta(days=3),
            ended_at=now - timedelta(days=3) + timedelta(hours=1),
            duration_seconds=3600,
            status=TimerStatus.COMPLETED,
            entry_type=TimeEntryType.MANUAL
        )

        self.client.force_login(self.admin_user)
        url = reverse('timetracking:workspace_timesheet', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(f"{url}?date_range=today")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['date_filter'], 'today')

        logs = resp.context['logs_page']
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].id, today_entry.id)

        content = resp.content.decode('utf-8')
        self.assertIn('data-testid="detailed-day-view-banner"', content)
        self.assertIn('Detailed Day View:', content)
        self.assertIn('data-testid="day-view-prev-btn"', content)
        self.assertIn('data-testid="day-view-next-btn"', content)
        self.assertIn('id="timesheet-section"', content)
        self.assertIn('?date_range=today#timesheet-section', content)

    def test_bullet_and_numbered_list_rich_text_rendering(self):
        """Markdown bullet points and numbered lists render as semantic ul, ol, li without flattening or scripts."""
        from core.templatetags.rich_text import render_rich_text

        # Unordered bullet list
        raw_ul = "Tasks accomplished:\n- Implemented API endpoints\n- Added database indexes\n- Verified unit tests"
        html_ul = render_rich_text(raw_ul)
        self.assertIn('<ul>', html_ul)
        self.assertIn('<li>Implemented API endpoints</li>', html_ul)
        self.assertIn('<li>Added database indexes</li>', html_ul)
        self.assertIn('<li>Verified unit tests</li>', html_ul)

        # Ordered numbered list
        raw_ol = "Deployment steps:\n1. Run migrations\n2. Collect static\n3. Restart web workers"
        html_ol = render_rich_text(raw_ol)
        self.assertIn('<ol>', html_ol)
        self.assertIn('<li>Run migrations</li>', html_ol)
        self.assertIn('<li>Collect static</li>', html_ol)
        self.assertIn('<li>Restart web workers</li>', html_ol)

        # XSS injection within lists
        malicious = "- Safe item\n- <script>alert('xss')</script><img src=x onerror=alert(1)>"
        safe_html = render_rich_text(malicious)
        self.assertNotIn('<script>', safe_html)
        self.assertNotIn('onerror', safe_html)
        self.assertIn('Safe item', safe_html)



