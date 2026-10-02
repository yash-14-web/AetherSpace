from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse, HttpResponseBadRequest
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone

from django.core.exceptions import PermissionDenied

from workspaces.permissions import workspace_member_required, can_user_perform_action
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from accounts.models import User
from .models import (
    Task, TaskActivity, TaskComment, TaskStatus, TaskPriority,
    Subtask, TaskAttachment, Sprint, SprintStatus,
    CodeReviewRequest, CodeReviewStatus
)
from .forms import TaskForm, TaskFilterForm, CodeReviewRequestForm, TaskCommentForm, SprintForm
from .services import (
    create_task, update_task, change_task_status,
    sync_subtasks, create_subtask, toggle_subtask, delete_subtask,
    create_code_review_request, update_code_review_status,
    attach_bug_to_task, detach_bug_from_task
)
from files.models import StoredFile
from files.services import (
    SupabaseStorageService, compute_sha256, detect_file_category, MAX_FILE_SIZE_BYTES
)


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

    created_by_filter = request.GET.get('created_by', '').strip()
    if created_by_filter == 'me':
        tasks_qs = tasks_qs.filter(reporter=request.user)

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
        'current_created_by': created_by_filter,
        'active_members': active_members,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
        'can_create_task': can_user_perform_action(request.user, workspace, 'task.create'),
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
        'can_create_task': can_user_perform_action(request.user, workspace, 'task.create'),
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

    if not can_user_perform_action(request.user, workspace, 'task.create'):
        raise PermissionDenied(
            f"You do not have permission to create tasks in '{workspace.name}'. "
            "Only Managers and Administrators can create tasks. You may request temporary access."
        )

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
            # Sync subtasks if submitted
            raw_subtasks = request.POST.get('subtasks_json', '').strip()
            if raw_subtasks:
                try:
                    import json
                    subtasks_data = json.loads(raw_subtasks)
                    if isinstance(subtasks_data, list):
                        sync_subtasks(task, subtasks_data, actor=request.user)
                except (ValueError, TypeError):
                    pass

            messages.success(request, f"Task #{task.task_code} was successfully created.")
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
        'existing_subtasks_json': '[]',
    }
    return render(request, 'tasks/task_form.html', context)


@workspace_member_required
def task_detail_view(request, slug, task_code):
    """
    Detailed task view featuring metadata sidebar, description, status dropdown,
    subtasks list, and chronological TaskActivity audit timeline.
    """
    workspace = request.workspace
    membership = request.membership

    # Clean leading '#' if provided
    clean_code = task_code.lstrip('#')
    task = get_object_or_404(
        Task.objects.select_related('workspace', 'assignee', 'reporter').prefetch_related(
            'subtasks',
            'attachments__file',
            'attachments__file__uploaded_by'
        ),
        workspace=workspace,
        task_code=clean_code
    )

    activities = task.activities.select_related('actor').order_by('-created_at')
    comments = task.comments.select_related('author', 'code_review', 'bug').order_by('created_at')
    related_bugs = task.bugs.select_related('assignee', 'module').order_by('-created_at')
    subtasks = task.subtasks.all()
    attachments = task.attachments.select_related('file', 'file__uploaded_by').all()
    code_reviews = task.code_reviews.select_related('requester', 'reviewer').order_by('-created_at')
    code_review_form = CodeReviewRequestForm(task=task, requester=request.user, workspace=workspace)
    comment_form = TaskCommentForm(task=task)

    from bugs.models import Bug
    available_bugs = Bug.objects.filter(workspace=workspace).exclude(linked_task=task).order_by('-created_at')

    context = {
        'workspace': workspace,
        'membership': membership,
        'task': task,
        'task_summary': task.get_summary_data(),
        'subtasks': subtasks,
        'attachments': attachments,
        'activities': activities,
        'comments': comments,
        'comment_form': comment_form,
        'related_bugs': related_bugs,
        'available_bugs': available_bugs,
        'code_reviews': code_reviews,
        'code_review_form': code_review_form,
        'CodeReviewStatus': CodeReviewStatus,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
        'initial_tab': request.GET.get('tab', 'overview'),
    }
    return render(request, 'tasks/task_detail.html', context)


