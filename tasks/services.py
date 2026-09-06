import secrets
from django.db import transaction
from django.utils import timezone
from .models import Task, TaskActivity, TaskStatus, TaskPriority


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
                estimated_hours=None, sprint='Sprint 01', tags='') -> Task:
    """
    Creates a new task in the given workspace, assigning a collision-free 6-digit ID,
    and records an initial TaskActivity log.
    """
    task_code = generate_unique_task_code()
    
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

    if assignee:
        assignee_name = assignee.full_name or assignee.email
        TaskActivity.objects.create(
            task=task,
            actor=reporter,
            action=TaskActivity.Action.ASSIGNED,
            new_value=assignee_name,
            message=f"Assigned task to {assignee_name}"
        )

    return task


@transaction.atomic
def update_task(task: Task, actor, **kwargs) -> Task:
    """
    Updates task fields and creates granular TaskActivity records for each changed field.
    Supported fields: title, description, status, priority, assignee, due_date, estimated_hours.
    """
    updated_fields = []
    
    # Check status change
    if 'status' in kwargs and kwargs['status'] != task.status:
        old_status = task.get_status_display()
        task.status = kwargs['status']
        new_status = task.get_status_display()
        updated_fields.append('status')
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.STATUS_CHANGED,
            old_value=old_status,
            new_value=new_status,
            message=f"Changed status from '{old_status}' to '{new_status}'"
        )

    # Check priority change
    if 'priority' in kwargs and kwargs['priority'] != task.priority:
        old_pri = task.get_priority_display()
        task.priority = kwargs['priority']
        new_pri = task.get_priority_display()
        updated_fields.append('priority')
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.PRIORITY_CHANGED,
            old_value=old_pri,
            new_value=new_pri,
            message=f"Changed priority from '{old_pri}' to '{new_pri}'"
        )

    # Check assignee change
    if 'assignee' in kwargs and kwargs['assignee'] != task.assignee:
        old_assignee_name = (task.assignee.full_name or task.assignee.email) if task.assignee else "Unassigned"
        task.assignee = kwargs['assignee']
        new_assignee_name = (task.assignee.full_name or task.assignee.email) if task.assignee else "Unassigned"
        updated_fields.append('assignee')
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.ASSIGNED,
            old_value=old_assignee_name,
            new_value=new_assignee_name,
            message=f"Reassigned from {old_assignee_name} to {new_assignee_name}"
        )

    # Check due date change
    if 'due_date' in kwargs and kwargs['due_date'] != task.due_date:
        old_due = str(task.due_date) if task.due_date else "None"
        task.due_date = kwargs['due_date']
        new_due = str(task.due_date) if task.due_date else "None"
        updated_fields.append('due_date')
        TaskActivity.objects.create(
            task=task,
            actor=actor,
            action=TaskActivity.Action.UPDATED,
            old_value=old_due,
            new_value=new_due,
            message=f"Updated due date to {new_due}"
        )

    # Direct attribute updates
    for field in ['title', 'description', 'estimated_hours', 'sprint', 'tags']:
        if field in kwargs and kwargs[field] != getattr(task, field):
            setattr(task, field, kwargs[field])
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
