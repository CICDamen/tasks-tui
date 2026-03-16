"""Wrapper around the `gws tasks` CLI for Google Tasks access."""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime


_cached_tasklist_id: str | None = None
_cached_tasklist_title: str = "My Tasks"


def _default_tasklist_id() -> str:
    """Return the ID of the primary Google Tasks list ('My Tasks'), discovered on first call."""
    global _cached_tasklist_id, _cached_tasklist_title
    if _cached_tasklist_id is not None:
        return _cached_tasklist_id
    data = _gws("tasklists", "list")
    items = data.get("items", [])
    for item in items:
        if item.get("title") == "My Tasks":
            _cached_tasklist_id = item["id"]
            _cached_tasklist_title = item.get("title", "My Tasks")
            return _cached_tasklist_id
    if items:
        _cached_tasklist_id = items[0]["id"]
        _cached_tasklist_title = items[0].get("title", "My Tasks")
        return _cached_tasklist_id
    raise RuntimeError("No Google Tasks lists found. Is gws authenticated?")


@dataclass
class Task:
    id: str
    title: str
    status: str  # "needsAction" | "completed"
    notes: str = ""
    due: str = ""  # ISO 8601 date string or ""
    completed_at: str = ""  # ISO 8601 date string or ""
    parent_id: str = ""  # non-empty for subtasks
    list_title: str = ""  # name of the Google Tasks list this task belongs to

    @property
    def label(self) -> str:
        """Extract [label] prefix from title if present."""
        if self.title.startswith("["):
            end = self.title.find("]")
            if end > 0:
                return self.title[1:end]
        return ""

    @property
    def display_title(self) -> str:
        """Title with [label] prefix stripped."""
        if self.label:
            return self.title[len(self.label) + 2 :].lstrip()
        return self.title

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @property
    def days_until_due(self) -> int | None:
        if not self.due:
            return None
        try:
            due_dt = datetime.fromisoformat(self.due.replace("Z", "+00:00")).date()
            return (due_dt - datetime.now().date()).days
        except ValueError:
            return None

    @property
    def due_label(self) -> str:
        if not self.due:
            return "today"
        days = self.days_until_due
        if days is None:
            return ""
        if days < 0:
            return "overdue"
        if days == 0:
            return "today"
        if days == 1:
            return "tomorrow"
        if days < 7:
            return f"in {days}d"
        try:
            due_dt = datetime.fromisoformat(self.due.replace("Z", "+00:00")).date()
            return due_dt.strftime("%b %-d")
        except ValueError:
            return ""

    @property
    def due_css_class(self) -> str:
        if not self.due:
            return "due-urgent"
        days = self.days_until_due
        if days is None:
            return "due-label"
        if days < 0:
            return "due-overdue"
        if days <= 1:
            return "due-urgent"
        if days <= 4:
            return "due-soon"
        return "due-label"

    @property
    def is_overdue(self) -> bool:
        days = self.days_until_due
        return days is not None and days < 0

    @property
    def completed_label(self) -> str:
        if not self.completed_at:
            return ""
        try:
            completed_dt = datetime.fromisoformat(
                self.completed_at.replace("Z", "+00:00")
            ).date()
            today = datetime.now().date()
            delta = (today - completed_dt).days
            if delta == 0:
                return "today"
            if delta == 1:
                return "yesterday"
            if delta < 7:
                return f"{delta}d ago"
            return completed_dt.strftime("%b %-d")
        except ValueError:
            return ""


