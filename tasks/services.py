import secrets
from django.db import transaction
from django.utils import timezone
from .models import Task, TaskActivity, TaskComment, TaskStatus, TaskPriority, CodeReviewRequest, CodeReviewStatus


def generate_unique_task_code() -> str:
    """
    Generate a unique 6-digit numeric task code (e.g. '619347').
    Uses secrets.randbelow for cryptographic randomness and validates uniqueness
    against existing database records with a retry loop.
    """
    max_attempts = 20
    for _ in range(max_attempts):
        # Generate number between 100000 and 999999 inclusive
        candidate = str(secrets.randbelow(900000) + 100000)
        if not Task.objects.filter(task_code=candidate).exists():
            return candidate

    # Fallback in theoretical saturation: sequential probe
    last_task = Task.objects.order_by('-created_at').first()
    if last_task and last_task.task_code.isdigit():
        candidate_int = (int(last_task.task_code) + 1) % 900000 + 100000
        return str(candidate_int)
    return str(secrets.randbelow(900000) + 100000)


@transaction.atomic
def create_task(workspace, reporter, title, description='', status=TaskStatus.TODO,
                priority=TaskPriority.MEDIUM, assignee=None, due_date=None,
                estimated_hours=None, sprint='Sprint 01', tags='', sprint_ref=None) -> Task:
    """
    Creates a new task in the given workspace, assigning a collision-free 6-digit ID,
    and records an initial TaskActivity log.
    """
    task_code = generate_unique_task_code()
    
    if sprint_ref and not sprint:
        sprint = sprint_ref.name

    task = Task.objects.create(
        task_code=task_code,
        workspace=workspace,
        reporter=reporter,
        title=title.strip(),
        description=description.strip() if description else '',
        status=status,
        priority=priority,
        assignee=assignee,
        due_date=due_date,
        estimated_hours=estimated_hours,
        sprint=sprint or 'Sprint 01',
        sprint_ref=sprint_ref,
        tags=tags or ''
    )

    # Log task creation activity
    TaskActivity.objects.create(
        task=task,
        actor=reporter,
        action=TaskActivity.Action.CREATED,
        new_value=task.title,
        message=f"Created task #{task.task_code} in '{workspace.name}'"
    )

    # Generate initial structured system comment in COMMENTS
    TaskComment.objects.create(
        task=task,
        author=reporter,
        comment_type=TaskComment.CommentType.SYSTEM,
        system_event_type=TaskComment.SystemEventType.TASK_CREATED,
        content=task.description or '',
        metadata={
            'task_code': task.task_code,
            'display_code': task.display_code,
            'title': task.title,
            'priority': task.get_priority_display(),
            'priority_display': task.get_priority_display(),
            'status': task.get_status_display(),
            'status_display': task.get_status_display(),
            'requester': (reporter.full_name or reporter.email) if reporter else 'Unknown',
            'assignee': (assignee.full_name or assignee.email) if assignee else 'Unassigned',
            'description': task.description or '',
            'due_date': str(due_date) if due_date else None,
        }
    )

    if assignee:
        assignee_name = assignee.full_name or assignee.email
        TaskActivity.objects.create(
            task=task,
            actor=reporter,
            action=TaskActivity.Action.ASSIGNED,
            new_value=assignee_name,
            message=f"Assigned task to {assignee_name}"
        )
        # Notify assignee
        try:
            from notifications.services import create_notification
            from notifications.models import NotificationCategory, NotificationType
            create_notification(
                recipient=assignee,
                category=NotificationCategory.TASK,
                notification_type=NotificationType.TASK_ASSIGNED,
                title=f"Task #{task.task_code} Assigned",
                body=f"You were assigned to '{task.title}' by {reporter.full_name or reporter.email}",
                workspace=workspace,
                actor=reporter,
                action_url=task.get_absolute_url()
            )
        except Exception:
            pass

        # Email assignee
        try:
            from notifications.email_service import send_task_assigned_email
            if not reporter or assignee.id != reporter.id:
                send_task_assigned_email(task=task, assignee=assignee, actor=reporter)
        except Exception:
            pass

    return task


