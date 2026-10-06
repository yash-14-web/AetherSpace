import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import PermissionDenied

from workspaces.permissions import workspace_member_required
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole, WorkspaceModule
from .models import (
    Bug, BugActivity, BugComment, BugStatus, BugPriority,
    BugSeverity, BugEnvironment, BugAttachment
)
from .forms import BugForm, BugFilterForm
from .services import create_bug, update_bug, change_bug_status
from files.models import StoredFile
from files.services import (
    SupabaseStorageService, compute_sha256, detect_file_category, MAX_FILE_SIZE_BYTES
)

logger = logging.getLogger(__name__)


@login_required
def bugs_redirect_router(request):
    """
    Intelligent routing for /bugs/ root endpoint:
    Redirects to the user's active workspace bug list if available,
    or falls back to the cross-workspace 'My Bugs' view.
    """
    first_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status='ACTIVE'
    ).select_related('workspace').first()

    if first_membership:
        return redirect('bugs:bug_list', slug=first_membership.workspace.slug)
    return redirect('bugs:my_bugs')


@workspace_member_required
def bug_dashboard_view(request, slug):
    """
    Visual Bug Tracking Dashboard matching Panel 1 of mockup:
    Metric cards, Bugs by Status donut breakdown, Bugs by Priority,
    Recent Bugs list, and Top Modules breakdown.
    """
    workspace = request.workspace
    membership = request.membership

    bugs_qs = Bug.objects.filter(workspace=workspace).select_related('assignee', 'reporter', 'module')

    total_bugs = bugs_qs.count()
    open_count = bugs_qs.filter(status=BugStatus.OPEN).count()
    in_progress_count = bugs_qs.filter(status=BugStatus.IN_PROGRESS).count()
    resolved_count = bugs_qs.filter(status=BugStatus.RESOLVED).count()
    closed_count = bugs_qs.filter(status=BugStatus.CLOSED).count()

    # Calculate status percentages for donut chart
    def pct(count):
        return round((count / total_bugs * 100), 1) if total_bugs > 0 else 0

    status_breakdown = {
        'open': {'count': open_count, 'pct': pct(open_count)},
        'in_progress': {'count': in_progress_count, 'pct': pct(in_progress_count)},
        'resolved': {'count': resolved_count, 'pct': pct(resolved_count)},
        'closed': {'count': closed_count, 'pct': pct(closed_count)},
    }

    # Priority counts
    priority_counts = {
        'critical': bugs_qs.filter(priority=BugPriority.CRITICAL).count(),
        'high': bugs_qs.filter(priority=BugPriority.HIGH).count(),
        'medium': bugs_qs.filter(priority=BugPriority.MEDIUM).count(),
        'low': bugs_qs.filter(priority=BugPriority.LOW).count(),
    }

    # Top modules with bugs
    module_counts = bugs_qs.exclude(module__isnull=True).values('module__id', 'module__name').annotate(count=Count('id')).order_by('-count')[:5]
    top_modules = []
    for item in module_counts:
        c = item['count']
        top_modules.append({
            'module': item['module__name'],
            'module_id': item['module__id'],
            'count': c,
            'pct': pct(c)
        })

    # Recent 6 bugs
    recent_bugs = bugs_qs.order_by('-created_at')[:6]

    context = {
        'workspace': workspace,
        'membership': membership,
        'total_bugs': total_bugs,
        'open_count': open_count,
        'in_progress_count': in_progress_count,
        'resolved_count': resolved_count,
        'closed_count': closed_count,
        'status_breakdown': status_breakdown,
        'priority_counts': priority_counts,
        'top_modules': top_modules,
        'recent_bugs': recent_bugs,
    }
    return render(request, 'bugs/bug_dashboard.html', context)


