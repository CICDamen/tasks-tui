"""Reusable list-item widgets for the task list view."""

import hashlib

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import ListItem, Static

from gtasks_tui.tasks_api import Task


# Six distinct colors for terminal — assigned to lists via hash
_LIST_COLOR_COUNT = 6


def _list_color_class(list_title: str) -> str:
    index = int(hashlib.md5(list_title.encode()).hexdigest(), 16) % _LIST_COLOR_COUNT
    return f"task-label-color-{index}"


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
        label = self.gtask.label or self.gtask.list_title
        label_text = f"\\[{label}]" if label else " "
        color_class = _list_color_class(label) if label else "task-label-color-0"
        with Horizontal(classes=row_class):
            if self._is_subtask:
                yield Static("↳", classes="subtask-prefix")
            yield Static(icon, classes=f"task-icon {icon_class}")
            yield Static(label_text, classes=f"task-label {color_class}")
            yield Static(self.gtask.display_title, classes=title_class)
            if date_text:
                yield Static(date_text, classes=date_class)