@transaction.atomic
def update_task(task: Task, actor, **kwargs) -> Task:
    """
    Updates task fields and creates granular TaskActivity records for each changed field.
    Supported fields: title, description, status, priority, assignee, due_date, estimated_hours, sprint, tags.
    """
    # Fetch current database record to accurately detect changes even if task was mutated in-memory
    db_task = Task.objects.select_related('assignee').get(pk=task.pk) if task.pk else None
    updated_fields = []
    
    # Check status change
    if 'status' in kwargs:
        target_status = kwargs['status']
        current_status = db_task.status if db_task else task.status
        if target_status != current_status:
            old_status = db_task.get_status_display() if db_task else task.get_status_display()
            task.status = target_status
            new_status = task.get_status_display()
            TaskActivity.objects.create(
                task=task,
                actor=actor,
                action=TaskActivity.Action.STATUS_CHANGED,
                old_value=old_status,
                new_value=new_status,
                message=f"Changed status from '{old_status}' to '{new_status}'"
            )
            # Notify reporter of status update
            try:
                from notifications.services import create_notification
                from notifications.models import NotificationCategory, NotificationType
                if task.reporter and actor and task.reporter.id != actor.id:
                    create_notification(
                        recipient=task.reporter,
                        category=NotificationCategory.TASK,
                        notification_type=NotificationType.TASK_STATUS_CHANGED,
                        title=f"Task #{task.task_code} Status: {new_status}",
                        body=f"Task '{task.title}' was moved to {new_status} by {actor.full_name or actor.email}",
                        workspace=task.workspace,
                        actor=actor,
                        action_url=task.get_absolute_url()
                    )
            except Exception:
                pass
        else:
            task.status = target_status
        updated_fields.append('status')

    # Check priority change
    if 'priority' in kwargs:
        target_pri = kwargs['priority']
        current_pri = db_task.priority if db_task else task.priority
        if target_pri != current_pri:
            old_pri = db_task.get_priority_display() if db_task else task.get_priority_display()
            task.priority = target_pri
            new_pri = task.get_priority_display()
            TaskActivity.objects.create(
                task=task,
                actor=actor,
                action=TaskActivity.Action.PRIORITY_CHANGED,
                old_value=old_pri,
                new_value=new_pri,
                message=f"Changed priority from '{old_pri}' to '{new_pri}'"
            )
        else:
            task.priority = target_pri
        updated_fields.append('priority')

    # Check assignee change
    if 'assignee' in kwargs:
        target_assignee = kwargs['assignee']
        current_assignee = db_task.assignee if db_task else task.assignee
        if target_assignee != current_assignee:
            old_assignee_name = (current_assignee.full_name or current_assignee.email) if current_assignee else "Unassigned"
            task.assignee = target_assignee
            new_assignee_name = (target_assignee.full_name or target_assignee.email) if target_assignee else "Unassigned"
            TaskActivity.objects.create(
                task=task,
                actor=actor,
                action=TaskActivity.Action.ASSIGNED,
                old_value=old_assignee_name,
                new_value=new_assignee_name,
                message=f"Reassigned from {old_assignee_name} to {new_assignee_name}"
            )
            # Notify new assignee
            try:
                from notifications.services import create_notification
                from notifications.models import NotificationCategory, NotificationType
                if task.assignee and actor and task.assignee.id != actor.id:
                    create_notification(
                        recipient=task.assignee,
                        category=NotificationCategory.TASK,
                        notification_type=NotificationType.TASK_ASSIGNED,
                        title=f"Task #{task.task_code} Assigned",
                        body=f"You were assigned to '{task.title}' by {actor.full_name or actor.email}",
                        workspace=task.workspace,
                        actor=actor,
                        action_url=task.get_absolute_url()
                    )
            except Exception:
                pass

            # Email new assignee
            try:
                from notifications.email_service import send_task_assigned_email
                if task.assignee and actor and task.assignee.id != actor.id:
                    send_task_assigned_email(task=task, assignee=task.assignee, actor=actor)
            except Exception:
                pass
        else:
            task.assignee = target_assignee
        updated_fields.append('assignee')

    # Check due date change
    if 'due_date' in kwargs:
        target_due = kwargs['due_date']
        current_due = db_task.due_date if db_task else task.due_date
        if target_due != current_due:
            old_due_str = str(current_due) if current_due else "None"
            task.due_date = target_due
            new_due_str = str(task.due_date) if task.due_date else "None"
            TaskActivity.objects.create(
                task=task,
                actor=actor,
                action=TaskActivity.Action.UPDATED,
                old_value=old_due_str,
                new_value=new_due_str,
                message=f"Updated due date to {new_due_str}"
            )
        else:
            task.due_date = target_due
        updated_fields.append('due_date')

    # Direct attribute updates
    for field in ['title', 'description', 'estimated_hours', 'sprint', 'tags']:
        if field in kwargs:
            target_val = kwargs[field]
            current_val = getattr(db_task, field) if db_task else getattr(task, field)
            if target_val != current_val:
                setattr(task, field, target_val)
            else:
                setattr(task, field, target_val)
            updated_fields.append(field)

    if updated_fields:
        updated_fields.append('updated_at')
        task.save(update_fields=list(set(updated_fields)))

    return task


