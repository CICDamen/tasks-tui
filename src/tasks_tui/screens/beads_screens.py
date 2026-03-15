"""Screens for viewing and editing Beads issues."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

from tasks_tui.beads_api import STATUSES, BeadsIssue, get_beads_label
from tasks_tui.date_utils import _format_date_label, _iso_to_date
from tasks_tui.screens.shared import DatePickerScreen


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