@workspace_member_required
def bug_list_view(request, slug):
    """
    Filterable, searchable, and paginated Bug List matching Panel 2 of mockup.
    Includes status filter tabs, search toolbar, multi-select criteria, and quick actions.
    """
    workspace = request.workspace
    membership = request.membership

    bugs_qs = Bug.objects.filter(workspace=workspace).select_related('assignee', 'reporter', 'module')

    # Status counts for tabs
    status_counts = {
        'all': bugs_qs.count(),
        'open': bugs_qs.filter(status=BugStatus.OPEN).count(),
        'in_progress': bugs_qs.filter(status=BugStatus.IN_PROGRESS).count(),
        'resolved': bugs_qs.filter(status=BugStatus.RESOLVED).count(),
        'closed': bugs_qs.filter(status=BugStatus.CLOSED).count(),
        'my_bugs': bugs_qs.filter(assignee=request.user).count(),
    }

    # Filters
    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    priority_filter = request.GET.get('priority', '').strip()
    severity_filter = request.GET.get('severity', '').strip()
    module_filter = request.GET.get('module', '').strip()
    environment_filter = request.GET.get('environment', '').strip()
    assignee_filter = request.GET.get('assignee', '').strip()

    if q:
        clean_q = q.lstrip('#')
        bugs_qs = bugs_qs.filter(
            Q(title__icontains=q) |
            Q(bug_code__icontains=clean_q) |
            Q(description__icontains=q) |
            Q(labels__icontains=q)
        )

    if status_filter:
        if status_filter.upper() == 'MY_BUGS':
            bugs_qs = bugs_qs.filter(assignee=request.user)
        elif status_filter in dict(BugStatus.choices):
            bugs_qs = bugs_qs.filter(status=status_filter)

    if priority_filter and priority_filter in dict(BugPriority.choices):
        bugs_qs = bugs_qs.filter(priority=priority_filter)

    if severity_filter and severity_filter in dict(BugSeverity.choices):
        bugs_qs = bugs_qs.filter(severity=severity_filter)

    if module_filter:
        bugs_qs = bugs_qs.filter(Q(module__id__iexact=module_filter) | Q(module__name__iexact=module_filter))

    if environment_filter and environment_filter in dict(BugEnvironment.choices):
        bugs_qs = bugs_qs.filter(environment=environment_filter)

    if assignee_filter:
        if assignee_filter == 'unassigned':
            bugs_qs = bugs_qs.filter(assignee__isnull=True)
        elif assignee_filter == 'me':
            bugs_qs = bugs_qs.filter(assignee=request.user)
        else:
            bugs_qs = bugs_qs.filter(assignee_id=assignee_filter)

    # Order by creation date
    bugs_qs = bugs_qs.order_by('-created_at')

    # Pagination: 10 per page matching mockup
    paginator = Paginator(bugs_qs, 10)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Active workspace members for assignee dropdown
    active_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user')

    workspace_modules = WorkspaceModule.objects.filter(workspace=workspace).order_by('name')

    context = {
        'workspace': workspace,
        'membership': membership,
        'page_obj': page_obj,
        'total_filtered': bugs_qs.count(),
        'status_counts': status_counts,
        'active_members': active_members,
        'workspace_modules': workspace_modules,
        'current_q': q,
        'current_status': status_filter,
        'current_priority': priority_filter,
        'current_severity': severity_filter,
        'current_module': module_filter,
        'current_environment': environment_filter,
        'current_assignee': assignee_filter,
        'BugStatus': BugStatus,
        'BugPriority': BugPriority,
        'BugSeverity': BugSeverity,
        'BugEnvironment': BugEnvironment,
    }
    return render(request, 'bugs/bug_list.html', context)


@workspace_member_required
def bug_detail_view(request, slug, bug_code):
    """
    Detailed Bug View matching Panel 3 & 7 of mockup:
    Left tabs (Overview, Comments, Attachments, Activity),
    Steps to Reproduce, Expected vs Actual results, and Sidebar metadata.
    """
    workspace = request.workspace
    membership = request.membership

    # Strip potential prefix variations
    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(
        Bug.objects.select_related('workspace', 'assignee', 'reporter', 'module', 'linked_task').prefetch_related(
            'attachments__file',
            'attachments__file__uploaded_by'
        ),
        workspace=workspace,
        bug_code=clean_code
    )

    activities = bug.activities.select_related('actor').order_by('-created_at')
    comments = bug.comments.select_related('author').order_by('created_at')
    attachments = bug.attachments.select_related('file', 'file__uploaded_by').all()

    context = {
        'workspace': workspace,
        'membership': membership,
        'bug': bug,
        'activities': activities,
        'comments': comments,
        'attachments': attachments,
        'initial_tab': request.GET.get('tab', 'overview'),
        'BugStatus': BugStatus,
        'BugPriority': BugPriority,
        'BugSeverity': BugSeverity,
    }
    return render(request, 'bugs/bug_detail.html', context)


