from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import PermissionDenied

from workspaces.permissions import workspace_member_required
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole
from .models import (
    Bug, BugActivity, BugComment, BugStatus, BugPriority,
    BugSeverity, BugEnvironment, BugModule
)
from .forms import BugForm, BugFilterForm
from .services import create_bug, update_bug, change_bug_status


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

    bugs_qs = Bug.objects.filter(workspace=workspace).select_related('assignee', 'reporter')

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
    module_counts = bugs_qs.values('module').annotate(count=Count('id')).order_by('-count')[:5]
    top_modules = []
    for item in module_counts:
        c = item['count']
        top_modules.append({
            'module': item['module'],
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

    bugs_qs = Bug.objects.filter(workspace=workspace).select_related('assignee', 'reporter')

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
        bugs_qs = bugs_qs.filter(module=module_filter)

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

    context = {
        'workspace': workspace,
        'membership': membership,
        'page_obj': page_obj,
        'total_filtered': bugs_qs.count(),
        'status_counts': status_counts,
        'active_members': active_members,
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
        'BugModule': BugModule,
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
        Bug.objects.select_related('workspace', 'assignee', 'reporter'),
        workspace=workspace,
        bug_code=clean_code
    )

    activities = bug.activities.select_related('actor').order_by('-created_at')
    comments = bug.comments.select_related('author').order_by('created_at')

    context = {
        'workspace': workspace,
        'membership': membership,
        'bug': bug,
        'activities': activities,
        'comments': comments,
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
            bug = create_bug(
                workspace=workspace,
                reporter=request.user,
                title=form.cleaned_data['title'],
                description=form.cleaned_data.get('description', ''),
                steps_to_reproduce=form.cleaned_data.get('steps_to_reproduce', ''),
                expected_result=form.cleaned_data.get('expected_result', ''),
                actual_result=form.cleaned_data.get('actual_result', ''),
                status=form.cleaned_data.get('status', BugStatus.OPEN),
                priority=form.cleaned_data.get('priority', BugPriority.MEDIUM),
                severity=form.cleaned_data.get('severity', BugSeverity.SEV3),
                environment=form.cleaned_data.get('environment', BugEnvironment.STAGING),
                module=form.cleaned_data.get('module', BugModule.OTHER),
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
            'module': BugModule.OTHER,
        }
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
        Bug.objects.select_related('workspace', 'assignee', 'reporter'),
        workspace=workspace,
        bug_code=clean_code
    )

    if request.method == 'POST':
        form = BugForm(request.POST, instance=bug, workspace=workspace)
        if form.is_valid():
            update_bug(
                bug=bug,
                actor=request.user,
                title=form.cleaned_data['title'],
                description=form.cleaned_data.get('description', ''),
                steps_to_reproduce=form.cleaned_data.get('steps_to_reproduce', ''),
                expected_result=form.cleaned_data.get('expected_result', ''),
                actual_result=form.cleaned_data.get('actual_result', ''),
                status=form.cleaned_data.get('status'),
                priority=form.cleaned_data.get('priority'),
                severity=form.cleaned_data.get('severity'),
                environment=form.cleaned_data.get('environment'),
                module=form.cleaned_data.get('module'),
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
        messages.success(request, "Comment posted successfully.")
    else:
        messages.error(request, "Comment cannot be empty.")

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
