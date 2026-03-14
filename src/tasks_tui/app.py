"""Google Tasks terminal UI."""

import calendar as cal_mod
from datetime import date as DateType
from datetime import datetime, timedelta
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    Switch,
    TextArea,
)
from textual import work

from tasks_tui.beads_api import (
    STATUSES,
    BeadsIssue,
    create_beads_child_issue,
    discover_beads_workspaces,
    get_beads_label,
    list_beads_issues,
    set_beads_label,
    update_beads_issue,
)
from tasks_tui.config import CONFIG_PATH, DEFAULTS, get_project_config, load_config, save_config
from tasks_tui.sync import SyncEngine
from tasks_tui.tasks_api import (
    Task,
    complete_task,
    create_subtask,
    create_task,
    delete_task,
    list_completed_tasks,
    list_tasks,
    uncomplete_task,
    update_task,
)


class SectionHeader(ListItem):
    def __init__(self, label: str, variant: str = "default") -> None:
        super().__init__()
        self._label = label
        self._variant = variant

    def compose(self) -> ComposeResult:
        yield Static(
            f"▸ {self._label}", classes=f"section-header section-header-{self._variant}"
        )


class TaskItem(ListItem):
    def __init__(self, task: Task, is_subtask: bool = False) -> None:
        super().__init__()
        self.gtask = task
        self._is_subtask = is_subtask

    def compose(self) -> ComposeResult:
        if self.gtask.completed:
            icon = "✓"
            icon_class = "completed"
            title_class = "task-title completed-title"
            date_text = self.gtask.completed_label
            date_class = "completed-label"
        else:
            icon = "!" if self.gtask.is_overdue else "○"
            icon_class = "overdue" if self.gtask.is_overdue else "pending"
            title_class = "task-title"
            date_text = self.gtask.due_label
            date_class = self.gtask.due_css_class

        row_class = "task-row subtask-row" if self._is_subtask else "task-row"
        label_text = f"\\[{self.gtask.label}]" if self.gtask.label else " "
        with Horizontal(classes=row_class):
            if self._is_subtask:
                yield Static("↳", classes="subtask-prefix")
            yield Static(icon, classes=f"task-icon {icon_class}")
            yield Static(label_text, classes="task-label task-label-gtask")
            yield Static(self.gtask.display_title, classes=title_class)
            if date_text:
                yield Static(date_text, classes=date_class)


class BeadsItem(ListItem):
    def __init__(self, issue: BeadsIssue, depth: int = 0, project_label: str = "") -> None:
        super().__init__()
        self.issue = issue
        self._depth = depth
        self._project_label = project_label or issue.project

    def compose(self) -> ComposeResult:
        row_class = "task-row beads-subtask-row" if self._depth > 0 else "task-row"
        beads_label = get_beads_label(self.issue.id, self._project_label)
        with Horizontal(classes=row_class):
            if self._depth > 0:
                yield Static("↳", classes="subtask-prefix")
            yield Static(
                self.issue.status_icon,
                classes=f"task-icon {self.issue.status_css_class}",
            )
            yield Static(f"\\[{beads_label}]", classes="task-label task-label-beads")
            yield Static(self.issue.title, classes="task-title")
            if self.issue.due_label:
                yield Static(self.issue.due_label, classes=self.issue.due_css_class)


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