@workspace_member_required
def bug_create_view(request, slug):
    """
    Raise New Bug form matching Panel 4 of mockup.
    Saves new bug with automatic collision-safe B-###### code.
    """
    workspace = request.workspace
    membership = request.membership

    if request.method == 'POST':
        form = BugForm(request.POST, workspace=workspace)
        if form.is_valid():
            reporter_user = form.cleaned_data.get('reporter') or request.user
            bug = create_bug(
                workspace=workspace,
                reporter=reporter_user,
                title=form.cleaned_data['title'],
                description=form.cleaned_data.get('description', ''),
                steps_to_reproduce=form.cleaned_data.get('steps_to_reproduce', ''),
                expected_result=form.cleaned_data.get('expected_result', ''),
                actual_result=form.cleaned_data.get('actual_result', ''),
                status=form.cleaned_data.get('status', BugStatus.OPEN),
                priority=form.cleaned_data.get('priority', BugPriority.MEDIUM),
                severity=form.cleaned_data.get('severity', BugSeverity.SEV3),
                environment=form.cleaned_data.get('environment', BugEnvironment.STAGING),
                module=form.cleaned_data.get('module'),
                linked_task=form.cleaned_data.get('linked_task'),
                browser_device=form.cleaned_data.get('browser_device', ''),
                sprint=form.cleaned_data.get('sprint', 'Sprint 01'),
                assignee=form.cleaned_data.get('assignee'),
                due_date=form.cleaned_data.get('due_date'),
                labels=form.cleaned_data.get('labels', ''),
            )
            messages.success(request, f"Bug {bug.bug_code} was successfully reported.")
            return redirect('bugs:bug_detail', slug=workspace.slug, bug_code=bug.bug_code)
    else:
        initial_data = {
            'status': BugStatus.OPEN,
            'priority': BugPriority.MEDIUM,
            'severity': BugSeverity.SEV3,
            'environment': BugEnvironment.STAGING,
            'reporter': request.user,
        }
        # Pre-select linked_task if passed via query string (e.g. from task detail)
        linked_task_id = request.GET.get('linked_task')
        if linked_task_id:
            from tasks.models import Task
            task_obj = Task.objects.filter(workspace=workspace, id=linked_task_id).first()
            if task_obj:
                initial_data['linked_task'] = task_obj

        form = BugForm(workspace=workspace, initial=initial_data)

    context = {
        'workspace': workspace,
        'membership': membership,
        'form': form,
        'is_create': True,
    }
    return render(request, 'bugs/bug_form.html', context)


@workspace_member_required
def bug_edit_view(request, slug, bug_code):
    """
    Edit Bug view matching Panel 5 of mockup.
    Modifies attributes and records granular audit history.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(
        Bug.objects.select_related('workspace', 'assignee', 'reporter', 'module', 'linked_task'),
        workspace=workspace,
        bug_code=clean_code
    )

    if request.method == 'POST':
        form = BugForm(request.POST, instance=bug, workspace=workspace)
        if form.is_valid():
            reporter_user = form.cleaned_data.get('reporter') or bug.reporter
            update_bug(
                bug=bug,
                actor=request.user,
                title=form.cleaned_data['title'],
                reporter=reporter_user,
                description=form.cleaned_data.get('description', ''),
                steps_to_reproduce=form.cleaned_data.get('steps_to_reproduce', ''),
                expected_result=form.cleaned_data.get('expected_result', ''),
                actual_result=form.cleaned_data.get('actual_result', ''),
                status=form.cleaned_data.get('status'),
                priority=form.cleaned_data.get('priority'),
                severity=form.cleaned_data.get('severity'),
                environment=form.cleaned_data.get('environment'),
                module=form.cleaned_data.get('module'),
                linked_task=form.cleaned_data.get('linked_task'),
                browser_device=form.cleaned_data.get('browser_device', ''),
                sprint=form.cleaned_data.get('sprint', 'Sprint 01'),
                assignee=form.cleaned_data.get('assignee'),
                due_date=form.cleaned_data.get('due_date'),
                labels=form.cleaned_data.get('labels', ''),
            )
            messages.success(request, f"Bug {bug.bug_code} was successfully updated.")
            return redirect('bugs:bug_detail', slug=workspace.slug, bug_code=bug.bug_code)
    else:
        form = BugForm(instance=bug, workspace=workspace)

    context = {
        'workspace': workspace,
        'membership': membership,
        'form': form,
        'bug': bug,
        'is_create': False,
    }
    return render(request, 'bugs/bug_form.html', context)


@workspace_member_required
def bug_status_update_view(request, slug, bug_code):
    """
    Quick status transition via sidebar select dropdown.
    """
    if request.method != 'POST':
        return redirect('bugs:bug_detail', slug=slug, bug_code=bug_code)

    workspace = request.workspace
    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)

    new_status = request.POST.get('status')
    if new_status in dict(BugStatus.choices):
        change_bug_status(bug, new_status, request.user)
        messages.success(request, f"Status updated to '{bug.get_status_display()}'.")
    else:
        messages.error(request, "Invalid status choice.")

    return redirect('bugs:bug_detail', slug=workspace.slug, bug_code=bug.bug_code)


@workspace_member_required
def bug_activity_view(request, slug, bug_code):
    """
    Dedicated Bug Activity & Audit timeline matching Panel 7 of mockup.
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)
    activities = bug.activities.select_related('actor').order_by('-created_at')

    context = {
        'workspace': workspace,
        'membership': membership,
        'bug': bug,
        'activities': activities,
    }
    return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=activity")


