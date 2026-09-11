import uuid
from datetime import date, datetime, time, timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model

from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from tasks.models import Task, TaskPriority, TaskStatus
from bugs.models import Bug, BugSeverity, BugStatus
from meetings.models import Meeting, MeetingType, MeetingStatus
from calendars.models import (
    CalendarEvent,
    CalendarEventType,
    CalendarCategory,
    EventStatus,
    EventRepeat,
    CalendarEventAttendee,
    AttendeeStatus,
)
from calendars.services import (
    build_month_calendar_matrix,
    build_agenda_stream,
    build_upcoming_deadlines,
    create_calendar_event,
    get_unified_schedule_items,
)

User = get_user_model()


class CalendarModelAndServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='owner@example.com',
            password='TestPassword123!',
            full_name='Alice Owner'
        )
        self.manager = User.objects.create_user(
            email='manager@example.com',
            password='TestPassword123!',
            full_name='Mary Manager'
        )
        self.contributor = User.objects.create_user(
            email='dev@example.com',
            password='TestPassword123!',
            full_name='Bob Contributor'
        )
        self.workspace = Workspace.objects.create(
            name='Calendar Space',
            slug='calendar-space',
            owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_create_calendar_event(self):
        start = timezone.now() + timedelta(days=2)
        end = start + timedelta(hours=2)
        event_data = {
            'title': 'Q3 Product Planning',
            'description': 'Roadmap sync',
            'computed_start_at': start,
            'computed_end_at': end,
            'event_type': CalendarEventType.GENERAL,
            'calendar_category': CalendarCategory.WORKSPACE,
            'location': 'Room 4B',
            'meeting_link': 'https://meet.jit.si/aether-test'
        }
        event = create_calendar_event(
            workspace=self.workspace,
            user=self.owner,
            data=event_data,
            invitees=[self.contributor, self.manager]
        )

        self.assertEqual(event.title, 'Q3 Product Planning')
        self.assertEqual(event.workspace, self.workspace)
        # 1 creator (accepted) + 2 invitees = 3 attendees
        self.assertEqual(event.attendees.count(), 3)
        self.assertEqual(event.event_type, CalendarEventType.GENERAL)
        self.assertFalse(event.is_all_day)

    def test_unified_schedule_items_and_cross_entities(self):
        now = timezone.now()
        start_date = now.date() - timedelta(days=5)
        end_date = now.date() + timedelta(days=15)

        # 1. Calendar Event
        event_time = timezone.make_aware(datetime.combine(now.date() + timedelta(days=2), time(10, 0)))
        create_calendar_event(
            workspace=self.workspace,
            user=self.owner,
            data={
                'title': 'Sprint Kickoff',
                'computed_start_at': event_time,
                'computed_end_at': event_time + timedelta(hours=1),
                'event_type': CalendarEventType.MILESTONE,
            }
        )

        # 2. Task with due date
        Task.objects.create(
            task_code='619347',
            workspace=self.workspace,
            title='Design DB Schema',
            reporter=self.owner,
            assignee=self.contributor,
            priority=TaskPriority.HIGH,
            status=TaskStatus.IN_PROGRESS,
            due_date=now.date() + timedelta(days=3),
        )

        # 3. Bug with due date
        Bug.objects.create(
            bug_code='B-882316',
            workspace=self.workspace,
            title='Fix Auth CSRF issue',
            reporter=self.contributor,
            assignee=self.contributor,
            severity=BugSeverity.SEV2,
            status=BugStatus.OPEN,
            due_date=now.date() + timedelta(days=4),
        )

        # 4. Meeting scheduled
        meeting_time = timezone.make_aware(datetime.combine(now.date() + timedelta(days=5), time(15, 30)))
        Meeting.objects.create(
            workspace=self.workspace,
            host=self.manager,
            title='Design Review Session',
            scheduled_start=meeting_time,
            meeting_code='meet-1111-2222',
            meeting_type=MeetingType.STANDUP,
            status=MeetingStatus.SCHEDULED,
        )

        items = get_unified_schedule_items(
            workspace=self.workspace,
            start_date=start_date,
            end_date=end_date,
        )

        kinds = {item['category'] for item in items}
        self.assertIn('milestone', kinds)
        self.assertIn('task', kinds)
        self.assertIn('bug', kinds)
        self.assertIn('meeting', kinds)

        # Build agenda stream
        agenda_data = build_agenda_stream(
            workspace=self.workspace,
            target_date=start_date,
            days_ahead=20,
        )
        self.assertTrue(len(agenda_data['date_groups']) > 0)

        # Build month calendar matrix
        cal_data = build_month_calendar_matrix(
            workspace=self.workspace,
            year=now.year,
            month=now.month,
        )
        self.assertEqual(cal_data['year'], now.year)
        self.assertEqual(cal_data['month'], now.month)
        self.assertEqual(len(cal_data['weeks']), 6)

    def test_overdue_and_upcoming_deadlines(self):
        now = timezone.now()
        yesterday = now.date() - timedelta(days=1)
        tomorrow = now.date() + timedelta(days=1)

        # Overdue task
        Task.objects.create(
            task_code='619348',
            workspace=self.workspace,
            title='Overdue Task 1',
            reporter=self.owner,
            assignee=self.contributor,
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            due_date=yesterday,
        )

        # Completed task (should NOT be in overdue)
        Task.objects.create(
            task_code='619349',
            workspace=self.workspace,
            title='Done Task',
            reporter=self.owner,
            assignee=self.contributor,
            status=TaskStatus.DONE,
            priority=TaskPriority.MEDIUM,
            due_date=yesterday,
        )

        # Overdue bug
        Bug.objects.create(
            bug_code='B-882317',
            workspace=self.workspace,
            title='Critical memory leak',
            reporter=self.owner,
            assignee=self.contributor,
            status=BugStatus.IN_PROGRESS,
            severity=BugSeverity.SEV1,
            due_date=yesterday,
        )

        # Tomorrow task
        Task.objects.create(
            task_code='619350',
            workspace=self.workspace,
            title='Tomorrow delivery',
            reporter=self.owner,
            assignee=self.contributor,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            due_date=tomorrow,
        )

        deadlines = build_upcoming_deadlines(self.workspace)
        self.assertEqual(len(deadlines['overdue_items']), 2)
        self.assertEqual(deadlines['deadline_summary']['overdue_total'], 2)
        self.assertTrue(len(deadlines['tomorrow']) >= 1)


class CalendarViewsAndRBACTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = 'Password123!'
        self.owner = User.objects.create_user(
            email='boss@example.com',
            password=self.password,
            full_name='Boss Admin'
        )
        self.manager = User.objects.create_user(
            email='mary@example.com',
            password=self.password,
            full_name='Mary Manager'
        )
        self.contributor = User.objects.create_user(
            email='dan@example.com',
            password=self.password,
            full_name='Dan Dev'
        )
        self.outsider = User.objects.create_user(
            email='bob@example.com',
            password=self.password,
            full_name='Bob Outsider'
        )

        self.workspace = Workspace.objects.create(
            name='Agile Team Hub',
            slug='agile-team-hub',
            owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.manager,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.contributor,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

    def test_calendar_view_authenticated_workspace_member(self):
        self.client.login(username='boss@example.com', password=self.password)
        url = reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Agile Team Hub')
        self.assertContains(resp, 'Calendar')

    def test_calendar_view_outsider_denied(self):
        self.client.login(username='bob@example.com', password=self.password)
        url = reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_agenda_view(self):
        self.client.login(username='dan@example.com', password=self.password)
        url = reverse('calendars:agenda_view', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Agenda')
        self.assertContains(resp, 'Timeline Stream')

    def test_upcoming_deadlines_view(self):
        self.client.login(username='mary@example.com', password=self.password)
        url = reverse('calendars:upcoming_deadlines', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Upcoming Deadlines')

    def test_event_creation_flow(self):
        self.client.login(username='mary@example.com', password=self.password)
        url = reverse('calendars:event_create', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Create Event')

        now = timezone.now()
        post_data = {
            'title': 'New Sprint Planning',
            'description': 'Discussion on backlog priorities and roadmap.',
            'event_type': 'GENERAL',
            'calendar_category': 'WORKSPACE',
            'repeat': 'NONE',
            'start_date': (now.date() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'start_time': '10:00',
            'end_date': (now.date() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'end_time': '11:30',
            'location': 'Conference Hall A',
            'meeting_link': 'https://meet.aetherspace.io/sprint-10',
            'invitees': [str(self.contributor.id), str(self.owner.id)],
        }

        post_resp = self.client.post(url, data=post_data)
        if post_resp.status_code != 302:
            form = post_resp.context.get('form')
            if form:
                print("DEBUG FORM ERRORS:", form.errors)
        self.assertEqual(post_resp.status_code, 302)
        event = CalendarEvent.objects.filter(workspace=self.workspace, title='New Sprint Planning').first()
        self.assertIsNotNone(event)
        self.assertEqual(event.created_by, self.manager)
        # creator + 2 invitees = 3 attendees
        self.assertEqual(event.attendees.count(), 3)

    def test_event_detail_and_rbac_permissions(self):
        # Create an event owned by manager
        now = timezone.now()
        event = CalendarEvent.objects.create(
            workspace=self.workspace,
            title='Manager Sync',
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=1, hours=1),
            created_by=self.manager,
        )

        detail_url = reverse('calendars:event_detail', kwargs={'slug': self.workspace.slug, 'event_id': event.id})
        edit_url = reverse('calendars:event_edit', kwargs={'slug': self.workspace.slug, 'event_id': event.id})
        delete_url = reverse('calendars:event_delete', kwargs={'slug': self.workspace.slug, 'event_id': event.id})

        # 1. Contributor (non-creator) can view event details
        self.client.login(username='dan@example.com', password=self.password)
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Manager Sync')

        # Contributor cannot edit manager's event
        edit_resp = self.client.get(edit_url)
        self.assertEqual(edit_resp.status_code, 403)

        # Contributor cannot delete manager's event
        del_resp = self.client.post(delete_url)
        self.assertEqual(del_resp.status_code, 403)

        # 2. Manager (creator) can edit and delete
        self.client.login(username='mary@example.com', password=self.password)
        edit_resp = self.client.get(edit_url)
        self.assertEqual(edit_resp.status_code, 200)

        # 3. Admin can edit any workspace event
        self.client.login(username='boss@example.com', password=self.password)
        admin_edit_resp = self.client.get(edit_url)
        self.assertEqual(admin_edit_resp.status_code, 200)

        # Admin deletes event
        admin_del_resp = self.client.post(delete_url)
        self.assertEqual(admin_del_resp.status_code, 302)
        self.assertFalse(CalendarEvent.objects.filter(pk=event.pk).exists())
