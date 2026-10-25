import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimerStatus(models.TextChoices):
    IDLE = 'IDLE', _('Idle')
    RUNNING = 'RUNNING', _('Running')
    PAUSED = 'PAUSED', _('Paused')
    COMPLETED = 'COMPLETED', _('Completed')


class TimeEntryType(models.TextChoices):
    TIMER = 'TIMER', _('Live Timer')
    MANUAL = 'MANUAL', _('Manual Entry')


class TimeEntry(models.Model):
    """
    Authoritative time tracking record.
    Connects elapsed sprint work to workspaces, contributors, and optional 6-digit tasks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='time_entries',
        db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='time_entries',
        db_index=True
    )
    task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='time_entries',
        db_index=True
    )
    description = models.CharField(max_length=255, blank=True, default='')
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_resumed_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    accumulated_seconds = models.PositiveIntegerField(
        default=0,
        help_text=_("Total accumulated active running seconds (excluding paused intervals).")
    )
    duration_seconds = models.PositiveIntegerField(default=0, help_text=_("Total elapsed duration in seconds."))
    status = models.CharField(
        max_length=15,
        choices=TimerStatus.choices,
        default=TimerStatus.COMPLETED,
        db_index=True
    )
    is_running = models.BooleanField(default=False, db_index=True)
    entry_type = models.CharField(
        max_length=10,
        choices=TimeEntryType.choices,
        default=TimeEntryType.TIMER
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['workspace', 'user', '-started_at']),
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['workspace', 'is_running']),
            models.Index(fields=['user', 'is_running']),
        ]

    def save(self, *args, **kwargs):
        if self.is_running:
            if self.status in [TimerStatus.COMPLETED, TimerStatus.IDLE]:
                self.status = TimerStatus.RUNNING
            if not self.last_resumed_at:
                self.last_resumed_at = self.started_at
        super().save(*args, **kwargs)

    def __str__(self):
        task_str = f" (#{self.task.task_code})" if self.task else ""
        return f"{self.user.email} - {self.duration_formatted}{task_str}"

    @property
    def current_duration_seconds(self):
        """
        Returns elapsed seconds, dynamically computing live duration if timer is running.
        Excludes paused intervals.
        """
        if self.status == TimerStatus.RUNNING or (self.is_running and self.status != TimerStatus.PAUSED):
            now = timezone.now()
            resumed_ref = self.last_resumed_at or self.started_at
            active_interval = max(0, int((now - resumed_ref).total_seconds()))
            return self.accumulated_seconds + active_interval
        elif self.status == TimerStatus.PAUSED:
            return self.accumulated_seconds
        return self.duration_seconds

    @property
    def duration_formatted(self):
        """Format seconds into readable string (e.g. 1h 45m or 25m)."""
        secs = self.current_duration_seconds
        hours = secs // 3600
        minutes = (secs % 3600) // 60
        remaining_secs = secs % 60

        if hours > 0:
            if minutes > 0:
                return f"{hours}h {minutes}m"
            return f"{hours}h"
        elif minutes > 0:
            return f"{minutes}m {remaining_secs}s" if remaining_secs > 0 else f"{minutes}m"
        return f"{remaining_secs}s"

    @property
    def hours_decimal(self):
        """Decimal hours representation (e.g. 1.75)."""
        return round(self.current_duration_seconds / 3600.0, 2)

    @property
    def category(self):
        """Extract category from [Category] tag in description or infer from task/title/bug."""
        if self.description:
            import re
            matches = re.findall(r'\[(.*?)\]', self.description)
            for tag in matches:
                tag_clean = tag.strip()
                if tag_clean == 'Bug Fix' or tag_clean.startswith('Bug:'):
                    return 'Bug fixes'
                if tag_clean == 'Task / Development':
                    return 'Development'
                if tag_clean != 'Billable' and tag_clean in [
                    'Development', 'Design', 'API integration', 'Code review', 'Bug fixes', 'Documentation', 'Meeting', 'Research', 'Other'
                ]:
                    return tag_clean
        # Fallback heuristics based on task title, code, or description
        text = f"{self.task.title if self.task else ''} {self.description or ''}".lower()
        if 'bug' in text or 'fix' in text or (self.task and 'bug' in self.task.task_code.lower()) or 'b-' in text:
            return 'Bug fixes'
        if 'research' in text or 'investigat' in text or 'spike' in text or 'explor' in text:
            return 'Research'
        if 'design' in text or 'ui' in text or 'ux' in text or 'style' in text:
            return 'Design'
        if 'api' in text or 'endpoint' in text or 'backend' in text:
            return 'API integration'
        if 'review' in text or 'pr ' in text:
            return 'Code review'
        if 'doc' in text or 'spec' in text:
            return 'Documentation'
        if 'meet' in text or 'sync' in text or 'standup' in text:
            return 'Meeting'
        return 'Development'

    @property
    def clean_description(self):
        """Returns work description without metadata tags [Category], [Billable], or [Bug: ...]."""
        if not self.description:
            return ''
        import re
        cleaned = re.sub(
            r'\[(Billable|Development|Task / Development|Design|API integration|API Integration|Code review|Code Review|Bug fixes|Bug Fix|Documentation|Meeting|Research|Other|Bug:\s*B-\d{6})\]\s*',
            '',
            self.description
        ).strip()
        return cleaned or self.description

    @property
    def linked_bug_code(self):
        """Extracts B-XXXXXX bug code from description if tagged."""
        if not self.description:
            return ''
        import re
        match = re.search(r'\[Bug:\s*(B-\d{6})\]', self.description)
        return match.group(1) if match else ''

    @property
    def linked_bug(self):
        """
        Fetches the associated Bug defect instance if linked_bug_code is present.
        Uses in-memory cache if populated by pre-fetch routines to avoid N+1 queries.
        """
        if hasattr(self, '_cached_bug'):
            return self._cached_bug
        code = self.linked_bug_code
        if code:
            from bugs.models import Bug
            return Bug.objects.filter(workspace=self.workspace, bug_code=code).select_related('linked_task', 'assignee', 'module').first()
        return None

    @property
    def work_item_type(self):
        """Returns the primary work item classification: 'bug', 'task', or 'general'."""
        if self.linked_bug_code:
            return 'bug'
        elif self.task_id:
            return 'task'
        return 'general'

    @property
    def is_billable(self):
        """True if [Billable] tag is present in description."""
        return '[Billable]' in (self.description or '')

    @property
    def entry_source_display(self):
        """Returns readable entry source: Timer vs Manual vs Legacy."""
        if self.entry_type == TimeEntryType.MANUAL:
            return 'Manual'
        elif self.entry_type == TimeEntryType.TIMER:
            return 'Timer'
        return 'Legacy'

    @property
    def project_name(self):
        """Workspace or project name."""
        return self.workspace.name

    @property
    def sprint_name(self):
        """Sprint name if task is assigned to a sprint."""
        if self.task and self.task.sprint_ref:
            return self.task.sprint_ref.name
        return '—'

    @property
    def category_info(self):
        """Visual styling and icon configuration for task category."""
        cat = self.category
        mapping = {
            'Bug fixes': {
                'name': 'Bug Fix',
                'color': 'rose',
                'bg': 'bg-rose-500/10 text-rose-500 border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/30',
                'badge_bg': 'bg-rose-500/20 text-rose-400',
                'dot': 'bg-rose-500',
                'icon': 'bug',
                'hex': '#e11d48',
                'timeline_color': 'bg-rose-600 border-rose-500 text-white'
            },
            'API integration': {
                'name': 'API Integration',
                'color': 'emerald',
                'bg': 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30',
                'badge_bg': 'bg-emerald-500/20 text-emerald-400',
                'dot': 'bg-emerald-500',
                'icon': 'database',
                'hex': '#059669',
                'timeline_color': 'bg-emerald-600 border-emerald-500 text-white'
            },
            'Design': {
                'name': 'Design',
                'color': 'purple',
                'bg': 'bg-purple-500/10 text-purple-400 border-purple-500/20 dark:bg-purple-500/10 dark:text-purple-400 dark:border-purple-500/30',
                'badge_bg': 'bg-purple-500/20 text-purple-400',
                'dot': 'bg-purple-500',
                'icon': 'palette',
                'hex': '#9333ea',
                'timeline_color': 'bg-purple-600 border-purple-500 text-white'
            },
            'Code review': {
                'name': 'Code Review',
                'color': 'amber',
                'bg': 'bg-amber-500/10 text-amber-500 border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/30',
                'badge_bg': 'bg-amber-500/20 text-amber-400',
                'dot': 'bg-amber-500',
                'icon': 'code-review',
                'hex': '#d97706',
                'timeline_color': 'bg-amber-600 border-amber-500 text-white'
            },
            'Documentation': {
                'name': 'Documentation',
                'color': 'cyan',
                'bg': 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 dark:bg-cyan-500/10 dark:text-cyan-400 dark:border-cyan-500/30',
                'badge_bg': 'bg-cyan-500/20 text-cyan-400',
                'dot': 'bg-cyan-500',
                'icon': 'document',
                'hex': '#0891b2',
                'timeline_color': 'bg-cyan-600 border-cyan-500 text-white'
            },
            'Meeting': {
                'name': 'Meeting',
                'color': 'indigo',
                'bg': 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20 dark:bg-indigo-500/10 dark:text-indigo-400 dark:border-indigo-500/30',
                'badge_bg': 'bg-indigo-500/20 text-indigo-400',
                'dot': 'bg-indigo-500',
                'icon': 'users',
                'hex': '#4f46e5',
                'timeline_color': 'bg-indigo-600 border-indigo-500 text-white'
            },
            'Research': {
                'name': 'Research',
                'color': 'teal',
                'bg': 'bg-teal-500/10 text-teal-400 border-teal-500/20 dark:bg-teal-500/10 dark:text-teal-400 dark:border-teal-500/30',
                'badge_bg': 'bg-teal-500/20 text-teal-400',
                'dot': 'bg-teal-500',
                'icon': 'search',
                'hex': '#0d9488',
                'timeline_color': 'bg-teal-600 border-teal-500 text-white'
            },
            'Other': {
                'name': 'Other',
                'color': 'slate',
                'bg': 'bg-slate-500/10 text-slate-400 border-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400 dark:border-slate-500/30',
                'badge_bg': 'bg-slate-500/20 text-slate-400',
                'dot': 'bg-slate-400',
                'icon': 'tag',
                'hex': '#64748b',
                'timeline_color': 'bg-slate-600 border-slate-500 text-white'
            },
            'Development': {
                'name': 'Task / Development',
                'color': 'blue',
                'bg': 'bg-blue-500/10 text-blue-400 border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/30',
                'badge_bg': 'bg-blue-500/20 text-blue-400',
                'dot': 'bg-blue-500',
                'icon': 'code',
                'hex': '#2563eb',
                'timeline_color': 'bg-blue-600 border-blue-500 text-white'
            },
        }
        return mapping.get(cat, mapping['Development'])


    def pause(self):
        """Pause running timer without finalizing. Preserves accumulated duration."""
        if self.status == TimerStatus.RUNNING or self.is_running:
            now = timezone.now()
            resumed_ref = self.last_resumed_at or self.started_at
            active_interval = max(0, int((now - resumed_ref).total_seconds()))
            self.accumulated_seconds += active_interval
            self.duration_seconds = self.accumulated_seconds
            self.paused_at = now
            self.status = TimerStatus.PAUSED
            self.is_running = False
            self.save(update_fields=['accumulated_seconds', 'duration_seconds', 'paused_at', 'status', 'is_running', 'updated_at'])
            return True
        return False

    def resume(self):
        """Resume a paused timer. Begins a new running interval from preserved accumulated duration."""
        if self.status == TimerStatus.PAUSED:
            now = timezone.now()
            self.last_resumed_at = now
            self.paused_at = None
            self.status = TimerStatus.RUNNING
            self.is_running = True
            self.save(update_fields=['last_resumed_at', 'paused_at', 'status', 'is_running', 'updated_at'])
            return True
        return False

    def stop(self):
        """Stop running or paused timer and finalize duration."""
        if self.status in [TimerStatus.RUNNING, TimerStatus.PAUSED] or self.is_running:
            now = timezone.now()
            if self.status == TimerStatus.RUNNING or self.is_running:
                resumed_ref = self.last_resumed_at or self.started_at
                active_interval = max(0, int((now - resumed_ref).total_seconds()))
                self.accumulated_seconds += active_interval
            self.ended_at = now
            self.duration_seconds = max(1, self.accumulated_seconds)
            self.status = TimerStatus.COMPLETED
            self.is_running = False
            self.save(update_fields=['ended_at', 'accumulated_seconds', 'duration_seconds', 'status', 'is_running', 'updated_at'])
            return True
        return False