@workspace_member_required
def bug_comment_add_view(request, slug, bug_code):
    """
    Post a new discussion comment on a bug.
    """
    if request.method != 'POST':
        return redirect('bugs:bug_detail', slug=slug, bug_code=bug_code)

    workspace = request.workspace
    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)

    content = request.POST.get('content', '').strip()
    if content:
        BugComment.objects.create(
            bug=bug,
            author=request.user,
            content=content
        )
        snippet = content[:60] + ('...' if len(content) > 60 else '')
        BugActivity.objects.create(
            bug=bug,
            actor=request.user,
            action=BugActivity.Action.COMMENTED,
            message=f'Added a comment: "{snippet}"'
        )

        # Scan for mentions and notify (ReDoS-hardened deterministic parser)
        from accounts.models import User
        from notifications.services import create_notification
        from notifications.models import NotificationCategory, NotificationType
        from notifications.email_service import send_mention_email
        from core.templatetags.rich_text import extract_mention_cids

        active_members = [
            m.user for m in WorkspaceMembership.objects.filter(
                workspace=workspace,
                status=MembershipStatus.ACTIVE
            ).select_related('user').exclude(user=request.user)
        ]

        active_members_by_cid = {u.contributor_id: u for u in active_members if u.contributor_id}
        mentioned_users = set()

        for cid in extract_mention_cids(content):
            if cid in active_members_by_cid:
                mentioned_users.add(active_members_by_cid[cid])

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
                        category=NotificationCategory.BUG,
                        notification_type=NotificationType.BUG_ASSIGNED,
                        title=f"{actor_name} mentioned you in Bug {bug.bug_code}",
                        body=f"{actor_name} mentioned you in a comment on '{bug.title}'",
                        workspace=workspace,
                        actor=request.user,
                        action_url=f"/bugs/w/{workspace.slug}/{bug.bug_code}/?tab=comments"
                    )
                except Exception:
                    pass

                try:
                    send_mention_email(
                        user=u,
                        actor=request.user,
                        context_type="Defect",
                        context_title=f"{bug.bug_code} - {bug.title}",
                        snippet=snippet,
                        action_url=f"/bugs/w/{workspace.slug}/{bug.bug_code}/?tab=comments"
                    )
                except Exception:
                    pass

        messages.success(request, "Comment posted successfully.")
    else:
        messages.error(request, "Comment cannot be empty.")

    return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=comments")


