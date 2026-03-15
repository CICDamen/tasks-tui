"""All modal screens and their small helper widgets."""

import calendar as cal_mod
from datetime import date as DateType
from datetime import datetime, timedelta
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static, Switch, TextArea

from tasks_tui.beads_api import (
    STATUSES,
    BeadsIssue,
    discover_beads_workspaces,
    get_beads_label,
)
from tasks_tui.config import DEFAULTS, get_project_config
from tasks_tui.date_utils import _format_date_label, _iso_to_date
from tasks_tui.tasks_api import Task


class BeadsDetailScreen(ModalScreen[bool]):
    """Detail view for a Beads issue. Dismisses True when user presses e to edit."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("e", "open_edit", "Edit"),
    ]

    def __init__(self, issue: BeadsIssue) -> None:
        super().__init__()
        self._issue = issue

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-dialog"):
            yield Label(f"[{self._issue.id}] {self._issue.title}", id="detail-title")
            yield Static(
                f"Project: {self._issue.project}   Status: {self._issue.status}",
                id="detail-meta",
            )
            yield Static("─" * 40, id="detail-divider")
            yield TextArea(
                self._issue.description
                if self._issue.description
                else "(no description)",
                id="detail-notes",
            )
            yield Static("esc close  e edit", id="dialog-hint")

    def on_mount(self) -> None:
        self.query_one("#detail-notes", TextArea).read_only = True

    def action_close(self) -> None:
        self.dismiss(False)

    def action_open_edit(self) -> None:
        self.dismiss(True)


class BeadsEditScreen(ModalScreen[dict | None]):
    """Edit a Beads issue: title, status, priority, description, due date."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Save"),
    ]

    PRIORITY_LABELS = ["P0", "P1", "P2", "P3", "P4"]
    STATUS_LABELS = ["open", "in_progress", "blocked", "deferred"]

    def __init__(self, issue: BeadsIssue) -> None:
        super().__init__()
        self._beads_issue = issue
        self._due_iso = issue.due_at
        self._status_idx = (
            STATUSES.index(issue.status) if issue.status in STATUSES else 0
        )
        self._priority = issue.priority
        self._current_label = get_beads_label(issue.id, issue.project)

    def compose(self) -> ComposeResult:
        with Vertical(id="new-task-dialog"):
            yield Label(f"Edit [{self._beads_issue.id}]", id="dialog-title")
            yield Input(value=self._current_label, placeholder="Label...", id="task-label")
            yield Input(value=self._beads_issue.title, id="task-title")
            with Horizontal(classes="due-row"):
                yield Button(
                    _format_date_label(self._due_iso), id="due-btn", classes="due-btn"
                )
                yield Button("✕", id="clear-btn", classes="clear-btn")
            with Horizontal(classes="beads-meta-row"):
                yield Button(
                    self.STATUS_LABELS[self._status_idx],
                    id="status-btn",
                    classes="beads-cycle-btn",
                )
                yield Button(
                    self.PRIORITY_LABELS[self._priority],
                    id="priority-btn",
                    classes="beads-cycle-btn",
                )
            yield TextArea(self._beads_issue.description, id="task-notes")
            yield Static("ctrl+s save  esc cancel", id="dialog-hint")

    def on_mount(self) -> None:
        self.query_one("#task-title", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "due-btn":
            self._open_picker()
        elif event.button.id == "clear-btn":
            self._due_iso = ""
            self.query_one("#due-btn", Button).label = "📅  No date"
        elif event.button.id == "status-btn":
            self._status_idx = (self._status_idx + 1) % len(self.STATUS_LABELS)
            self.query_one("#status-btn", Button).label = self.STATUS_LABELS[
                self._status_idx
            ]
        elif event.button.id == "priority-btn":
            self._priority = (self._priority + 1) % len(self.PRIORITY_LABELS)
            self.query_one("#priority-btn", Button).label = self.PRIORITY_LABELS[
                self._priority
            ]

    def _open_picker(self) -> None:
        initial = _iso_to_date(self._due_iso)

        def on_picked(result: str | None) -> None:
            if result is not None:
                self._due_iso = result + "T00:00:00.000Z"
                self.query_one("#due-btn", Button).label = _format_date_label(
                    self._due_iso
                )

        self.app.push_screen(DatePickerScreen(initial), on_picked)

    def action_confirm(self) -> None:
        title = self.query_one("#task-title", Input).value.strip()
        if not title:
            return
        self.dismiss(
            {
                "title": title,
                "label": self.query_one("#task-label", Input).value.strip(),
                "status": self.STATUS_LABELS[self._status_idx],
                "priority": self._priority,
                "description": self.query_one("#task-notes", TextArea).text,
                "due": self._due_iso,
            }
        )

    def action_cancel(self) -> None:
        self.dismiss(None)


class DatePickerScreen(ModalScreen[str | None]):
    """Calendar date picker modal."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select_date", "Select"),
        Binding("left", "prev_day", show=False),
        Binding("right", "next_day", show=False),
        Binding("up", "prev_week", show=False),
        Binding("down", "next_week", show=False),
        Binding("pageup", "prev_month", "Prev month"),
        Binding("pagedown", "next_month", "Next month"),
    ]

    def __init__(self, initial: DateType | None = None) -> None:
        super().__init__()
        self._selected = initial or datetime.now().date()

    def compose(self) -> ComposeResult:
        with Vertical(id="datepicker-dialog"):
            yield Label("", id="datepicker-month")
            yield Static("", id="datepicker-cal")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        d = self._selected
        self.query_one("#datepicker-month", Label).update(
            f"{cal_mod.month_name[d.month]} {d.year}"
        )
        lines = ["Mo Tu We Th Fr Sa Su"]
        for week in cal_mod.monthcalendar(d.year, d.month):
            row = []
            for day in week:
                if day == 0:
                    row.append("  ")
                elif day == d.day:
                    row.append(f"[reverse]{day:2}[/reverse]")
                else:
                    row.append(f"{day:2}")
            lines.append(" ".join(row))
        self.query_one("#datepicker-cal", Static).update("\n".join(lines))

    def _move(self, days: int) -> None:
        self._selected += timedelta(days=days)
        self._refresh()

    def _move_month(self, delta: int) -> None:
        d = self._selected
        month = d.month + delta
        year = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        max_day = cal_mod.monthrange(year, month)[1]
        self._selected = d.replace(year=year, month=month, day=min(d.day, max_day))
        self._refresh()

    def action_prev_day(self) -> None:
        self._move(-1)

    def action_next_day(self) -> None:
        self._move(1)

    def action_prev_week(self) -> None:
        self._move(-7)

    def action_next_week(self) -> None:
        self._move(7)

    def action_prev_month(self) -> None:
        self._move_month(-1)

    def action_next_month(self) -> None:
        self._move_month(1)

    def action_select_date(self) -> None:
        self.dismiss(self._selected.isoformat())

    def action_cancel(self) -> None:
        self.dismiss(None)


class NewTaskScreen(ModalScreen[dict | None]):
    """Modal for creating a new task."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Save"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._due_iso = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="new-task-dialog"):
            yield Label("New Task", id="dialog-title")
            yield Input(placeholder="Label (optional)...", id="task-label")
            yield Input(placeholder="Task title...", id="task-title")
            with Horizontal(classes="due-row"):
                yield Button("📅  No date", id="due-btn", classes="due-btn")
                yield Button("✕", id="clear-btn", classes="clear-btn")
            yield Static("ctrl+s save  esc cancel", id="dialog-hint")

    def on_mount(self) -> None:
        self.query_one("#task-title", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "due-btn":
            self._open_picker()
        elif event.button.id == "clear-btn":
            self._due_iso = ""
            self.query_one("#due-btn", Button).label = "📅  No date"

    def _open_picker(self) -> None:
        initial = _iso_to_date(self._due_iso)

        def on_picked(result: str | None) -> None:
            if result is not None:
                self._due_iso = result + "T00:00:00.000Z"
                self.query_one("#due-btn", Button).label = _format_date_label(
                    self._due_iso
                )

        self.app.push_screen(DatePickerScreen(initial), on_picked)

    def action_confirm(self) -> None:
        label = self.query_one("#task-label", Input).value.strip()
        title = self.query_one("#task-title", Input).value.strip()
        if not title:
            return
        if label:
            title = f"[{label}] {title}"
        self.dismiss({"title": title, "due": self._due_iso})

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditTaskScreen(ModalScreen[dict | None]):
    """Modal for editing an existing task."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Save"),
    ]

    def __init__(self, task: Task) -> None:
        super().__init__()
        self._edit_task = task
        self._due_iso = task.due

    def compose(self) -> ComposeResult:
        with Vertical(id="new-task-dialog"):
            yield Label("Edit Task", id="dialog-title")
            yield Input(value=self._edit_task.label, placeholder="Label (optional)...", id="task-label")
            yield Input(value=self._edit_task.display_title, id="task-title")
            with Horizontal(classes="due-row"):
                yield Button(
                    _format_date_label(self._due_iso), id="due-btn", classes="due-btn"
                )
                yield Button("✕", id="clear-btn", classes="clear-btn")
            yield TextArea(self._edit_task.notes, id="task-notes")
            yield Static("ctrl+s save  esc cancel", id="dialog-hint")

    def on_mount(self) -> None:
        self.query_one("#task-title", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "due-btn":
            self._open_picker()
        elif event.button.id == "clear-btn":
            self._due_iso = ""
            self.query_one("#due-btn", Button).label = "📅  No date"

    def _open_picker(self) -> None:
        initial = _iso_to_date(self._due_iso)

        def on_picked(result: str | None) -> None:
            if result is not None:
                self._due_iso = result + "T00:00:00.000Z"
                self.query_one("#due-btn", Button).label = _format_date_label(
                    self._due_iso
                )

        self.app.push_screen(DatePickerScreen(initial), on_picked)

    def action_confirm(self) -> None:
        label = self.query_one("#task-label", Input).value.strip()
        title = self.query_one("#task-title", Input).value.strip()
        if not title:
            return
        if label:
            title = f"[{label}] {title}"
        notes = self.query_one("#task-notes", TextArea).text
        self.dismiss({"title": title, "due": self._due_iso, "notes": notes})

    def action_cancel(self) -> None:
        self.dismiss(None)


class TaskDetailScreen(ModalScreen[bool]):
    """Read-only view of a task's details. Dismisses with True if user wants to edit."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("e", "open_edit", "Edit"),
    ]

    def __init__(self, task: Task) -> None:
        super().__init__()
        self._detail_task = task

    def compose(self) -> ComposeResult:
        due = self._detail_task.due_label or "No due date"
        status = (
            "Completed"
            if self._detail_task.completed
            else ("Overdue" if self._detail_task.is_overdue else "Open")
        )
        with Vertical(id="detail-dialog"):
            yield Label(self._detail_task.title, id="detail-title")
            yield Static(f"Due: {due}   Status: {status}", id="detail-meta")
            yield Static("─" * 40, id="detail-divider")
            yield TextArea(
                self._detail_task.notes
                if self._detail_task.notes
                else "(no description)",
                id="detail-notes",
            )
            yield Static("esc close  e edit", id="dialog-hint")

    def on_mount(self) -> None:
        self.query_one("#detail-notes", TextArea).read_only = True

    def action_close(self) -> None:
        self.dismiss(False)

    def action_open_edit(self) -> None:
        self.dismiss(True)


