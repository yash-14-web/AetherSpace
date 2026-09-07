import secrets
from django.db import transaction
from .models import Bug, BugActivity, BugStatus


def generate_unique_bug_code():
    """
    Generate a collision-safe 6-digit numeric bug identifier with 'B-' prefix,
    e.g. 'B-882316'.
    Uses cryptographic randomness and loops with existence checks to guarantee uniqueness.
    """
    max_attempts = 100
    for _ in range(max_attempts):
        # 6-digit number between 100000 and 999999
        code_number = secrets.randbelow(900000) + 100000
        candidate_code = f"B-{code_number}"
        if not Bug.objects.filter(bug_code=candidate_code).exists():
            return candidate_code

    raise RuntimeError("Failed to generate a unique bug identifier after maximum retries.")


@transaction.atomic
def create_bug(
    workspace,
    reporter,
    title,
    description="",
    steps_to_reproduce="",
    expected_result="",
    actual_result="",
    status=BugStatus.OPEN,
    priority="MEDIUM",
    severity="SEV3",
    environment="STAGING",
    module=None,
    browser_device="",
    sprint="Sprint 01",
    assignee=None,
    due_date=None,
    labels="",
):
    """
    Create a new Bug with an automatically assigned collision-safe B-###### code
    and write the initial CREATED audit activity log.
    """
    bug_code = generate_unique_bug_code()

    bug = Bug.objects.create(
        bug_code=bug_code,
        workspace=workspace,
        reporter=reporter,
        title=title,
        description=description,
        steps_to_reproduce=steps_to_reproduce,
        expected_result=expected_result,
        actual_result=actual_result,
        status=status,
        priority=priority,
        severity=severity,
        environment=environment,
        module=module,
        browser_device=browser_device,
        sprint=sprint,
        assignee=assignee,
        due_date=due_date,
        labels=labels,
    )

    # Initial activity log
    BugActivity.objects.create(
        bug=bug,
        actor=reporter,
        action=BugActivity.Action.CREATED,
        new_value=bug_code,
        message=f"Raised bug {bug_code} with status '{bug.get_status_display()}' and priority '{bug.get_priority_display()}'.",
    )

    if assignee:
        assignee_name = assignee.full_name or assignee.email
        BugActivity.objects.create(
            bug=bug,
            actor=reporter,
            action=BugActivity.Action.ASSIGNED,
            new_value=str(assignee.id),
            message=f"Assigned bug to {assignee_name}.",
        )

    return bug


@transaction.atomic
def update_bug(bug, actor, **kwargs):
    """
    Update bug attributes and record granular BugActivity records for auditability.
    """
    changes = []

    # Check status change
    if 'status' in kwargs and kwargs['status'] and kwargs['status'] != bug.status:
        old_status = bug.get_status_display()
        bug.status = kwargs['status']
        new_status = bug.get_status_display()
        changes.append({
            'action': BugActivity.Action.STATUS_CHANGED,
            'old': old_status,
            'new': new_status,
            'msg': f"Changed status from '{old_status}' to '{new_status}'."
        })

    # Check priority change
    if 'priority' in kwargs and kwargs['priority'] and kwargs['priority'] != bug.priority:
        old_p = bug.get_priority_display()
        bug.priority = kwargs['priority']
        new_p = bug.get_priority_display()
        changes.append({
            'action': BugActivity.Action.PRIORITY_CHANGED,
            'old': old_p,
            'new': new_p,
            'msg': f"Changed priority from '{old_p}' to '{new_p}'."
        })

    # Check severity change
    if 'severity' in kwargs and kwargs['severity'] and kwargs['severity'] != bug.severity:
        old_s = bug.get_severity_display()
        bug.severity = kwargs['severity']
        new_s = bug.get_severity_display()
        changes.append({
            'action': BugActivity.Action.SEVERITY_CHANGED,
            'old': old_s,
            'new': new_s,
            'msg': f"Changed severity from '{old_s}' to '{new_s}'."
        })

    # Check assignee change
    if 'assignee' in kwargs and kwargs['assignee'] != bug.assignee:
        old_assignee = bug.assignee.full_name if bug.assignee else "Unassigned"
        new_assignee = kwargs['assignee'].full_name if kwargs['assignee'] else "Unassigned"
        bug.assignee = kwargs['assignee']
        changes.append({
            'action': BugActivity.Action.ASSIGNED,
            'old': old_assignee,
            'new': new_assignee,
            'msg': f"Reassigned bug from {old_assignee} to {new_assignee}."
        })

    # Check reporter change
    if 'reporter' in kwargs and kwargs['reporter'] and kwargs['reporter'] != bug.reporter:
        old_reporter = bug.reporter.full_name or bug.reporter.email if bug.reporter else "None"
        new_reporter = kwargs['reporter'].full_name or kwargs['reporter'].email if kwargs['reporter'] else "None"
        bug.reporter = kwargs['reporter']
        changes.append({
            'action': BugActivity.Action.UPDATED,
            'old': old_reporter,
            'new': new_reporter,
            'msg': f"Changed reporter from {old_reporter} to {new_reporter}."
        })

    # Check module change
    if 'module' in kwargs and kwargs['module'] != bug.module:
        old_mod = bug.module.name if bug.module else "None"
        new_mod = kwargs['module'].name if kwargs['module'] else "None"
        bug.module = kwargs['module']
        changes.append({
            'action': BugActivity.Action.UPDATED,
            'old': old_mod,
            'new': new_mod,
            'msg': f"Changed module from '{old_mod}' to '{new_mod}'."
        })

    # Update other scalar fields
    for field in [
        'title', 'description', 'steps_to_reproduce', 'expected_result',
        'actual_result', 'environment', 'browser_device', 'sprint',
        'due_date', 'labels'
    ]:
        if field in kwargs:
            setattr(bug, field, kwargs[field])

    bug.save()

    for change in changes:
        BugActivity.objects.create(
            bug=bug,
            actor=actor,
            action=change['action'],
            old_value=change['old'],
            new_value=change['new'],
            message=change['msg']
        )

    if not changes:
        BugActivity.objects.create(
            bug=bug,
            actor=actor,
            action=BugActivity.Action.UPDATED,
            message="Updated bug details and technical notes."
        )

    return bug


@transaction.atomic
def change_bug_status(bug, new_status, actor):
    """
    Transition a bug's workflow status.
    """
    if bug.status == new_status:
        return bug

    old_display = bug.get_status_display()
    bug.status = new_status
    bug.save(update_fields=['status', 'updated_at'])
    new_display = bug.get_status_display()

    BugActivity.objects.create(
        bug=bug,
        actor=actor,
        action=BugActivity.Action.STATUS_CHANGED,
        old_value=old_display,
        new_value=new_display,
        message=f"Status updated from '{old_display}' to '{new_display}'."
    )
    return bug
