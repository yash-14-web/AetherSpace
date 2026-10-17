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
    get_upcoming_schedule_items,
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

    def test_week_and_day_views(self):
        self.client.login(username='mary@example.com', password=self.password)
        base_url = reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug})

        # 1. Week view
        resp_week = self.client.get(f"{base_url}?view=week")
        self.assertEqual(resp_week.status_code, 200)
        self.assertIn('week_data', resp_week.context)
        self.assertEqual(len(resp_week.context['week_data']['days']), 7)

        # 2. Day view
        resp_day = self.client.get(f"{base_url}?view=day")
        self.assertEqual(resp_day.status_code, 200)
        self.assertIn('day_data', resp_day.context)
        self.assertEqual(len(resp_day.context['day_data']['hourly_slots']), 13)

    def test_upcoming_deadlines_timeframes(self):
        self.client.login(username='mary@example.com', password=self.password)
        url = reverse('calendars:upcoming_deadlines', kwargs={'slug': self.workspace.slug})

        # 14 days timeframe
        resp_14 = self.client.get(f"{url}?days=14")
        self.assertEqual(resp_14.status_code, 200)
        self.assertContains(resp_14, 'Next 14 Days')

        # 30 days timeframe
        resp_30 = self.client.get(f"{url}?days=30")
        self.assertEqual(resp_30.status_code, 200)
        self.assertContains(resp_30, 'Next 30 Days')

    def test_event_creation_with_agenda_and_reference_links(self):
        import json
        self.client.login(username='mary@example.com', password=self.password)
        url = reverse('calendars:event_create', kwargs={'slug': self.workspace.slug})

        now = timezone.now()
        post_data = {
            'title': 'Sprint Review & Architecture Sync',
            'description': 'Discussion on backlog priorities.',
            'event_type': 'MEETING',
            'calendar_category': 'WORKSPACE',
            'repeat': 'NONE',
            'start_date': (now.date() + timedelta(days=3)).strftime('%Y-%m-%d'),
            'start_time': '14:00',
            'end_date': (now.date() + timedelta(days=3)).strftime('%Y-%m-%d'),
            'end_time': '15:30',
            'agenda': '1. System Demo\n2. Q&A\n3. Action Items',
            'reference_links_raw': json.dumps([
                {'title': 'System Spec Document', 'url': 'https://docs.aetherspace.io/spec'},
                {'title': 'Figma Mockup', 'url': 'https://figma.com/file/123'}
            ]),
            'invitees': [str(self.contributor.id)],
        }

        post_resp = self.client.post(url, data=post_data)
        self.assertEqual(post_resp.status_code, 302)

        event = CalendarEvent.objects.filter(workspace=self.workspace, title='Sprint Review & Architecture Sync').first()
        self.assertIsNotNone(event)
        self.assertIn('System Demo', event.agenda)
        self.assertEqual(len(event.reference_links), 2)
        self.assertEqual(event.reference_links[0]['title'], 'System Spec Document')

        # Verify Detail Page renders agenda and reference links
        detail_url = reverse('calendars:event_detail', kwargs={'slug': self.workspace.slug, 'event_id': event.id})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'System Demo')
        self.assertContains(detail_resp, 'System Spec Document')
        self.assertContains(detail_resp, 'https://docs.aetherspace.io/spec')

    def test_calendar_markdown_agenda_rendering_and_persistence(self):
        """Markdown agenda is persisted in raw form and rendered as sanitized HTML in detail view."""
        self.client.login(username='mary@example.com', password=self.password)
        create_url = reverse('calendars:event_create', kwargs={'slug': self.workspace.slug})

        raw_agenda = (
            "### Architecture Review\n"
            "**Key Principles**:\n"
            "- [ ] Review DB schema\n"
            "- [x] Validate RBAC rules\n"
            "> Stability first.\n"
            "`run_command`"
        )
        post_data = {
            'title': 'Markdown Architecture Sync',
            'event_type': 'MEETING',
            'calendar_category': 'WORKSPACE',
            'repeat': 'NONE',
            'start_date': (timezone.now().date() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'start_time': '10:00',
            'end_date': (timezone.now().date() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'end_time': '11:00',
            'agenda': raw_agenda,
            'invitees': [str(self.contributor.id)],
        }
        resp = self.client.post(create_url, data=post_data)
        self.assertEqual(resp.status_code, 302)

        # 1. Verify exact raw markdown is persisted in DB
        event = CalendarEvent.objects.get(workspace=self.workspace, title='Markdown Architecture Sync')
        self.assertEqual(event.agenda, raw_agenda)

        # 2. Verify Detail view renders sanitized HTML rather than raw markdown syntax
        detail_url = reverse('calendars:event_detail', kwargs={'slug': self.workspace.slug, 'event_id': event.id})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, '<h3')
        self.assertContains(detail_resp, 'Architecture Review')
        self.assertContains(detail_resp, '<strong>Key Principles</strong>')
        self.assertContains(detail_resp, 'type="checkbox"')
        self.assertContains(detail_resp, '<blockquote')
        self.assertContains(detail_resp, '<code>run_command</code>')

        # 3. Verify Edit view reloads exact raw markdown into textarea
        edit_url = reverse('calendars:event_edit', kwargs={'slug': self.workspace.slug, 'event_id': event.id})
        edit_resp = self.client.get(edit_url)
        self.assertEqual(edit_resp.status_code, 200)
        self.assertContains(edit_resp, '### Architecture Review')

    def test_calendar_people_search_first_and_workspace_isolation(self):
        """Calendar people picker operates search-first, returns real names, and enforces workspace isolation."""
        self.client.login(username='mary@example.com', password=self.password)
        search_api_url = reverse('workspaces:api_workspace_members_search', kwargs={'slug': self.workspace.slug})

        # 1. Empty query must return empty list (search-first requirement)
        empty_resp = self.client.get(f"{search_api_url}?q=")
        self.assertEqual(empty_resp.status_code, 200)
        empty_data = empty_resp.json()
        self.assertEqual(empty_data['status'], 'ok')
        self.assertEqual(len(empty_data['users']), 0)

        # 2. Searching by name returns permitted member with real full name and Contributor ID
        search_resp = self.client.get(f"{search_api_url}?q=Dan")
        self.assertEqual(search_resp.status_code, 200)
        search_data = search_resp.json()
        self.assertEqual(search_data['status'], 'ok')
        self.assertEqual(len(search_data['users']), 1)
        user_info = search_data['users'][0]
        self.assertEqual(user_info['full_name'], 'Dan Dev')
        self.assertEqual(user_info['id'], str(self.contributor.id))
        self.assertTrue('contributor_id' in user_info)

        # 3. Searching for an outsider user not belonging to this workspace returns 0 results (isolation)
        outsider_resp = self.client.get(f"{search_api_url}?q=Bob")
        self.assertEqual(outsider_resp.status_code, 200)
        outsider_data = outsider_resp.json()
        self.assertEqual(len(outsider_data['users']), 0)

        # 3. Searching for a user belonging to another workspace returns 0 results (isolation)
        foreign_user = User.objects.create_user(
            email='foreign@othercompany.com',
            password='TestPassword123!',
            full_name='Foreign Hacker'
        )
        foreign_ws = Workspace.objects.create(name='Foreign WS', slug='foreign-ws', owner=foreign_user)
        WorkspaceMembership.objects.create(
            workspace=foreign_ws,
            user=foreign_user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        isolated_resp = self.client.get(f"{search_api_url}?q=Foreign")
        self.assertEqual(isolated_resp.status_code, 200)
        isolated_data = isolated_resp.json()
        self.assertEqual(len(isolated_data['users']), 0)


class CalendarRedesignAndSchedulingAuditTests(TestCase):
    """
    Test suite verifying the approved Calendar UI redesign, scheduling logic audit,
    lifecycle status enforcement, and upcoming events filtering rules.
    """
    def setUp(self):
        self.client = Client()
        self.password = 'TestPassword123!'
        self.user = User.objects.create_user(
            email='auditor@aetherspace.dev',
            password=self.password,
            full_name='Audit Engineer'
        )
        self.workspace = Workspace.objects.create(
            name='Audit Workspace',
            slug='audit-workspace',
            owner=self.user
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )
        self.client.login(username='auditor@aetherspace.dev', password=self.password)

    def test_upcoming_event_filtering_lifecycle(self):
        """
        Critical invariant: Completed/ended meetings, passed events, cancelled events,
        completed tasks, and closed bugs must NEVER appear in Upcoming Events.
        """
        now = timezone.now()
        today = timezone.localdate()

        # 1. Past ended meeting (MUST BE EXCLUDED)
        Meeting.objects.create(
            workspace=self.workspace,
            host=self.user,
            title='Old Morning Standup',
            scheduled_start=now - timedelta(hours=3),
            scheduled_end=now - timedelta(hours=2, minutes=30),
            actual_start=now - timedelta(hours=3),
            actual_end=now - timedelta(hours=2, minutes=30),
            status=MeetingStatus.ENDED,
            meeting_code='meet-past-ended'
        )

        # 2. Past meeting still marked SCHEDULED (passed time) (MUST BE EXCLUDED)
        Meeting.objects.create(
            workspace=self.workspace,
            host=self.user,
            title='Missed Scheduled Call',
            scheduled_start=now - timedelta(hours=2),
            scheduled_end=now - timedelta(hours=1),
            status=MeetingStatus.SCHEDULED,
            meeting_code='meet-past-sched'
        )

        # 3. Cancelled meeting (MUST BE EXCLUDED)
        Meeting.objects.create(
            workspace=self.workspace,
            host=self.user,
            title='Cancelled Sync',
            scheduled_start=now + timedelta(hours=2),
            scheduled_end=now + timedelta(hours=3),
            status=MeetingStatus.CANCELLED,
            meeting_code='meet-cancelled'
        )

        # 4. Future scheduled meeting (MUST BE INCLUDED)
        Meeting.objects.create(
            workspace=self.workspace,
            host=self.user,
            title='Sprint Retrospective',
            scheduled_start=now + timedelta(hours=4),
            scheduled_end=now + timedelta(hours=5),
            status=MeetingStatus.SCHEDULED,
            meeting_code='meet-retro'
        )

        # 5. Live ongoing meeting (scheduled_end >= now) (MUST BE INCLUDED)
        Meeting.objects.create(
            workspace=self.workspace,
            host=self.user,
            title='Emergency War Room',
            scheduled_start=now - timedelta(minutes=15),
            scheduled_end=now + timedelta(minutes=45),
            status=MeetingStatus.LIVE,
            meeting_code='meet-war-room'
        )

        # 6. Completed CalendarEvent (MUST BE EXCLUDED)
        create_calendar_event(
            workspace=self.workspace,
            user=self.user,
            data={
                'title': 'Completed Workshop',
                'computed_start_at': now - timedelta(days=1),
                'computed_end_at': now - timedelta(days=1) + timedelta(hours=2),
                'event_type': CalendarEventType.GENERAL,
                'status': EventStatus.COMPLETED
            }
        )

        # 7. Future CalendarEvent (MUST BE INCLUDED)
        create_calendar_event(
            workspace=self.workspace,
            user=self.user,
            data={
                'title': 'Q4 Product Roadmap',
                'computed_start_at': now + timedelta(days=3),
                'computed_end_at': now + timedelta(days=3, hours=2),
                'event_type': CalendarEventType.MILESTONE,
                'status': EventStatus.UPCOMING
            }
        )

        # 8. Completed Task (MUST BE EXCLUDED)
        Task.objects.create(
            task_code='771001',
            workspace=self.workspace,
            title='Finished Setup Docs',
            reporter=self.user,
            assignee=self.user,
            due_date=today + timedelta(days=2),
            status=TaskStatus.DONE
        )

        # 9. Active Task due future (MUST BE INCLUDED)
        Task.objects.create(
            task_code='771002',
            workspace=self.workspace,
            title='Implement Cache Layer',
            reporter=self.user,
            assignee=self.user,
            due_date=today + timedelta(days=2),
            status=TaskStatus.IN_PROGRESS
        )

        # 10. Closed Bug (MUST BE EXCLUDED)
        Bug.objects.create(
            bug_code='B-991001',
            workspace=self.workspace,
            title='Closed CSS Glitch',
            reporter=self.user,
            assignee=self.user,
            due_date=today + timedelta(days=1),
            status=BugStatus.CLOSED
        )

        # Query upcoming items
        upcoming = get_upcoming_schedule_items(self.workspace, limit=20)
        titles = [item['title'] for item in upcoming]

        # Invariant assertions: past/ended/cancelled/completed items MUST NOT be present
        self.assertNotIn('Old Morning Standup', titles)
        self.assertNotIn('Missed Scheduled Call', titles)
        self.assertNotIn('Cancelled Sync', titles)
        self.assertNotIn('Completed Workshop', titles)
        self.assertNotIn('Finished Setup Docs', titles)
        self.assertNotIn('Closed CSS Glitch', titles)

        # Invariant assertions: valid future and ongoing items MUST be present
        self.assertIn('Emergency War Room', titles)
        self.assertIn('Sprint Retrospective', titles)
        self.assertIn('Q4 Product Roadmap', titles)
        self.assertIn('Implement Cache Layer', titles)

    def test_upcoming_events_chronological_ordering(self):
        """Upcoming events must be strictly ordered ascending by start datetime."""
        now = timezone.now()
        today = timezone.localdate()

        Meeting.objects.create(
            workspace=self.workspace,
            host=self.user,
            title='Meeting Later Today',
            scheduled_start=now + timedelta(hours=2),
            scheduled_end=now + timedelta(hours=3),
            status=MeetingStatus.SCHEDULED,
            meeting_code='meet-later-today'
        )
        Task.objects.create(
            task_code='771003',
            workspace=self.workspace,
            title='Task Due Tomorrow',
            reporter=self.user,
            assignee=self.user,
            due_date=today + timedelta(days=1),
            status=TaskStatus.TODO
        )
        create_calendar_event(
            workspace=self.workspace,
            user=self.user,
            data={
                'title': 'Milestone Next Week',
                'computed_start_at': now + timedelta(days=5),
                'computed_end_at': now + timedelta(days=5, hours=1),
                'event_type': CalendarEventType.MILESTONE,
                'status': EventStatus.UPCOMING
            }
        )

        upcoming = get_upcoming_schedule_items(self.workspace, limit=10)
        for i in range(len(upcoming) - 1):
            self.assertLessEqual(upcoming[i]['dt_sort'], upcoming[i + 1]['dt_sort'])

    def test_month_navigation_and_year_transitions(self):
        """Grid must calculate correct weeks, adjacent days, and prev/next across month/year borders."""
        # Test December -> January boundary
        dec_cal = build_month_calendar_matrix(self.workspace, year=2026, month=12)
        self.assertEqual(dec_cal['year'], 2026)
        self.assertEqual(dec_cal['month'], 12)
        self.assertEqual(len(dec_cal['weeks']), 6)
        # 6 weeks * 7 days = 42 cells
        total_cells = sum(len(w) for w in dec_cal['weeks'])
        self.assertEqual(total_cells, 42)

        # Test January -> previous year boundary
        jan_cal = build_month_calendar_matrix(self.workspace, year=2027, month=1)
        self.assertEqual(jan_cal['year'], 2027)
        self.assertEqual(jan_cal['month'], 1)
        self.assertEqual(len(jan_cal['weeks']), 6)

    def test_category_filters(self):
        """Category filter pills must selectively query and render corresponding items."""
        now = timezone.now()
        today = timezone.localdate()

        Task.objects.create(
            task_code='771004',
            workspace=self.workspace,
            title='Only Task Filter Item',
            reporter=self.user,
            due_date=today,
            status=TaskStatus.TODO
        )
        Bug.objects.create(
            bug_code='B-771004',
            workspace=self.workspace,
            title='Only Bug Filter Item',
            reporter=self.user,
            due_date=today,
            status=BugStatus.OPEN
        )

        # 1. Filter only tasks
        url_tasks = reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug}) + '?cats=tasks'
        resp_tasks = self.client.get(url_tasks)
        self.assertEqual(resp_tasks.status_code, 200)
        self.assertEqual(resp_tasks.context['selected_cat'], 'tasks')
        self.assertContains(resp_tasks, 'Only Task Filter Item')
        self.assertNotContains(resp_tasks, 'Only Bug Filter Item')

        # 2. Filter only bugs
        url_bugs = reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug}) + '?cats=bugs'
        resp_bugs = self.client.get(url_bugs)
        self.assertEqual(resp_bugs.status_code, 200)
        self.assertEqual(resp_bugs.context['selected_cat'], 'bugs')
        self.assertContains(resp_bugs, 'Only Bug Filter Item')
        self.assertNotContains(resp_bugs, 'Only Task Filter Item')

    def test_view_navigation_and_template_cards_rendered(self):
        """Calendar renders Month, Week, Day, and Agenda views with approved cards."""
        base_url = reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug})

        # Month view
        month_resp = self.client.get(base_url + '?view=month')
        self.assertEqual(month_resp.status_code, 200)
        self.assertContains(month_resp, 'Plan, schedule, and stay in sync with your workspace.')
        self.assertContains(month_resp, 'Create Event')
        self.assertContains(month_resp, 'Upcoming Events')
        self.assertContains(month_resp, 'Quick Actions')
        self.assertContains(month_resp, 'Start Meeting')
        self.assertContains(month_resp, 'View Agenda')
        self.assertContains(month_resp, 'View Deadlines')

        # Week view
        week_resp = self.client.get(base_url + '?view=week')
        self.assertEqual(week_resp.status_code, 200)
        self.assertContains(week_resp, 'Quick Actions')

        # Day view
        day_resp = self.client.get(base_url + '?view=day')
        self.assertEqual(day_resp.status_code, 200)
        self.assertContains(day_resp, 'Quick Actions')

        # Agenda view
        agenda_url = reverse('calendars:agenda_view', kwargs={'slug': self.workspace.slug})
        agenda_resp = self.client.get(agenda_url)
        self.assertEqual(agenda_resp.status_code, 200)

    def test_quick_action_routes_validity(self):
        """All 4 Quick Actions must map to valid accessible routes for workspace members."""
        ws_slug = self.workspace.slug

        # 1. Create Event
        url_event_create = reverse('calendars:event_create', kwargs={'slug': ws_slug})
        self.assertEqual(self.client.get(url_event_create).status_code, 200)

        # 2. Start Meeting launcher
        url_meeting_start = reverse('meetings:meeting_start', kwargs={'slug': ws_slug})
        # Instant launcher accepts GET to render launcher, redirects, or returns 503 if maintenance
        resp_start = self.client.get(url_meeting_start)
        self.assertIn(resp_start.status_code, [200, 302, 503])

        # 3. View Agenda
        url_agenda = reverse('calendars:agenda_view', kwargs={'slug': ws_slug})
        self.assertEqual(self.client.get(url_agenda).status_code, 200)

        # 4. View Deadlines
        url_deadlines = reverse('calendars:upcoming_deadlines', kwargs={'slug': ws_slug})
        self.assertEqual(self.client.get(url_deadlines).status_code, 200)

    def test_workspace_isolation_in_calendar(self):
        """Events from another workspace must not appear in this workspace."""
        other_user = User.objects.create_user(
            email='other@foreign.com',
            password=self.password,
            full_name='Other Owner'
        )
        other_workspace = Workspace.objects.create(
            name='Other Workspace',
            slug='other-workspace',
            owner=other_user
        )
        now = timezone.now()
        create_calendar_event(
            workspace=other_workspace,
            user=other_user,
            data={
                'title': 'Foreign Confidential Meeting',
                'computed_start_at': now + timedelta(days=1),
                'computed_end_at': now + timedelta(days=1, hours=1),
                'event_type': CalendarEventType.GENERAL
            }
        )

        resp = self.client.get(reverse('calendars:calendar_view', kwargs={'slug': self.workspace.slug}))
        self.assertNotContains(resp, 'Foreign Confidential Meeting')