class ProjectFilterRow(Widget):
    """One row in the project filter panel: project name + visible toggle."""

    def __init__(self, name: str, visible: bool) -> None:
        super().__init__(classes="filter-row")
        self._name = name
        self._visible = visible

    def compose(self) -> ComposeResult:
        yield Static(self._name, classes="filter-name")
        yield Switch(value=self._visible, classes="filter-switch")

    @property
    def project_name(self) -> str:
        return self._name

    @property
    def is_visible(self) -> bool:
        return self.query_one(Switch).value


class ProjectFilterScreen(ModalScreen):
    """Quick project visibility filter — toggle which beads projects appear in the task view."""

    BINDINGS = [
        Binding("escape", "close_filter", "Close"),
        Binding("ctrl+a", "select_all", "All", priority=True),
        Binding("ctrl+n", "deselect_all", "None", priority=True),
    ]

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-dialog"):
            yield Label("PROJECTS", id="filter-title")
            yield Input(placeholder="Search…", id="filter-search")
            yield Vertical(id="filter-rows")
            yield Static("ctrl+a all · ctrl+n none · esc close", id="filter-hint")

    def on_mount(self) -> None:
        self.query_one("#filter-search", Input).focus()
        self._discover()

    @work(thread=True)
    def _discover(self) -> None:
        workspaces = discover_beads_workspaces()
        self.app.call_from_thread(self._populate, workspaces)

    def _populate(self, workspaces: dict[str, str]) -> None:
        rows = self.query_one("#filter-rows", Vertical)
        for workspace_path in sorted(workspaces):
            name = Path(workspace_path).name
            proj = get_project_config(name, self._config)
            rows.mount(ProjectFilterRow(name=name, visible=proj["visible"]))

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.lower()
        for row in self.query(ProjectFilterRow):
            row.display = not query or query in row.project_name.lower()

    def action_select_all(self) -> None:
        for row in self.query(ProjectFilterRow):
            row.query_one(Switch).value = True

    def action_deselect_all(self) -> None:
        for row in self.query(ProjectFilterRow):
            row.query_one(Switch).value = False

    def action_close_filter(self) -> None:
        projects: dict[str, dict] = dict(self._config.get("projects", {}))
        for row in self.query(ProjectFilterRow):
            proj = get_project_config(row.project_name, self._config)
            projects[row.project_name] = {**proj, "visible": row.is_visible}
        self.dismiss(projects)


