"""Reusable list-item widgets for the task list view."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import ListItem, Static

from tasks_tui.beads_api import BeadsIssue, get_beads_label
from tasks_tui.tasks_api import Task


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