def change_task_status(task: Task, actor, new_status: str) -> Task:
    """Helper specifically for quick Kanban moves."""
    if new_status not in dict(TaskStatus.choices):
        raise ValueError(f"Invalid status '{new_status}'")
    return update_task(task, actor, status=new_status)


@transaction.atomic
def sync_subtasks(task: Task, subtasks_data: list, actor=None) -> list:
    """
    Synchronize subtasks for a task from an ordered list of dicts:
    [{ 'id': '...', 'title': '...', 'is_completed': False }, ...]
    Creates new subtasks, updates existing ones, and removes unreferenced ones.
    """
    from .models import Subtask
    existing_subtasks = {str(st.id): st for st in task.subtasks.all()}
    kept_ids = set()
    result = []

    for index, item in enumerate(subtasks_data):
        title = item.get('title', '').strip()
        if not title:
            continue

        raw_id = str(item.get('id', '')).strip()
        is_completed = bool(item.get('is_completed', False))

        if raw_id in existing_subtasks:
            # Update existing
            st = existing_subtasks[raw_id]
            st.title = title
            st.is_completed = is_completed
            st.order = index
            st.save(update_fields=['title', 'is_completed', 'order', 'updated_at'])
            kept_ids.add(raw_id)
            result.append(st)
        else:
            # Create new
            st = Subtask.objects.create(
                task=task,
                title=title,
                is_completed=is_completed,
                order=index
            )
            kept_ids.add(str(st.id))
            result.append(st)

    # Delete removed subtasks
    to_delete = [st for st_id, st in existing_subtasks.items() if st_id not in kept_ids]
    if to_delete:
        Subtask.objects.filter(id__in=[st.id for st in to_delete]).delete()

    return result


@transaction.atomic
def create_subtask(task: Task, title: str, is_completed: bool = False, actor=None):
    """
    Create a single subtask on a task and optionally log TaskActivity.
    """
    from .models import Subtask
    title = title.strip()
    if not title:
        raise ValueError("Subtask title cannot be blank.")

    next_order = task.subtasks.count()
    subtask = Subtask.objects.create(
        task=task,
        title=title,
        is_completed=is_completed,
        order=next_order
    )

    if actor:
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.UPDATED,
            new_value=title,
            message=f"Added subtask: '{title}'"
        )

    return subtask


@transaction.atomic
def toggle_subtask(task: Task, subtask_id, actor=None):
    """
    Toggle subtask completion status.
    """
    from .models import Subtask
    subtask = task.subtasks.get(id=subtask_id)
    subtask.is_completed = not subtask.is_completed
    subtask.save(update_fields=['is_completed', 'updated_at'])

    if actor:
        status_text = "completed" if subtask.is_completed else "reopened"
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.UPDATED,
            new_value=str(subtask.is_completed),
            message=f"Marked subtask '{subtask.title}' as {status_text}."
        )

    return subtask


@transaction.atomic
def delete_subtask(task: Task, subtask_id, actor=None):
    """
    Delete a subtask from a task.
    """
    from .models import Subtask
    subtask = task.subtasks.get(id=subtask_id)
    title = subtask.title
    subtask.delete()

    if actor:
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.UPDATED,
            new_value="",
            message=f"Deleted subtask: '{title}'"
        )
    return True


def generate_unique_code_review_code() -> str:
    """
    Generate unique code review reference, e.g. 'CR-619347'.
    Uses secrets.randbelow for cryptographic randomness with retry uniqueness validation.
    """
    max_attempts = 20
    for _ in range(max_attempts):
        candidate = f"CR-{secrets.randbelow(900000) + 100000}"
        if not CodeReviewRequest.objects.filter(review_code=candidate).exists():
            return candidate

    last_cr = CodeReviewRequest.objects.order_by('-created_at').first()
    if last_cr and last_cr.review_code.startswith("CR-") and last_cr.review_code[3:].isdigit():
        num = (int(last_cr.review_code[3:]) + 1) % 900000 + 100000
        return f"CR-{num}"
    return f"CR-{secrets.randbelow(900000) + 100000}"


