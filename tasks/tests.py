from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, UserRole
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus, TemporaryAccessGrant
from .models import Task, TaskActivity, TaskStatus, TaskPriority, Sprint, SprintStatus, CodeReviewRequest, CodeReviewStatus, TaskComment
from .services import (
    generate_unique_task_code, create_task, update_task, change_task_status,
    create_code_review_request, update_code_review_status, attach_bug_to_task, detach_bug_from_task
)
import json
from .forms import TaskForm, CodeReviewRequestForm
from bugs.models import Bug, BugSeverity, BugStatus
from core.templatetags.rich_text import render_rich_text
from django.core.exceptions import PermissionDenied, ValidationError


class TaskManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "StrongPassword123!"

        # Create primary workspace and owner
        self.alice = User.objects.create_user(
            email="alice.tasks@aetherspace.dev",
            password=self.password,
            full_name="Alice Engineer"
        )
        self.workspace = Workspace.objects.create(
            name="Alpha Workspace",
            slug="alpha-workspace",
            owner=self.alice
        )
        self.alice_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.alice,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        # Create a teammate contributor
        self.bob = User.objects.create_user(
            email="bob.tasks@aetherspace.dev",
            password=self.password,
            full_name="Bob Developer"
        )
        self.bob_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.bob,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Create another isolated workspace and user
        self.charlie = User.objects.create_user(
            email="charlie.tasks@aetherspace.dev",
            password=self.password,
            full_name="Charlie Intruder"
        )
        self.other_workspace = Workspace.objects.create(
            name="Beta Workspace",
            slug="beta-workspace",
            owner=self.charlie
        )
        self.charlie_membership = WorkspaceMembership.objects.create(
            workspace=self.other_workspace,
            user=self.charlie,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_task_code_generation_is_6_digits_and_unique(self):
        """Verify Task IDs are 6 digits and collision safe."""
        code1 = generate_unique_task_code()
        self.assertEqual(len(code1), 6)
        self.assertTrue(code1.isdigit())

        # Create a task with code1
        Task.objects.create(
            task_code=code1,
            workspace=self.workspace,
            reporter=self.alice,
            title="Initial Test Task"
        )

        # Next generated code must not equal existing code
        code2 = generate_unique_task_code()
        self.assertNotEqual(code1, code2)
        self.assertEqual(len(code2), 6)

    def test_create_task_service_and_activity_logging(self):
        """Test task creation creates Task and logs TaskActivity."""
        task = create_task(
            workspace=self.workspace,
            reporter=self.alice,
            title="Implement Sprint Backlog",
            description="Core agile backlog functionality",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee=self.bob,
            due_date=timezone.now().date() + timedelta(days=5)
        )

        self.assertIsNotNone(task.id)
        self.assertEqual(len(task.task_code), 6)
        self.assertEqual(task.status, TaskStatus.TODO)
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(task.assignee, self.bob)

        # Check activities
        activities = task.activities.all()
        self.assertGreaterEqual(activities.count(), 1)
        creation_act = activities.filter(action=TaskActivity.Action.CREATED).first()
        self.assertIsNotNone(creation_act)
        self.assertEqual(creation_act.actor, self.alice)

    def test_status_workflow_progression_and_audit(self):
        """
        Verify workflow progression: To Do -> In Progress -> Code Review -> Testing -> Done.
        """
        task = create_task(
            workspace=self.workspace,
            reporter=self.alice,
            title="Workflow Verification Task"
        )
        self.assertEqual(task.status, TaskStatus.TODO)

        workflow = [
            TaskStatus.IN_PROGRESS,
            TaskStatus.CODE_REVIEW,
            TaskStatus.TESTING,
            TaskStatus.DONE,
        ]

        for next_status in workflow:
            change_task_status(task, self.alice, next_status)
            task.refresh_from_db()
            self.assertEqual(task.status, next_status)

        # Check activities recorded for status changes
        status_activities = task.activities.filter(action=TaskActivity.Action.STATUS_CHANGED)
        self.assertEqual(status_activities.count(), 4)

    def test_workspace_isolation_blocks_non_members(self):
        """
        Charlie is only a member of Beta Workspace.
        Charlie must be denied access (403) to Alpha Workspace tasks.
        """
        self.client.login(email="charlie.tasks@aetherspace.dev", password=self.password)

        # List view
        url = reverse('tasks:task_list', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # Kanban view
        board_url = reverse('tasks:task_board', kwargs={'slug': self.workspace.slug})
        response = self.client.get(board_url)
        self.assertEqual(response.status_code, 403)

        # Create view
        create_url = reverse('tasks:task_create', kwargs={'slug': self.workspace.slug})
        response = self.client.get(create_url)
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated requests must redirect to login."""
        url = reverse('tasks:task_list', kwargs={'slug': self.workspace.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)

    def test_authorized_member_can_view_and_create_tasks(self):
        """
        Contributor Bob can view the task list, but cannot create a task without permission (403).
        Admin Alice can create a task.
        Bob with an active TemporaryAccessGrant can create a task.
        """
        self.client.login(email="bob.tasks@aetherspace.dev", password=self.password)

        list_url = reverse('tasks:task_list', kwargs={'slug': self.workspace.slug})
        list_resp = self.client.get(list_url)
        self.assertEqual(list_resp.status_code, 200)

        create_url = reverse('tasks:task_create', kwargs={'slug': self.workspace.slug})
        # Contributor is forbidden from creating task
        denied_response = self.client.post(create_url, {
            'title': 'Build Tailwind Navigation Bar',
            'description': 'Mobile responsive navigation rail',
            'status': TaskStatus.TODO,
            'priority': TaskPriority.HIGH,
            'assignee': self.bob.id,
            'due_date': str(timezone.now().date() + timedelta(days=3))
        })
        self.assertEqual(denied_response.status_code, 403)

        # Alice (Admin) can create a task
        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        admin_response = self.client.post(create_url, {
            'title': 'Build Tailwind Navigation Bar',
            'description': 'Mobile responsive navigation rail',
            'status': TaskStatus.TODO,
            'priority': TaskPriority.HIGH,
            'assignee': self.bob.id,
            'due_date': str(timezone.now().date() + timedelta(days=3))
        })
        self.assertEqual(admin_response.status_code, 302)
        created_task = Task.objects.filter(title='Build Tailwind Navigation Bar').first()
        self.assertIsNotNone(created_task)
        self.assertEqual(created_task.workspace, self.workspace)
        self.assertEqual(created_task.reporter, self.alice)

        # Bob with active TemporaryAccessGrant can create a task
        TemporaryAccessGrant.objects.create(
            user=self.bob,
            workspace=self.workspace,
            action='task.create',
            granted_by=self.alice,
            expires_at=timezone.now() + timezone.timedelta(hours=2),
            reason='Temporary feature task creation'
        )
        self.client.login(email="bob.tasks@aetherspace.dev", password=self.password)
        grant_response = self.client.post(create_url, {
            'title': 'Contributor Task With Grant',
            'description': 'Created via approved temporary grant',
            'status': TaskStatus.TODO,
            'priority': TaskPriority.MEDIUM,
            'assignee': self.bob.id,
            'due_date': str(timezone.now().date() + timedelta(days=1))
        })
        self.assertEqual(grant_response.status_code, 302)
        granted_task = Task.objects.filter(title='Contributor Task With Grant').first()
        self.assertIsNotNone(granted_task)
        self.assertEqual(granted_task.reporter, self.bob)

    def test_task_search_and_filters(self):
        """Test search by 6-digit code, title, status, and priority."""
        t1 = create_task(
            workspace=self.workspace,
            reporter=self.alice,
            title="Setup PostgreSQL Supabase SSL",
            status=TaskStatus.TODO,
            priority=TaskPriority.URGENT,
            assignee=self.alice
        )
        t2 = create_task(
            workspace=self.workspace,
            reporter=self.alice,
            title="Configure Alpine.js Dropdowns",
            status=TaskStatus.DONE,
            priority=TaskPriority.LOW,
            assignee=self.bob
        )

        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        list_url = reverse('tasks:task_list', kwargs={'slug': self.workspace.slug})

        # Search by code
        response = self.client.get(f"{list_url}?q={t1.task_code}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, t1.title)
        self.assertNotContains(response, t2.title)

        # Filter by status DONE
        response = self.client.get(f"{list_url}?status=DONE")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, t2.title)
        self.assertNotContains(response, t1.title)

        # Filter by priority URGENT
        response = self.client.get(f"{list_url}?priority=URGENT")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, t1.title)
        self.assertNotContains(response, t2.title)

    def test_kanban_board_renders_workflow_columns(self):
        """Kanban board groups tasks into 5 columns."""
        task_todo = create_task(self.workspace, self.alice, "Task for To Do", status=TaskStatus.TODO)
        task_done = create_task(self.workspace, self.alice, "Task for Done", status=TaskStatus.DONE)

        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        board_url = reverse('tasks:task_board', kwargs={'slug': self.workspace.slug})
        response = self.client.get(board_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "To Do")
        self.assertContains(response, "In Progress")
        self.assertContains(response, "Code Review")
        self.assertContains(response, "Testing")
        self.assertContains(response, "Done")
        self.assertContains(response, task_todo.task_code)
        self.assertContains(response, task_done.task_code)

    def test_quick_status_update_endpoint(self):
        """POST to task_status_update successfully transitions task status."""
        task = create_task(self.workspace, self.alice, "Quick Move Task", status=TaskStatus.TODO)
        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)

        update_url = reverse('tasks:task_status_update', kwargs={
            'slug': self.workspace.slug,
            'task_code': task.task_code
        })

        response = self.client.post(update_url, {'status': TaskStatus.IN_PROGRESS})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.IN_PROGRESS)

    def test_my_tasks_view_returns_only_user_assigned_tasks(self):
        """My Tasks should only show tasks assigned to the authenticated user."""
        t_alice = create_task(self.workspace, self.alice, "Alice Task", assignee=self.alice)
        t_bob = create_task(self.workspace, self.alice, "Bob Task", assignee=self.bob)

        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        my_tasks_url = reverse('tasks:my_tasks')
        response = self.client.get(my_tasks_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Task")
        self.assertNotContains(response, "Bob Task")

    def test_assignee_validation_cannot_assign_non_workspace_member(self):
        """Form validation prevents assigning a user from outside the workspace."""
        form = TaskForm(
            data={
                'title': 'Invalid Assignee Task',
                'status': TaskStatus.TODO,
                'priority': TaskPriority.MEDIUM,
                'assignee': self.charlie.id  # Charlie is in other_workspace
            },
            workspace=self.workspace
        )
        self.assertFalse(form.is_valid())
        self.assertIn('assignee', form.errors)

    def test_task_delete_view_rbac_admin_and_manager_allowed(self):
        """
        Workspace Admins and Managers can delete tasks.
        """
        # Create a manager user in this workspace
        manager_user = User.objects.create_user(
            email="manager.tasks@aetherspace.dev",
            password=self.password,
            full_name="Workspace Manager"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=manager_user,
            role=WorkspaceRole.MANAGER,
            status=MembershipStatus.ACTIVE
        )

        task1 = create_task(self.workspace, self.alice, "Task to be deleted by Admin")
        task2 = create_task(self.workspace, self.alice, "Task to be deleted by Manager")

        # 1. Admin deletes task1
        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        del_url1 = reverse('tasks:task_delete', kwargs={'slug': self.workspace.slug, 'task_code': task1.task_code})
        resp1 = self.client.post(del_url1)
        self.assertEqual(resp1.status_code, 302)
        self.assertFalse(Task.objects.filter(id=task1.id).exists())

        # 2. Manager deletes task2
        self.client.login(email="manager.tasks@aetherspace.dev", password=self.password)
        del_url2 = reverse('tasks:task_delete', kwargs={'slug': self.workspace.slug, 'task_code': task2.task_code})
        resp2 = self.client.post(del_url2)
        self.assertEqual(resp2.status_code, 302)
        self.assertFalse(Task.objects.filter(id=task2.id).exists())

    def test_task_delete_view_rbac_contributor_forbidden(self):
        """
        Contributors MUST be blocked from deleting tasks with 403 Forbidden.
        """
        task = create_task(self.workspace, self.alice, "Protected Task From Contributor")
        self.client.login(email="bob.tasks@aetherspace.dev", password=self.password)

        del_url = reverse('tasks:task_delete', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        # GET confirm page
        resp_get = self.client.get(del_url)
        self.assertEqual(resp_get.status_code, 403)

        # POST delete attempt
        resp_post = self.client.post(del_url)
        self.assertEqual(resp_post.status_code, 403)

        # Ensure task is NOT deleted
        self.assertTrue(Task.objects.filter(id=task.id).exists())

    def test_create_task_with_sprint_tags_and_display_code(self):
        """
        Verify task sprint, tags, and T-XXXXXX display code.
        """
        task = create_task(
            self.workspace,
            self.alice,
            "Sprint Feature Task",
            sprint="Sprint 04",
            tags="Frontend, Auth"
        )
        self.assertEqual(task.sprint, "Sprint 04")
        self.assertEqual(task.tags, "Frontend, Auth")
        self.assertEqual(task.display_code, f"T-{task.task_code}")

    def test_subtask_creation_and_sync(self):
        """Test creating and synchronizing subtasks on a task."""
        from .models import Subtask
        from .services import sync_subtasks

        task = create_task(self.workspace, self.alice, "Task with Subtasks")
        subtasks_data = [
            {'id': 'temp_1', 'title': 'Design Database Schema', 'is_completed': True},
            {'id': 'temp_2', 'title': 'Build API Views', 'is_completed': False},
            {'id': 'temp_3', 'title': 'Write Unit Tests', 'is_completed': False},
        ]
        created = sync_subtasks(task, subtasks_data, actor=self.alice)
        self.assertEqual(len(created), 3)
        self.assertEqual(task.subtask_count, 3)
        self.assertEqual(task.completed_subtask_count, 1)
        self.assertEqual(task.subtask_progress_percentage, 33)

        # Re-sync: update title of first, remove third, add fourth
        updated_data = [
            {'id': str(created[0].id), 'title': 'Design Database Schema (Done)', 'is_completed': True},
            {'id': str(created[1].id), 'title': 'Build API Views', 'is_completed': True},
            {'id': 'temp_4', 'title': 'Deploy to Staging', 'is_completed': False},
        ]
        synced = sync_subtasks(task, updated_data, actor=self.alice)
        self.assertEqual(len(synced), 3)
        self.assertEqual(task.subtask_count, 3)
        self.assertEqual(task.completed_subtask_count, 2)
        self.assertEqual(task.subtask_progress_percentage, 67)
        self.assertFalse(Subtask.objects.filter(title='Write Unit Tests').exists())

    def test_subtask_toggle_service_and_endpoint(self):
        """Test toggling a subtask via service and via AJAX endpoint."""
        import json
        from .services import create_subtask

        task = create_task(self.workspace, self.alice, "Toggle Subtask Task")
        st = create_subtask(task, "Check responsive layout", is_completed=False, actor=self.alice)
        self.assertFalse(st.is_completed)

        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        toggle_url = reverse('tasks:subtask_toggle', kwargs={
            'slug': self.workspace.slug,
            'task_code': task.task_code,
            'subtask_id': st.id
        })
        resp = self.client.post(toggle_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_completed'])
        self.assertEqual(data['completed_count'], 1)

        st.refresh_from_db()
        self.assertTrue(st.is_completed)

    def test_task_create_view_with_subtasks_payload(self):
        """Test that task_create_view persists subtasks submitted as subtasks_json."""
        import json
        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)

        create_url = reverse('tasks:task_create', kwargs={'slug': self.workspace.slug})
        subtasks_json = json.dumps([
            {'title': 'Write specification doc', 'is_completed': True},
            {'title': 'Review code with peer', 'is_completed': False},
        ])
        post_data = {
            'title': 'Feature: WebRTC Screen Sharing',
            'description': 'Peer to peer video and audio sharing',
            'status': TaskStatus.TODO,
            'priority': TaskPriority.HIGH,
            'subtasks_json': subtasks_json
        }

        resp = self.client.post(create_url, data=post_data)
        self.assertEqual(resp.status_code, 302)

        task = Task.objects.filter(workspace=self.workspace, title='Feature: WebRTC Screen Sharing').first()
        self.assertIsNotNone(task)
        self.assertEqual(task.subtask_count, 2)
        self.assertEqual(task.completed_subtask_count, 1)

    def test_subtask_create_and_delete_ajax_endpoints(self):
        """Test AJAX creation and deletion of subtasks on the task detail page."""
        import json
        self.client.login(email="alice.tasks@aetherspace.dev", password=self.password)
        task = create_task(self.workspace, self.alice, "Detail Subtasks Task")

        create_url = reverse('tasks:subtask_create', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        resp = self.client.post(
            create_url,
            data=json.dumps({'title': 'Inline added subtask'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        st_id = data['subtask']['id']
        self.assertEqual(task.subtask_count, 1)

        # Now delete it
        del_url = reverse('tasks:subtask_delete', kwargs={
            'slug': self.workspace.slug,
            'task_code': task.task_code,
            'subtask_id': st_id
        })
        resp_del = self.client.post(del_url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_del.status_code, 200)
        del_data = resp_del.json()
        self.assertTrue(del_data['success'])
        self.assertEqual(del_data['total_count'], 0)
        self.assertEqual(task.subtask_count, 0)


class SprintPlanningUnitTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "StrongPassword123!"

        self.admin = User.objects.create_user(
            email="admin.sprint@aetherspace.dev",
            password=self.password,
            full_name="Admin Sprint"
        )
        self.contributor = User.objects.create_user(
            email="contrib.sprint@aetherspace.dev",
            password=self.password,
            full_name="Contrib Sprint"
        )
        self.workspace = Workspace.objects.create(
            name="Agile Workspace",
            slug="agile-workspace",
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

        self.sprint1 = Sprint.objects.create(
            workspace=self.workspace,
            name="Sprint 1 - Launch Prep",
            goal="Ship MVP",
            status=SprintStatus.PLANNING,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=14)
        )
        self.task1 = create_task(
            workspace=self.workspace,
            reporter=self.admin,
            title="Setup DB Schema",
            sprint="Sprint 1 - Launch Prep",
            sprint_ref=self.sprint1
        )
        self.task_backlog = create_task(
            workspace=self.workspace,
            reporter=self.admin,
            title="Backlog Item",
            sprint="Backlog",
            sprint_ref=None
        )

    def test_sprint_planning_page_loads(self):
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        url = reverse('tasks:sprint_planning', kwargs={'slug': self.workspace.slug})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sprint Planning & Agile Iterations")
        self.assertContains(resp, "Sprint 1 - Launch Prep")

    def test_create_sprint_as_admin(self):
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        url = reverse('tasks:sprint_create', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(url, {
            'name': 'Sprint 2 - User Onboarding',
            'goal': 'Design nice forms',
            'start_date': str(timezone.now().date()),
            'end_date': str(timezone.now().date() + timedelta(days=14))
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Sprint.objects.filter(name='Sprint 2 - User Onboarding', workspace=self.workspace).exists())

    def test_start_and_complete_sprint(self):
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        action_url = reverse('tasks:sprint_action', kwargs={'slug': self.workspace.slug, 'sprint_id': self.sprint1.id})

        # 1. Start sprint
        resp_start = self.client.post(action_url, {'action': 'start'})
        self.assertEqual(resp_start.status_code, 302)
        self.sprint1.refresh_from_db()
        self.assertEqual(self.sprint1.status, SprintStatus.ACTIVE)

        # 2. Complete sprint (task1 is incomplete, should move to backlog)
        resp_complete = self.client.post(action_url, {'action': 'complete'})
        self.assertEqual(resp_complete.status_code, 302)
        self.sprint1.refresh_from_db()
        self.assertEqual(self.sprint1.status, SprintStatus.COMPLETED)
        self.task1.refresh_from_db()
        self.assertIsNone(self.task1.sprint_ref)
        self.assertEqual(self.task1.sprint, 'Backlog')

    def test_move_task_between_sprint_and_backlog(self):
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        move_url = reverse('tasks:sprint_move_task', kwargs={'slug': self.workspace.slug})

        # Move backlog task into sprint1
        resp = self.client.post(move_url, {
            'task_id': str(self.task_backlog.id),
            'target_sprint_id': str(self.sprint1.id)
        })
        self.assertEqual(resp.status_code, 302)
        self.task_backlog.refresh_from_db()
        self.assertEqual(self.task_backlog.sprint_ref, self.sprint1)
        self.assertEqual(self.task_backlog.sprint, self.sprint1.name)

        # Move back to backlog
        resp2 = self.client.post(move_url, {
            'task_id': str(self.task_backlog.id),
            'target_sprint_id': 'backlog'
        })
        self.assertEqual(resp2.status_code, 302)
        self.task_backlog.refresh_from_db()
        self.assertIsNone(self.task_backlog.sprint_ref)
        self.assertEqual(self.task_backlog.sprint, 'Backlog')

    def test_quick_create_task_into_sprint(self):
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        create_url = reverse('tasks:sprint_quick_create_task', kwargs={'slug': self.workspace.slug})

        resp = self.client.post(create_url, {
            'title': 'New Rapid Task',
            'sprint_id': str(self.sprint1.id),
            'priority': 'HIGH',
            'estimated_hours': '3.5'
        })
        self.assertEqual(resp.status_code, 302)
        created = Task.objects.filter(workspace=self.workspace, title='New Rapid Task').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.sprint_ref, self.sprint1)
        self.assertEqual(created.priority, 'HIGH')
        self.assertEqual(created.estimated_hours, 3.5)
        self.assertTrue(len(created.task_code) == 6)

    def test_edit_sprint_as_admin(self):
        """Verify Admin can edit sprint details including name, goal, dates, and status."""
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        edit_url = reverse('tasks:sprint_edit', kwargs={'slug': self.workspace.slug, 'sprint_id': self.sprint1.id})

        start = timezone.now().date()
        end = start + timedelta(days=21)
        resp = self.client.post(edit_url, {
            'name': 'Sprint 1 - Renamed & Activated',
            'goal': 'Updated goal deliverables',
            'status': SprintStatus.ACTIVE,
            'start_date': str(start),
            'end_date': str(end)
        })
        self.assertEqual(resp.status_code, 302)
        self.sprint1.refresh_from_db()
        self.assertEqual(self.sprint1.name, 'Sprint 1 - Renamed & Activated')
        self.assertEqual(self.sprint1.goal, 'Updated goal deliverables')
        self.assertEqual(self.sprint1.status, SprintStatus.ACTIVE)
        self.assertEqual(self.sprint1.start_date, start)
        self.assertEqual(self.sprint1.end_date, end)

    def test_edit_sprint_rbac_blocks_contributor(self):
        """Verify Contributor cannot edit sprint details (RBAC enforcement)."""
        self.client.login(email="contrib.sprint@aetherspace.dev", password=self.password)
        edit_url = reverse('tasks:sprint_edit', kwargs={'slug': self.workspace.slug, 'sprint_id': self.sprint1.id})

        resp = self.client.post(edit_url, {
            'name': 'Hacked Sprint Name',
            'goal': 'Should not change'
        })
        self.assertEqual(resp.status_code, 302)
        self.sprint1.refresh_from_db()
        self.assertNotEqual(self.sprint1.name, 'Hacked Sprint Name')

        # Test AJAX version returns 403 JSON
        resp_ajax = self.client.post(edit_url, {'name': 'Hacked Sprint'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_ajax.status_code, 403)

    def test_cancel_sprint_moves_incomplete_tasks_to_backlog(self):
        """Verify cancelling a sprint moves incomplete tasks to Product Backlog."""
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        action_url = reverse('tasks:sprint_action', kwargs={'slug': self.workspace.slug, 'sprint_id': self.sprint1.id})

        resp = self.client.post(action_url, {'action': 'cancel'})
        self.assertEqual(resp.status_code, 302)
        self.sprint1.refresh_from_db()
        self.assertEqual(self.sprint1.status, SprintStatus.CANCELLED)

        self.task1.refresh_from_db()
        self.assertIsNone(self.task1.sprint_ref)
        self.assertEqual(self.task1.sprint, 'Backlog')

    def test_delete_sprint_moves_tasks_to_backlog(self):
        """Verify deleting a sprint returns its tasks to Backlog and removes sprint record."""
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        sprint_id = self.sprint1.id
        action_url = reverse('tasks:sprint_action', kwargs={'slug': self.workspace.slug, 'sprint_id': sprint_id})

        resp = self.client.post(action_url, {'action': 'delete'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Sprint.objects.filter(id=sprint_id).exists())

        self.task1.refresh_from_db()
        self.assertIsNone(self.task1.sprint_ref)
        self.assertEqual(self.task1.sprint, 'Backlog')

    def test_sprint_metrics_and_velocity_calculation(self):
        """Verify database-backed metrics: counts, velocity, task breakdowns, progress percentage."""
        # Setup completed sprint with a DONE task
        sprint_completed = Sprint.objects.create(
            workspace=self.workspace,
            name="Sprint 0 - Past",
            status=SprintStatus.COMPLETED
        )
        create_task(
            workspace=self.workspace,
            reporter=self.admin,
            title="Completed Task in Completed Sprint",
            status=TaskStatus.DONE,
            sprint_ref=sprint_completed,
            estimated_hours=5.0
        )

        # Activate sprint1 with 1 DONE and 1 TODO task
        self.sprint1.status = SprintStatus.ACTIVE
        self.sprint1.save()
        self.task1.status = TaskStatus.DONE
        self.task1.estimated_hours = 4.0
        self.task1.save()

        task_in_prog = create_task(
            workspace=self.workspace,
            reporter=self.admin,
            title="In Progress Active Sprint Task",
            status=TaskStatus.IN_PROGRESS,
            sprint_ref=self.sprint1,
            estimated_hours=6.0
        )

        # Check model methods
        breakdown = self.sprint1.task_status_breakdown
        self.assertEqual(breakdown['done'], 1)
        self.assertEqual(breakdown['in_progress'], 1)
        self.assertEqual(breakdown['total'], 2)
        self.assertEqual(self.sprint1.progress_percentage, 50)
        self.assertEqual(self.sprint1.total_estimated_hours, 10.0)

        # Check view context metrics
        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        resp = self.client.get(reverse('tasks:sprint_planning', kwargs={'slug': self.workspace.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['velocity_count'], 1)
        self.assertEqual(resp.context['sprint_counts']['active'], 1)
        self.assertEqual(resp.context['sprint_counts']['completed'], 1)
        self.assertEqual(resp.context['sprint_counts']['total'], 2)

    def test_workspace_isolation_blocks_outsider(self):
        """Verify users cannot view or manipulate sprints of workspaces they don't belong to."""
        outsider = User.objects.create_user(
            email="outsider.sprint@aetherspace.dev",
            password=self.password,
            full_name="Outsider User"
        )
        self.client.login(email="outsider.sprint@aetherspace.dev", password=self.password)

        # Planning view 403
        resp = self.client.get(reverse('tasks:sprint_planning', kwargs={'slug': self.workspace.slug}))
        self.assertEqual(resp.status_code, 403)

        # Edit sprint 403
        edit_url = reverse('tasks:sprint_edit', kwargs={'slug': self.workspace.slug, 'sprint_id': self.sprint1.id})
        resp_edit = self.client.post(edit_url, {'name': 'Hacker Sprint'})
        self.assertEqual(resp_edit.status_code, 403)

    def test_workspace_dashboard_displays_real_active_sprint(self):
        """Verify Workspace Dashboard dynamically reflects active sprint name and progress."""
        self.sprint1.status = SprintStatus.ACTIVE
        self.sprint1.save()
        self.task1.status = TaskStatus.DONE
        self.task1.save()

        self.client.login(email="admin.sprint@aetherspace.dev", password=self.password)
        resp = self.client.get(reverse('workspaces:workspace_dashboard', kwargs={'slug': self.workspace.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_sprint'], self.sprint1)
        self.assertContains(resp, self.sprint1.name)
        self.assertNotContains(resp, "Sprint 4")


class TaskHubEnhancementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.password = "StrongPassword123!"

        self.alice = User.objects.create_user(
            email="alice.hub@aetherspace.dev",
            password=self.password,
            full_name="Alice Lead"
        )
        self.workspace = Workspace.objects.create(
            name="Hub Workspace",
            slug="hub-workspace",
            owner=self.alice
        )
        self.alice_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.alice,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        self.bob = User.objects.create_user(
            email="bob.hub@aetherspace.dev",
            password=self.password,
            full_name="Bob Engineer"
        )
        self.bob_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.bob,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        self.charlie = User.objects.create_user(
            email="charlie.outsider@aetherspace.dev",
            password=self.password,
            full_name="Charlie Outsider"
        )
        self.other_workspace = Workspace.objects.create(
            name="External Workspace",
            slug="external-workspace",
            owner=self.charlie
        )
        self.charlie_membership = WorkspaceMembership.objects.create(
            workspace=self.other_workspace,
            user=self.charlie,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        self.task = create_task(
            workspace=self.workspace,
            reporter=self.alice,
            title="Integrate Markdown & Code Reviews",
            description="### Technical Scope\nEnsure full **Markdown** rendering and *peer reviews*.",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            assignee=self.bob,
            due_date=timezone.now().date() + timedelta(days=7),
            tags="Backend, Frontend"
        )

    def test_task_summary_generation(self):
        """Verify task summary data dictionary reads directly from models."""
        summary = self.task.get_summary_data()
        self.assertEqual(summary['task_code'], self.task.task_code)
        self.assertEqual(summary['display_code'], f"T-{self.task.task_code}")
        self.assertEqual(summary['title'], self.task.title)
        self.assertEqual(summary['description'], self.task.description)
        self.assertEqual(summary['status'], TaskStatus.IN_PROGRESS)
        self.assertEqual(summary['priority'], TaskPriority.HIGH)
        self.assertEqual(summary['requester'], self.alice)
        self.assertEqual(summary['assignee'], self.bob)
        self.assertEqual(summary['due_date'], self.task.due_date)
        self.assertIn("Backend", summary['labels'])
        self.assertIn("Frontend", summary['labels'])
        self.assertFalse(summary['has_bugs'])
        self.assertEqual(len(summary['connected_bugs']), 0)

    def test_attached_bug_display_and_no_bug_state(self):
        """Verify attached bugs are displayed and bug section is omitted when no bugs exist."""
        # 1. No bug state
        self.client.login(email="alice.hub@aetherspace.dev", password=self.password)
        detail_url = reverse('tasks:task_detail', kwargs={'slug': self.workspace.slug, 'task_code': self.task.task_code})
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        # In the summary card, the bug section should not appear
        self.assertNotContains(resp, "Connected Defects & Bugs (")

        # 2. Attach a bug
        bug = Bug.objects.create(
            bug_code="B-998877",
            workspace=self.workspace,
            title="Syntax error in markdown parser",
            reporter=self.alice,
            assignee=self.bob,
            linked_task=self.task,
            severity="SEV2",
            status="OPEN"
        )
        summary = self.task.get_summary_data()
        self.assertTrue(summary['has_bugs'])
        self.assertEqual(len(summary['connected_bugs']), 1)
        self.assertEqual(summary['connected_bugs'][0]['bug_code'], "B-998877")

        # 3. GET task detail with attached bug
        resp2 = self.client.get(detail_url)
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, "Linked Defects & Bugs")
        self.assertContains(resp2, "B-998877")
        self.assertContains(resp2, "Syntax error in markdown parser")

    def test_markdown_rendering_and_sanitization(self):
        """Test headings, bold, italic, lists, links, code, quotes, tables, and XSS sanitization."""
        markdown_text = (
            "# Main Heading\n\n"
            "## Sub Heading\n\n"
            "**Bold Text** and *Italic Text*\n\n"
            "- Item 1\n"
            "- Item 2\n\n"
            "[Safe Link](https://aetherspace.dev)\n\n"
            "`inline_code()`\n\n"
            "```python\ndef hello():\n    return 'world'\n```\n\n"
            "> Quote block\n\n"
            "| Column 1 | Column 2 |\n"
            "| --- | --- |\n"
            "| Val 1 | Val 2 |\n"
        )
        rendered = render_rich_text(markdown_text)
        self.assertIn("<h1>Main Heading</h1>", rendered)
        self.assertIn("<h2>Sub Heading</h2>", rendered)
        self.assertIn("<strong>Bold Text</strong>", rendered)
        self.assertIn("<em>Italic Text</em>", rendered)
        self.assertIn("<li>Item 1</li>", rendered)
        self.assertIn("<li>Item 2</li>", rendered)
        self.assertIn('href="https://aetherspace.dev"', rendered)
        self.assertIn("<code>inline_code()</code>", rendered)
        self.assertIn("<pre><code", rendered)
        self.assertIn("<blockquote>", rendered)
        self.assertIn("<table>", rendered)
        self.assertIn("<th>Column 1</th>", rendered)
        self.assertIn("<td>Val 1</td>", rendered)

        # XSS sanitization test
        malicious = (
            "<script>alert('XSS')</script>"
            "<img src=x onerror=alert(1)>"
            "<a href=\"javascript:alert('pwned')\">Click me</a>"
        )
        cleaned = render_rich_text(malicious)
        self.assertNotIn("<script", cleaned.lower())
        self.assertNotIn("</script>", cleaned.lower())
        self.assertNotIn("<img", cleaned.lower())
        self.assertNotIn("onerror", cleaned.lower())
        self.assertNotIn("javascript:", cleaned.lower())

    def test_task_edit_persistence(self):
        """Verify successful edit saves all fields atomically and updates DB."""
        self.client.login(email="alice.hub@aetherspace.dev", password=self.password)
        edit_url = reverse('tasks:task_edit', kwargs={'slug': self.workspace.slug, 'task_code': self.task.task_code})
        new_due = str(timezone.now().date() + timedelta(days=10))

        resp = self.client.post(edit_url, {
            'title': 'Completely Updated Task Title',
            'description': 'Updated technical specifications and acceptance criteria.',
            'status': TaskStatus.TESTING,
            'priority': TaskPriority.URGENT,
            'assignee': str(self.bob.id),
            'sprint': 'Sprint 02',
            'due_date': new_due,
            'tags': 'Release, Critical',
            'estimated_hours': '8.5'
        })
        if resp.status_code != 302:
            form_errors = resp.context['form'].errors if 'form' in resp.context else None
            msg_list = [m.message for m in resp.context.get('messages', [])]
            self.fail(f"Expected 302 redirect but got {resp.status_code}. Form errors: {form_errors}. Messages: {msg_list}")

        self.assertEqual(resp.status_code, 302)

        # Verify values persisted in database
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, 'Completely Updated Task Title')
        self.assertEqual(self.task.description, 'Updated technical specifications and acceptance criteria.')
        self.assertEqual(self.task.status, TaskStatus.TESTING)
        self.assertEqual(self.task.priority, TaskPriority.URGENT)
        self.assertEqual(str(self.task.due_date), new_due)
        self.assertEqual(float(self.task.estimated_hours), 8.5)

    def test_failed_edit_does_not_show_success_and_preserves_input(self):
        """Verify failed validation does not show success message, shows error, and preserves user input."""
        self.client.login(email="alice.hub@aetherspace.dev", password=self.password)
        edit_url = reverse('tasks:task_edit', kwargs={'slug': self.workspace.slug, 'task_code': self.task.task_code})

        # Submit invalid empty title
        resp = self.client.post(edit_url, {
            'title': '',  # invalid
            'description': 'My preserved description input',
            'status': TaskStatus.DONE,
            'priority': TaskPriority.LOW
        })
        self.assertEqual(resp.status_code, 200)

        # Task in DB should not be changed
        self.task.refresh_from_db()
        self.assertNotEqual(self.task.status, TaskStatus.DONE)
        self.assertNotEqual(self.task.title, '')

        # Messages check: success should NOT be shown, error should be shown
        messages = list(resp.context['messages'])
        success_messages = [m for m in messages if m.level_tag == 'success']
        error_messages = [m for m in messages if m.level_tag == 'error']
        self.assertEqual(len(success_messages), 0)
        self.assertGreaterEqual(len(error_messages), 1)

        # Form contains user input preserved
        self.assertEqual(resp.context['form']['description'].value(), 'My preserved description input')

    def test_code_review_creation_and_task_relationship(self):
        """Verify code review request creation, code format, and real relationship to Task."""
        cr = create_code_review_request(
            task=self.task,
            requester=self.alice,
            title="PR #42: Feature Architecture",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/42",
            description="Please review module boundaries."
        )
        self.assertIsNotNone(cr.id)
        self.assertTrue(cr.review_code.startswith("CR-"))
        self.assertEqual(cr.task, self.task)
        self.assertEqual(cr.requester, self.alice)
        self.assertEqual(cr.status, CodeReviewStatus.REQUESTED)

        # Verify real Django relationship
        self.assertEqual(self.task.code_reviews.count(), 1)
        self.assertEqual(self.task.code_reviews.first(), cr)

        # Verify TaskActivity created
        activity = self.task.activities.filter(new_value=cr.review_code).first()
        self.assertIsNotNone(activity)
        self.assertIn("Created Code Review Request", activity.message)

    def test_code_review_workspace_isolation(self):
        """Verify unauthorized users outside workspace cannot create code review requests."""
        with self.assertRaises(PermissionDenied):
            create_code_review_request(
                task=self.task,
                requester=self.charlie,  # belongs to other_workspace
                title="Malicious PR",
                github_pr_url="https://github.com/aetherspace/aetherspace/pull/99"
            )

    def test_invalid_github_pr_url(self):
        """Verify invalid GitHub PR URLs are rejected."""
        with self.assertRaises(ValidationError):
            create_code_review_request(
                task=self.task,
                requester=self.alice,
                title="Invalid URL test",
                github_pr_url="https://google.com/search?q=pr"
            )

        with self.assertRaises(ValidationError):
            create_code_review_request(
                task=self.task,
                requester=self.alice,
                title="Not a PR URL",
                github_pr_url="https://github.com/aetherspace/aetherspace/issues/42"
            )

    def test_duplicate_code_review_handling(self):
        """Verify duplicate active code review requests on the same PR URL are prevented."""
        create_code_review_request(
            task=self.task,
            requester=self.alice,
            title="Initial Review",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/55"
        )

        with self.assertRaises(ValidationError):
            create_code_review_request(
                task=self.task,
                requester=self.bob,
                title="Duplicate Review",
                github_pr_url="https://github.com/aetherspace/aetherspace/pull/55"
            )

    def test_code_review_status_transitions_and_permissions(self):
        """Verify valid status transitions and permission checks."""
        cr = create_code_review_request(
            task=self.task,
            requester=self.alice,
            title="Review Workflow",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/77"
        )
        self.assertEqual(cr.status, CodeReviewStatus.REQUESTED)

        # Transition to IN_REVIEW by manager/admin Alice
        update_code_review_status(cr, actor=self.alice, new_status=CodeReviewStatus.IN_REVIEW)
        cr.refresh_from_db()
        self.assertEqual(cr.status, CodeReviewStatus.IN_REVIEW)

        # Transition to CHANGES_REQUESTED
        update_code_review_status(cr, actor=self.alice, new_status=CodeReviewStatus.CHANGES_REQUESTED)
        cr.refresh_from_db()
        self.assertEqual(cr.status, CodeReviewStatus.CHANGES_REQUESTED)

        # Transition to APPROVED
        update_code_review_status(cr, actor=self.alice, new_status=CodeReviewStatus.APPROVED)
        cr.refresh_from_db()
        self.assertEqual(cr.status, CodeReviewStatus.APPROVED)

        # Transition to MERGED
        update_code_review_status(cr, actor=self.alice, new_status=CodeReviewStatus.MERGED)
        cr.refresh_from_db()
        self.assertEqual(cr.status, CodeReviewStatus.MERGED)

        # Charlie (outside workspace) cannot change status
        with self.assertRaises(PermissionDenied):
            update_code_review_status(cr, actor=self.charlie, new_status=CodeReviewStatus.CLOSED)

        # Invalid status rejected
        with self.assertRaises(ValidationError):
            update_code_review_status(cr, actor=self.alice, new_status="NON_EXISTENT_STATUS")

    def test_markdown_preview_endpoint(self):
        """Verify markdown preview POST returns rendered sanitized HTML."""
        self.client.login(email="alice.hub@aetherspace.dev", password=self.password)
        preview_url = reverse('tasks:markdown_preview', kwargs={'slug': self.workspace.slug})
        resp = self.client.post(
            preview_url,
            data=json.dumps({'content': '### Heading 3\n- **Item** with `code`\n<script>alert(1)</script>'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("html", data)
        self.assertIn("<h3>Heading 3</h3>", data["html"])
        self.assertIn("<strong>Item</strong>", data["html"])
        self.assertNotIn("<script>", data["html"])

    def test_code_review_form_auto_populate_and_view_submission(self):
        """Verify code review form auto-populates Task ID and Title, and submission succeeds."""
        self.client.login(email="alice.hub@aetherspace.dev", password=self.password)
        form = CodeReviewRequestForm(task=self.task, requester=self.alice, workspace=self.workspace)
        self.assertEqual(form.fields['task_code_display'].initial, self.task.display_code)
        self.assertEqual(form.fields['task_title_display'].initial, self.task.title)
        self.assertEqual(form.fields['title'].initial, f"Code Review: {self.task.title}")

        create_url = reverse('tasks:code_review_create', kwargs={'slug': self.workspace.slug, 'task_code': self.task.task_code})
        resp = self.client.post(create_url, {
            'title': f"Review for #{self.task.task_code}",
            'github_pr_url': "https://github.com/aetherspace/aetherspace/pull/101",
            'description': "Automated review submission via Task Hub"
        })
        self.assertEqual(resp.status_code, 302)

        cr = CodeReviewRequest.objects.filter(github_pr_url="https://github.com/aetherspace/aetherspace/pull/101").first()
        self.assertIsNotNone(cr)
        self.assertEqual(cr.task, self.task)
        self.assertEqual(cr.requester, self.alice)
        self.assertEqual(cr.status, CodeReviewStatus.REQUESTED)

    def test_code_review_status_update_view(self):
        """Verify code review status update view updates status and redirects."""
        cr = create_code_review_request(
            task=self.task,
            requester=self.alice,
            title="Initial PR",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/102"
        )
        self.client.login(email="alice.hub@aetherspace.dev", password=self.password)
        update_url = reverse('tasks:code_review_status_update', kwargs={
            'slug': self.workspace.slug,
            'review_id': cr.id
        })
        resp = self.client.post(update_url, {'status': CodeReviewStatus.IN_REVIEW})
        self.assertEqual(resp.status_code, 302)
        cr.refresh_from_db()
        self.assertEqual(cr.status, CodeReviewStatus.IN_REVIEW)


class TaskHubCommentsActivityCodeReviewTests(TestCase):
    """
    Comprehensive tests for Task Hub: Comments, Activity & Code Review Enhancement.
    Covers the 20 acceptance tests required by the specification.
    """
    def setUp(self):
        self.client = Client()
        self.password = "AetherSecret123!"

        # Create Workspace Alpha and users
        self.owner = User.objects.create_user(
            email="yaswanth@aetherspace.dev",
            password=self.password,
            full_name="Yaswanth Owner"
        )
        self.workspace = Workspace.objects.create(
            name="AetherSpace Core",
            slug="aetherspace-core",
            owner=self.owner
        )
        self.owner_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.owner,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

        self.developer = User.objects.create_user(
            email="rahul@aetherspace.dev",
            password=self.password,
            full_name="Rahul Developer"
        )
        self.dev_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.developer,
            role=WorkspaceRole.CONTRIBUTOR,
            status=MembershipStatus.ACTIVE
        )

        # Isolated Workspace Beta and user
        self.outsider = User.objects.create_user(
            email="outsider@external.dev",
            password=self.password,
            full_name="External Hacker"
        )
        self.other_workspace = Workspace.objects.create(
            name="External Team",
            slug="external-team",
            owner=self.outsider
        )
        self.outsider_membership = WorkspaceMembership.objects.create(
            workspace=self.other_workspace,
            user=self.outsider,
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        )

    def test_01_task_creation_creates_one_summary_comment(self):
        """1. Verify task creation creates exactly one initial structured summary comment in COMMENTS."""
        task = create_task(
            workspace=self.workspace,
            reporter=self.owner,
            title="Implement User Authentication",
            description="Build secure login flow",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee=self.developer
        )
        comments = task.comments.all()
        self.assertEqual(comments.count(), 1)
        comment = comments.first()
        self.assertTrue(comment.is_system)
        self.assertEqual(comment.comment_type, TaskComment.CommentType.SYSTEM)
        self.assertEqual(comment.system_event_type, TaskComment.SystemEventType.TASK_CREATED)

    def test_02_summary_comment_contains_real_task_data(self):
        """2. Verify summary comment contains real data from the actual Task model."""
        task = create_task(
            workspace=self.workspace,
            reporter=self.owner,
            title="Implement User Authentication",
            description="Detailed specifications for login authentication.",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            assignee=self.developer
        )
        comment = task.comments.filter(system_event_type=TaskComment.SystemEventType.TASK_CREATED).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.metadata.get('task_code'), task.task_code)
        self.assertEqual(comment.metadata.get('title'), "Implement User Authentication")
        self.assertEqual(comment.metadata.get('priority'), task.get_priority_display())
        self.assertEqual(comment.metadata.get('status'), task.get_status_display())
        self.assertEqual(comment.metadata.get('requester'), self.owner.full_name or self.owner.email)
        self.assertEqual(comment.metadata.get('assignee'), self.developer.full_name or self.developer.email)
        self.assertEqual(comment.metadata.get('description'), "Detailed specifications for login authentication.")

    def test_03_bug_attachment_creates_system_comment(self):
        """3. Verify bug attachment generates a real system comment with bug details."""
        task = create_task(
            workspace=self.workspace,
            reporter=self.owner,
            title="Task with bug attach"
        )
        bug = Bug.objects.create(
            workspace=self.workspace,
            reporter=self.owner,
            title="Login session expires unexpectedly",
            severity=BugSeverity.SEV2,
            status=BugStatus.OPEN
        )

        attach_bug_to_task(task=task, bug=bug, actor=self.owner)

        system_comment = task.comments.filter(system_event_type=TaskComment.SystemEventType.BUG_ATTACHED).first()
        self.assertIsNotNone(system_comment)
        self.assertTrue(system_comment.is_system)
        self.assertEqual(system_comment.bug, bug)
        self.assertEqual(system_comment.metadata.get('bug_code'), bug.bug_code)
        self.assertEqual(system_comment.metadata.get('title'), bug.title)
        self.assertEqual(system_comment.metadata.get('severity'), bug.get_severity_display())
        self.assertEqual(system_comment.metadata.get('status'), bug.get_status_display())

    def test_04_bug_attachment_creates_activity_event(self):
        """4. Verify bug attachment creates a compact chronological Activity event."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Bug Activity Task")
        bug = Bug.objects.create(
            workspace=self.workspace,
            reporter=self.owner,
            title="Memory leak in worker",
            severity=BugSeverity.SEV1,
            status=BugStatus.OPEN
        )

        attach_bug_to_task(task=task, bug=bug, actor=self.developer)

        act = task.activities.filter(action=TaskActivity.Action.BUG_LINKED).first()
        self.assertIsNotNone(act)
        self.assertEqual(act.actor, self.developer)
        self.assertIn(bug.bug_code, act.message)

    def test_05_bug_detachment_creates_comment_and_activity(self):
        """5. Verify bug detachment creates both a system comment and an Activity event."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Detachable Bug Task")
        bug = Bug.objects.create(
            workspace=self.workspace,
            reporter=self.owner,
            title="Spurious warning in console",
            severity=BugSeverity.SEV3,
            status=BugStatus.OPEN
        )
        attach_bug_to_task(task=task, bug=bug, actor=self.owner)

        detach_bug_from_task(task=task, bug=bug, actor=self.developer)
        bug.refresh_from_db()
        self.assertIsNone(bug.linked_task)

        # Check comment
        detach_comment = task.comments.filter(system_event_type=TaskComment.SystemEventType.BUG_DETACHED).first()
        self.assertIsNotNone(detach_comment)
        self.assertEqual(detach_comment.metadata.get('bug_code'), bug.bug_code)

        # Check activity
        detach_act = task.activities.filter(action=TaskActivity.Action.BUG_UNLINKED).first()
        self.assertIsNotNone(detach_act)
        self.assertEqual(detach_act.actor, self.developer)
        self.assertIn(bug.bug_code, detach_act.message)

    def test_06_code_review_not_automatically_created(self):
        """6. Verify Code Review is OPTIONAL and NOT automatically created on task creation."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Simple Task No Review")
        self.assertEqual(task.code_reviews.count(), 0)

    def test_07_user_can_explicitly_raise_code_review_when_permitted(self):
        """7. Verify permitted workspace member can explicitly raise a Code Review."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Auth Flow")
        cr = create_code_review_request(
            task=task,
            requester=self.developer,
            reviewer=self.owner,
            title="PR Review for Auth Flow",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/201",
            description="Please check token expiry."
        )
        self.assertIsNotNone(cr.id)
        self.assertTrue(cr.review_code.startswith("CR-"))
        self.assertEqual(cr.status, CodeReviewStatus.REQUESTED)
        self.assertEqual(cr.reviewer, self.owner)
        self.assertEqual(cr.requester, self.developer)

    def test_08_code_review_connects_to_correct_task(self):
        """8. Verify Code Review connects to the correct Task model."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Task Relationship Check")
        cr = create_code_review_request(
            task=task,
            requester=self.developer,
            title="Relationship Review",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/202"
        )
        self.assertEqual(cr.task, task)
        self.assertIn(cr, task.code_reviews.all())

    def test_09_code_review_creates_task_comment(self):
        """9. Verify Code Review creation automatically posts a structured system comment in Task comments."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="CR Comment Test")
        cr = create_code_review_request(
            task=task,
            requester=self.owner,
            reviewer=self.developer,
            title="CR Structured Comment",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/203"
        )

        cr_comment = task.comments.filter(system_event_type=TaskComment.SystemEventType.CODE_REVIEW_REQUESTED).first()
        self.assertIsNotNone(cr_comment)
        self.assertTrue(cr_comment.is_system)
        self.assertEqual(cr_comment.code_review, cr)
        self.assertEqual(cr_comment.metadata.get('review_code'), cr.review_code)
        self.assertEqual(cr_comment.metadata.get('requester'), self.owner.full_name or self.owner.email)
        self.assertEqual(cr_comment.metadata.get('reviewer'), self.developer.full_name or self.developer.email)

    def test_10_reviewer_can_provide_feedback_through_task_comments(self):
        """10. Verify reviewer can provide feedback through Task comments linked to the code review."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Review Feedback Task")
        cr = create_code_review_request(
            task=task,
            requester=self.owner,
            reviewer=self.developer,
            title="Review for Tokens",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/204"
        )

        self.client.login(email="rahul@aetherspace.dev", password=self.password)
        comment_url = reverse('tasks:task_comment_add', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        resp = self.client.post(comment_url, {
            'content': 'Please update authentication validation.\n- Add token check\n- Expire session',
            'code_review_id': cr.id
        })
        self.assertEqual(resp.status_code, 302)

        user_comment = task.comments.filter(author=self.developer, code_review=cr).first()
        self.assertIsNotNone(user_comment)
        self.assertFalse(user_comment.is_system)
        self.assertEqual(user_comment.code_review, cr)
        self.assertIn("Add token check", user_comment.content)

    def test_11_code_review_status_changes_create_comment_and_activity(self):
        """11. Verify Code Review status changes create both system comment and Activity event."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Status Transition Task")
        cr = create_code_review_request(
            task=task,
            requester=self.owner,
            reviewer=self.developer,
            title="Review Status Test",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/205"
        )

        update_code_review_status(cr, actor=self.developer, new_status=CodeReviewStatus.CHANGES_REQUESTED)

        # Verify system comment
        status_comment = task.comments.filter(system_event_type=TaskComment.SystemEventType.CODE_REVIEW_STATUS_CHANGED).first()
        self.assertIsNotNone(status_comment)
        self.assertEqual(status_comment.metadata.get('old_status'), "Requested")
        self.assertEqual(status_comment.metadata.get('new_status'), "Changes Requested")
        self.assertEqual(status_comment.metadata.get('changed_by'), self.developer.full_name or self.developer.email)

        # Verify activity
        status_act = task.activities.filter(action=TaskActivity.Action.STATUS_CHANGED, new_value="Changes Requested").first()
        self.assertIsNotNone(status_act)
        self.assertEqual(status_act.actor, self.developer)

    def test_12_markdown_rendering_works(self):
        """12. Verify Markdown formatting (headings, lists, code, bold, italic) renders correctly."""
        raw_markdown = """### Architecture Review
- **Bold item**
- *Italic item*
`inline_code()`

```python
def authenticate():
    return True
```
"""
        rendered = render_rich_text(raw_markdown)
        self.assertIn("<h3>Architecture Review</h3>", rendered)
        self.assertIn("<strong>Bold item</strong>", rendered)
        self.assertIn("<em>Italic item</em>", rendered)
        self.assertIn("<code>inline_code()</code>", rendered)
        self.assertIn("<pre>", rendered)

    def test_13_markdown_sanitization_prevents_xss(self):
        """13. Verify Markdown sanitization strips dangerous tags/attributes to prevent XSS."""
        malicious = """Hello <script>alert('pwned')</script> world!
<img src="x" onerror="alert('xss')">
<a href="javascript:alert(1)">Click me</a>
"""
        sanitized = render_rich_text(malicious)
        self.assertNotIn("<script>", sanitized)
        self.assertNotIn("</script>", sanitized)
        self.assertNotIn("onerror", sanitized)
        self.assertNotIn("javascript:", sanitized)

    def test_14_unauthorized_users_cannot_create_code_reviews(self):
        """14. Verify unauthorized users outside workspace cannot create Code Reviews."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Secure CR Task")
        with self.assertRaises(PermissionDenied):
            create_code_review_request(
                task=task,
                requester=self.outsider,
                title="Unauthorized PR",
                github_pr_url="https://github.com/aetherspace/aetherspace/pull/206"
            )

    def test_15_cross_workspace_code_review_access_blocked(self):
        """15. Verify cross-workspace Code Review access via view is blocked."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Cross Workspace Task")
        self.client.login(email="outsider@external.dev", password=self.password)
        create_url = reverse('tasks:code_review_create', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        resp = self.client.post(create_url, {
            'title': 'Hacker PR',
            'github_pr_url': 'https://github.com/aetherspace/aetherspace/pull/207'
        })
        self.assertEqual(resp.status_code, 403)

    def test_16_invalid_github_pr_url_rejected(self):
        """16. Verify invalid GitHub PR URLs are rejected."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="URL Validation Task")
        with self.assertRaises(ValidationError):
            create_code_review_request(
                task=task,
                requester=self.owner,
                title="Non GitHub PR",
                github_pr_url="https://notgithub.com/repo/pull/1"
            )

        with self.assertRaises(ValidationError):
            create_code_review_request(
                task=task,
                requester=self.owner,
                title="Issues URL not PR",
                github_pr_url="https://github.com/owner/repo/issues/10"
            )

    def test_17_failed_task_update_does_not_show_success(self):
        """17. Verify failed Task update (e.g. invalid status) raises error and does not mutate state."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Task Failure Check")
        initial_status = task.status
        with self.assertRaises((ValidationError, ValueError)):
            change_task_status(task, actor=self.owner, new_status="INVALID_STATUS")
        task.refresh_from_db()
        self.assertEqual(task.status, initial_status)

    def test_18_failed_comment_operation_does_not_show_success(self):
        """18. Verify failed Comment operation (e.g. editing system comment or blank content) fails safely."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Comment Safety Task")
        system_comment = task.comments.first()
        self.assertTrue(system_comment.is_system)

        # Attempt to edit system comment via view
        self.client.login(email="yaswanth@aetherspace.dev", password=self.password)
        edit_url = reverse('tasks:task_comment_edit', kwargs={
            'slug': self.workspace.slug,
            'task_code': task.task_code,
            'comment_id': system_comment.id
        })
        resp = self.client.post(edit_url, {'content': 'Hacked content'})
        self.assertEqual(resp.status_code, 403)

        # Blank content submission rejected
        add_url = reverse('tasks:task_comment_add', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        resp = self.client.post(add_url, {'content': '   '})
        # Handled safely without creating an empty comment
        self.assertEqual(task.comments.filter(comment_type=TaskComment.CommentType.USER).count(), 0)

    def test_19_failed_code_review_operation_does_not_show_success(self):
        """19. Verify failed Code Review submission (e.g. invalid form) does not create record."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Failed CR Task")
        self.client.login(email="yaswanth@aetherspace.dev", password=self.password)
        create_url = reverse('tasks:code_review_create', kwargs={'slug': self.workspace.slug, 'task_code': task.task_code})
        resp = self.client.post(create_url, {
            'title': '',  # Title is required
            'github_pr_url': 'invalid-url'
        })
        self.assertEqual(task.code_reviews.count(), 0)

    def test_20_duplicate_code_review_handling_works(self):
        """20. Verify duplicate active Code Review requests on the same PR URL are prevented."""
        task = create_task(workspace=self.workspace, reporter=self.owner, title="Duplicate CR Task")
        create_code_review_request(
            task=task,
            requester=self.owner,
            title="First Review",
            github_pr_url="https://github.com/aetherspace/aetherspace/pull/220"
        )
        with self.assertRaises(ValidationError):
            create_code_review_request(
                task=task,
                requester=self.developer,
                title="Second Review Same PR",
                github_pr_url="https://github.com/aetherspace/aetherspace/pull/220"
            )




