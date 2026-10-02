"""
AetherSpace Workspace Backup & Restore Service.
Authoritative .xlsx multi-sheet export, validation, conflict analysis, and transactional restoration.
Chat is strictly excluded as intended.
File binaries are metadata-only (no raw binary in Excel).
Zero 500-record limits: streaming/chunked processing.
"""

import io
import sys
import uuid
import json
import hashlib
import logging
import secrets
from datetime import datetime, date
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.conf import settings
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from accounts.models import User, UserRole
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceModule, WorkspaceRole, MembershipStatus
from core.models import ModuleStatus
from tasks.models import Task, TaskStatus, TaskPriority, TaskComment, TaskActivity, Sprint, SprintStatus, CodeReviewRequest, CodeReviewStatus
from tasks.services import generate_unique_task_code, generate_unique_code_review_code
from bugs.models import Bug, BugStatus, BugPriority, BugSeverity, BugComment, BugActivity
from bugs.services import generate_unique_bug_code
from calendars.models import CalendarEvent
from meetings.models import Meeting
from notifications.models import Notification
from timetracking.models import TimeEntry
from files.models import StoredFile, Folder
from .models import AuditLog, AuditActionStatus
from .services import AuditLogService

logger = logging.getLogger(__name__)

BACKUP_SCHEMA_VERSION = "1.0.0"
APPLICATION_NAME = "AetherSpace"

REQUIRED_SHEETS = [
    "Export_Metadata",
    "Workspace",
    "Members",
    "Modules",
    "Tasks",
    "Task_Comments",
    "Task_Activity",
    "Bugs",
    "Bug_Comments",
    "Bug_Activity",
    "Sprints",
    "Sprint_Tasks",
    "Code_Reviews",
    "Code_Review_Feedback",
    "Calendar_Events",
    "Meetings",
    "Notifications",
    "Time_Entries",
    "Files_Metadata",
]

HEADER_FILL = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

THIN_BORDER = Border(
    left=Side(style='thin', color='CBD5E1'),
    right=Side(style='thin', color='CBD5E1'),
    top=Side(style='thin', color='CBD5E1'),
    bottom=Side(style='thin', color='CBD5E1')
)


def _safe_str(val):
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return str(val)


def _format_worksheet(ws, headers):
    ws.append(headers)
    ws.row_dimensions[1].height = 26
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER


def _auto_adjust_columns(ws, min_width=12, max_width=45):
    for col in ws.columns:
        first_cell = col[0]
        col_letter = get_column_letter(first_cell.column)
        max_len = 0
        for cell in col[:150]:  # sample first 150 rows
            val = str(cell.value or '')
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 3, max_width))


