"""Task list rendering helpers."""

from datetime import date, datetime, timedelta

from textual.widgets import ListItem, ListView, Static

from gtasks_tui.date_utils import _iso_to_date
from gtasks_tui.tasks_api import Task
from gtasks_tui.widgets import SectionHeader, TaskItem


def render_task_list(
    lv: ListView,
    tasks: list[Task],
    completed_tasks: list[Task],
    filter_days: int | None = None,
    filter_lists: set[str] | None = None,
    sort_key: str = "due_date",
) -> None:
    """Clear and repopulate *lv* with tasks and subtasks."""
    lv.clear()

    if filter_lists is not None:
        tasks = [t for t in tasks if t.list_title in filter_lists]
        completed_tasks = [t for t in completed_tasks if t.list_title in filter_lists]

    if filter_days is not None:
        cutoff = datetime.now().date() - timedelta(days=filter_days)
        completed_tasks = [
            t
            for t in completed_tasks
            if t.completed_at and (_iso_to_date(t.completed_at) or date.min) >= cutoff
        ]

    if not tasks and not completed_tasks:
        lv.append(
            ListItem(Static("No tasks. Press [n] to create one.", id="empty-label"))
        )
        return

    subtasks_by_parent: dict[str, list[Task]] = {}
    for t in tasks:
        if t.parent_id:
            subtasks_by_parent.setdefault(t.parent_id, []).append(t)

    top_level = [t for t in tasks if not t.parent_id]
    if sort_key == "label":
        top_level.sort(
            key=lambda t: (
                not t.label,
                t.label or "",
                t.days_until_due is None,
                t.days_until_due or 0,
            )
        )
    else:
        top_level.sort(
            key=lambda t: (t.days_until_due is None, t.days_until_due or 0, t.label)
        )

    lv.append(SectionHeader("Open", variant="open"))
    if top_level:
        for task in top_level:
            lv.append(TaskItem(task))
            for subtask in subtasks_by_parent.get(task.id, []):
                lv.append(TaskItem(subtask, is_subtask=True))
    else:
        lv.append(ListItem(Static("No open tasks.", classes="section-empty")))

    if completed_tasks:
        lv.append(ListItem(Static("")))
        lv.append(SectionHeader("Completed", variant="completed"))
        for task in completed_tasks:
            lv.append(TaskItem(task))