@workspace_member_required
def task_edit_view(request, slug, task_code):
    """
    Edit task view: modifies attributes, records granular activity logs,
    and synchronizes subtasks.
    Enforces atomic transaction and verifies actual database persistence before reporting success.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = task_code.lstrip('#')
    task = get_object_or_404(
        Task.objects.select_related('workspace', 'assignee', 'reporter').prefetch_related('subtasks'),
        workspace=workspace,
        task_code=clean_code
    )

    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, workspace=workspace)
        if not form.is_valid():
            messages.error(request, "Failed to update task. Please correct the validation errors below.")
        else:
            try:
                from django.db import transaction
                with transaction.atomic():
                    updated_task = update_task(
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
                    # Sync subtasks if submitted
                    raw_subtasks = request.POST.get('subtasks_json', '').strip()
                    if raw_subtasks is not None and raw_subtasks != '':
                        try:
                            import json
                            subtasks_data = json.loads(raw_subtasks)
                            if isinstance(subtasks_data, list):
                                sync_subtasks(task, subtasks_data, actor=request.user)
                        except (ValueError, TypeError):
                            pass

                    # Refresh from database to verify persistence
                    updated_task.refresh_from_db()

                    # Persistence verification checks
                    if updated_task.title != form.cleaned_data['title']:
                        raise ValueError("Persistence verification failed for title.")
                    if (updated_task.description or '') != (form.cleaned_data.get('description') or ''):
                        raise ValueError("Persistence verification failed for description.")
                    if updated_task.status != form.cleaned_data.get('status'):
                        raise ValueError("Persistence verification failed for status.")
                    if updated_task.priority != form.cleaned_data.get('priority'):
                        raise ValueError("Persistence verification failed for priority.")
                    if updated_task.assignee != form.cleaned_data.get('assignee'):
                        raise ValueError("Persistence verification failed for assignee.")
                    if updated_task.due_date != form.cleaned_data.get('due_date'):
                        raise ValueError("Persistence verification failed for due date.")

                messages.success(request, f"Task #{updated_task.task_code} was successfully updated.")
                return redirect('tasks:task_detail', slug=workspace.slug, task_code=updated_task.task_code)
            except Exception as e:
                messages.error(request, f"Failed to update task: {str(e)}")
    else:
        form = TaskForm(instance=task, workspace=workspace)

    import json
    existing_subtasks = [
        {'id': str(st.id), 'title': st.title, 'is_completed': st.is_completed, 'order': st.order}
        for st in task.subtasks.all()
    ]

    context = {
        'workspace': workspace,
        'membership': membership,
        'task': task,
        'form': form,
        'is_create': False,
        'existing_subtasks_json': json.dumps(existing_subtasks),
    }
    return render(request, 'tasks/task_form.html', context)


@workspace_member_required
def code_review_create_view(request, slug, task_code):
    """
    Creates a new CodeReviewRequest linked to a Task.
    Populates Task ID/Title, verifies workspace ownership and membership,
    validates GitHub PR URL, and generates a TaskActivity record.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = task_code.lstrip('#')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    if request.method == 'POST':
        form = CodeReviewRequestForm(
            request.POST,
            task=task,
            requester=request.user,
            workspace=workspace
        )
        if form.is_valid():
            try:
                cr = create_code_review_request(
                    task=task,
                    requester=request.user,
                    title=form.cleaned_data['title'],
                    github_pr_url=form.cleaned_data['github_pr_url'],
                    description=form.cleaned_data.get('description', ''),
                    reviewer=form.cleaned_data.get('reviewer')
                )
                messages.success(request, f"Code Review Request {cr.review_code} was successfully created.")
                return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': workspace.slug, 'task_code': task.task_code})}?tab=comments")
            except Exception as e:
                messages.error(request, f"Failed to create code review: {str(e)}")
        else:
            first_err = next(iter(form.errors.values()))[0] if form.errors else "Please check form fields."
            messages.error(request, f"Failed to create code review: {first_err}")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': workspace.slug, 'task_code': task.task_code})}?tab=code_reviews")


@workspace_member_required
def code_review_status_update_view(request, slug, review_id):
    """
    Updates status for a CodeReviewRequest with server-side RBAC validation.
    """
    workspace = request.workspace
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    cr = get_object_or_404(
        CodeReviewRequest.objects.select_related('task', 'task__workspace', 'task__assignee'),
        id=review_id,
        task__workspace=workspace
    )

    new_status = request.POST.get('status', '').strip()
    try:
        update_code_review_status(code_review=cr, actor=request.user, new_status=new_status)
        messages.success(request, f"Code Review {cr.review_code} status updated to {cr.get_status_display()}.")
    except Exception as e:
        messages.error(request, f"Cannot update code review status: {str(e)}")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': workspace.slug, 'task_code': cr.task.task_code})}?tab=code_reviews")


@workspace_member_required
def markdown_preview_view(request, slug):
    """
    Renders preview of markdown text with bleach sanitization and table support.
    """
    import json
    from core.templatetags.rich_text import render_rich_text
    if request.method == 'POST':
        content = ''
        if request.content_type == 'application/json':
            try:
                body = json.loads(request.body.decode('utf-8'))
                content = body.get('content', '')
            except Exception:
                content = ''
        else:
            content = request.POST.get('content', '')

        html = render_rich_text(content)
        return JsonResponse({'status': 'ok', 'html': str(html)})
    return HttpResponseBadRequest("POST required")


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


