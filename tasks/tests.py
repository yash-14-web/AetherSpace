from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, UserRole
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from .models import Task, TaskActivity, TaskStatus, TaskPriority
from .services import generate_unique_task_code, create_task, update_task, change_task_status
from .forms import TaskForm


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
        """Bob (contributor) can view list and create a task."""
        self.client.login(email="bob.tasks@aetherspace.dev", password=self.password)

        create_url = reverse('tasks:task_create', kwargs={'slug': self.workspace.slug})
        response = self.client.post(create_url, {
            'title': 'Build Tailwind Navigation Bar',
            'description': 'Mobile responsive navigation rail',
            'status': TaskStatus.TODO,
            'priority': TaskPriority.HIGH,
            'assignee': self.bob.id,
            'due_date': str(timezone.now().date() + timedelta(days=3))
        })

        created_task = Task.objects.filter(title='Build Tailwind Navigation Bar').first()
        self.assertIsNotNone(created_task)
        self.assertEqual(created_task.workspace, self.workspace)
        self.assertEqual(created_task.reporter, self.bob)
        self.assertEqual(created_task.assignee, self.bob)
        self.assertEqual(response.status_code, 302)

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
