# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import csv
import io
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ROLE, allow_permission
from plane.app.serializers import IssueCreateSerializer
from plane.app.views import BaseAPIView
from plane.db.models import Cycle, CycleIssue, Label, Module, ModuleIssue, Project, ProjectMember, State

MAX_IMPORT_ROWS = 200

FIELD_ALIASES = {
    "name": {"name", "title"},
    "description": {"description"},
    "priority": {"priority"},
    "state": {"state", "state_name"},
    "labels": {"labels"},
    "assignees": {"assignees", "assignee_emails"},
    "start_date": {"start_date"},
    "target_date": {"target_date", "due_date"},
    "module": {"module", "module_name", "modules"},
    "cycle": {"cycle", "cycle_name"},
}

VALID_PRIORITIES = {"urgent", "high", "medium", "low", "none"}


def _normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def _map_row(row: dict) -> dict:
    normalized = {_normalize_header(key): (value or "").strip() for key, value in row.items()}
    mapped = {}

    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized and normalized[alias]:
                mapped[field] = normalized[alias]
                break

    return mapped


def _parse_date(value: str):
    if not value:
        return None

    parsed = parse_date(value)
    if parsed:
        return parsed

    for date_format in ("%d %b %Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    return None


def _link_issue_to_modules(issue, module_names_value, modules_by_name, project_id, workspace_id):
    if not module_names_value:
        return

    module_issues = []
    seen_module_ids = set()

    for module_name in module_names_value.split(","):
        module_id = modules_by_name.get(module_name.strip().lower())
        if module_id and module_id not in seen_module_ids:
            seen_module_ids.add(module_id)
            module_issues.append(
                ModuleIssue(
                    issue=issue,
                    module_id=module_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                )
            )

    if module_issues:
        ModuleIssue.objects.bulk_create(module_issues, ignore_conflicts=True, batch_size=10)


def _link_issue_to_cycle(issue, cycle_name_value, cycles_by_id, project_id, workspace_id):
    if not cycle_name_value:
        return

    cycle = cycles_by_id.get(cycle_name_value.strip().lower())
    if not cycle:
        return

    if cycle.end_date is not None and cycle.end_date < timezone.now():
        return

    CycleIssue.objects.bulk_create(
        [
            CycleIssue(
                issue=issue,
                cycle_id=cycle.id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        ],
        ignore_conflicts=True,
        batch_size=10,
    )


class IssueCsvImportEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id):
        uploaded_file = request.FILES.get("file")

        if not uploaded_file:
            return Response({"error": "CSV file is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not uploaded_file.name.lower().endswith(".csv"):
            return Response({"error": "Only CSV files are supported."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            raw_content = uploaded_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"error": "CSV file must be UTF-8 encoded."}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(raw_content))
        rows = list(reader)

        if not rows:
            return Response({"error": "CSV file is empty."}, status=status.HTTP_400_BAD_REQUEST)

        if len(rows) > MAX_IMPORT_ROWS:
            return Response(
                {"error": f"CSV file cannot contain more than {MAX_IMPORT_ROWS} rows."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project = Project.objects.get(pk=project_id, workspace__slug=slug)

        states_by_name = {state.name.lower(): state.id for state in State.objects.filter(project_id=project_id)}
        labels_by_name = {label.name.lower(): label.id for label in Label.objects.filter(project_id=project_id)}
        modules_by_name = {
            module.name.lower(): module.id
            for module in Module.objects.filter(project_id=project_id, archived_at__isnull=True)
        }
        cycles_by_name = {
            cycle.name.lower(): cycle
            for cycle in Cycle.objects.filter(project_id=project_id, archived_at__isnull=True)
        }
        members_by_email = {
            member.member.email.lower(): member.member_id
            for member in ProjectMember.objects.filter(project_id=project_id, is_active=True, role__gte=15).select_related(
                "member"
            )
            if member.member.email
        }

        created_count = 0
        failed_count = 0
        errors = []

        for index, row in enumerate(rows, start=2):
            mapped_row = _map_row(row)
            name = mapped_row.get("name")

            if not name:
                failed_count += 1
                errors.append({"row": index, "error": "Name is required."})
                continue

            issue_data = {"name": name}

            if description := mapped_row.get("description"):
                issue_data["description_html"] = f"<p>{description}</p>"

            if priority := mapped_row.get("priority"):
                priority_value = priority.lower()
                if priority_value in VALID_PRIORITIES:
                    issue_data["priority"] = priority_value

            if state_name := mapped_row.get("state"):
                state_id = states_by_name.get(state_name.lower())
                if state_id:
                    issue_data["state_id"] = str(state_id)

            if labels_value := mapped_row.get("labels"):
                label_ids = [
                    str(labels_by_name[label_name.strip().lower()])
                    for label_name in labels_value.split(",")
                    if label_name.strip().lower() in labels_by_name
                ]
                if label_ids:
                    issue_data["label_ids"] = label_ids

            if assignees_value := mapped_row.get("assignees"):
                assignee_ids = [
                    str(members_by_email[email.strip().lower()])
                    for email in assignees_value.split(",")
                    if email.strip().lower() in members_by_email
                ]
                if assignee_ids:
                    issue_data["assignee_ids"] = assignee_ids

            if start_date_value := mapped_row.get("start_date"):
                parsed_start_date = _parse_date(start_date_value)
                if parsed_start_date:
                    issue_data["start_date"] = parsed_start_date.isoformat()

            if target_date_value := mapped_row.get("target_date"):
                parsed_target_date = _parse_date(target_date_value)
                if parsed_target_date:
                    issue_data["target_date"] = parsed_target_date.isoformat()

            serializer = IssueCreateSerializer(
                data=issue_data,
                context={
                    "project_id": project_id,
                    "workspace_id": project.workspace_id,
                    "default_assignee_id": project.default_assignee_id,
                },
            )

            if serializer.is_valid():
                issue = serializer.save()
                _link_issue_to_modules(
                    issue,
                    mapped_row.get("module"),
                    modules_by_name,
                    project_id,
                    project.workspace_id,
                )
                _link_issue_to_cycle(
                    issue,
                    mapped_row.get("cycle"),
                    cycles_by_name,
                    project_id,
                    project.workspace_id,
                )
                created_count += 1
            else:
                failed_count += 1
                errors.append({"row": index, "error": serializer.errors})

        return Response(
            {
                "created": created_count,
                "failed": failed_count,
                "errors": errors[:20],
            },
            status=status.HTTP_200_OK,
        )