@workspace_member_required
def task_comment_add_view(request, slug, task_code):
    """
    Post a new user comment or reviewer feedback on a task.
    Saves comment, creates a TaskActivity entry, and redirects back to Comments tab.
    """
    if request.method != 'POST':
        return redirect('tasks:task_detail', slug=slug, task_code=task_code)

    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    content = request.POST.get('content', '').strip()
    code_review_id = request.POST.get('code_review') or request.POST.get('code_review_id')
    code_review = None
    if code_review_id:
        code_review = CodeReviewRequest.objects.filter(id=code_review_id, task=task).first()

    if content:
        TaskComment.objects.create(
            task=task,
            author=request.user,
            comment_type=TaskComment.CommentType.USER,
            code_review=code_review,
            content=content
        )
        snippet = content[:60] + ('...' if len(content) > 60 else '')
        if code_review:
            activity_msg = f'Added reviewer feedback on {code_review.review_code}: "{snippet}"'
        else:
            activity_msg = f'Added a comment: "{snippet}"'

        TaskActivity.objects.create(
            task=task,
            actor=request.user,
            action=TaskActivity.Action.COMMENTED,
            message=activity_msg
        )

        # Scan for mentions and notify
        import re
        from accounts.models import User
        from notifications.services import create_notification
        from notifications.models import NotificationCategory, NotificationType
        from notifications.email_service import send_mention_email

        active_members = [
            m.user for m in WorkspaceMembership.objects.filter(
                workspace=workspace,
                status=MembershipStatus.ACTIVE
            ).select_related('user').exclude(user=request.user)
        ]

        mentioned_users = set()

        for match in re.finditer(r'@\[([^\]]+)\]\((\d{5}[A-Za-z])\)', content):
            cid = match.group(2)
            for u in active_members:
                if u.contributor_id == cid:
                    mentioned_users.add(u)

        for match in re.finditer(r'@(\d{5}[A-Za-z])\b', content):
            cid = match.group(1)
            for u in active_members:
                if u.contributor_id == cid:
                    mentioned_users.add(u)

        for u in active_members:
            if u.full_name and f"@{u.full_name}" in content:
                mentioned_users.add(u)
            elif u.username and f"@{u.username}" in content:
                mentioned_users.add(u)
            elif u.contributor_id and f"@{u.contributor_id}" in content:
                mentioned_users.add(u)

        if mentioned_users:
            actor_name = request.user.full_name or request.user.email
            for u in mentioned_users:
                try:
                    create_notification(
                        recipient=u,
                        category=NotificationCategory.TASK,
                        notification_type=NotificationType.TASK_ASSIGNED,
                        title=f"{actor_name} mentioned you in Task #{task.task_code}",
                        body=f"{actor_name} mentioned you in a comment on '{task.title}'",
                        workspace=workspace,
                        actor=request.user,
                        action_url=f"/tasks/w/{workspace.slug}/{task.task_code}/?tab=comments"
                    )
                except Exception:
                    pass

                try:
                    send_mention_email(
                        user=u,
                        actor=request.user,
                        context_type="Task",
                        context_title=f"#{task.task_code} - {task.title}",
                        snippet=snippet,
                        action_url=f"/tasks/w/{workspace.slug}/{task.task_code}/?tab=comments"
                    )
                except Exception:
                    pass

        messages.success(request, "Comment posted successfully.")
    else:
        messages.error(request, "Comment content cannot be empty.")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=comments")


@workspace_member_required
def task_comment_edit_view(request, slug, task_code, comment_id):
    """
    Edit a normal user comment.
    System-generated comments cannot be edited by normal users.
    Only the comment author or workspace Admin/Manager can edit.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)
    comment = get_object_or_404(TaskComment, id=comment_id, task=task)

    if comment.is_system:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("System-generated comments cannot be edited.")

    if request.user != comment.author and not membership.can_manage_content:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to edit this comment.")

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if not content:
            messages.error(request, "Comment content cannot be empty.")
        else:
            comment.content = content
            comment.save(update_fields=['content', 'updated_at'])
            messages.success(request, "Comment updated successfully.")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=comments")


@workspace_member_required
def task_comment_delete_view(request, slug, task_code, comment_id):
    """
    Delete a comment.
    System-generated comments cannot be deleted by normal users.
    Allowed only for the comment author or workspace Admin/Manager.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)
    comment = get_object_or_404(TaskComment, id=comment_id, task=task)

    if comment.is_system:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("System-generated comments cannot be deleted.")

    if request.user != comment.author and not membership.can_manage_content:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to delete this comment.")

    if request.method == 'POST':
        comment.delete()
        messages.success(request, "Comment removed.")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=comments")


