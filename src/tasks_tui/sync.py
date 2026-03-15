"""Sync engine for bidirectional beads ↔ Google Tasks synchronisation."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tasks_tui.config import get_project_config
from tasks_tui.beads_api import (
    BeadsIssue,
    create_beads_issue,
    discover_beads_workspaces,
    list_closed_mapped_issues,
    list_issues_via_cli,
)
from tasks_tui.tasks_api import (
    complete_task_in_list,
    create_task_in_list,
    create_tasklist,
    list_tasklists,
    list_tasks_in_list,
    update_task_in_list,
)

MAPPING_FILE = Path.home() / ".beads" / "gtasks-sync.json"


@dataclass
class MappingEntry:
    beads_id: str
    beads_db_path: str
    gtask_id: str
    gtask_list_id: str
    last_synced_at: str  # ISO 8601 UTC; for future delta-sync use


# ---------------------------------------------------------------------------
# Mapping file I/O
# ---------------------------------------------------------------------------


def load_mapping() -> dict:
    """Load the sync mapping file. Returns an empty mapping on missing or corrupt file."""
    if not MAPPING_FILE.exists():
        return {"projects": {}, "mappings": []}
    try:
        data = json.loads(MAPPING_FILE.read_text())
        if not isinstance(data, dict):
            return {"projects": {}, "mappings": []}
        data.setdefault("projects", {})
        data.setdefault("mappings", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"projects": {}, "mappings": []}


def save_mapping(mapping: dict) -> None:
    """Atomically write the mapping to disk via a .tmp file then os.replace."""
    MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MAPPING_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, indent=2))
    os.replace(tmp, MAPPING_FILE)


# ---------------------------------------------------------------------------
# Field conversion helpers
# ---------------------------------------------------------------------------


def _beads_due_to_gtask_due(due_at: str) -> str:
    """Convert beads ISO datetime to Google Tasks date-only format (date portion only)."""
    if not due_at:
        return ""
    try:
        dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
        # Google Tasks API expects RFC 3339 timestamp; use midnight UTC
        return dt.strftime("%Y-%m-%dT00:00:00.000Z")
    except ValueError:
        return ""


def fields_from_issue(issue: BeadsIssue) -> dict:
    """Convert a BeadsIssue to a dict of Google Tasks API fields.

    The (bd) marker is appended to notes so that the Google Task is identifiable
    as being tracked by beads.
    """
    description = issue.description or ""
    notes = f"{description} {BD_MARKER}".strip()
    return {
        "title": issue.title,
        "notes": notes,
        "due": _beads_due_to_gtask_due(issue.due_at),
    }


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


BD_MARKER = "(bd)"


def _has_bd_marker(notes: str | None) -> bool:
    """Return True if the text contains the (bd) beads sync marker."""
    return BD_MARKER in (notes or "")


def _strip_bd_marker(notes: str | None) -> str:
    """Remove the (bd) marker from text and normalise surrounding whitespace."""
    return " ".join((notes or "").replace(BD_MARKER, " ").split())




# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------


class SyncEngine:
    """Runs one full sync pass: beads → Google Tasks, with beads as source of truth."""

    def __init__(self, config: dict | None = None) -> None:
        self._mapping = load_mapping()
        self._config: dict = config or {}

    def run(self, progress: Callable[[str], None] | None = None) -> None:
        """Execute the sync. Calls progress(msg) with status updates."""
        _progress = progress or (lambda _: None)

        workspaces = discover_beads_workspaces()
        if not workspaces:
            _progress("No beads workspaces found — nothing to sync")
            return

        errors: list[str] = []
        for workspace_path, db_path in workspaces.items():
            project_name = Path(workspace_path).name
            if not get_project_config(project_name, self._config)["sync"]:
                _progress(f"Skipping {project_name} (sync disabled)")
                continue
            _progress(f"Syncing {project_name}…")
            try:
                self._sync_project(workspace_path, db_path, project_name, errors)
            except Exception as e:
                errors.append(f"{project_name}: {e}")

        save_mapping(self._mapping)

        if errors:
            _progress("Sync finished with errors: " + "; ".join(errors))
        else:
            _progress("Sync complete")

    def _get_or_create_tasklist(self, workspace_path: str, name: str) -> str:
        """Return the Google Tasks list ID for workspace_path, creating it if needed."""
        projects = self._mapping["projects"]

        # Fast path: already stored
        if workspace_path in projects:
            return projects[workspace_path]["tasklist_id"]

        # Scan existing lists by name (first match)
        try:
            tasklists = list_tasklists()
        except Exception:
            tasklists = []

        for tl in tasklists:
            if tl.get("title") == name:
                tasklist_id = tl["id"]
                projects[workspace_path] = {
                    "tasklist_id": tasklist_id,
                    "tasklist_name": name,
                }
                return tasklist_id

        # Create a new list
        tl = create_tasklist(name)
        tasklist_id = tl["id"]
        projects[workspace_path] = {"tasklist_id": tasklist_id, "tasklist_name": name}
        return tasklist_id

    def _entries_for_db(self, db_path: str) -> dict[str, dict]:
        """Return {beads_id: entry_dict} for all mapping entries belonging to db_path."""
        return {
            e["beads_id"]: e
            for e in self._mapping["mappings"]
            if e["beads_db_path"] == db_path
        }

    def _add_entry(self, issue: BeadsIssue, gtask_id: str, gtask_list_id: str) -> None:
        self._mapping["mappings"].append(
            {
                "beads_id": issue.id,
                "beads_db_path": issue.db_path,
                "gtask_id": gtask_id,
                "gtask_list_id": gtask_list_id,
                "last_synced_at": _now_utc(),
            }
        )

    def _update_timestamp(self, beads_id: str) -> None:
        for e in self._mapping["mappings"]:
            if e["beads_id"] == beads_id:
                e["last_synced_at"] = _now_utc()
                return

    def _remove_entry(self, beads_id: str) -> None:
        self._mapping["mappings"] = [
            e for e in self._mapping["mappings"] if e["beads_id"] != beads_id
        ]

    def _mapped_gtask_ids(self) -> set[str]:
        """Return the set of all gtask_ids that are already in the mapping."""
        return {e["gtask_id"] for e in self._mapping["mappings"]}

    def _sync_gtasks_to_beads(
        self,
        tasklist_id: str,
        workspace_path: str,
        db_path: str,
        project_name: str,
        errors: list[str],
    ) -> None:
        """Pull Google Tasks with (bd) marker into beads as new issues."""
        try:
            tasks = list_tasks_in_list(tasklist_id)
        except Exception as e:
            errors.append(f"list tasks for {project_name}: {e}")
            return

        already_mapped = self._mapped_gtask_ids()
        for task in tasks:
            if task.id in already_mapped:
                continue
            if not _has_bd_marker(task.notes):
                continue
            description = _strip_bd_marker(task.notes)
            try:
                new_id = create_beads_issue(
                    workspace_path=workspace_path,
                    db_path=db_path,
                    title=task.title,
                    description=description,
                    due=task.due,
                )
                self._mapping["mappings"].append(
                    {
                        "beads_id": new_id,
                        "beads_db_path": db_path,
                        "gtask_id": task.id,
                        "gtask_list_id": tasklist_id,
                        "last_synced_at": _now_utc(),
                    }
                )
            except Exception as e:
                errors.append(f"create beads issue from gtask {task.id}: {e}")

    def _sync_project(
        self, workspace_path: str, db_path: str, project_name: str, errors: list[str]
    ) -> None:
        tasklist_id = self._get_or_create_tasklist(workspace_path, project_name)
        mapped = self._entries_for_db(db_path)
        mapped_ids = set(mapped.keys())

        live_issues = list_issues_via_cli(workspace_path, db_path)

        for issue in live_issues:
            fields = fields_from_issue(issue)
            if issue.id not in mapped_ids:
                # New beads issue — push to Google Tasks
                gtask = create_task_in_list(
                    tasklist_id,
                    title=fields["title"],
                    due=fields["due"],
                    notes=fields["notes"],
                )
                self._add_entry(issue, gtask.id, tasklist_id)
            else:
                # Existing — beads wins, overwrite Google Task
                entry = mapped[issue.id]
                update_task_in_list(
                    entry["gtask_list_id"],
                    entry["gtask_id"],
                    title=fields["title"],
                    due=fields["due"],
                    notes=fields["notes"],
                )
                self._update_timestamp(issue.id)

        # Detect closed/deleted issues that have mapping entries
        live_ids = {i.id for i in live_issues}
        closed_issues = list_closed_mapped_issues(mapped_ids, db_path)
        closed_ids = {i.id for i in closed_issues}

        for issue in closed_issues:
            entry = mapped[issue.id]
            try:
                complete_task_in_list(entry["gtask_list_id"], entry["gtask_id"])
                self._remove_entry(issue.id)
            except Exception as e:
                errors.append(f"complete {issue.id}: {e}")

        # Detect fully orphaned entries (deleted without appearing in closed query)
        orphaned_ids = mapped_ids - live_ids - closed_ids
        for beads_id in orphaned_ids:
            entry = mapped[beads_id]
            try:
                complete_task_in_list(entry["gtask_list_id"], entry["gtask_id"])
                self._remove_entry(beads_id)
            except Exception as e:
                errors.append(f"complete orphan {beads_id}: {e}")

        # Google Tasks → beads: pull tasks with (bd) marker into beads as new issues
        self._sync_gtasks_to_beads(tasklist_id, workspace_path, db_path, project_name, errors)