def _iso_to_date(iso: str) -> DateType | None:
    """Convert ISO 8601 string to date, or None."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _format_date_label(iso: str) -> str:
    """Format an ISO date string for display in the date button."""
    d = _iso_to_date(iso)
    if d is None:
        return "📅  No date"
    return f"📅  {d.strftime('%b %-d, %Y')}"


def _parse_date_input(raw: str) -> DateType | None:
    """Parse a due date input string to a date object, for pre-populating the picker."""
    iso = _parse_due(raw.strip())
    if iso:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return None


def _parse_due(raw: str) -> str:
    """Parse a human-readable date into ISO 8601 string, or return ''."""
    if not raw:
        return ""
    raw = raw.strip().lower()
    today = datetime.now().date()
    if raw == "today":
        return today.isoformat() + "T00:00:00.000Z"
    if raw == "tomorrow":
        return (today + timedelta(days=1)).isoformat() + "T00:00:00.000Z"
    for fmt in ("%Y-%m-%d", "%b %d %Y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            return parsed.isoformat() + "T00:00:00.000Z"
        except ValueError:
            continue
    # "Mar 15" — no year, infer current or next year
    try:
        parsed = datetime.strptime(f"{raw} {today.year}", "%b %d %Y").date()
        if parsed < today:
            parsed = parsed.replace(year=today.year + 1)
        return parsed.isoformat() + "T00:00:00.000Z"
    except ValueError:
        pass
    return ""


class GTasksApp(App):
    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        background: $primary;
        color: $text;
    }

    ListView {
        height: 1fr;
        border: none;
        padding: 0 1;
        scrollbar-color: $primary 30%;
        scrollbar-color-hover: $primary;
    }

    ListItem {
        padding: 0;
        height: 1;
    }

    ListItem:focus-within, ListItem.--highlight {
        background: $primary 15%;
    }

    .task-row {
        height: 1;
        width: 100%;
    }

    .task-icon {
        width: 3;
        color: $text-muted;
    }

    .task-icon.pending {
        color: $text-muted;
    }

    .task-icon.overdue {
        color: $error;
        text-style: bold;
    }

    .task-icon.completed {
        color: $success;
    }

    .subtask-row {
        padding-left: 2;
    }

    .subtask-prefix {
        width: 2;
        color: $text-muted;
    }

    .task-title {
        width: 1fr;
        color: $text;
    }

    .due-label {
        width: 12;
        text-align: right;
        color: $text-muted;
    }

    .due-overdue {
        width: 12;
        text-align: right;
        color: $error;
        text-style: bold;
    }

    .due-urgent {
        width: 12;
        text-align: right;
        color: $warning;
    }

    .due-soon {
        width: 12;
        text-align: right;
        color: $success;
    }

    .completed-title {
        color: $text-muted;
        text-style: strike;
    }

    .completed-label {
        width: 12;
        text-align: right;
        color: $text-muted;
    }

    .section-header {
        text-align: left;
        height: 1;
        padding: 0 1;
        text-style: bold;
        background: $boost;
    }

    .section-header-open {
        color: $primary;
    }

    .section-header-completed {
        color: $success;
    }

    SectionHeader {
        height: 1;
        padding: 0;
    }

    SectionHeader:focus-within, SectionHeader.--highlight {
        background: $boost;
    }

    /* Modal dialogs */
    #new-task-dialog {
        background: $panel;
        border: round $primary;
        padding: 1 2;
        width: 60;
        height: auto;
        align: center middle;
    }

    #datepicker-dialog {
        background: $panel;
        border: round $primary;
        padding: 1 2;
        width: 36;
        height: auto;
        align: center middle;
    }

    #datepicker-month {
        text-align: center;
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    #datepicker-cal {
        color: $text;
        margin-bottom: 1;
    }

    .due-row {
        height: 3;
        margin-bottom: 1;
    }

    .due-btn {
        width: 1fr;
    }

    .clear-btn {
        width: 5;
        margin-left: 1;
    }

    #dialog-title {
        text-style: bold;
        margin-bottom: 1;
        color: $primary;
    }

    Input {
        margin-bottom: 1;
    }

    #dialog-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }

    #detail-dialog {
        background: $panel;
        border: round $primary;
        padding: 1 2;
        width: 70;
        height: 24;
        align: center middle;
    }

    #detail-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #detail-meta {
        color: $text-muted;
        margin-bottom: 1;
    }

    #detail-divider {
        color: $text-muted;
        margin-bottom: 1;
    }

    #detail-notes {
        height: 1fr;
        border: none;
    }

    #task-notes {
        height: 6;
        margin-bottom: 1;
    }

    #empty-label {
        color: $text-muted;
        text-align: center;
        margin-top: 4;
    }

    .section-empty {
        color: $text-muted;
        padding: 0 3;
    }

    .task-label {
        width: 14;
        text-style: bold;
    }

    .task-label-gtask {
        color: $primary;
    }

    .task-label-beads {
        color: $accent;
    }

    .beads-open {
        color: $text-muted;
    }

    .beads-inprogress {
        color: $warning;
        text-style: bold;
    }

    .beads-blocked {
        color: $error;
        text-style: bold;
    }

    .beads-deferred {
        color: $text-muted;
        text-style: dim;
    }

    .section-header-beads {
        color: $accent;
    }

    .beads-meta-row {
        height: 3;
        margin-bottom: 1;
    }

    .beads-cycle-btn {
        width: 1fr;
        margin-right: 1;
    }

    .beads-subtask-row {
        padding-left: 2;
    }

    .sync-status {
        height: 1;
        color: $text-muted;
        text-align: right;
        padding: 0 1;
        background: $boost;
    }

    /* Setup / first-run screen */
    #setup-dialog {
        background: $panel;
        border: round $primary;
        padding: 2 3;
        width: 56;
        height: auto;
        align: center middle;
    }

    #setup-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        text-align: center;
    }

    #setup-desc {
        color: $text-muted;
        margin-bottom: 1;
        text-align: center;
    }

    .setup-section {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    .setup-row {
        height: 3;
        margin-bottom: 0;
        align: left middle;
    }

    .setup-option-label {
        width: 1fr;
        color: $text;
    }

    .setup-spacer {
        height: 1;
    }

    #setup-save {
        width: 100%;
        margin-top: 1;
    }

    #setup-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }

    .project-row {
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }

    .project-name {
        width: 14;
        color: $text;
    }

    .project-label-input {
        width: 1fr;
    }

    #projects-loading {
        color: $text-muted;
        margin: 1 0;
    }

    /* Project filter panel */
    #filter-dialog {
        background: $panel;
        border: round $primary;
        padding: 1 2;
        width: 44;
        height: auto;
        max-height: 70vh;
        align: center middle;
    }

    #filter-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #filter-search {
        margin-bottom: 1;
    }

    #filter-rows {
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }

    .filter-row {
        height: auto;
        padding-bottom: 1;
        align: left middle;
    }

    .filter-name {
        width: 1fr;
        color: $text;
    }

    #filter-hint {
        color: $text-muted;
        text-align: center;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("n", "new_task", "New"),
        Binding("s", "new_subtask", "Subtask"),
        Binding("enter", "open_task", "Open"),
        Binding("e", "edit_task", "Edit"),
        Binding("space", "toggle_complete", "Check/Uncheck"),
        Binding("d", "delete_task", "Delete"),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("ctrl+s", "sync", "Sync"),
        Binding("f", "filter_projects", "Filter"),
        Binding("p", "config", "Prefs"),
    ]

    TITLE = "Google Tasks"

    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._tasks: list[Task] = []
        self._completed_tasks: list[Task] = []
        self._beads_issues: list[BeadsIssue] = []
        self._sync_running: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(id="task-list")
        yield Static("", id="sync-status", classes="sync-status")
        yield Footer()

    def on_mount(self) -> None:
        if not CONFIG_PATH.exists():
            self.push_screen(SetupScreen(first_run=True), self._on_setup_done)
        else:
            self._start_app()

    def _on_setup_done(self, config: dict | None) -> None:
        if config is not None:
            save_config(config)
            self._config = config
        self._start_app()

    def _start_app(self) -> None:
        self._load_tasks()
        if self._config["sync"]["enabled"] and self._config["sync"]["auto_sync_on_start"]:
            self.action_sync()

    def _load_tasks(self) -> None:
        if self._config["sources"]["google_tasks"]:
            try:
                self._tasks = list_tasks()
                self._completed_tasks = list_completed_tasks()
            except Exception as e:
                self.notify(f"Failed to load tasks: {e}", severity="error")
                self._tasks = []
                self._completed_tasks = []
        else:
            self._tasks = []
            self._completed_tasks = []
        if self._config["sources"]["beads"]:
            try:
                self._beads_issues = [
                    i for i in list_beads_issues()
                    if get_project_config(i.project, self._config)["visible"]
                ]
            except Exception:
                self._beads_issues = []
        else:
            self._beads_issues = []
        self._render_tasks()

    def _render_tasks(self) -> None:
        lv = self.query_one("#task-list", ListView)
        lv.clear()
        if not self._tasks and not self._completed_tasks and not self._beads_issues:
            lv.append(
                ListItem(Static("No tasks. Press [n] to create one.", id="empty-label"))
            )
            return

        subtasks_by_parent: dict[str, list[Task]] = {}
        for t in self._tasks:
            if t.parent_id:
                subtasks_by_parent.setdefault(t.parent_id, []).append(t)

        issue_ids = {i.id for i in self._beads_issues}
        children_by_parent: dict[str, list[BeadsIssue]] = {}
        beads_top_level: list[BeadsIssue] = []
        for issue in self._beads_issues:
            if issue.parent_id and issue.parent_id in issue_ids:
                children_by_parent.setdefault(issue.parent_id, []).append(issue)
            else:
                beads_top_level.append(issue)

        def _append_beads(issue: BeadsIssue, depth: int = 0) -> None:
            proj_label = get_project_config(issue.project, self._config)["label"]
            lv.append(BeadsItem(issue, depth=depth, project_label=proj_label))
            for child in children_by_parent.get(issue.id, []):
                _append_beads(child, depth + 1)

        def _beads_days(i: BeadsIssue) -> int | None:
            if not i.due_at:
                return None
            try:
                due_dt = datetime.fromisoformat(i.due_at.replace("Z", "+00:00")).date()
                return (due_dt - datetime.now().date()).days
            except ValueError:
                return None

        # Unified open list: (task|beads, item) sorted by (no_date, days, label)
        open_items: list[tuple[str, Task | BeadsIssue]] = []
        for t in self._tasks:
            if not t.parent_id:
                open_items.append(("task", t))
        for i in beads_top_level:
            open_items.append(("beads", i))

        def _sort_key(entry: tuple) -> tuple:
            kind, item = entry
            if kind == "task":
                days = item.days_until_due
                label = item.label
            else:
                days = _beads_days(item)
                proj_label = get_project_config(item.project, self._config)["label"]
                label = get_beads_label(item.id, proj_label)
            return (days is None, days or 0, label)

        open_items.sort(key=_sort_key)

        lv.append(SectionHeader("Open", variant="open"))
        if open_items:
            for kind, item in open_items:
                if kind == "task":
                    lv.append(TaskItem(item))
                    for subtask in subtasks_by_parent.get(item.id, []):
                        lv.append(TaskItem(subtask, is_subtask=True))
                else:
                    _append_beads(item)
        else:
            lv.append(ListItem(Static("No open tasks.", classes="section-empty")))
        if self._completed_tasks:
            lv.append(ListItem(Static("")))
            lv.append(SectionHeader("Completed", variant="completed"))
            for task in self._completed_tasks:
                lv.append(TaskItem(task))

    def _selected_task(self) -> Task | None:
        lv = self.query_one("#task-list", ListView)
        if lv.highlighted_child is None:
            return None
        item = lv.highlighted_child
        if isinstance(item, TaskItem):
            return item.gtask
        return None

    def _selected_beads_issue(self) -> BeadsIssue | None:
        lv = self.query_one("#task-list", ListView)
        if lv.highlighted_child is None:
            return None
        item = lv.highlighted_child
        if isinstance(item, BeadsItem):
            return item.issue
        return None

    def action_sync(self) -> None:
        if not self._config["sync"]["enabled"]:
            self.notify("Sync is disabled in config", severity="warning")
            return
        if self._sync_running:
            self.notify("Sync already in progress", severity="warning")
            return
        self._sync_running = True
        self._update_sync_status("Syncing…")
        self._sync_worker()

    @work(thread=True)
    def _sync_worker(self) -> None:
        messages: list[str] = []
        error = False
        try:
            SyncEngine(config=self._config).run(progress=messages.append)
        except Exception as e:
            messages.append(f"Sync error: {e}")
            error = True

        last_msg = messages[-1] if messages else "Sync complete"
        if error or "error" in last_msg.lower():
            self.call_from_thread(self._on_sync_done, last_msg, True)
        else:
            now = datetime.now().strftime("%H:%M")
            self.call_from_thread(self._on_sync_done, f"Last synced {now}", False)

    def _update_sync_status(self, msg: str) -> None:
        try:
            self.query_one("#sync-status", Static).update(msg)
        except Exception:
            pass

    def _on_sync_done(self, status_msg: str, error: bool) -> None:
        self._sync_running = False
        self._update_sync_status(status_msg)
        if not error:
            self._load_tasks()

    def action_refresh(self) -> None:
        self._load_tasks()
        self.notify("Refreshed")

    def action_open_task(self) -> None:
        issue = self._selected_beads_issue()
        if issue:

            def on_detail_closed(wants_edit: bool) -> None:
                if wants_edit:
                    self._open_beads_edit(issue)

            self.push_screen(BeadsDetailScreen(issue), on_detail_closed)
            return
        task = self._selected_task()
        if not task:
            return

        def on_closed(wants_edit: bool) -> None:
            if wants_edit:
                self.action_edit_task()

        self.push_screen(TaskDetailScreen(task), on_closed)

    def action_new_task(self) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_task(result["title"], due=result.get("due", ""))
                    self._load_tasks()
                    self.notify(f"Created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed to create task: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def action_new_subtask(self) -> None:
        issue = self._selected_beads_issue()
        if issue:
            self._new_beads_subtask(issue)
            return
        task = self._selected_task()
        if not task:
            self.notify("Select a task first", severity="warning")
            return
        # Subtasks can only be created under top-level tasks
        parent_id = task.parent_id if task.parent_id else task.id

        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_subtask(
                        result["title"], parent_id, due=result.get("due", "")
                    )
                    self._load_tasks()
                    self.notify(f"Subtask created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def _new_beads_subtask(self, parent: BeadsIssue) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_beads_child_issue(parent, result["title"], due=result.get("due", ""))
                    self._load_tasks()
                    self.notify(f"Subtask created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def action_toggle_complete(self) -> None:
        if self._selected_beads_issue():
            self.notify("Use e to edit status on Beads tasks", severity="warning")
            return
        task = self._selected_task()
        if not task:
            return
        try:
            if task.completed:
                uncomplete_task(task.id)
                self._load_tasks()
                self.notify(f"Reopened: {task.title}")
            else:
                complete_task(task.id)
                self._load_tasks()
                self.notify(f"Completed: {task.title}")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")

    def _open_beads_edit(self, issue: BeadsIssue) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                try:
                    set_beads_label(issue.id, result["label"], issue.project)
                    update_beads_issue(
                        issue,
                        title=result["title"],
                        status=result["status"],
                        priority=result["priority"],
                        description=result["description"],
                        due=result["due"],
                    )
                    self._load_tasks()
                    self.notify(f"Updated: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(BeadsEditScreen(issue), on_result)

    def action_edit_task(self) -> None:
        issue = self._selected_beads_issue()
        if issue:
            self._open_beads_edit(issue)
            return
        task = self._selected_task()
        if not task:
            return

        def on_result(result: dict | None) -> None:
            if result:
                try:
                    update_task(
                        task.id,
                        result["title"],
                        due=result.get("due", ""),
                        notes=result.get("notes", ""),
                    )
                    self._load_tasks()
                    self.notify(f"Updated: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(EditTaskScreen(task), on_result)

    def action_delete_task(self) -> None:
        if self._selected_beads_issue():
            self.notify("Beads tasks are read-only", severity="warning")
            return
        task = self._selected_task()
        if not task:
            return
        try:
            delete_task(task.id)
            self._load_tasks()
            self.notify(f"Deleted: {task.title}")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")

    def action_filter_projects(self) -> None:
        def on_result(projects: dict | None) -> None:
            if projects is not None:
                self._config.setdefault("projects", {}).update(projects)
                save_config(self._config)
                self._load_tasks()

        self.push_screen(ProjectFilterScreen(config=self._config), on_result)

    def action_config(self) -> None:
        def on_result(config: dict | None) -> None:
            if config is not None:
                save_config(config)
                self._config = config
                self._load_tasks()
                self.notify("Configuration saved")

        self.push_screen(SetupScreen(config=self._config), on_result)


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
        Binding("a", "select_all", "All"),
        Binding("n", "deselect_all", "None"),
    ]

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-dialog"):
            yield Label("PROJECTS", id="filter-title")
            yield Input(placeholder="Search…", id="filter-search")
            yield Vertical(id="filter-rows")
            yield Static("a all · n none · esc close", id="filter-hint")

    def on_mount(self) -> None:
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
                    "beads_search_root": self.query_one("#sw-search-root", Input).value,
                },
                "projects": projects,
            })

    def action_skip(self) -> None:
        self.dismiss(None)


def main() -> None:
    GTasksApp().run()


if __name__ == "__main__":
    main()