@workspace_member_required
def task_bug_attach_view(request, slug, task_code):
    """
    Attaches an existing workspace bug to this task.
    Enforces atomic transaction and updates Comments + Activity.
    """
    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    if request.method == 'POST':
        bug_id = request.POST.get('bug_id')
        bug_code = request.POST.get('bug_code')
        from bugs.models import Bug
        bug = None
        if bug_id:
            bug = Bug.objects.filter(workspace=workspace, id=bug_id).first()
        elif bug_code:
            bug = Bug.objects.filter(workspace=workspace, bug_code=bug_code.strip()).first()

        if not bug:
            messages.error(request, "Bug not found or does not belong to this workspace.")
        else:
            try:
                attach_bug_to_task(task=task, bug=bug, actor=request.user)
                messages.success(request, f"Bug {bug.bug_code} successfully attached to task #{task.task_code}.")
            except Exception as e:
                messages.error(request, f"Failed to attach bug: {str(e)}")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=comments")


@workspace_member_required
def task_bug_detach_view(request, slug, task_code, bug_code=None, bug_id=None):
    """
    Detaches a bug from this task.
    Updates Comments + Activity.
    """
    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    if request.method == 'POST':
        import uuid
        from bugs.models import Bug
        identifier = bug_code or bug_id
        try:
            val_uuid = uuid.UUID(str(identifier))
            bug = get_object_or_404(Bug, workspace=workspace, id=val_uuid, linked_task=task)
        except (ValueError, AttributeError):
            bug = get_object_or_404(Bug, workspace=workspace, bug_code=identifier, linked_task=task)

        try:
            detach_bug_from_task(task=task, bug=bug, actor=request.user)
            messages.success(request, f"Bug {bug.bug_code} detached from task #{task.task_code}.")
        except Exception as e:
            messages.error(request, f"Failed to detach bug: {str(e)}")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=comments")


@workspace_member_required
def subtask_create_view(request, slug, task_code):
    """
    Create a new subtask under the given task.
    Supports both JSON/AJAX and traditional POST.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    title = ''
    if request.content_type == 'application/json':
        try:
            import json
            data = json.loads(request.body)
            title = data.get('title', '').strip()
        except (ValueError, TypeError):
            title = ''
    else:
        title = request.POST.get('title', '').strip()

    if not title:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'success': False, 'error': 'Title is required'}, status=400)
        messages.error(request, "Subtask title cannot be empty.")
        return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=subtasks")

    st = create_subtask(task=task, title=title, actor=request.user)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'subtask': {
                'id': str(st.id),
                'title': st.title,
                'is_completed': st.is_completed,
                'order': st.order,
            },
            'total_count': task.subtask_count,
            'completed_count': task.completed_subtask_count,
            'progress_percentage': task.subtask_progress_percentage,
        })

    messages.success(request, f"Added subtask '{st.title}'.")
    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=subtasks")


@workspace_member_required
def subtask_toggle_view(request, slug, task_code, subtask_id):
    """
    Toggle completion status of a subtask.
    Returns updated progress metrics for real-time UI updates.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)
    st = get_object_or_404(Subtask, id=subtask_id, task=task)

    st = toggle_subtask(task=task, subtask_id=subtask_id, actor=request.user)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or request.GET.get('format') == 'json':
        return JsonResponse({
            'success': True,
            'subtask_id': str(st.id),
            'is_completed': st.is_completed,
            'total_count': task.subtask_count,
            'completed_count': task.completed_subtask_count,
            'progress_percentage': task.subtask_progress_percentage,
        })

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=subtasks")


