"""Tests for the Textual UI — key bindings and actions."""

from unittest.mock import patch

import pytest

from gtasks_tui.app import GTasksApp
from gtasks_tui.tasks_api import Task

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

OPEN_TASKS = [
    Task(
        id="1", title="Buy milk", status="needsAction", due="2026-03-13T00:00:00.000Z"
    ),
    Task(id="2", title="Call dentist", status="needsAction"),
    Task(
        id="3",
        title="Overdue report",
        status="needsAction",
        due="2026-03-10T00:00:00.000Z",
    ),
]

COMPLETED_TASKS = [
    Task(
        id="4",
        title="Send invoice",
        status="completed",
        completed_at="2026-03-11T00:00:00.000Z",
    ),
]

NO_TASKS: list[Task] = []


def _mock_load(open_tasks=NO_TASKS, completed_tasks=NO_TASKS):
    return (
        patch("gtasks_tui.app.list_tasks", return_value=open_tasks),
        patch("gtasks_tui.app.list_completed_tasks", return_value=completed_tasks),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renders_open_tasks():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            titles = [i.gtask.title for i in items]
            assert "Buy milk" in titles
            assert "Call dentist" in titles
            assert "Overdue report" in titles


@pytest.mark.asyncio
async def test_renders_completed_tasks(freezegun_today):
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            assert any(i.gtask.title == "Send invoice" for i in items)


@pytest.mark.asyncio
async def test_renders_open_section_header():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            headers = list(pilot.app.query("SectionHeader"))
            labels = [h._label for h in headers]
            assert "Open" in labels


@pytest.mark.asyncio
async def test_renders_completed_section_header(freezegun_today):
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            headers = list(pilot.app.query("SectionHeader"))
            labels = [h._label for h in headers]
            assert "Completed" in labels


@pytest.mark.asyncio
async def test_renders_empty_state():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            assert len(list(pilot.app.query("TaskItem"))) == 0
            assert pilot.app.query_one("#empty-label") is not None


# ---------------------------------------------------------------------------
# n — new task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_task_created():
    created = []

    def fake_create(title, due=""):
        created.append(title)
        return Task(id="new", title=title, status="needsAction")

    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.create_task", side_effect=fake_create),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.press("n")
            await pilot.pause()
            await pilot.press(*"Walk the dog")
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert "Walk the dog" in created


@pytest.mark.asyncio
async def test_new_task_cancelled_with_escape():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.create_task") as mock_create,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.press("n")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# space — toggle complete / uncomplete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_space_completes_open_task():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.complete_task") as mock_complete,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 1  # index 0 is the SectionHeader
            await pilot.pause()
            pilot.app.action_toggle_complete()
            await pilot.pause()
            mock_complete.assert_called_once_with("1", list_id="")


@pytest.mark.asyncio
async def test_space_uncompletes_completed_task(freezegun_today):
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS),
        patch("gtasks_tui.app.uncomplete_task") as mock_uncomplete,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 4  # 0=Open header, 1=no open tasks, 2=spacer, 3=Completed header, 4=task
            await pilot.pause()
            pilot.app.action_toggle_complete()
            await pilot.pause()
            mock_uncomplete.assert_called_once_with("4", list_id="")


@pytest.mark.asyncio
async def test_space_on_section_header_does_nothing():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.complete_task") as mock_complete,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 0  # SectionHeader
            await pilot.pause()
            pilot.app.action_toggle_complete()
            await pilot.pause()
            mock_complete.assert_not_called()


# ---------------------------------------------------------------------------
# d — delete task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_open_task():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.delete_task") as mock_delete,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 1
            await pilot.pause()
            pilot.app.action_delete_task()
            await pilot.pause()
            mock_delete.assert_called_once_with("1", list_id="")


@pytest.mark.asyncio
async def test_delete_completed_task(freezegun_today):
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS),
        patch("gtasks_tui.app.delete_task") as mock_delete,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 4  # 0=Open header, 1=no open tasks, 2=spacer, 3=Completed header, 4=task
            await pilot.pause()
            pilot.app.action_delete_task()
            await pilot.pause()
            mock_delete.assert_called_once_with("4", list_id="")


@pytest.mark.asyncio
async def test_delete_on_section_header_does_nothing():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.delete_task") as mock_delete,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 0
            await pilot.pause()
            pilot.app.action_delete_task()
            await pilot.pause()
            mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# e — edit task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_task_updates_title():
    updated = {}

    def fake_update(task_id, title, list_id="", due="", notes=""):
        updated["id"] = task_id
        updated["title"] = title

    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.update_task", side_effect=fake_update),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_task = lambda: OPEN_TASKS[0]
            pilot.app.action_edit_task()
            await pilot.pause()
            title_input = pilot.app.screen.query_one("#task-title")
            title_input.clear()
            await pilot.press(*"Buy oat milk")
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("title") == "Buy oat milk"
            assert updated.get("id") == "1"


@pytest.mark.asyncio
async def test_edit_cancelled_with_escape():
    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.update_task") as mock_update,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_task = lambda: OPEN_TASKS[0]
            pilot.app.action_edit_task()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_edit_task_updates_notes():
    updated = {}

    def fake_update(task_id, title, list_id="", due="", notes=""):
        updated["notes"] = notes

    with (
        patch("gtasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.update_task", side_effect=fake_update),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_task = lambda: OPEN_TASKS[0]
            pilot.app.action_edit_task()
            await pilot.pause()
            notes_area = pilot.app.screen.query_one("#task-notes")
            notes_area.text = "My notes"
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("notes") == "My notes"


@pytest.mark.asyncio
async def test_edit_task_preserves_existing_due():
    updated = {}

    def fake_update(task_id, title, list_id="", due="", notes=""):
        updated["due"] = due

    task_with_due = OPEN_TASKS[0]
    with (
        patch("gtasks_tui.app.list_tasks", return_value=[task_with_due]),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
        patch("gtasks_tui.app.update_task", side_effect=fake_update),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_task = lambda: task_with_due
            pilot.app.action_edit_task()
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("due") == "2026-03-13T00:00:00.000Z"


# ---------------------------------------------------------------------------
# r — refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_reloads_tasks():
    call_count = [0]

    def fake_list():
        call_count[0] += 1
        return OPEN_TASKS

    with (
        patch("gtasks_tui.app.list_tasks", side_effect=fake_list),
        patch("gtasks_tui.app.list_completed_tasks", return_value=[]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            initial = call_count[0]
            await pilot.press("r")
            await pilot.pause()
            assert call_count[0] > initial