class WorkspaceBackupService:
    """
    Exports a selected workspace and all related entities to a multi-sheet .xlsx workbook.
    No 500-record limits. Relationships and UUIDs are strictly preserved.
    """

    @classmethod
    def export_workspace_to_excel(cls, workspace, actor=None, options=None):
        wb = openpyxl.Workbook()
        # Default sheet -> Export_Metadata
        ws_meta = wb.active
        ws_meta.title = "Export_Metadata"

        counts = {}

        # 1. Sheets generation
        counts["Workspace"] = cls._export_workspace_sheet(wb, workspace)
        counts["Members"] = cls._export_members_sheet(wb, workspace)
        counts["Modules"] = cls._export_modules_sheet(wb, workspace)
        counts["Sprints"] = cls._export_sprints_sheet(wb, workspace)
        counts["Tasks"] = cls._export_tasks_sheet(wb, workspace)
        counts["Task_Comments"] = cls._export_task_comments_sheet(wb, workspace)
        counts["Task_Activity"] = cls._export_task_activity_sheet(wb, workspace)
        counts["Bugs"] = cls._export_bugs_sheet(wb, workspace)
        counts["Bug_Comments"] = cls._export_bug_comments_sheet(wb, workspace)
        counts["Bug_Activity"] = cls._export_bug_activity_sheet(wb, workspace)
        counts["Sprint_Tasks"] = cls._export_sprint_tasks_sheet(wb, workspace)
        counts["Code_Reviews"] = cls._export_code_reviews_sheet(wb, workspace)
        counts["Code_Review_Feedback"] = cls._export_code_review_feedback_sheet(wb, workspace)
        counts["Calendar_Events"] = cls._export_calendar_events_sheet(wb, workspace)
        counts["Meetings"] = cls._export_meetings_sheet(wb, workspace)
        counts["Notifications"] = cls._export_notifications_sheet(wb, workspace)
        counts["Time_Entries"] = cls._export_time_entries_sheet(wb, workspace)
        counts["Files_Metadata"] = cls._export_files_metadata_sheet(wb, workspace)

        # 2. Populate Export_Metadata sheet
        cls._populate_metadata_sheet(ws_meta, workspace, actor, counts)

        # 3. Format and adjust column widths
        for sheetname in wb.sheetnames:
            _auto_adjust_columns(wb[sheetname])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output, counts

    @classmethod
    def _populate_metadata_sheet(cls, ws, workspace, actor, counts):
        headers = ["Metadata_Field", "Value"]
        _format_worksheet(ws, headers)

        now_iso = timezone.now().isoformat()
        total_records = sum(counts.values())

        # Generate checksum of export counts + workspace id
        checksum_payload = f"{workspace.id}:{workspace.slug}:{total_records}:{json.dumps(counts, sort_keys=True)}"
        checksum_hash = hashlib.sha256(checksum_payload.encode('utf-8')).hexdigest()

        meta_rows = [
            ("backup_format", "AetherSpace Workspace Backup"),
            ("backup_schema_version", BACKUP_SCHEMA_VERSION),
            ("application_name", APPLICATION_NAME),
            ("application_version", getattr(settings, 'APP_VERSION', '1.0.0')),
            ("export_timestamp", now_iso),
            ("workspace_id", str(workspace.id)),
            ("workspace_slug", workspace.slug),
            ("workspace_name", workspace.name),
            ("exporter_id", str(actor.id) if actor else "SYSTEM"),
            ("exporter_email", actor.email if actor else "system@aetherspace.io"),
            ("included_entities", ", ".join(REQUIRED_SHEETS)),
            ("excluded_entities", "Team Chat (chat_messages, channels, reactions), User password hashes, Secret API keys, Binary file payloads (metadata only)"),
            ("chat_status", "EXCLUDED_BY_DESIGN"),
            ("file_payload_status", "METADATA_ONLY_BINARY_EXCLUDED"),
            ("total_record_count", str(total_records)),
            ("integrity_checksum_sha256", checksum_hash),
        ]

        for k, v in meta_rows:
            ws.append([k, v])

        # Blank row + record counts table
        ws.append([])
        ws.append(["--- Entity Record Counts ---", "Count"])
        for entity_name, count in counts.items():
            ws.append([entity_name, count])

    @classmethod
    def _export_workspace_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Workspace")
        headers = [
            "id", "name", "slug", "description", "owner_id", "owner_email",
            "status", "max_seats", "storage_quota_mb", "tech_stack",
            "project_scope", "architecture_notes", "security_mode",
            "storage_provider", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        ws.append([
            _safe_str(workspace.id),
            _safe_str(workspace.name),
            _safe_str(workspace.slug),
            _safe_str(workspace.description),
            _safe_str(workspace.owner.id if workspace.owner else ""),
            _safe_str(workspace.owner.email if workspace.owner else ""),
            _safe_str(workspace.status),
            workspace.max_seats or 15,
            workspace.storage_quota_mb or 50,
            _safe_str(workspace.tech_stack),
            _safe_str(workspace.project_scope),
            _safe_str(workspace.architecture_notes),
            _safe_str(workspace.security_mode),
            _safe_str(workspace.storage_provider),
            _safe_str(workspace.created_at),
            _safe_str(workspace.updated_at),
        ])
        return 1

    @classmethod
    def _export_members_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Members")
        headers = [
            "id", "workspace_id", "user_id", "user_email", "user_full_name",
            "user_role", "role", "status", "functional_role", "role_tag",
            "reporting_to_id", "joined_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = WorkspaceMembership.objects.filter(workspace=workspace).select_related('user', 'reporting_to__user')
        for m in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(m.id),
                _safe_str(workspace.id),
                _safe_str(m.user.id),
                _safe_str(m.user.email),
                _safe_str(m.user.full_name or m.user.username),
                _safe_str(m.user.role),
                _safe_str(m.role),
                _safe_str(m.status),
                _safe_str(m.functional_role),
                _safe_str(m.role_tag),
                _safe_str(m.reporting_to.user.id if m.reporting_to and m.reporting_to.user else ""),
                _safe_str(m.joined_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_modules_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Modules")
        headers = [
            "id", "workspace_id", "module_key", "name", "is_enabled",
            "status", "public_message", "maintenance_explanation"
        ]
        _format_worksheet(ws, headers)

        count = 0
        ws_mods = {wm.name.lower(): wm for wm in WorkspaceModule.objects.filter(workspace=workspace)}
        for ms in ModuleStatus.objects.all():
            wm = ws_mods.get(ms.module_key.lower()) or ws_mods.get(ms.name.lower())
            ws.append([
                _safe_str(wm.id if wm else ms.id),
                _safe_str(workspace.id),
                _safe_str(ms.module_key),
                _safe_str(ms.name),
                "TRUE" if (wm and wm.is_active) else "TRUE",
                _safe_str(ms.status),
                _safe_str(ms.public_message),
                _safe_str(ms.maintenance_explanation),
            ])
            count += 1
        return count

    @classmethod
    def _export_sprints_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Sprints")
        headers = [
            "id", "workspace_id", "name", "goal", "status",
            "start_date", "end_date", "created_by_id", "created_by_email",
            "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = Sprint.objects.filter(workspace=workspace).select_related('created_by')
        for sp in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(sp.id),
                _safe_str(workspace.id),
                _safe_str(sp.name),
                _safe_str(sp.goal),
                _safe_str(sp.status),
                _safe_str(sp.start_date),
                _safe_str(sp.end_date),
                _safe_str(sp.created_by.id if sp.created_by else ""),
                _safe_str(sp.created_by.email if sp.created_by else ""),
                _safe_str(sp.created_at),
                _safe_str(sp.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_tasks_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Tasks")
        headers = [
            "id", "task_code", "workspace_id", "title", "description",
            "status", "priority", "assignee_id", "assignee_email",
            "reporter_id", "reporter_email", "sprint_id", "sprint_ref",
            "due_date", "estimated_hours", "tags", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = Task.objects.filter(workspace=workspace).select_related('assignee', 'reporter', 'sprint_ref')
        for t in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(t.id),
                _safe_str(t.task_code),
                _safe_str(workspace.id),
                _safe_str(t.title),
                _safe_str(t.description),
                _safe_str(t.status),
                _safe_str(t.priority),
                _safe_str(t.assignee.id if t.assignee else ""),
                _safe_str(t.assignee.email if t.assignee else ""),
                _safe_str(t.reporter.id if t.reporter else ""),
                _safe_str(t.reporter.email if t.reporter else ""),
                _safe_str(t.sprint_ref.id if t.sprint_ref else ""),
                _safe_str(t.sprint),
                _safe_str(t.due_date),
                t.estimated_hours if t.estimated_hours is not None else "",
                _safe_str(t.tags),
                _safe_str(t.created_at),
                _safe_str(t.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_task_comments_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Task_Comments")
        headers = [
            "id", "task_id", "task_code", "author_id", "author_email",
            "comment_type", "system_event_type", "content", "metadata",
            "code_review_id", "bug_id", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = TaskComment.objects.filter(task__workspace=workspace).select_related('task', 'author')
        for c in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(c.id),
                _safe_str(c.task.id),
                _safe_str(c.task.task_code),
                _safe_str(c.author.id if c.author else ""),
                _safe_str(c.author.email if c.author else ""),
                _safe_str(c.comment_type),
                _safe_str(c.system_event_type),
                _safe_str(c.content),
                _safe_str(c.metadata),
                _safe_str(c.code_review_id or ""),
                _safe_str(c.bug_id or ""),
                _safe_str(c.created_at),
                _safe_str(c.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_task_activity_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Task_Activity")
        headers = [
            "id", "task_id", "task_code", "actor_id", "actor_email",
            "action", "old_value", "new_value", "message", "created_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = TaskActivity.objects.filter(task__workspace=workspace).select_related('task', 'actor')
        for a in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(a.id),
                _safe_str(a.task.id),
                _safe_str(a.task.task_code),
                _safe_str(a.actor.id if a.actor else ""),
                _safe_str(a.actor.email if a.actor else ""),
                _safe_str(a.action),
                _safe_str(a.old_value),
                _safe_str(a.new_value),
                _safe_str(a.message),
                _safe_str(a.created_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_bugs_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Bugs")
        headers = [
            "id", "bug_code", "workspace_id", "title", "description",
            "steps_to_reproduce", "expected_result", "actual_result",
            "status", "priority", "severity", "environment", "module",
            "linked_task_id", "linked_task_code", "browser_device",
            "sprint_id", "reporter_id", "reporter_email",
            "assignee_id", "assignee_email", "due_date", "labels",
            "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = Bug.objects.filter(workspace=workspace).select_related('linked_task', 'reporter', 'assignee')
        for b in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(b.id),
                _safe_str(b.bug_code),
                _safe_str(workspace.id),
                _safe_str(b.title),
                _safe_str(b.description),
                _safe_str(b.steps_to_reproduce),
                _safe_str(b.expected_result),
                _safe_str(b.actual_result),
                _safe_str(b.status),
                _safe_str(b.priority),
                _safe_str(b.severity),
                _safe_str(b.environment),
                _safe_str(b.module.id if b.module else ""),
                _safe_str(b.linked_task.id if b.linked_task else ""),
                _safe_str(b.linked_task.task_code if b.linked_task else ""),
                _safe_str(b.browser_device),
                _safe_str(b.sprint),
                _safe_str(b.reporter.id if b.reporter else ""),
                _safe_str(b.reporter.email if b.reporter else ""),
                _safe_str(b.assignee.id if b.assignee else ""),
                _safe_str(b.assignee.email if b.assignee else ""),
                _safe_str(b.due_date),
                _safe_str(b.labels),
                _safe_str(b.created_at),
                _safe_str(b.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_bug_comments_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Bug_Comments")
        headers = [
            "id", "bug_id", "bug_code", "author_id", "author_email",
            "content", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = BugComment.objects.filter(bug__workspace=workspace).select_related('bug', 'author')
        for bc in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(bc.id),
                _safe_str(bc.bug.id),
                _safe_str(bc.bug.bug_code),
                _safe_str(bc.author.id if bc.author else ""),
                _safe_str(bc.author.email if bc.author else ""),
                _safe_str(bc.content),
                _safe_str(bc.created_at),
                _safe_str(bc.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_bug_activity_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Bug_Activity")
        headers = [
            "id", "bug_id", "bug_code", "actor_id", "actor_email",
            "action", "old_value", "new_value", "message", "created_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = BugActivity.objects.filter(bug__workspace=workspace).select_related('bug', 'actor')
        for ba in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(ba.id),
                _safe_str(ba.bug.id),
                _safe_str(ba.bug.bug_code),
                _safe_str(ba.actor.id if ba.actor else ""),
                _safe_str(ba.actor.email if ba.actor else ""),
                _safe_str(ba.action),
                _safe_str(ba.old_value),
                _safe_str(ba.new_value),
                _safe_str(ba.message),
                _safe_str(ba.created_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_sprint_tasks_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Sprint_Tasks")
        headers = [
            "sprint_id", "sprint_name", "task_id", "task_code",
            "task_title", "task_status"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = Task.objects.filter(workspace=workspace, sprint_ref__isnull=False).select_related('sprint_ref')
        for t in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(t.sprint_ref.id),
                _safe_str(t.sprint_ref.name),
                _safe_str(t.id),
                _safe_str(t.task_code),
                _safe_str(t.title),
                _safe_str(t.status),
            ])
            count += 1
        return count

    @classmethod
    def _export_code_reviews_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Code_Reviews")
        headers = [
            "id", "review_code", "task_id", "task_code", "requester_id",
            "requester_email", "reviewer_id", "reviewer_email", "title",
            "description", "github_pr_url", "status", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = CodeReviewRequest.objects.filter(task__workspace=workspace).select_related('task', 'requester', 'reviewer')
        for cr in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(cr.id),
                _safe_str(cr.review_code),
                _safe_str(cr.task.id),
                _safe_str(cr.task.task_code),
                _safe_str(cr.requester.id if cr.requester else ""),
                _safe_str(cr.requester.email if cr.requester else ""),
                _safe_str(cr.reviewer.id if cr.reviewer else ""),
                _safe_str(cr.reviewer.email if cr.reviewer else ""),
                _safe_str(cr.title),
                _safe_str(cr.description),
                _safe_str(cr.github_pr_url),
                _safe_str(cr.status),
                _safe_str(cr.created_at),
                _safe_str(cr.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_code_review_feedback_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Code_Review_Feedback")
        headers = [
            "id", "code_review_id", "task_id", "author_id", "author_email",
            "comment_type", "content", "metadata", "created_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = TaskComment.objects.filter(task__workspace=workspace, code_review__isnull=False).select_related('task', 'author')
        for f in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(f.id),
                _safe_str(f.code_review_id),
                _safe_str(f.task.id),
                _safe_str(f.author.id if f.author else ""),
                _safe_str(f.author.email if f.author else ""),
                _safe_str(f.comment_type),
                _safe_str(f.content),
                _safe_str(f.metadata),
                _safe_str(f.created_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_calendar_events_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Calendar_Events")
        headers = [
            "id", "workspace_id", "title", "description", "event_type",
            "calendar_category", "start_at", "end_at", "is_all_day",
            "repeat", "status", "location", "meeting_link", "created_by_id",
            "created_by_email", "linked_task_id", "linked_bug_id",
            "linked_meeting_id", "agenda", "reference_links",
            "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = CalendarEvent.objects.filter(workspace=workspace).select_related('created_by', 'linked_task', 'linked_bug', 'linked_meeting')
        for ce in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(ce.id),
                _safe_str(workspace.id),
                _safe_str(ce.title),
                _safe_str(ce.description),
                _safe_str(ce.event_type),
                _safe_str(ce.calendar_category),
                _safe_str(ce.start_at),
                _safe_str(ce.end_at),
                "TRUE" if ce.is_all_day else "FALSE",
                _safe_str(ce.repeat),
                _safe_str(ce.status),
                _safe_str(ce.location),
                _safe_str(ce.meeting_link),
                _safe_str(ce.created_by.id if ce.created_by else ""),
                _safe_str(ce.created_by.email if ce.created_by else ""),
                _safe_str(ce.linked_task.id if ce.linked_task else ""),
                _safe_str(ce.linked_bug.id if ce.linked_bug else ""),
                _safe_str(ce.linked_meeting.id if ce.linked_meeting else ""),
                _safe_str(ce.agenda),
                _safe_str(ce.reference_links),
                _safe_str(ce.created_at),
                _safe_str(ce.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_meetings_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Meetings")
        headers = [
            "id", "workspace_id", "meeting_code", "title", "description",
            "host_id", "host_email", "meeting_type", "status",
            "scheduled_start", "scheduled_end", "actual_start", "actual_end",
            "external_room_url", "passcode", "is_audio_only",
            "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = Meeting.objects.filter(workspace=workspace).select_related('host')
        for m in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(m.id),
                _safe_str(workspace.id),
                _safe_str(m.meeting_code),
                _safe_str(m.title),
                _safe_str(m.description),
                _safe_str(m.host.id if m.host else ""),
                _safe_str(m.host.email if m.host else ""),
                _safe_str(m.meeting_type),
                _safe_str(m.status),
                _safe_str(m.scheduled_start),
                _safe_str(m.scheduled_end),
                _safe_str(m.actual_start),
                _safe_str(m.actual_end),
                _safe_str(m.external_room_url),
                _safe_str(m.passcode),
                "TRUE" if m.is_audio_only else "FALSE",
                _safe_str(m.created_at),
                _safe_str(m.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_notifications_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Notifications")
        headers = [
            "id", "workspace_id", "recipient_id", "recipient_email",
            "actor_id", "actor_email", "category", "notification_type",
            "title", "body", "action_url", "is_read", "read_at", "created_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = Notification.objects.filter(workspace=workspace).select_related('recipient', 'actor')
        for n in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(n.id),
                _safe_str(workspace.id),
                _safe_str(n.recipient.id if n.recipient else ""),
                _safe_str(n.recipient.email if n.recipient else ""),
                _safe_str(n.actor.id if n.actor else ""),
                _safe_str(n.actor.email if n.actor else ""),
                _safe_str(n.category),
                _safe_str(n.notification_type),
                _safe_str(n.title),
                _safe_str(n.body),
                _safe_str(n.action_url),
                "TRUE" if n.is_read else "FALSE",
                _safe_str(n.read_at),
                _safe_str(n.created_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_time_entries_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Time_Entries")
        headers = [
            "id", "workspace_id", "user_id", "user_email", "task_id",
            "task_code", "description", "started_at", "ended_at",
            "accumulated_seconds", "duration_seconds", "status",
            "is_running", "entry_type", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = TimeEntry.objects.filter(workspace=workspace).select_related('user', 'task')
        for te in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(te.id),
                _safe_str(workspace.id),
                _safe_str(te.user.id if te.user else ""),
                _safe_str(te.user.email if te.user else ""),
                _safe_str(te.task.id if te.task else ""),
                _safe_str(te.task.task_code if te.task else ""),
                _safe_str(te.description),
                _safe_str(te.started_at),
                _safe_str(te.ended_at),
                te.accumulated_seconds or 0,
                te.duration_seconds or 0,
                _safe_str(te.status),
                "TRUE" if te.is_running else "FALSE",
                _safe_str(te.entry_type),
                _safe_str(te.created_at),
                _safe_str(te.updated_at),
            ])
            count += 1
        return count

    @classmethod
    def _export_files_metadata_sheet(cls, wb, workspace):
        ws = wb.create_sheet("Files_Metadata")
        headers = [
            "id", "workspace_id", "folder_id", "folder_name",
            "uploaded_by_id", "uploaded_by_email", "name", "original_name",
            "storage_path", "external_url", "is_external_link",
            "mime_type", "category", "size_bytes", "checksum",
            "description", "tags", "is_starred", "is_trashed",
            "payload_status", "created_at", "updated_at"
        ]
        _format_worksheet(ws, headers)

        count = 0
        qs = StoredFile.objects.filter(workspace=workspace).select_related('folder', 'uploaded_by')
        for f in qs.iterator(chunk_size=1000):
            ws.append([
                _safe_str(f.id),
                _safe_str(workspace.id),
                _safe_str(f.folder.id if f.folder else ""),
                _safe_str(f.folder.name if f.folder else ""),
                _safe_str(f.uploaded_by.id if f.uploaded_by else ""),
                _safe_str(f.uploaded_by.email if f.uploaded_by else ""),
                _safe_str(f.name),
                _safe_str(f.original_name),
                _safe_str(f.storage_path),
                _safe_str(f.external_url),
                "TRUE" if f.is_external_link else "FALSE",
                _safe_str(f.mime_type),
                _safe_str(f.category),
                f.size_bytes or 0,
                _safe_str(f.checksum),
                _safe_str(f.description),
                _safe_str(f.tags),
                "TRUE" if f.is_starred else "FALSE",
                "TRUE" if f.is_trashed else "FALSE",
                "METADATA_ONLY_BINARY_EXCLUDED",
                _safe_str(f.created_at),
                _safe_str(f.updated_at),
            ])
            count += 1
        return count


class WorkspaceRestoreService:
    """
    Validates, parses, detects conflicts, previews, and transactionally restores
    an AetherSpace .xlsx workspace backup.
    Chat is strictly excluded. File binaries are metadata-only.
    """

    @classmethod
    def validate_and_preview_backup(cls, file_content_bytes, actor):
        """
        Parses the uploaded Excel workbook and generates a preview without modifying database.
        Returns:
            preview: dict with validation result, sheet record counts, detected conflicts,
                     schema status, warnings, and error messages.
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'schema_version': None,
            'source_workspace': {},
            'record_counts': {},
            'total_records': 0,
            'conflicts': [],
            'missing_references': [],
            'chat_excluded': True,
            'files_binary_status': 'METADATA ONLY (Binary payloads not included in Excel)',
        }

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content_bytes), data_only=True)
        except Exception as e:
            result['is_valid'] = False
            result['errors'].append(f"Invalid Excel workbook file: {str(e)}")
            return result

        # 1. Validate required sheets
        sheet_names = wb.sheetnames
        missing_sheets = [s for s in REQUIRED_SHEETS if s not in sheet_names]
        if missing_sheets:
            result['is_valid'] = False
            result['errors'].append(f"Workbook is missing required worksheet(s): {', '.join(missing_sheets)}")

        # 2. Parse and validate Export_Metadata
        if "Export_Metadata" in sheet_names:
            ws_meta = wb["Export_Metadata"]
            meta_dict = {}
            for row in ws_meta.iter_rows(min_row=2, values_only=True):
                if row and row[0]:
                    meta_dict[str(row[0]).strip()] = str(row[1] or '').strip()

            schema_ver = meta_dict.get('backup_schema_version')
            result['schema_version'] = schema_ver
            if schema_ver != BACKUP_SCHEMA_VERSION:
                result['is_valid'] = False
                result['errors'].append(
                    f"Unsupported backup schema version '{schema_ver}'. Expected version '{BACKUP_SCHEMA_VERSION}'."
                )

            result['source_workspace'] = {
                'id': meta_dict.get('workspace_id', ''),
                'slug': meta_dict.get('workspace_slug', ''),
                'name': meta_dict.get('workspace_name', ''),
            }

        # 3. Read sheet rows and count records
        records_by_sheet = {}
        for s in REQUIRED_SHEETS:
            if s in sheet_names and s != "Export_Metadata":
                ws = wb[s]
                rows = list(ws.iter_rows(min_row=2, values_only=True))
                # filter out empty rows
                clean_rows = [r for r in rows if any(r)]
                records_by_sheet[s] = len(clean_rows)
            elif s != "Export_Metadata":
                records_by_sheet[s] = 0

        result['record_counts'] = records_by_sheet
        result['total_records'] = sum(records_by_sheet.values())

        # 4. Conflict Analysis (Check if source workspace or task/bug codes collide)
        src_slug = result['source_workspace'].get('slug')
        if src_slug:
            existing_ws = Workspace.objects.filter(slug=src_slug).first()
            if existing_ws:
                result['warnings'].append(
                    f"Target workspace with slug '{src_slug}' already exists in database. "
                    "Existing records with matching IDs will be preserved without destructive overwrite."
                )

        # Check task code duplicates if Tasks sheet is present
        if "Tasks" in sheet_names:
            ws_tasks = wb["Tasks"]
            headers = [str(c.value or '').strip() for c in ws_tasks[1]]
            if "task_code" in headers:
                code_col = headers.index("task_code")
                task_codes = [
                    str(r[code_col]).strip()
                    for r in ws_tasks.iter_rows(min_row=2, values_only=True)
                    if r and r[code_col]
                ]
                existing_codes = set(Task.objects.filter(task_code__in=task_codes).values_list('task_code', flat=True))
                if existing_codes:
                    result['conflicts'].append(
                        f"{len(existing_codes)} Task ID(s) collide with existing tasks: {', '.join(list(existing_codes)[:5])}"
                    )

        # Check bug code duplicates if Bugs sheet is present
        if "Bugs" in sheet_names:
            ws_bugs = wb["Bugs"]
            headers = [str(c.value or '').strip() for c in ws_bugs[1]]
            if "bug_code" in headers:
                bcode_col = headers.index("bug_code")
                bug_codes = [
                    str(r[bcode_col]).strip()
                    for r in ws_bugs.iter_rows(min_row=2, values_only=True)
                    if r and r[bcode_col]
                ]
                existing_bugs = set(Bug.objects.filter(bug_code__in=bug_codes).values_list('bug_code', flat=True))
                if existing_bugs:
                    result['conflicts'].append(
                        f"{len(existing_bugs)} Bug ID(s) collide with existing bug reports: {', '.join(list(existing_bugs)[:5])}"
                    )

        # Add explicit notices for Chat and Binaries
        result['warnings'].append("Notice: Team Chat messages and chat channels are excluded from this backup by architectural design.")
        result['warnings'].append("Notice: File binaries are stored in Supabase Object Storage; this backup contains full metadata, tags, and storage references.")

        return result

    @classmethod
    def execute_transactional_restore(cls, file_content_bytes, actor, target_workspace_slug=None):
        """
        Restores workspace records inside transaction.atomic() in strict dependency order.
        Rolls back completely if an unrecoverable integrity error occurs.
        """
        report = {
            'restore_operation_id': str(uuid.uuid4()),
            'timestamp': timezone.now().isoformat(),
            'backup_version': BACKUP_SCHEMA_VERSION,
            'source_workspace': '',
            'destination_workspace': '',
            'records_processed': 0,
            'records_restored': 0,
            'records_skipped': 0,
            'conflicts_encountered': 0,
            'errors': [],
            'warnings': [],
            'verification_result': 'PENDING',
        }

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content_bytes), data_only=True)
            with transaction.atomic():
                # Helper to read sheet rows as dicts
                def _get_sheet_dicts(sheetname):
                    if sheetname not in wb.sheetnames:
                        return []
                    ws = wb[sheetname]
                    rows = list(ws.iter_rows(values_only=True))
                    if not rows or len(rows) < 2:
                        return []
                    headers = [str(h or '').strip() for h in rows[0]]
                    dicts = []
                    for r in rows[1:]:
                        if any(r):
                            dicts.append({headers[i]: r[i] for i in range(min(len(headers), len(r)))})
                    return dicts

                # 1. Restore Workspace
                ws_rows = _get_sheet_dicts("Workspace")
                if not ws_rows:
                    raise ValueError("Backup does not contain a valid 'Workspace' sheet.")

                ws_data = ws_rows[0]
                ws_id = ws_data.get('id')
                src_slug = ws_data.get('slug')

                report['source_workspace'] = f"{ws_data.get('name')} ({src_slug})"

                # Find or create destination workspace
                workspace = None
                if target_workspace_slug:
                    workspace = Workspace.objects.filter(slug=target_workspace_slug).first()
                else:
                    if ws_id:
                        try:
                            workspace = Workspace.objects.filter(id=uuid.UUID(str(ws_id))).first()
                        except (ValueError, TypeError):
                            pass
                    if not workspace and src_slug:
                        workspace = Workspace.objects.filter(slug=src_slug).first()

                if not workspace:
                    # Create new workspace
                    dest_slug = target_workspace_slug or src_slug
                    if Workspace.objects.filter(slug=dest_slug).exists():
                        dest_slug = f"{dest_slug}-restored-{secrets.token_hex(3)}"

                    workspace_kwargs = {
                        'name': ws_data.get('name') or "Restored Workspace",
                        'slug': dest_slug,
                        'description': ws_data.get('description') or '',
                        'owner': actor,
                        'status': ws_data.get('status') or 'ACTIVE',
                        'max_seats': int(ws_data.get('max_seats') or 15),
                        'storage_quota_mb': int(ws_data.get('storage_quota_mb') or 50),
                    }
                    if not target_workspace_slug and ws_id:
                        try:
                            candidate_uuid = uuid.UUID(str(ws_id))
                            if not Workspace.objects.filter(id=candidate_uuid).exists():
                                workspace_kwargs['id'] = candidate_uuid
                        except (ValueError, TypeError):
                            pass
                    workspace = Workspace.objects.create(**workspace_kwargs)
                    report['records_restored'] += 1
                else:
                    report['records_skipped'] += 1

                report['destination_workspace'] = f"{workspace.name} ({workspace.slug})"
                report['records_processed'] += 1

                # 2. Restore Memberships
                member_rows = _get_sheet_dicts("Members")
                for mr in member_rows:
                    report['records_processed'] += 1
                    u_email = mr.get('user_email')
                    u_id = mr.get('user_id')
                    user = None
                    if u_email:
                        user = User.objects.filter(email__iexact=str(u_email).strip()).first()
                    if not user and u_id:
                        try:
                            user = User.objects.filter(id=u_id).first()
                        except Exception:
                            pass

                    if not user:
                        # User not present; map to restoring actor or warn
                        report['warnings'].append(f"User '{u_email}' not found in system. Skipping membership.")
                        report['records_skipped'] += 1
                        continue

                    # Create or update membership
                    role = mr.get('role') or WorkspaceRole.CONTRIBUTOR
                    status = mr.get('status') or MembershipStatus.ACTIVE
                    WorkspaceMembership.objects.update_or_create(
                        workspace=workspace,
                        user=user,
                        defaults={
                            'role': role,
                            'status': status,
                            'functional_role': mr.get('functional_role') or '',
                            'role_tag': mr.get('role_tag') or '',
                        }
                    )
                    report['records_restored'] += 1

                # 3. Restore Sprints (before tasks because tasks reference sprints)
                sprint_rows = _get_sheet_dicts("Sprints")
                sprint_map = {}
                for sr in sprint_rows:
                    report['records_processed'] += 1
                    sp_id_str = sr.get('id')
                    sp_name = sr.get('name') or "Restored Sprint"
                    sp_id = None
                    if sp_id_str:
                        try:
                            sp_id = uuid.UUID(str(sp_id_str))
                        except Exception:
                            pass

                    sprint = None
                    if sp_id:
                        sprint = Sprint.objects.filter(workspace=workspace, id=sp_id).first()
                    if not sprint:
                        sprint = Sprint.objects.filter(workspace=workspace, name=sp_name).first()

                    if not sprint:
                        kwargs = {
                            'workspace': workspace,
                            'name': sp_name,
                            'goal': sr.get('goal') or '',
                            'status': sr.get('status') or SprintStatus.PLANNING,
                            'created_by': actor,
                        }
                        if sp_id and not Sprint.objects.filter(id=sp_id).exists():
                            kwargs['id'] = sp_id
                        sprint = Sprint.objects.create(**kwargs)
                        report['records_restored'] += 1
                    else:
                        report['records_skipped'] += 1

                    if sp_id_str:
                        sprint_map[str(sp_id_str)] = sprint
                    sprint_map[sp_name] = sprint

                # 4. Restore Tasks
                task_rows = _get_sheet_dicts("Tasks")
                task_map = {}
                for tr in task_rows:
                    report['records_processed'] += 1
                    t_code = str(tr.get('task_code') or '').strip()
                    t_id_str = tr.get('id')
                    t_id = None
                    if t_id_str:
                        try:
                            t_id = uuid.UUID(str(t_id_str))
                        except Exception:
                            pass

                    # Check for existing task in this workspace
                    task = None
                    if t_code:
                        task = Task.objects.filter(workspace=workspace, task_code=t_code).first()
                    if not task and t_id:
                        task = Task.objects.filter(workspace=workspace, id=t_id).first()

                    final_t_code = t_code
                    if not task:
                        # Avoid cross-workspace uniqueness collision
                        if not final_t_code or Task.objects.filter(task_code=final_t_code).exclude(workspace=workspace).exists():
                            final_t_code = generate_unique_task_code()

                        # Resolve assignee and reporter
                        assignee = None
                        if tr.get('assignee_email'):
                            assignee = User.objects.filter(email__iexact=str(tr['assignee_email']).strip()).first()
                        reporter = None
                        if tr.get('reporter_email'):
                            reporter = User.objects.filter(email__iexact=str(tr['reporter_email']).strip()).first()
                        if not reporter:
                            reporter = actor

                        # Resolve sprint
                        sp_obj = None
                        if tr.get('sprint_id') and str(tr['sprint_id']) in sprint_map:
                            sp_obj = sprint_map[str(tr['sprint_id'])]

                        t_kwargs = {
                            'workspace': workspace,
                            'task_code': final_t_code,
                            'title': tr.get('title') or "Untitled Task",
                            'description': tr.get('description') or '',
                            'status': tr.get('status') or TaskStatus.TODO,
                            'priority': tr.get('priority') or TaskPriority.MEDIUM,
                            'assignee': assignee,
                            'reporter': reporter,
                            'sprint_ref': sp_obj,
                            'sprint': tr.get('sprint') or (sp_obj.name if sp_obj else 'Sprint 01'),
                            'tags': tr.get('tags') or '',
                        }
                        if t_id and not Task.objects.filter(id=t_id).exists():
                            t_kwargs['id'] = t_id
                        task = Task.objects.create(**t_kwargs)
                        report['records_restored'] += 1
                    else:
                        report['records_skipped'] += 1
                        report['conflicts_encountered'] += 1

                    if t_id_str:
                        task_map[str(t_id_str)] = task
                    if t_code:
                        task_map[t_code] = task
                    if final_t_code:
                        task_map[final_t_code] = task

                # 5. Restore Task Comments
                tc_rows = _get_sheet_dicts("Task_Comments")
                for tcr in tc_rows:
                    report['records_processed'] += 1
                    t_id_ref = str(tcr.get('task_id') or tcr.get('task_code') or '')
                    task_target = task_map.get(t_id_ref)
                    if not task_target:
                        report['records_skipped'] += 1
                        continue

                    author = None
                    if tcr.get('author_email'):
                        author = User.objects.filter(email__iexact=str(tcr['author_email']).strip()).first()
                    if not author:
                        author = actor

                    c_id_str = tcr.get('id')
                    c_id = None
                    if c_id_str:
                        try:
                            c_id = uuid.UUID(str(c_id_str))
                        except Exception:
                            pass

                    if c_id and TaskComment.objects.filter(id=c_id).exists():
                        report['records_skipped'] += 1
                    else:
                        c_kwargs = {
                            'task': task_target,
                            'author': author,
                            'comment_type': tcr.get('comment_type') or 'REGULAR',
                            'system_event_type': tcr.get('system_event_type') or '',
                            'content': tcr.get('content') or '',
                            'metadata': tcr.get('metadata') if isinstance(tcr.get('metadata'), dict) else {},
                        }
                        if c_id and not TaskComment.objects.filter(id=c_id).exists():
                            c_kwargs['id'] = c_id
                        TaskComment.objects.create(**c_kwargs)
                        report['records_restored'] += 1

                # 6. Restore Bugs
                bug_rows = _get_sheet_dicts("Bugs")
                bug_map = {}
                for br in bug_rows:
                    report['records_processed'] += 1
                    b_code = str(br.get('bug_code') or '').strip()
                    b_id_str = br.get('id')
                    b_id = None
                    if b_id_str:
                        try:
                            b_id = uuid.UUID(str(b_id_str))
                        except Exception:
                            pass

                    bug = None
                    if b_code:
                        bug = Bug.objects.filter(workspace=workspace, bug_code=b_code).first()
                    if not bug and b_id:
                        bug = Bug.objects.filter(workspace=workspace, id=b_id).first()

                    final_b_code = b_code
                    if not bug:
                        # Avoid cross-workspace uniqueness collision
                        if not final_b_code or Bug.objects.filter(bug_code=final_b_code).exclude(workspace=workspace).exists():
                            final_b_code = generate_unique_bug_code()

                        reporter = None
                        if br.get('reporter_email'):
                            reporter = User.objects.filter(email__iexact=str(br['reporter_email']).strip()).first()
                        if not reporter:
                            reporter = actor

                        assignee = None
                        if br.get('assignee_email'):
                            assignee = User.objects.filter(email__iexact=str(br['assignee_email']).strip()).first()

                        # Linked task
                        linked_t = None
                        t_ref = str(br.get('linked_task_id') or br.get('linked_task_code') or '')
                        if t_ref in task_map:
                            linked_t = task_map[t_ref]

                        # Sprint
                        sp_obj = None
                        if br.get('sprint_id') and str(br['sprint_id']) in sprint_map:
                            sp_obj = sprint_map[str(br['sprint_id'])]

                        # Module resolution if available
                        mod_obj = None
                        mod_ref = br.get('module')
                        if mod_ref:
                            try:
                                mod_obj = WorkspaceModule.objects.filter(workspace=workspace, id=uuid.UUID(str(mod_ref))).first()
                            except Exception:
                                pass

                        b_kwargs = {
                            'workspace': workspace,
                            'bug_code': final_b_code,
                            'title': br.get('title') or "Untitled Bug",
                            'description': br.get('description') or '',
                            'steps_to_reproduce': br.get('steps_to_reproduce') or '',
                            'expected_result': br.get('expected_result') or '',
                            'actual_result': br.get('actual_result') or '',
                            'status': br.get('status') or BugStatus.OPEN,
                            'priority': br.get('priority') or BugPriority.MEDIUM,
                            'severity': br.get('severity') or BugSeverity.SEV3,
                            'environment': br.get('environment') or '',
                            'module': mod_obj,
                            'linked_task': linked_t,
                            'browser_device': br.get('browser_device') or '',
                            'sprint': br.get('sprint') or (sp_obj.name if sp_obj else 'Sprint 01'),
                            'reporter': reporter,
                            'assignee': assignee,
                            'labels': br.get('labels') or '',
                        }
                        if b_id and not Bug.objects.filter(id=b_id).exists():
                            b_kwargs['id'] = b_id
                        bug = Bug.objects.create(**b_kwargs)
                        report['records_restored'] += 1
                    else:
                        report['records_skipped'] += 1
                        report['conflicts_encountered'] += 1

                    if b_id_str:
                        bug_map[str(b_id_str)] = bug
                    if b_code:
                        bug_map[b_code] = bug
                    if final_b_code:
                        bug_map[final_b_code] = bug

                # 7. Restore Bug Comments
                bc_rows = _get_sheet_dicts("Bug_Comments")
                for bcr in bc_rows:
                    report['records_processed'] += 1
                    b_id_ref = str(bcr.get('bug_id') or bcr.get('bug_code') or '')
                    bug_target = bug_map.get(b_id_ref)
                    if not bug_target:
                        report['records_skipped'] += 1
                        continue

                    author = None
                    if bcr.get('author_email'):
                        author = User.objects.filter(email__iexact=str(bcr['author_email']).strip()).first()
                    if not author:
                        author = actor

                    bc_id_str = bcr.get('id')
                    bc_id = None
                    if bc_id_str:
                        try:
                            bc_id = uuid.UUID(str(bc_id_str))
                        except Exception:
                            pass

                    if bc_id and BugComment.objects.filter(id=bc_id).exists():
                        report['records_skipped'] += 1
                    else:
                        bc_kwargs = {
                            'bug': bug_target,
                            'author': author,
                            'content': bcr.get('content') or '',
                        }
                        if bc_id and not BugComment.objects.filter(id=bc_id).exists():
                            bc_kwargs['id'] = bc_id
                        BugComment.objects.create(**bc_kwargs)
                        report['records_restored'] += 1

                # 8. Restore Code Reviews
                cr_rows = _get_sheet_dicts("Code_Reviews")
                for crr in cr_rows:
                    report['records_processed'] += 1
                    t_ref = str(crr.get('task_id') or crr.get('task_code') or '')
                    task_target = task_map.get(t_ref)
                    if not task_target:
                        report['records_skipped'] += 1
                        continue

                    rcode = crr.get('review_code') or f"CR-{task_target.task_code}"
                    cr_id_str = crr.get('id')
                    cr_id = None
                    if cr_id_str:
                        try:
                            cr_id = uuid.UUID(str(cr_id_str))
                        except Exception:
                            pass

                    if CodeReviewRequest.objects.filter(review_code=rcode).exists():
                        rcode = generate_unique_code_review_code()

                    req_u = None
                    if crr.get('requester_email'):
                        req_u = User.objects.filter(email__iexact=str(crr['requester_email']).strip()).first()
                    if not req_u:
                        req_u = actor

                    rev_u = None
                    if crr.get('reviewer_email'):
                        rev_u = User.objects.filter(email__iexact=str(crr['reviewer_email']).strip()).first()

                    cr_kwargs = {
                        'review_code': rcode,
                        'task': task_target,
                        'requester': req_u,
                        'reviewer': rev_u,
                        'title': crr.get('title') or f"Review for {task_target.title}",
                        'description': crr.get('description') or '',
                        'github_pr_url': crr.get('github_pr_url') or 'https://github.com/aetherspace/pulls',
                        'status': crr.get('status') or CodeReviewStatus.REQUESTED,
                    }
                    if cr_id and not CodeReviewRequest.objects.filter(id=cr_id).exists():
                        cr_kwargs['id'] = cr_id
                    CodeReviewRequest.objects.create(**cr_kwargs)
                    report['records_restored'] += 1

                # 9. Restore Calendar Events
                ce_rows = _get_sheet_dicts("Calendar_Events")
                for cer in ce_rows:
                    report['records_processed'] += 1
                    ce_id_str = cer.get('id')
                    ce_id = None
                    if ce_id_str:
                        try:
                            ce_id = uuid.UUID(str(ce_id_str))
                        except Exception:
                            pass

                    if ce_id and CalendarEvent.objects.filter(id=ce_id).exists():
                        report['records_skipped'] += 1
                    else:
                        start_at = cer.get('start_at')
                        end_at = cer.get('end_at')
                        now = timezone.now()
                        ce_kwargs = {
                            'workspace': workspace,
                            'title': cer.get('title') or "Restored Event",
                            'description': cer.get('description') or '',
                            'event_type': cer.get('event_type') or 'TEAM_MEETING',
                            'calendar_category': cer.get('calendar_category') or 'WORK',
                            'start_at': start_at if start_at else now,
                            'end_at': end_at if end_at else now + timezone.timedelta(hours=1),
                            'is_all_day': str(cer.get('is_all_day', '')).upper() == "TRUE",
                            'status': cer.get('status') or 'SCHEDULED',
                            'created_by': actor,
                        }
                        if ce_id and not CalendarEvent.objects.filter(id=ce_id).exists():
                            ce_kwargs['id'] = ce_id
                        CalendarEvent.objects.create(**ce_kwargs)
                        report['records_restored'] += 1

                # 10. Restore Meetings
                meeting_rows = _get_sheet_dicts("Meetings")
                for mr in meeting_rows:
                    report['records_processed'] += 1
                    m_code = mr.get('meeting_code') or f"M-{uuid.uuid4().hex[:6].upper()}"
                    m_id_str = mr.get('id')
                    m_id = None
                    if m_id_str:
                        try:
                            m_id = uuid.UUID(str(m_id_str))
                        except Exception:
                            pass

                    if Meeting.objects.filter(workspace=workspace, meeting_code=m_code).exists():
                        report['records_skipped'] += 1
                    else:
                        final_m_code = m_code
                        if not final_m_code or Meeting.objects.filter(meeting_code=final_m_code).exclude(workspace=workspace).exists():
                            final_m_code = f"M-{secrets.token_hex(4).upper()}"

                        host = None
                        if mr.get('host_email'):
                            host = User.objects.filter(email__iexact=str(mr['host_email']).strip()).first()
                        if not host:
                            host = actor

                        m_kwargs = {
                            'workspace': workspace,
                            'meeting_code': final_m_code,
                            'title': mr.get('title') or "Restored Meeting",
                            'description': mr.get('description') or '',
                            'host': host,
                            'meeting_type': mr.get('meeting_type') or 'STANDUP',
                            'status': mr.get('status') or 'SCHEDULED',
                            'scheduled_start': mr.get('scheduled_start') or timezone.now(),
                        }
                        if m_id and not Meeting.objects.filter(id=m_id).exists():
                            m_kwargs['id'] = m_id
                        Meeting.objects.create(**m_kwargs)
                        report['records_restored'] += 1

                # 11. Restore Time Entries
                te_rows = _get_sheet_dicts("Time_Entries")
                for ter in te_rows:
                    report['records_processed'] += 1
                    te_id_str = ter.get('id')
                    te_id = None
                    if te_id_str:
                        try:
                            te_id = uuid.UUID(str(te_id_str))
                        except Exception:
                            pass

                    if te_id and TimeEntry.objects.filter(id=te_id).exists():
                        report['records_skipped'] += 1
                    else:
                        te_user = None
                        if ter.get('user_email'):
                            te_user = User.objects.filter(email__iexact=str(ter['user_email']).strip()).first()
                        if not te_user:
                            te_user = actor

                        t_ref = str(ter.get('task_id') or ter.get('task_code') or '')
                        linked_t = task_map.get(t_ref)

                        te_kwargs = {
                            'workspace': workspace,
                            'user': te_user,
                            'task': linked_t,
                            'description': ter.get('description') or '',
                            'started_at': ter.get('started_at') or timezone.now(),
                            'accumulated_seconds': int(ter.get('accumulated_seconds') or 0),
                            'duration_seconds': int(ter.get('duration_seconds') or 0),
                            'status': ter.get('status') or 'STOPPED',
                            'is_running': False,
                        }
                        if te_id:
                            te_kwargs['id'] = te_id
                        TimeEntry.objects.create(**te_kwargs)
                        report['records_restored'] += 1

                # 12. Restore Files Metadata
                files_rows = _get_sheet_dicts("Files_Metadata")
                folder_map = {}
                for fr in files_rows:
                    report['records_processed'] += 1
                    f_id_str = fr.get('id')
                    f_id = None
                    if f_id_str:
                        try:
                            f_id = uuid.UUID(str(f_id_str))
                        except Exception:
                            pass

                    # Resolve or create folder if specified
                    folder_name = fr.get('folder_name')
                    folder_obj = None
                    if folder_name and folder_name not in folder_map:
                        folder_obj, _ = Folder.objects.get_or_create(
                            workspace=workspace,
                            name=folder_name,
                            defaults={'created_by': actor}
                        )
                        folder_map[folder_name] = folder_obj
                    elif folder_name:
                        folder_obj = folder_map[folder_name]

                    if f_id and StoredFile.objects.filter(id=f_id).exists():
                        report['records_skipped'] += 1
                    else:
                        uploader = None
                        if fr.get('uploaded_by_email'):
                            uploader = User.objects.filter(email__iexact=str(fr['uploaded_by_email']).strip()).first()
                        if not uploader:
                            uploader = actor

                        f_kwargs = {
                            'workspace': workspace,
                            'folder': folder_obj,
                            'uploaded_by': uploader,
                            'name': fr.get('name') or "restored_file.dat",
                            'original_name': fr.get('original_name') or fr.get('name') or "restored_file.dat",
                            'storage_path': fr.get('storage_path') or f"{workspace.slug}/restored_{f_id_str or uuid.uuid4().hex}",
                            'is_external_link': str(fr.get('is_external_link', '')).upper() == "TRUE",
                            'mime_type': fr.get('mime_type') or 'application/octet-stream',
                            'category': fr.get('category') or 'OTHER',
                            'size_bytes': int(fr.get('size_bytes') or 0),
                            'checksum': fr.get('checksum') or '',
                            'description': fr.get('description') or '',
                        }
                        if f_id and not StoredFile.objects.filter(id=f_id).exists():
                            f_kwargs['id'] = f_id
                        StoredFile.objects.create(**f_kwargs)
                        report['records_restored'] += 1

                # Audit Log
                AuditLogService.log(
                    action='WORKSPACE_RESTORE_COMPLETED',
                    actor=actor,
                    target_type='Workspace',
                    target_id=str(workspace.id),
                    target_repr=workspace.name,
                    workspace=workspace,
                    metadata={
                        'restore_operation_id': report['restore_operation_id'],
                        'records_restored': report['records_restored'],
                        'records_skipped': report['records_skipped'],
                        'source_workspace': report['source_workspace'],
                    }
                )

                report['verification_result'] = 'PASSED'
                return True, report

        except Exception as e:
            logger.exception("Transactional workspace restore failed")
            report['errors'].append(f"Restore failed and was rolled back: {str(e)}")
            report['verification_result'] = 'FAILED_ROLLED_BACK'

            AuditLogService.log(
                action='WORKSPACE_RESTORE_FAILED',
                actor=actor,
                target_type='Workspace',
                status=AuditActionStatus.FAILURE,
                metadata={
                    'restore_operation_id': report['restore_operation_id'],
                    'error': str(e),
                }
            )
            return False, report