@workspace_member_required
def subtask_delete_view(request, slug, task_code, subtask_id):
    """
    Delete a subtask.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)
    st = get_object_or_404(Subtask, id=subtask_id, task=task)

    delete_subtask(task=task, subtask_id=subtask_id, actor=request.user)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or request.GET.get('format') == 'json':
        return JsonResponse({
            'success': True,
            'subtask_id': str(subtask_id),
            'total_count': task.subtask_count,
            'completed_count': task.completed_subtask_count,
            'progress_percentage': task.subtask_progress_percentage,
        })

    messages.success(request, "Subtask deleted.")
    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=subtasks")


@workspace_member_required
def task_attachment_upload_view(request, slug, task_code):
    """
    Handle task file attachments.
    Uploads to Supabase Storage (with local fallback), persists metadata in StoredFile & TaskAttachment,
    and logs activity.
    """
    workspace = request.workspace
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)

    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    file_obj = request.FILES.get('file')
    if not file_obj:
        messages.error(request, "Please select a file to upload.")
        return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=attachments")

    if file_obj.size > MAX_FILE_SIZE_BYTES:
        messages.error(request, f"File size exceeds limit ({MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB).")
        return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=attachments")

    try:
        import mimetypes
        original_name = file_obj.name
        checksum = compute_sha256(file_obj)
        mime_type, _ = mimetypes.guess_type(original_name)
        mime_type = mime_type or file_obj.content_type or 'application/octet-stream'
        category = detect_file_category(original_name, mime_type)

        storage_path = SupabaseStorageService.upload_file(
            file_obj=file_obj,
            workspace_id=workspace.id,
            filename=original_name,
            content_type=mime_type
        )

        stored_file = StoredFile.objects.create(
            workspace=workspace,
            uploaded_by=request.user,
            name=original_name,
            original_name=original_name,
            storage_path=storage_path,
            mime_type=mime_type,
            category=category,
            size_bytes=file_obj.size,
            checksum=checksum,
            description=f"Attached to task #{task.task_code}"
        )

        TaskAttachment.objects.create(task=task, file=stored_file)

        TaskActivity.objects.create(
            task=task,
            actor=request.user,
            action=TaskActivity.Action.UPDATED,
            message=f"Attached file '{original_name}' ({stored_file.formatted_size})"
        )

        messages.success(request, f"File '{original_name}' uploaded successfully.")
    except Exception as e:
        messages.error(request, f"File upload failed: {str(e)}")

    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=attachments")


@workspace_member_required
def task_attachment_delete_view(request, slug, task_code, attachment_id):
    """
    Remove an attachment from a task.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    membership = request.membership
    clean_code = task_code.lstrip('#').replace('T-', '').replace('t-', '')
    task = get_object_or_404(Task, workspace=workspace, task_code=clean_code)
    attachment = get_object_or_404(TaskAttachment, id=attachment_id, task=task)

    can_delete = (request.user == attachment.file.uploaded_by) or membership.can_manage_content
    if not can_delete:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to delete this attachment.")

    file_name = attachment.file.name
    attachment.delete()

    TaskActivity.objects.create(
        task=task,
        actor=request.user,
        action=TaskActivity.Action.UPDATED,
        message=f"Removed attachment '{file_name}'"
    )

    messages.success(request, f"Attachment '{file_name}' removed.")
    return redirect(f"{reverse('tasks:task_detail', kwargs={'slug': slug, 'task_code': task.task_code})}?tab=attachments")


