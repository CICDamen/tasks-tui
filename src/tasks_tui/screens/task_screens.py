"""Screens for creating, editing, and viewing Google Tasks."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

from tasks_tui.date_utils import _format_date_label, _iso_to_date
from tasks_tui.screens.shared import DatePickerScreen
from tasks_tui.tasks_api import Task


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
