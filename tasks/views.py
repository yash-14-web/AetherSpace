from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone

from workspaces.permissions import workspace_member_required
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from .models import Task, TaskActivity, TaskStatus, TaskPriority
from .forms import TaskForm, TaskFilterForm
from .services import create_task, update_task, change_task_status


@workspace_member_required
def task_list_view(request, slug):
    """
    Searchable, filterable, paginated task list for a workspace.
    Displays metric chips, search input, status/priority dropdowns, and responsive rows.
    """
    workspace = request.workspace
    membership = request.membership

    # Base queryset for this workspace
    tasks_qs = Task.objects.filter(workspace=workspace).select_related('assignee', 'reporter')

    # Metrics summary for filter chips
    status_counts = {
        'total': tasks_qs.count(),
        'todo': tasks_qs.filter(status=TaskStatus.TODO).count(),
        'in_progress': tasks_qs.filter(status=TaskStatus.IN_PROGRESS).count(),
        'code_review': tasks_qs.filter(status=TaskStatus.CODE_REVIEW).count(),
        'testing': tasks_qs.filter(status=TaskStatus.TESTING).count(),
        'done': tasks_qs.filter(status=TaskStatus.DONE).count(),
    }

    # Process filters
    filter_form = TaskFilterForm(request.GET)
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    priority_filter = request.GET.get('priority', '').strip()
    assignee_filter = request.GET.get('assignee', '').strip()

    if q:
        # Search task_code (allowing query with or without leading '#'), title, and description
        clean_code_q = q.lstrip('#')
        tasks_qs = tasks_qs.filter(
            Q(task_code__icontains=clean_code_q) |
            Q(title__icontains=q) |
            Q(description__icontains=q)
        )

    if status_filter and status_filter in dict(TaskStatus.choices):
        tasks_qs = tasks_qs.filter(status=status_filter)

    if priority_filter and priority_filter in dict(TaskPriority.choices):
        tasks_qs = tasks_qs.filter(priority=priority_filter)

    if assignee_filter:
        if assignee_filter == 'me':
            tasks_qs = tasks_qs.filter(assignee=request.user)
        elif assignee_filter == 'unassigned':
            tasks_qs = tasks_qs.filter(assignee__isnull=True)
        else:
            tasks_qs = tasks_qs.filter(assignee_id=assignee_filter)

    # Pagination: 12 tasks per page
    paginator = Paginator(tasks_qs, 12)
    page_number = request.GET.get('page', 1)
    try:
        tasks_page = paginator.page(page_number)
    except PageNotAnInteger:
        tasks_page = paginator.page(1)
    except EmptyPage:
        tasks_page = paginator.page(paginator.num_pages)

    # Workspace team members for assignee filter
    active_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user')

    context = {
        'workspace': workspace,
        'membership': membership,
        'tasks': tasks_page,
        'status_counts': status_counts,
        'filter_form': filter_form,
        'current_q': q,
        'current_status': status_filter,
        'current_priority': priority_filter,
        'current_assignee': assignee_filter,
        'active_members': active_members,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
    }
    return render(request, 'tasks/task_list.html', context)


@workspace_member_required
def task_board_view(request, slug):
    """
    Kanban Board view grouping tasks into 5 workflow stages:
    To Do -> In Progress -> Code Review -> Testing -> Done.
    """
    workspace = request.workspace
    membership = request.membership

    tasks_qs = Task.objects.filter(workspace=workspace).select_related('assignee', 'reporter')

    # Optional quick search/assignee filter on Kanban board
    q = request.GET.get('q', '').strip()
    if q:
        clean_code_q = q.lstrip('#')
        tasks_qs = tasks_qs.filter(
            Q(task_code__icontains=clean_code_q) |
            Q(title__icontains=q)
        )

    assignee_filter = request.GET.get('assignee', '').strip()
    if assignee_filter == 'me':
        tasks_qs = tasks_qs.filter(assignee=request.user)
    elif assignee_filter and assignee_filter != 'all':
        tasks_qs = tasks_qs.filter(assignee_id=assignee_filter)

    # Group into the 5 columns
    columns = [
        {
            'status': TaskStatus.TODO,
            'title': 'To Do',
            'color': 'slate',
            'tasks': [t for t in tasks_qs if t.status == TaskStatus.TODO]
        },
        {
            'status': TaskStatus.IN_PROGRESS,
            'title': 'In Progress',
            'color': 'blue',
            'tasks': [t for t in tasks_qs if t.status == TaskStatus.IN_PROGRESS]
        },
        {
            'status': TaskStatus.CODE_REVIEW,
            'title': 'Code Review',
            'color': 'amber',
            'tasks': [t for t in tasks_qs if t.status == TaskStatus.CODE_REVIEW]
        },
        {
            'status': TaskStatus.TESTING,
            'title': 'Testing',
            'color': 'purple',
            'tasks': [t for t in tasks_qs if t.status == TaskStatus.TESTING]
        },
        {
            'status': TaskStatus.DONE,
            'title': 'Done',
            'color': 'emerald',
            'tasks': [t for t in tasks_qs if t.status == TaskStatus.DONE]
        },
    ]

    active_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user')

    context = {
        'workspace': workspace,
        'membership': membership,
        'columns': columns,
        'total_tasks': len(tasks_qs),
        'active_members': active_members,
        'current_q': q,
        'current_assignee': assignee_filter,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
    }
    return render(request, 'tasks/kanban_board.html', context)