@workspace_member_required
def sprint_planning_view(request, slug):
    """
    Agile Sprint Planning Command Center.
    Visualizes the Active Sprint, Planned Sprints, and Product Backlog.
    Supports drag/move between sprints, quick task creation, and sprint lifecycle controls.
    """
    workspace = request.workspace
    membership = request.membership

    can_manage_sprint = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    # Auto-seed initial Sprint 1 if workspace has zero sprints
    if not Sprint.objects.filter(workspace=workspace).exists():
        now = timezone.now().date()
        Sprint.objects.create(
            workspace=workspace,
            name="Sprint 1",
            goal=f"Initial milestone sprint for {workspace.name} deliverables.",
            status=SprintStatus.ACTIVE,
            start_date=now,
            end_date=now + timezone.timedelta(days=14),
            created_by=request.user
        )

    # Active Sprint
    active_sprint = Sprint.objects.filter(
        workspace=workspace,
        status=SprintStatus.ACTIVE
    ).prefetch_related('tasks__assignee').first()

    # Planned Sprints
    planned_sprints = Sprint.objects.filter(
        workspace=workspace,
        status=SprintStatus.PLANNING
    ).prefetch_related('tasks__assignee').order_by('created_at')

    # Completed Sprints
    completed_sprints = Sprint.objects.filter(
        workspace=workspace,
        status=SprintStatus.COMPLETED
    ).order_by('-updated_at')[:5]

    # Filters
    q = request.GET.get('q', '').strip()
    assignee_filter = request.GET.get('assignee', '').strip()
    priority_filter = request.GET.get('priority', '').strip()

    # Backlog Tasks: tasks without an active or planned sprint
    # Or tasks explicitly marked with sprint='Backlog'
    backlog_qs = Task.objects.filter(
        workspace=workspace
    ).filter(
        Q(sprint_ref__isnull=True) | Q(sprint__iexact='backlog') | Q(sprint_ref__status=SprintStatus.COMPLETED)
    ).exclude(
        status=TaskStatus.DONE
    ).select_related('assignee')

    if q:
        clean_code = q.lstrip('#')
        backlog_qs = backlog_qs.filter(
            Q(task_code__icontains=clean_code) |
            Q(title__icontains=q)
        )

    if assignee_filter:
        if assignee_filter == 'me':
            backlog_qs = backlog_qs.filter(assignee=request.user)
        else:
            backlog_qs = backlog_qs.filter(assignee_id=assignee_filter)

    if priority_filter and priority_filter in dict(TaskPriority.choices):
        backlog_qs = backlog_qs.filter(priority=priority_filter)

    backlog_tasks = list(backlog_qs)

    # Team members for assignment filters and inline task creation
    active_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user')

    # Workspace sprint velocity (completed tasks in completed sprints)
    velocity_count = Task.objects.filter(
        workspace=workspace,
        sprint_ref__status=SprintStatus.COMPLETED,
        status=TaskStatus.DONE
    ).count()

    # Sprint counts across all statuses for summary metrics (Real Database Aggregation)
    all_sprints = Sprint.objects.filter(workspace=workspace)
    sprint_counts = {
        'planned': all_sprints.filter(status=SprintStatus.PLANNING).count(),
        'active': all_sprints.filter(status=SprintStatus.ACTIVE).count(),
        'completed': all_sprints.filter(status=SprintStatus.COMPLETED).count(),
        'cancelled': all_sprints.filter(status=SprintStatus.CANCELLED).count(),
        'total': all_sprints.count(),
    }

    # Cancelled Sprints
    cancelled_sprints = all_sprints.filter(
        status=SprintStatus.CANCELLED
    ).order_by('-updated_at')[:5]

    context = {
        'title': f"Sprint Planning — {workspace.name} — AetherSpace",
        'workspace': workspace,
        'membership': membership,
        'can_manage_sprint': can_manage_sprint,
        'is_manager_or_admin': can_manage_sprint,
        'sprint_counts': sprint_counts,
        'active_sprint': active_sprint,
        'planned_sprints': planned_sprints,
        'completed_sprints': completed_sprints,
        'cancelled_sprints': cancelled_sprints,
        'backlog_tasks': backlog_tasks,
        'backlog_count': len(backlog_tasks),
        'active_members': active_members,
        'members': active_members,
        'velocity_count': velocity_count,
        'q': q,
        'assignee_filter': assignee_filter,
        'priority_filter': priority_filter,
        'priorities': TaskPriority.choices,
        'sprint_statuses': SprintStatus.choices,
        'can_create_task': can_user_perform_action(request.user, workspace, 'task.create'),
    }
    return render(request, 'tasks/sprint_planning.html', context)


@workspace_member_required
def sprint_create_view(request, slug):
    """
    Create a new Sprint in PLANNING status (or selected status).
    """
    workspace = request.workspace
    membership = request.membership

    can_manage = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )
    if not can_manage:
        messages.error(request, "Permission denied. Only Admins and Managers can create Sprints.")
        return redirect('tasks:sprint_planning', slug=slug)

    if request.method == 'POST':
        form = SprintForm(request.POST)
        if form.is_valid():
            sprint = form.save(commit=False)
            sprint.workspace = workspace
            sprint.created_by = request.user
            if not sprint.status:
                sprint.status = SprintStatus.PLANNING

            # If created directly as ACTIVE, deactivate any existing active sprint
            if sprint.status == SprintStatus.ACTIVE:
                Sprint.objects.filter(workspace=workspace, status=SprintStatus.ACTIVE).update(status=SprintStatus.PLANNING)

            sprint.save()
            messages.success(request, f"Sprint '{sprint.name}' created ({sprint.get_status_display()}).")
        else:
            first_err = next(iter(form.errors.values()))[0] if form.errors else "Invalid sprint data."
            messages.error(request, f"Could not create sprint: {first_err}")

    return redirect('tasks:sprint_planning', slug=slug)