@transaction.atomic
def create_code_review_request(task: Task, requester, title: str, github_pr_url: str,
                               description: str = '', reviewer=None, status=CodeReviewStatus.REQUESTED) -> CodeReviewRequest:
    """
    Creates a new CodeReviewRequest linked to a Task, logs a real TaskActivity entry,
    and automatically posts a structured system comment in Task Comments.
    Validates requester membership, reviewer membership (if provided), PR URL, and duplicate active requests.
    """
    import re
    from django.core.exceptions import PermissionDenied, ValidationError
    from workspaces.models import WorkspaceMembership, MembershipStatus

    # Server-side validation: requester must be active member of task workspace
    if not WorkspaceMembership.objects.filter(
        workspace=task.workspace,
        user=requester,
        status=MembershipStatus.ACTIVE
    ).exists():
        raise PermissionDenied("Requester is not an active member of this workspace.")

    # Server-side validation: reviewer must be active member of task workspace if provided
    if reviewer:
        if not WorkspaceMembership.objects.filter(
            workspace=task.workspace,
            user=reviewer,
            status=MembershipStatus.ACTIVE
        ).exists():
            raise PermissionDenied("Selected reviewer is not an active member of this workspace.")

    # Validate PR URL format
    pr_pattern = re.compile(r'^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/pull/\d+/?$')
    clean_url = github_pr_url.strip()
    if not pr_pattern.match(clean_url):
        raise ValidationError("Invalid GitHub Pull Request URL.")

    # Check duplicate active review request on the same task for the same PR URL
    existing = CodeReviewRequest.objects.filter(
        task=task,
        github_pr_url=clean_url
    ).exclude(status__in=[CodeReviewStatus.CLOSED, CodeReviewStatus.MERGED])
    if existing.exists():
        raise ValidationError("An active code review request for this pull request already exists on this task.")

    review_code = generate_unique_code_review_code()
    cr = CodeReviewRequest.objects.create(
        review_code=review_code,
        task=task,
        requester=requester,
        reviewer=reviewer,
        title=title.strip(),
        description=description.strip() if description else '',
        github_pr_url=clean_url,
        status=status
    )

    # 1. Structured System Comment in COMMENTS
    TaskComment.objects.create(
        task=task,
        author=requester,
        comment_type=TaskComment.CommentType.SYSTEM,
        system_event_type=TaskComment.SystemEventType.CODE_REVIEW_REQUESTED,
        code_review=cr,
        content=f"Code Review {review_code} requested for PR: {clean_url}",
        metadata={
            'review_code': review_code,
            'title': cr.title,
            'task_code': task.task_code,
            'task_title': task.title,
            'requester': requester.full_name or requester.email,
            'reviewer': (reviewer.full_name or reviewer.email) if reviewer else 'Unassigned',
            'status': cr.get_status_display(),
            'github_pr_url': clean_url,
        }
    )

    # 2. Activity Log
    reviewer_text = f" with reviewer {reviewer.full_name or reviewer.email}" if reviewer else ""
    TaskActivity.objects.create(
        task=task,
        actor=requester,
        action=TaskActivity.Action.UPDATED,
        new_value=review_code,
        message=f"Created Code Review Request {review_code}{reviewer_text} for PR: {clean_url}"
    )

    return cr


@transaction.atomic
def update_code_review_status(code_review: CodeReviewRequest, actor, new_status: str) -> CodeReviewRequest:
    """
    Updates the status of a CodeReviewRequest with server-side permission enforcement,
    creates a structured system comment in Task Comments, and records an activity log on the connected task.
    """
    from django.core.exceptions import PermissionDenied, ValidationError
    from workspaces.models import WorkspaceMembership, MembershipStatus, WorkspaceRole

    if new_status not in dict(CodeReviewStatus.choices):
        raise ValidationError(f"Invalid code review status '{new_status}'.")

    # Permission check: Actor must be active workspace member
    membership = WorkspaceMembership.objects.filter(
        workspace=code_review.task.workspace,
        user=actor,
        status=MembershipStatus.ACTIVE
    ).first()

    if not membership:
        raise PermissionDenied("Actor is not an active member of this workspace.")

    # Admins, managers, and the requester/reviewer/assignee have permission to transition status
    is_privileged = (membership.role in [WorkspaceRole.ADMIN, WorkspaceRole.MANAGER])
    is_involved = (
        actor.id == code_review.requester_id or
        (code_review.reviewer_id and actor.id == code_review.reviewer_id) or
        (code_review.task.assignee_id and actor.id == code_review.task.assignee_id)
    )

    if not (is_privileged or is_involved):
        raise PermissionDenied("You do not have permission to modify this code review status.")

    old_status_display = code_review.get_status_display()
    code_review.status = new_status
    code_review.save(update_fields=['status', 'updated_at'])
    new_status_display = code_review.get_status_display()

    # 1. Structured System Comment in COMMENTS
    TaskComment.objects.create(
        task=code_review.task,
        author=actor,
        comment_type=TaskComment.CommentType.SYSTEM,
        system_event_type=TaskComment.SystemEventType.CODE_REVIEW_STATUS_CHANGED,
        code_review=code_review,
        content=f"Code Review {code_review.review_code} status updated: {old_status_display} → {new_status_display}",
        metadata={
            'review_code': code_review.review_code,
            'old_status': old_status_display,
            'new_status': new_status_display,
            'actor': actor.full_name or actor.email if actor else 'System',
            'changed_by': actor.full_name or actor.email if actor else 'System',
        }
    )

    # 2. Activity Log
    TaskActivity.objects.create(
        task=code_review.task,
        actor=actor,
        action=TaskActivity.Action.STATUS_CHANGED,
        old_value=old_status_display,
        new_value=new_status_display,
        message=f"🔵 Code Review {code_review.review_code} status changed: {old_status_display} → {new_status_display} by {actor.full_name or actor.email if actor else 'System'}"
    )

    return code_review


