"""Task list rendering helpers.

Provides ``render_task_list``, which populates a Textual ``ListView`` with the
combined set of Google Tasks and Beads issues, grouped and sorted by due date.
"""

from datetime import datetime

from textual.widgets import ListItem, ListView, Static

from tasks_tui.beads_api import BeadsIssue, get_beads_label
from tasks_tui.config import get_project_config
from tasks_tui.tasks_api import Task
from tasks_tui.widgets import BeadsItem, SectionHeader, TaskItem


def render_task_list(
    lv: ListView,
    tasks: list[Task],
    completed_tasks: list[Task],
    beads_issues: list[BeadsIssue],
    config: dict,
) -> None:
    """Clear and repopulate *lv* with tasks, subtasks, and beads issues."""
    lv.clear()

    if not tasks and not completed_tasks and not beads_issues:
        lv.append(
            ListItem(Static("No tasks. Press [n] to create one.", id="empty-label"))
        )
        return

    # ── Google Tasks hierarchy ────────────────────────────────────────────────
    subtasks_by_parent: dict[str, list[Task]] = {}
    for t in tasks:
        if t.parent_id:
            subtasks_by_parent.setdefault(t.parent_id, []).append(t)

    # ── Beads hierarchy ───────────────────────────────────────────────────────
    issue_ids = {i.id for i in beads_issues}
    children_by_parent: dict[str, list[BeadsIssue]] = {}
    beads_top_level: list[BeadsIssue] = []
    for issue in beads_issues:
        if issue.parent_id and issue.parent_id in issue_ids:
            children_by_parent.setdefault(issue.parent_id, []).append(issue)
        else:
            beads_top_level.append(issue)

    def _append_beads(issue: BeadsIssue, depth: int = 0) -> None:
        proj_label = get_project_config(issue.project, config)["label"]
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

    # ── Unified open list sorted by (no_date, days, label) ───────────────────
    open_items: list[tuple[str, Task | BeadsIssue]] = []
    for t in tasks:
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
            proj_label = get_project_config(item.project, config)["label"]
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

    if completed_tasks:
        lv.append(ListItem(Static("")))
        lv.append(SectionHeader("Completed", variant="completed"))
        for task in completed_tasks:
            lv.append(TaskItem(task))