@workspace_member_required
def task_create_view(request, slug):
    """
    Form view for creating a new task within the workspace.
    Generates a safe 6-digit numeric task code and logs activity.
    """
    workspace = request.workspace
    membership = request.membership

    if request.method == 'POST':
        form = TaskForm(request.POST, workspace=workspace)
        if form.is_valid():
            task = create_task(
                workspace=workspace,
                reporter=request.user,
                title=form.cleaned_data['title'],
                description=form.cleaned_data.get('description', ''),
                status=form.cleaned_data.get('status', TaskStatus.TODO),
                priority=form.cleaned_data.get('priority', TaskPriority.MEDIUM),
                assignee=form.cleaned_data.get('assignee'),
                due_date=form.cleaned_data.get('due_date'),
                estimated_hours=form.cleaned_data.get('estimated_hours'),
                sprint=form.cleaned_data.get('sprint', 'Sprint 01'),
                tags=form.cleaned_data.get('tags', '')
            )
            messages.success(request, f"Task #{task.task_code} '{task.title}' was successfully created.")
            return redirect('tasks:task_detail', slug=workspace.slug, task_code=task.task_code)
    else:
        initial_status = request.GET.get('status', TaskStatus.TODO)
        if initial_status not in dict(TaskStatus.choices):
            initial_status = TaskStatus.TODO
        form = TaskForm(workspace=workspace, initial={'status': initial_status})

    context = {
        'workspace': workspace,
        'membership': membership,
        'form': form,
        'is_create': True,
    }
    return render(request, 'tasks/task_form.html', context)


@workspace_member_required
def task_detail_view(request, slug, task_code):
    """
    Detailed task view featuring metadata sidebar, description, status dropdown,
    and chronological TaskActivity audit timeline.
    """
    workspace = request.workspace
    membership = request.membership

    # Clean leading '#' if provided
    clean_code = task_code.lstrip('#')
    task = get_object_or_404(
        Task.objects.select_related('workspace', 'assignee', 'reporter'),
        workspace=workspace,
        task_code=clean_code
    )

    activities = task.activities.select_related('actor').order_by('-created_at')

    context = {
        'workspace': workspace,
        'membership': membership,
        'task': task,
        'activities': activities,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
    }
    return render(request, 'tasks/task_detail.html', context)


@workspace_member_required
def task_edit_view(request, slug, task_code):
    """
    Edit task view: modifies attributes, records granular activity logs.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = task_code.lstrip('#')
    task = get_object_or_404(
        Task.objects.select_related('workspace', 'assignee', 'reporter'),
        workspace=workspace,
        task_code=clean_code
    )

    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, workspace=workspace)
        if form.is_valid():
            update_task(
                task=task,
                actor=request.user,
                title=form.cleaned_data['title'],
                description=form.cleaned_data.get('description', ''),
                status=form.cleaned_data.get('status'),
                priority=form.cleaned_data.get('priority'),
                assignee=form.cleaned_data.get('assignee'),
                due_date=form.cleaned_data.get('due_date'),
                estimated_hours=form.cleaned_data.get('estimated_hours'),
                sprint=form.cleaned_data.get('sprint', 'Sprint 01'),
                tags=form.cleaned_data.get('tags', '')
            )
            messages.success(request, f"Task #{task.task_code} was successfully updated.")
            return redirect('tasks:task_detail', slug=workspace.slug, task_code=task.task_code)
    else:
        form = TaskForm(instance=task, workspace=workspace)

    context = {
        'workspace': workspace,
        'membership': membership,
        'task': task,
        'form': form,
        'is_create': False,
    }
    return render(request, 'tasks/task_form.html', context)


@workspace_member_required
def task_status_update_view(request, slug, task_code):
    """
    Rapid status transition endpoint used by Kanban cards and detail header.
    Expects POST request with 'status'.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Method not allowed. POST required.")

    workspace = request.workspace
    clean_code = task_code.lstrip('#')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    new_status = request.POST.get('status', '').strip()
    if new_status not in dict(TaskStatus.choices):
        return HttpResponseBadRequest(f"Invalid status '{new_status}'")

    if new_status != task.status:
        change_task_status(task, request.user, new_status)
        messages.success(request, f"Task #{task.task_code} status updated to {task.get_status_display()}.")

    # If explicit AJAX or JSON requested, return JSON
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or request.GET.get('format') == 'json':
        return JsonResponse({
            'success': True,
            'task_code': task.task_code,
            'new_status': task.status,
            'new_status_display': task.get_status_display()
        })

    redirect_to = request.POST.get('next') or reverse('tasks:task_detail', kwargs={'slug': workspace.slug, 'task_code': task.task_code})
    return redirect(redirect_to)


