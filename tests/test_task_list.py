"""Tests for render_task_list sort behavior."""

from unittest.mock import patch

import pytest

from gtasks_tui.app import GTasksApp
from gtasks_tui.tasks_api import Task

SORT_TASKS = [
    Task(
        id="1",
        title="[Work] Report",
        status="needsAction",
        due="2026-03-15T00:00:00.000Z",
    ),
    Task(
        id="2",
        title="[Home] Groceries",
        status="needsAction",
        due="2026-03-13T00:00:00.000Z",
    ),
    Task(
        id="3",
        title="Unlabeled urgent",
        status="needsAction",
        due="2026-03-12T00:00:00.000Z",
    ),
    Task(id="4", title="[Home] Clean", status="needsAction"),
]


@pytest.mark.asyncio
async def test_default_sort_due_date_order(freezegun_today):
    """Default (due date) sort: most urgent first, no-due-date last."""
    tasks = [
        Task(id="1", title="No due date", status="needsAction"),
        Task(
            id="2",
            title="Due in 3 days",
            status="needsAction",
            due="2026-03-15T00:00:00.000Z",
        ),
        Task(
            id="3",
            title="Due today",
            status="needsAction",
            due="2026-03-12T00:00:00.000Z",
        ),
    ]
    with (
        patch("gtasks_tui.app.list_tasks", return_value=tasks),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            titles = [i.gtask.title for i in items]
            assert titles.index("Due today") < titles.index("Due in 3 days")
            assert titles.index("Due in 3 days") < titles.index("No due date")


@pytest.mark.asyncio
async def test_label_sort_alphabetical_and_unlabeled_last(freezegun_today):
    """Label sort: alphabetical by label, unlabeled tasks last."""
    with (
        patch("gtasks_tui.app.list_tasks", return_value=SORT_TASKS),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._sort_key = "label"
            pilot.app._apply_loaded_tasks(SORT_TASKS, [])
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            titles = [i.gtask.title for i in items]
            # Home tasks come before Work (alphabetical)
            assert titles.index("[Home] Groceries") < titles.index("[Work] Report")
            assert titles.index("[Home] Clean") < titles.index("[Work] Report")
            # Unlabeled comes last
            assert titles.index("Unlabeled urgent") > titles.index("[Work] Report")


@pytest.mark.asyncio
async def test_label_sort_secondary_due_date_within_label(freezegun_today):
    """Label sort: within the same label, due date is the secondary sort."""
    with (
        patch("gtasks_tui.app.list_tasks", return_value=SORT_TASKS),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._sort_key = "label"
            pilot.app._apply_loaded_tasks(SORT_TASKS, [])
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            titles = [i.gtask.title for i in items]
            # Within [Home]: Groceries (due Mar 13) before Clean (no due)
            assert titles.index("[Home] Groceries") < titles.index("[Home] Clean")
