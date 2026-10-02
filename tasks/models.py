import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class TaskStatus(models.TextChoices):
    TODO = 'TODO', _('To Do')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    CODE_REVIEW = 'CODE_REVIEW', _('Code Review')
    TESTING = 'TESTING', _('Testing')
    DONE = 'DONE', _('Done')


class TaskPriority(models.TextChoices):
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    URGENT = 'URGENT', _('Urgent')


class SprintStatus(models.TextChoices):
    PLANNING = 'PLANNING', _('Planned')
    ACTIVE = 'ACTIVE', _('Active')
    COMPLETED = 'COMPLETED', _('Completed')
    CANCELLED = 'CANCELLED', _('Cancelled')


class Sprint(models.Model):
    """
    Agile Sprint representing a timeboxed iteration of work.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='sprints'
    )
    name = models.CharField(max_length=100, help_text=_("e.g. Sprint 4 or Q4 Release Sprint"))
    goal = models.TextField(blank=True, default='', help_text=_("Key objective for this sprint"))
    status = models.CharField(
        max_length=20,
        choices=SprintStatus.choices,
        default=SprintStatus.PLANNING,
        db_index=True
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_sprints'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['workspace', '-created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status == SprintStatus.ACTIVE

    @property
    def is_completed(self):
        return self.status == SprintStatus.COMPLETED

    @property
    def is_planning(self):
        return self.status == SprintStatus.PLANNING

    @property
    def is_cancelled(self):
        return self.status == SprintStatus.CANCELLED

    @property
    def status_badge(self):
        badges = {
            SprintStatus.PLANNING: {
                'label': 'Planned',
                'bg': 'bg-amber-500/10 text-amber-600 border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/30',
                'dot': 'bg-amber-500',
                'icon': '🟡',
            },
            SprintStatus.ACTIVE: {
                'label': 'Active',
                'bg': 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30',
                'dot': 'bg-emerald-500',
                'icon': '🟢',
            },
            SprintStatus.COMPLETED: {
                'label': 'Completed',
                'bg': 'bg-blue-500/10 text-blue-600 border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/30',
                'dot': 'bg-blue-500',
                'icon': '🔵',
            },
            SprintStatus.CANCELLED: {
                'label': 'Cancelled',
                'bg': 'bg-rose-500/10 text-rose-600 border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/30',
                'dot': 'bg-rose-500',
                'icon': '🔴',
            },
        }
        return badges.get(self.status, badges[SprintStatus.PLANNING])

    @property
    def task_status_breakdown(self):
        """
        Returns real database breakdown of task counts by status:
        To Do, In Progress, Code Review, Testing, Done
        """
        tasks = self.tasks.all()
        return {
            'todo': tasks.filter(status=TaskStatus.TODO).count(),
            'in_progress': tasks.filter(status=TaskStatus.IN_PROGRESS).count(),
            'code_review': tasks.filter(status=TaskStatus.CODE_REVIEW).count(),
            'testing': tasks.filter(status=TaskStatus.TESTING).count(),
            'done': tasks.filter(status=TaskStatus.DONE).count(),
            'total': tasks.count(),
        }

    @property
    def days_remaining(self):
        if self.end_date:
            from django.utils import timezone
            today = timezone.now().date()
            diff = (self.end_date - today).days
            return max(0, diff)
        return None

    @property
    def total_tasks_count(self):
        return self.tasks.count()

    @property
    def completed_tasks_count(self):
        return self.tasks.filter(status=TaskStatus.DONE).count()

    @property
    def in_progress_tasks_count(self):
        return self.tasks.filter(status__in=[TaskStatus.IN_PROGRESS, TaskStatus.CODE_REVIEW, TaskStatus.TESTING]).count()

    @property
    def todo_tasks_count(self):
        return self.tasks.filter(status=TaskStatus.TODO).count()

    @property
    def progress_percentage(self):
        total = self.total_tasks_count
        if total == 0:
            return 0
        return int(round((self.completed_tasks_count / total) * 100))

    @property
    def total_estimated_hours(self):
        from django.db.models import Sum
        val = self.tasks.aggregate(total=Sum('estimated_hours'))['total']
        return val or 0

    @property
    def completed_estimated_hours(self):
        from django.db.models import Sum
        val = self.tasks.filter(status=TaskStatus.DONE).aggregate(total=Sum('estimated_hours'))['total']
        return val or 0


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        help_text=_("Human-facing 6-digit task identifier, e.g. 619347")
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.TODO,
        db_index=True
    )
    priority = models.CharField(
        max_length=20,
        choices=TaskPriority.choices,
        default=TaskPriority.MEDIUM,
        db_index=True
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_tasks'
    )
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    sprint_ref = models.ForeignKey(
        'tasks.Sprint',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks'
    )
    sprint = models.CharField(max_length=50, blank=True, default='Sprint 01')
    tags = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['workspace', 'priority']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['workspace', 'created_at']),
            models.Index(fields=['task_code']),
        ]

    def __str__(self):
        return f"T-{self.task_code} {self.title}"

    @property
    def display_code(self):
        return f"T-{self.task_code}"

    @property
    def is_overdue(self):
        if self.due_date and self.status != TaskStatus.DONE:
            from django.utils import timezone
            return self.due_date < timezone.now().date()
        return False

    @property
    def subtask_count(self):
        return self.subtasks.count()

    @property
    def completed_subtask_count(self):
        return self.subtasks.filter(is_completed=True).count()

    @property
    def subtask_progress_percentage(self):
        total = self.subtask_count
        if total == 0:
            return 0
        return int(round((self.completed_subtask_count / total) * 100))

    @property
    def total_logged_seconds(self):
        from django.db.models import Sum
        val = self.time_entries.aggregate(total=Sum('duration_seconds'))['total']
        return val or 0

    @property
    def total_logged_hours_display(self):
        total_seconds = self.total_logged_seconds
        hours = total_seconds / 3600
        if hours == 0:
            return "0 hrs"
        return f"{hours:.1f} hrs"

    def get_summary_data(self):
        """
        Returns structured task summary dictionary directly from Django models.
        """
        connected_bugs = []
        for bug in self.bugs.select_related('assignee', 'module').all():
            connected_bugs.append({
                'id': str(bug.id),
                'bug_code': bug.bug_code,
                'title': bug.title,
                'severity': bug.severity,
                'severity_display': bug.get_severity_display(),
                'status': bug.status,
                'status_display': bug.get_status_display(),
                'assignee': bug.assignee,
                'module_name': bug.module.name if bug.module else None,
            })

        labels_list = [t.strip() for t in self.tags.split(',') if t.strip()] if self.tags else []

        return {
            'task_code': self.task_code,
            'display_code': self.display_code,
            'title': self.title,
            'description': self.description,
            'priority': self.priority,
            'priority_display': self.get_priority_display(),
            'status': self.status,
            'status_display': self.get_status_display(),
            'requester': self.reporter,
            'assignee': self.assignee,
            'due_date': self.due_date,
            'labels': labels_list,
            'connected_bugs': connected_bugs,
            'has_bugs': len(connected_bugs) > 0,
        }


class Subtask(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='subtasks'
    )
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False, db_index=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['task', 'order']),
            models.Index(fields=['task', 'is_completed']),
        ]

    def __str__(self):
        status = "[x]" if self.is_completed else "[ ]"
        return f"{status} {self.title} (#{self.task.task_code})"


class TaskActivity(models.Model):
    class Action(models.TextChoices):
        CREATED = 'CREATED', _('Created')
        STATUS_CHANGED = 'STATUS_CHANGED', _('Status Changed')
        ASSIGNED = 'ASSIGNED', _('Assigned')
        PRIORITY_CHANGED = 'PRIORITY_CHANGED', _('Priority Changed')
        UPDATED = 'UPDATED', _('Updated')
        COMMENTED = 'COMMENTED', _('Commented')
        BUG_LINKED = 'BUG_LINKED', _('Bug Attached')
        BUG_UNLINKED = 'BUG_UNLINKED', _('Bug Detached')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_activities'
    )
    action = models.CharField(
        max_length=50,
        choices=Action.choices,
        default=Action.UPDATED
    )
    old_value = models.CharField(max_length=255, blank=True, default='')
    new_value = models.CharField(max_length=255, blank=True, default='')
    message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Task activities"

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else "System"
        return f"{actor_name} {self.get_action_display()} on #{self.task.task_code}"


class TaskComment(models.Model):
    class CommentType(models.TextChoices):
        USER = 'USER', _('User Comment')
        SYSTEM = 'SYSTEM', _('System Event')

    class SystemEventType(models.TextChoices):
        TASK_CREATED = 'TASK_CREATED', _('Task Created')
        BUG_ATTACHED = 'BUG_ATTACHED', _('Bug Attached')
        BUG_DETACHED = 'BUG_DETACHED', _('Bug Detached')
        CODE_REVIEW_REQUESTED = 'CODE_REVIEW_REQUESTED', _('Code Review Requested')
        CODE_REVIEW_STATUS_CHANGED = 'CODE_REVIEW_STATUS_CHANGED', _('Code Review Status Changed')
        REVIEWER_ASSIGNED = 'REVIEWER_ASSIGNED', _('Reviewer Assigned')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_comments'
    )
    comment_type = models.CharField(
        max_length=20,
        choices=CommentType.choices,
        default=CommentType.USER,
        db_index=True
    )
    system_event_type = models.CharField(
        max_length=50,
        choices=SystemEventType.choices,
        blank=True,
        default='',
        db_index=True
    )
    content = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    code_review = models.ForeignKey(
        'tasks.CodeReviewRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comments'
    )
    bug = models.ForeignKey(
        'bugs.Bug',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_comments'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        if self.is_system:
            return f"System Event ({self.get_system_event_type_display()}) on #{self.task.task_code}"
        author_name = self.author.full_name if self.author else "Anonymous"
        return f"Comment by {author_name} on #{self.task.task_code}"

    @property
    def is_system(self):
        return self.comment_type == self.CommentType.SYSTEM


class TaskAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.ForeignKey(
        'files.StoredFile',
        on_delete=models.CASCADE,
        related_name='task_attachments'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Attachment {self.file.name} on #{self.task.task_code}"


class CodeReviewStatus(models.TextChoices):
    REQUESTED = 'REQUESTED', _('Requested')
    IN_REVIEW = 'IN_REVIEW', _('In Review')
    CHANGES_REQUESTED = 'CHANGES_REQUESTED', _('Changes Requested')
    APPROVED = 'APPROVED', _('Approved')
    MERGED = 'MERGED', _('Merged')
    CLOSED = 'CLOSED', _('Closed')


class CodeReviewRequest(models.Model):
    """
    Code Review Request linked to a Task and an authoritative GitHub Pull Request.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review_code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_("Code review reference identifier, e.g. CR-619347")
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='code_reviews'
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='code_reviews_requested'
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='code_reviews_assigned'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    github_pr_url = models.URLField(max_length=500)
    status = models.CharField(
        max_length=30,
        choices=CodeReviewStatus.choices,
        default=CodeReviewStatus.REQUESTED,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', 'status']),
            models.Index(fields=['task', '-created_at']),
            models.Index(fields=['review_code']),
        ]

    def __str__(self):
        return f"{self.review_code} - {self.title} (#{self.task.task_code})"

    @property
    def display_code(self):
        return self.review_code

    @property
    def is_open(self):
        return self.status not in [CodeReviewStatus.CLOSED, CodeReviewStatus.MERGED]