@workspace_member_required
def sprint_edit_view(request, slug, sprint_id):
    """
    Dedicated view for editing sprint details (name, goal, status, start_date, end_date)
    with server-side RBAC validation and state-transition side effects.
    """
    workspace = request.workspace
    membership = request.membership

    can_manage = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )
    if not can_manage:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': 'Permission denied. Only workspace Admins and Managers can edit sprints.'}, status=403)
        messages.error(request, "Permission denied. Only workspace Admins and Managers can edit sprints.")
        return redirect('tasks:sprint_planning', slug=slug)

    sprint = get_object_or_404(Sprint, id=sprint_id, workspace=workspace)

    if request.method == 'POST':
        form = SprintForm(request.POST, instance=sprint)
        if form.is_valid():
            previous_status = sprint.status
            updated_sprint = form.save(commit=False)
            new_status = updated_sprint.status

            # Handle transition to ACTIVE
            if new_status == SprintStatus.ACTIVE and previous_status != SprintStatus.ACTIVE:
                Sprint.objects.filter(workspace=workspace, status=SprintStatus.ACTIVE).exclude(id=sprint.id).update(status=SprintStatus.PLANNING)
                if not updated_sprint.start_date:
                    updated_sprint.start_date = timezone.now().date()
                if not updated_sprint.end_date:
                    updated_sprint.end_date = updated_sprint.start_date + timezone.timedelta(days=14)

            # Handle transition to COMPLETED or CANCELLED: return incomplete tasks to Backlog
            elif new_status in (SprintStatus.COMPLETED, SprintStatus.CANCELLED) and previous_status not in (SprintStatus.COMPLETED, SprintStatus.CANCELLED):
                incomplete_tasks = sprint.tasks.exclude(status=TaskStatus.DONE)
                count = incomplete_tasks.count()
                if count > 0:
                    incomplete_tasks.update(sprint_ref=None, sprint='Backlog')
                    action_label = "completed" if new_status == SprintStatus.COMPLETED else "cancelled"
                    messages.info(request, f"Sprint '{updated_sprint.name}' {action_label}. {count} incomplete task(s) returned to Backlog.")

            updated_sprint.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'message': f"Sprint '{updated_sprint.name}' updated successfully.",
                    'sprint': {
                        'id': str(updated_sprint.id),
                        'name': updated_sprint.name,
                        'goal': updated_sprint.goal,
                        'status': updated_sprint.status,
                        'start_date': updated_sprint.start_date.isoformat() if updated_sprint.start_date else '',
                        'end_date': updated_sprint.end_date.isoformat() if updated_sprint.end_date else '',
                    }
                })

            messages.success(request, f"Sprint '{updated_sprint.name}' updated successfully.")
            return redirect('tasks:sprint_planning', slug=slug)
        else:
            errors = []
            for field, err_list in form.errors.items():
                for err in err_list:
                    errors.append(f"{field.capitalize()}: {err}" if field != '__all__' else str(err))
            error_message = "; ".join(errors) if errors else "Invalid sprint data."

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': error_message, 'errors': form.errors}, status=400)
            messages.error(request, f"Failed to update sprint: {error_message}")
            return redirect('tasks:sprint_planning', slug=slug)

    # GET request - return sprint details as JSON
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'status': 'success',
            'sprint': {
                'id': str(sprint.id),
                'name': sprint.name,
                'goal': sprint.goal,
                'status': sprint.status,
                'start_date': sprint.start_date.isoformat() if sprint.start_date else '',
                'end_date': sprint.end_date.isoformat() if sprint.end_date else '',
            }
        })

    return redirect('tasks:sprint_planning', slug=slug)


@workspace_member_required
def sprint_action_view(request, slug, sprint_id):
    """
    Start, Complete, Cancel, Edit, or Delete a Sprint.
    """
    workspace = request.workspace
    membership = request.membership

    can_manage = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )
    if not can_manage:
        messages.error(request, "Permission denied.")
        return redirect('tasks:sprint_planning', slug=slug)

    sprint = get_object_or_404(Sprint, id=sprint_id, workspace=workspace)

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'start':
            # Demote any currently active sprint to planning
            Sprint.objects.filter(workspace=workspace, status=SprintStatus.ACTIVE).exclude(id=sprint.id).update(status=SprintStatus.PLANNING)
            sprint.status = SprintStatus.ACTIVE
            if not sprint.start_date:
                sprint.start_date = timezone.now().date()
            if not sprint.end_date:
                sprint.end_date = sprint.start_date + timezone.timedelta(days=14)
            sprint.save()
            messages.success(request, f"Sprint '{sprint.name}' is now Active!")

        elif action == 'complete':
            sprint.status = SprintStatus.COMPLETED
            sprint.save()

            # Move incomplete tasks to Backlog
            incomplete_tasks = sprint.tasks.exclude(status=TaskStatus.DONE)
            count = incomplete_tasks.count()
            if count > 0:
                incomplete_tasks.update(sprint_ref=None, sprint='Backlog')
                messages.info(request, f"Sprint '{sprint.name}' completed! {count} incomplete task(s) moved to Product Backlog.")
            else:
                messages.success(request, f"Sprint '{sprint.name}' completed with 100% completion rate! 🎉")

        elif action == 'cancel':
            sprint.status = SprintStatus.CANCELLED
            sprint.save()

            incomplete_tasks = sprint.tasks.exclude(status=TaskStatus.DONE)
            count = incomplete_tasks.count()
            if count > 0:
                incomplete_tasks.update(sprint_ref=None, sprint='Backlog')
                messages.info(request, f"Sprint '{sprint.name}' cancelled. {count} incomplete task(s) returned to Backlog.")
            else:
                messages.info(request, f"Sprint '{sprint.name}' cancelled.")

        elif action == 'edit':
            form = SprintForm(request.POST, instance=sprint)
            if form.is_valid():
                previous_status = sprint.status
                updated_sprint = form.save(commit=False)
                new_status = updated_sprint.status

                if new_status == SprintStatus.ACTIVE and previous_status != SprintStatus.ACTIVE:
                    Sprint.objects.filter(workspace=workspace, status=SprintStatus.ACTIVE).exclude(id=sprint.id).update(status=SprintStatus.PLANNING)
                elif new_status in (SprintStatus.COMPLETED, SprintStatus.CANCELLED) and previous_status not in (SprintStatus.COMPLETED, SprintStatus.CANCELLED):
                    incomplete_tasks = sprint.tasks.exclude(status=TaskStatus.DONE)
                    if incomplete_tasks.exists():
                        incomplete_tasks.update(sprint_ref=None, sprint='Backlog')

                updated_sprint.save()
                messages.success(request, f"Sprint '{updated_sprint.name}' updated.")
            else:
                err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
                messages.error(request, f"Failed to update sprint: {err_msg}")

        elif action == 'delete':
            # Move any tasks to Backlog before deleting
            sprint.tasks.update(sprint_ref=None, sprint='Backlog')
            sprint_name = sprint.name
            sprint.delete()
            messages.success(request, f"Sprint '{sprint_name}' deleted. Associated tasks moved to Backlog.")

    return redirect('tasks:sprint_planning', slug=slug)