@workspace_member_required
def task_activity_view(request, slug, task_code):
    """
    Dedicated chronological text-based task history view.
    Follows blueprint rule: 'Chronological text-based task history. Rule: Do not introduce radar/graph charts.'
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = task_code.lstrip('#')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)
    activities = task.activities.select_related('actor').order_by('-created_at')

    context = {
        'workspace': workspace,
        'membership': membership,
        'task': task,
        'activities': activities,
    }
    return render(request, 'tasks/task_activity.html', context)


@login_required
def my_tasks_view(request):
    """
    Cross-workspace personal task view:
    Shows all active tasks assigned to the current user across authorized workspaces.
    """
    # Fetch user's active workspaces
    active_memberships = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status='ACTIVE'
    ).select_related('workspace')

    workspace_ids = [m.workspace_id for m in active_memberships]

    tasks_qs = Task.objects.filter(
        workspace_id__in=workspace_ids,
        assignee=request.user
    ).select_related('workspace')

    status_filter = request.GET.get('status', '').strip()
    priority_filter = request.GET.get('priority', '').strip()
    workspace_filter = request.GET.get('workspace', '').strip()

    if status_filter and status_filter in dict(TaskStatus.choices):
        tasks_qs = tasks_qs.filter(status=status_filter)
    if priority_filter and priority_filter in dict(TaskPriority.choices):
        tasks_qs = tasks_qs.filter(priority=priority_filter)
    if workspace_filter:
        tasks_qs = tasks_qs.filter(workspace__slug=workspace_filter)

    # Counts
    all_my_tasks = Task.objects.filter(workspace_id__in=workspace_ids, assignee=request.user)
    counts = {
        'total': all_my_tasks.count(),
        'todo': all_my_tasks.filter(status=TaskStatus.TODO).count(),
        'in_progress': all_my_tasks.filter(status=TaskStatus.IN_PROGRESS).count(),
        'review': all_my_tasks.filter(status=TaskStatus.CODE_REVIEW).count(),
        'testing': all_my_tasks.filter(status=TaskStatus.TESTING).count(),
        'done': all_my_tasks.filter(status=TaskStatus.DONE).count(),
    }

    paginator = Paginator(tasks_qs, 15)
    page_number = request.GET.get('page', 1)
    try:
        tasks_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        tasks_page = paginator.page(1)

    context = {
        'tasks': tasks_page,
        'counts': counts,
        'active_memberships': active_memberships,
        'current_status': status_filter,
        'current_priority': priority_filter,
        'current_workspace': workspace_filter,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
    }
    return render(request, 'tasks/my_tasks.html', context)


@login_required
def tasks_redirect_router(request):
    """
    Global /tasks/ entrypoint router:
    If user belongs to workspaces, direct them to their primary workspace's task list,
    otherwise to /tasks/my/.
    """
    first_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status='ACTIVE'
    ).select_related('workspace').first()

    if first_membership:
        return redirect('tasks:task_list', slug=first_membership.workspace.slug)
    return redirect('tasks:my_tasks')


@workspace_member_required
def task_delete_view(request, slug, task_code):
    """
    Delete task endpoint: restricted strictly to Manager and Admin roles.
    Raises PermissionDenied (403) for Contributors.
    """
    workspace = request.workspace
    membership = request.membership

    # Strict server-side RBAC: only Admin and Manager can delete
    if not membership.can_manage_content:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Only workspace Managers and Administrators can delete tasks.")

    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    if request.method == 'POST':
        task_title = task.title
        code = task.task_code
        task.delete()
        messages.success(request, f"Task T-{code} '{task_title}' was permanently deleted.")
        return redirect('tasks:task_list', slug=workspace.slug)

    context = {
        'workspace': workspace,
        'membership': membership,
        'task': task,
    }
    return render(request, 'tasks/task_confirm_delete.html', context)