class ProjectRow(Widget):
    """One row per beads workspace shown in the SetupScreen PROJECTS section."""

    def __init__(self, name: str, sync: bool, visible: bool, label: str) -> None:
        super().__init__(classes="project-row")
        self._name = name
        self._sync = sync
        self._visible = visible
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._name, classes="project-name")
        yield Switch(value=self._sync, classes="project-sync-switch")
        yield Switch(value=self._visible, classes="project-visible-switch")
        yield Input(value=self._label, classes="project-label-input")

    @property
    def project_name(self) -> str:
        return self._name

    def get_values(self) -> dict:
        switches = list(self.query(Switch))
        return {
            "sync": switches[0].value,
            "visible": switches[1].value,
            "label": self.query_one(Input).value or self._name,
        }


class SetupScreen(ModalScreen):
    """Configuration screen — shown on first run and accessible via ','."""

    BINDINGS = [Binding("escape", "skip", "Cancel")]

    def __init__(self, config: dict | None = None, first_run: bool = False) -> None:
        super().__init__()
        self._initial = config or {}
        self._first_run = first_run

    def _get(self, section: str, key: str):
        return self._initial.get(section, {}).get(key, DEFAULTS[section][key])

    def compose(self) -> ComposeResult:
        title = "Welcome to tasks-tui  ✦" if self._first_run else "Configuration"
        desc = (
            "Let's set up your configuration.\n"
            "You can also edit ~/.config/tasks-tui/config.json directly."
            if self._first_run
            else "Toggle options and press Save. Takes effect immediately."
        )
        save_label = "Save & Start" if self._first_run else "Save"
        hint = "esc  skip and use defaults" if self._first_run else "esc  cancel"

        with Vertical(id="setup-dialog"):
            yield Label(title, id="setup-title")
            yield Static(desc, id="setup-desc")
            yield Static("", classes="setup-spacer")

            yield Static("DATA SOURCES", classes="setup-section")
            with Horizontal(classes="setup-row"):
                yield Static("Google Tasks", classes="setup-option-label")
                yield Switch(value=self._get("sources", "google_tasks"), id="sw-google-tasks")
            with Horizontal(classes="setup-row"):
                yield Static("Beads issues", classes="setup-option-label")
                yield Switch(value=self._get("sources", "beads"), id="sw-beads")
            with Horizontal(classes="setup-row"):
                yield Static("Search root", classes="setup-option-label")
                yield Input(
                    value=self._get("sources", "beads_search_root"),
                    placeholder="e.g. ~/Code",
                    id="sw-search-root",
                )

            yield Static("", classes="setup-spacer")
            yield Static("SYNC  (Beads → Google Tasks)", classes="setup-section")
            with Horizontal(classes="setup-row"):
                yield Static("Enable sync", classes="setup-option-label")
                yield Switch(value=self._get("sync", "enabled"), id="sw-sync-enabled")
            with Horizontal(classes="setup-row"):
                yield Static("Auto-sync on start", classes="setup-option-label")
                yield Switch(value=self._get("sync", "auto_sync_on_start"), id="sw-auto-sync")

            if not self._first_run:
                yield Static("", classes="setup-spacer")
                yield Static("PROJECTS  (sync  visible  label)", classes="setup-section")
                yield Static("Discovering projects…", id="projects-loading")

            yield Static("", classes="setup-spacer")
            yield Button(save_label, id="setup-save", variant="primary")
            yield Static(hint, id="setup-hint")

    def on_mount(self) -> None:
        if not self._first_run:
            self._discover_projects()

    @work(thread=True)
    def _discover_projects(self) -> None:
        workspaces = discover_beads_workspaces()
        self.app.call_from_thread(self._populate_projects, workspaces)

    def _populate_projects(self, workspaces: dict[str, str]) -> None:
        loading = self.query_one("#projects-loading", Static)
        loading.remove()
        dialog = self.query_one("#setup-dialog", Vertical)
        save_btn = self.query_one("#setup-save", Button)
        for workspace_path in sorted(workspaces):
            name = Path(workspace_path).name
            proj = get_project_config(name, self._initial)
            row = ProjectRow(name=name, sync=proj["sync"], visible=proj["visible"], label=proj["label"])
            dialog.mount(row, before=save_btn)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-save":
            beads_on = self.query_one("#sw-beads", Switch).value
            search_root = self.query_one("#sw-search-root", Input).value.strip()
            if beads_on and search_root and not Path(search_root).expanduser().exists():
                self.notify("Search root path does not exist", severity="error")
                return
            if beads_on and not search_root:
                self.notify("Search root path is required when beads is enabled", severity="error")
                return
            projects: dict[str, dict] = dict(self._initial.get("projects", {}))
            for row in self.query(ProjectRow):
                projects[row.project_name] = row.get_values()
            self.dismiss({
                "sync": {
                    "enabled": self.query_one("#sw-sync-enabled", Switch).value,
                    "auto_sync_on_start": self.query_one("#sw-auto-sync", Switch).value,
                },
                "sources": {
                    "google_tasks": self.query_one("#sw-google-tasks", Switch).value,
                    "beads": self.query_one("#sw-beads", Switch).value,
                    "beads_search_root": search_root,
                },
                "projects": projects,
            })

    def action_skip(self) -> None:
        self.dismiss(None)