def _gws(
    resource: str, method: str, params: dict | None = None, body: dict | None = None
) -> dict:
    cmd = ["gws", "tasks", resource, method]
    if params:
        cmd += ["--params", json.dumps(params)]
    if body:
        cmd += ["--json", json.dumps(body)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=15
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "(no output)"
        raise RuntimeError(f"gws command failed: {stderr}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "gws CLI not found. Install it and ensure it is on your PATH."
        ) from None
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def list_tasks() -> list[Task]:
    tasklist_id = _default_tasklist_id()
    data = _gws(
        "tasks",
        "list",
        params={
            "tasklist": tasklist_id,
            "showCompleted": False,
            "showHidden": False,
        },
    )
    items = data.get("items", [])
    return [
        Task(
            id=t["id"],
            title=t.get("title", ""),
            status=t.get("status", "needsAction"),
            notes=t.get("notes", ""),
            due=t.get("due", ""),
            parent_id=t.get("parent", ""),
            list_title=_cached_tasklist_title,
        )
        for t in items
        if t.get("title")
    ]


def list_completed_tasks(max_results: int = 20) -> list[Task]:
    data = _gws(
        "tasks",
        "list",
        params={
            "tasklist": _default_tasklist_id(),
            "showCompleted": True,
            "showHidden": True,
            "maxResults": max_results,
        },
    )
    items = data.get("items", [])
    return [
        Task(
            id=t["id"],
            title=t.get("title", ""),
            status=t.get("status", "needsAction"),
            notes=t.get("notes", ""),
            due=t.get("due", ""),
            completed_at=t.get("completed", ""),
            list_title=_cached_tasklist_title,
        )
        for t in items
        if t.get("title") and t.get("status") == "completed"
    ]


def create_subtask(title: str, parent_id: str, due: str = "", notes: str = "") -> Task:
    body: dict = {"title": title, "status": "needsAction"}
    if due:
        body["due"] = due
    if notes:
        body["notes"] = notes
    t = _gws(
        "tasks",
        "insert",
        params={"tasklist": _default_tasklist_id(), "parent": parent_id},
        body=body,
    )
    return Task(
        id=t["id"],
        title=t["title"],
        status=t["status"],
        notes=t.get("notes", ""),
        due=t.get("due", ""),
        parent_id=parent_id,
    )


def create_task(title: str, due: str = "", notes: str = "") -> Task:
    body: dict = {"title": title, "status": "needsAction"}
    if due:
        body["due"] = due
    if notes:
        body["notes"] = notes
    t = _gws("tasks", "insert", params={"tasklist": _default_tasklist_id()}, body=body)
    return Task(
        id=t["id"],
        title=t["title"],
        status=t["status"],
        notes=t.get("notes", ""),
        due=t.get("due", ""),
    )


def update_task(task_id: str, title: str, due: str = "", notes: str = "") -> None:
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    _gws(
        "tasks",
        "patch",
        params={"tasklist": _default_tasklist_id(), "task": task_id},
        body=body,
    )


def complete_task(task_id: str) -> None:
    _gws(
        "tasks",
        "patch",
        params={"tasklist": _default_tasklist_id(), "task": task_id},
        body={"status": "completed"},
    )


def uncomplete_task(task_id: str) -> None:
    _gws(
        "tasks",
        "patch",
        params={"tasklist": _default_tasklist_id(), "task": task_id},
        body={"status": "needsAction"},
    )


def delete_task(task_id: str) -> None:
    _gws(
        "tasks", "delete", params={"tasklist": _default_tasklist_id(), "task": task_id}
    )


def list_tasklists() -> list[dict]:
    """Return all Google Tasks task lists for the authenticated user."""
    data = _gws("tasklists", "list")
    return data.get("items", [])


def create_tasklist(name: str) -> dict:
    """Create a new Google Tasks task list with the given name. Returns the created list dict."""
    return _gws("tasklists", "insert", body={"title": name})


def create_task_in_list(
    tasklist_id: str, title: str, due: str = "", notes: str = ""
) -> Task:
    """Create a task in the given tasklist. Returns the created Task."""
    body: dict = {"title": title, "status": "needsAction"}
    if due:
        body["due"] = due
    if notes:
        body["notes"] = notes
    t = _gws("tasks", "insert", params={"tasklist": tasklist_id}, body=body)
    return Task(
        id=t["id"],
        title=t["title"],
        status=t["status"],
        notes=t.get("notes", ""),
        due=t.get("due", ""),
    )


def update_task_in_list(
    tasklist_id: str, task_id: str, title: str, due: str = "", notes: str = ""
) -> None:
    """Update a task in the given tasklist (beads-wins: overwrites all fields)."""
    body: dict = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due
    _gws("tasks", "patch", params={"tasklist": tasklist_id, "task": task_id}, body=body)


def list_tasks_in_list(tasklist_id: str) -> list[Task]:
    """Return all active (non-completed) tasks in the given tasklist."""
    data = _gws(
        "tasks",
        "list",
        params={"tasklist": tasklist_id, "showCompleted": False, "showHidden": False},
    )
    items = data.get("items", [])
    return [
        Task(
            id=t["id"],
            title=t.get("title", ""),
            status=t.get("status", "needsAction"),
            notes=t.get("notes", ""),
            due=t.get("due", ""),
            parent_id=t.get("parent", ""),
        )
        for t in items
        if t.get("title")
    ]


def complete_task_in_list(tasklist_id: str, task_id: str) -> None:
    """Mark a task in the given tasklist as completed."""
    _gws(
        "tasks",
        "patch",
        params={"tasklist": tasklist_id, "task": task_id},
        body={"status": "completed"},
    )