@workspace_member_required
def bug_comment_edit_view(request, slug, bug_code, comment_id):
    """
    Edit a bug discussion comment (author or Admin/Manager only).
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)
    comment = get_object_or_404(BugComment, id=comment_id, bug=bug)

    if request.user != comment.author and not membership.can_manage_content:
        raise PermissionDenied("You do not have permission to edit this comment.")

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        if not content:
            messages.error(request, "Comment content cannot be empty.")
        else:
            comment.content = content
            comment.save(update_fields=['content', 'updated_at'])
            snippet = content[:60] + ('...' if len(content) > 60 else '')
            BugActivity.objects.create(
                bug=bug,
                actor=request.user,
                action=BugActivity.Action.UPDATED,
                message=f'Edited comment: "{snippet}"'
            )
            messages.success(request, "Comment updated successfully.")

    return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=comments")


@workspace_member_required
def bug_comment_delete_view(request, slug, bug_code, comment_id):
    """
    Delete a bug discussion comment (author or Admin/Manager only).
    """
    workspace = request.workspace
    membership = request.membership

    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)
    comment = get_object_or_404(BugComment, id=comment_id, bug=bug)

    if request.user != comment.author and not membership.can_manage_content:
        raise PermissionDenied("You do not have permission to delete this comment.")

    if request.method == 'POST':
        comment.delete()
        messages.success(request, "Comment removed.")

    return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=comments")


@workspace_member_required
def bug_delete_view(request, slug, bug_code):
    """
    Delete bug endpoint: strictly restricted to Workspace Managers and Admins.
    Raises PermissionDenied (403) for Contributors.
    """
    workspace = request.workspace
    membership = request.membership

    if not membership.can_manage_content:
        raise PermissionDenied("Only workspace Managers and Administrators can delete bugs.")

    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"

    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)

    if request.method == 'POST':
        title = bug.title
        code = bug.bug_code
        bug.delete()
        messages.success(request, f"Bug {code} '{title}' was permanently deleted.")
        return redirect('bugs:bug_list', slug=workspace.slug)

    context = {
        'workspace': workspace,
        'membership': membership,
        'bug': bug,
    }
    return render(request, 'bugs/bug_confirm_delete.html', context)


@login_required
def my_bugs_view(request):
    """
    Global personal bugs tracker across all user workspaces matching Panel 6 of mockup:
    Tabs for 'Assigned to Me' and 'Reported by Me'.
    """
    filter_type = request.GET.get('tab', 'assigned')

    base_qs = Bug.objects.filter(
        workspace__memberships__user=request.user,
        workspace__memberships__status=MembershipStatus.ACTIVE,
        workspace__status='ACTIVE'
    ).select_related('workspace', 'assignee', 'reporter').distinct()

    if filter_type == 'reported':
        bugs_qs = base_qs.filter(reporter=request.user)
    else:
        bugs_qs = base_qs.filter(assignee=request.user)

    assigned_count = base_qs.filter(assignee=request.user).count()
    reported_count = base_qs.filter(reporter=request.user).count()

    context = {
        'bugs': bugs_qs.order_by('-created_at'),
        'filter_type': filter_type,
        'assigned_count': assigned_count,
        'reported_count': reported_count,
        'BugStatus': BugStatus,
        'BugPriority': BugPriority,
    }
    return render(request, 'bugs/my_bugs.html', context)


@workspace_member_required
def bug_attachment_upload_view(request, slug, bug_code):
    """
    Handle defect attachments.
    Uploads to Supabase Storage (with local fallback), persists metadata in StoredFile & BugAttachment,
    and logs activity.
    """
    workspace = request.workspace
    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"
    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)

    if request.method != 'POST':
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("POST required")

    file_obj = request.FILES.get('file')
    if not file_obj:
        messages.error(request, "Please select a file to upload.")
        return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=attachments")

    if file_obj.size > MAX_FILE_SIZE_BYTES:
        messages.error(request, f"File size exceeds limit ({MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB).")
        return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=attachments")

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
            description=f"Attached to defect {bug.bug_code}"
        )

        BugAttachment.objects.create(bug=bug, file=stored_file)

        BugActivity.objects.create(
            bug=bug,
            actor=request.user,
            action=BugActivity.Action.ATTACHMENT_ADDED,
            message=f"Attached file '{original_name}' ({stored_file.formatted_size})"
        )

        messages.success(request, f"File '{original_name}' uploaded successfully.")
    except Exception as e:
        logger.exception("File upload failed for bug %s: %s", getattr(bug, 'id', None), e)
        messages.error(request, "File upload failed. An unexpected error occurred.")

    return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=attachments")


@workspace_member_required
def bug_attachment_delete_view(request, slug, bug_code, attachment_id):
    """
    Remove an attachment from a defect.
    """
    if request.method != 'POST':
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("POST required")

    workspace = request.workspace
    membership = request.membership
    clean_code = bug_code.strip()
    if not clean_code.startswith('B-'):
        clean_code = f"B-{clean_code.lstrip('#')}"
    bug = get_object_or_404(Bug, workspace=workspace, bug_code=clean_code)
    attachment = get_object_or_404(BugAttachment, id=attachment_id, bug=bug)

    can_delete = (request.user == attachment.file.uploaded_by) or membership.can_manage_content
    if not can_delete:
        raise PermissionDenied("You do not have permission to delete this attachment.")

    file_name = attachment.file.name
    attachment.delete()

    BugActivity.objects.create(
        bug=bug,
        actor=request.user,
        action=BugActivity.Action.UPDATED,
        message=f"Removed attachment '{file_name}'"
    )

    messages.success(request, f"Attachment '{file_name}' removed.")
    return redirect(f"{reverse('bugs:bug_detail', kwargs={'slug': slug, 'bug_code': bug.bug_code})}?tab=attachments")