@workspace_member_required
def sprint_move_task_view(request, slug):
    """
    Move a task to a specific Sprint or to Product Backlog.
    Accepts POST with task_id and target_sprint_id ('backlog' or UUID).
    """
    workspace = request.workspace
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    task_id = request.POST.get('task_id', '').strip()
    target_sprint_id = request.POST.get('target_sprint_id', '').strip()

    task = get_object_or_404(Task, id=task_id, workspace=workspace)

    if target_sprint_id == 'backlog' or not target_sprint_id:
        task.sprint_ref = None
        task.sprint = 'Backlog'
        task.save()
        msg = f"Task #{task.task_code} moved to Product Backlog."
    else:
        target_sprint = get_object_or_404(Sprint, id=target_sprint_id, workspace=workspace)
        task.sprint_ref = target_sprint
        task.sprint = target_sprint.name
        task.save()
        msg = f"Task #{task.task_code} moved to '{target_sprint.name}'."

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('ajax') == '1':
        return JsonResponse({'status': 'ok', 'message': msg})

    messages.success(request, msg)
    return redirect('tasks:sprint_planning', slug=slug)


@workspace_member_required
def sprint_quick_create_task_view(request, slug):
    """
    Quickly create a task directly from the Sprint Planning interface.
    """
    workspace = request.workspace
    if not can_user_perform_action(request.user, workspace, 'task.create'):
        raise PermissionDenied(
            f"You do not have permission to create tasks in '{workspace.name}'. "
            "Only Managers and Administrators can create tasks. You may request temporary access."
        )
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    title = request.POST.get('title', '').strip()
    target_sprint_id = request.POST.get('sprint_id', '').strip() or request.POST.get('target_sprint_id', '').strip()
    priority = request.POST.get('priority', TaskPriority.MEDIUM)
    assignee_id = request.POST.get('assignee_id', '').strip()
    estimated_hours_raw = request.POST.get('estimated_hours', '').strip()

    if not title:
        messages.error(request, "Task title is required.")
        return redirect('tasks:sprint_planning', slug=slug)

    assignee = None
    if assignee_id:
        assignee = User.objects.filter(id=assignee_id).first()

    sprint_ref = None
    sprint_name = 'Backlog'
    if target_sprint_id and target_sprint_id != 'backlog':
        sprint_ref = Sprint.objects.filter(id=target_sprint_id, workspace=workspace).first()
        if sprint_ref:
            sprint_name = sprint_ref.name

    estimated_hours = None
    if estimated_hours_raw:
        try:
            estimated_hours = float(estimated_hours_raw)
        except ValueError:
            pass

    task = create_task(
        workspace=workspace,
        reporter=request.user,
        title=title,
        status=TaskStatus.TODO,
        priority=priority,
        assignee=assignee,
        sprint=sprint_name,
        sprint_ref=sprint_ref,
        estimated_hours=estimated_hours
    )

    messages.success(request, f"Created task #{task.task_code}: {task.title}")
    return redirect('tasks:sprint_planning', slug=slug)