@transaction.atomic
def attach_bug_to_task(task: Task, bug, actor) -> TaskComment:
    """
    Attaches a Bug to a Task.
    Updates the Bug record, generates a real system-generated TaskComment,
    and records an event in TaskActivity as well as BugActivity.
    """
    from django.core.exceptions import PermissionDenied, ValidationError
    from bugs.models import BugActivity

    if task.workspace_id != bug.workspace_id:
        raise ValidationError("Bug does not belong to the same workspace as this task.")

    bug.linked_task = task
    bug.save(update_fields=['linked_task', 'updated_at'])

    actor_name = actor.full_name or actor.email if actor else 'System'

    # 1. System-generated COMMENT
    comment = TaskComment.objects.create(
        task=task,
        author=actor,
        comment_type=TaskComment.CommentType.SYSTEM,
        system_event_type=TaskComment.SystemEventType.BUG_ATTACHED,
        bug=bug,
        content=f"Bug {bug.bug_code} has been attached to this task.",
        metadata={
            'bug_code': bug.bug_code,
            'title': bug.title,
            'priority': bug.get_priority_display(),
            'severity': bug.get_severity_display(),
            'status': bug.get_status_display(),
            'assignee': (bug.assignee.full_name or bug.assignee.email) if bug.assignee else 'Unassigned',
            'actor': actor_name,
        }
    )

    # 2. Task ACTIVITY
    TaskActivity.objects.create(
        task=task,
        actor=actor,
        action=TaskActivity.Action.BUG_LINKED,
        new_value=bug.bug_code,
        message=f"🐛 {bug.bug_code} attached to task by {actor_name}"
    )

    # 3. Bug ACTIVITY
    BugActivity.objects.create(
        bug=bug,
        actor=actor,
        action=BugActivity.Action.UPDATED,
        new_value=task.task_code,
        message=f"Linked bug to task #{task.task_code} ({task.title}) by {actor_name}"
    )

    return comment


@transaction.atomic
def detach_bug_from_task(task: Task, bug, actor) -> TaskComment:
    """
    Detaches a Bug from a Task.
    Updates the Bug record, generates a real system-generated TaskComment,
    and records an event in TaskActivity as well as BugActivity.
    """
    from bugs.models import BugActivity

    bug.linked_task = None
    bug.save(update_fields=['linked_task', 'updated_at'])

    actor_name = actor.full_name or actor.email if actor else 'System'

    # 1. System-generated COMMENT
    comment = TaskComment.objects.create(
        task=task,
        author=actor,
        comment_type=TaskComment.CommentType.SYSTEM,
        system_event_type=TaskComment.SystemEventType.BUG_DETACHED,
        bug=bug,
        content=f"Bug {bug.bug_code} has been detached from this task by {actor_name}.",
        metadata={
            'bug_code': bug.bug_code,
            'title': bug.title,
            'actor': actor_name,
        }
    )

    # 2. Task ACTIVITY
    TaskActivity.objects.create(
        task=task,
        actor=actor,
        action=TaskActivity.Action.BUG_UNLINKED,
        new_value=bug.bug_code,
        message=f"🐛 {bug.bug_code} detached from task by {actor_name}"
    )

    # 3. Bug ACTIVITY
    BugActivity.objects.create(
        bug=bug,
        actor=actor,
        action=BugActivity.Action.UPDATED,
        new_value="None",
        message=f"Unlinked bug from task #{task.task_code} by {actor_name}"
    )

    return comment

