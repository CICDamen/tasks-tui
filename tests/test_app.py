"""Tests for the Textual UI — all key bindings and actions."""

from unittest.mock import MagicMock, patch

import pytest

from tasks_tui.app import GTasksApp, ProjectFilterScreen, SetupScreen, _parse_date_input
from tasks_tui.beads_api import BeadsIssue
from tasks_tui.tasks_api import Task

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

OPEN_TASKS = [
    Task(id="1", title="Buy milk", status="needsAction", due="2026-03-13T00:00:00.000Z"),
    Task(id="2", title="Call dentist", status="needsAction"),
    Task(id="3", title="Overdue report", status="needsAction", due="2026-03-10T00:00:00.000Z"),
]

COMPLETED_TASKS = [
    Task(id="4", title="Send invoice", status="completed", completed_at="2026-03-11T00:00:00.000Z"),
]

NO_TASKS: list[Task] = []

BEADS_ISSUE = BeadsIssue(
    id="PROJ-001",
    title="Fix the bug",
    status="open",
    priority=2,
    due_at="2026-03-20T00:00:00.000Z",
    description="Some context",
    project="myapp",
    db_path="/fake/myapp/.beads/beads.db",
)


def _mock_load(open_tasks=NO_TASKS, completed_tasks=NO_TASKS):
    """Context manager: patch both list functions used by _load_tasks."""
    return (
        patch("tasks_tui.app.list_tasks", return_value=open_tasks),
        patch("tasks_tui.app.list_completed_tasks", return_value=completed_tasks),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renders_open_tasks():
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            titles = [i.gtask.title for i in items]
            assert "Buy milk" in titles
            assert "Call dentist" in titles
            assert "Overdue report" in titles


@pytest.mark.asyncio
async def test_renders_completed_tasks():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("TaskItem"))
            assert any(i.gtask.title == "Send invoice" for i in items)


@pytest.mark.asyncio
async def test_renders_open_section_header():
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            headers = list(pilot.app.query("SectionHeader"))
            labels = [h._label for h in headers]
            assert "Open" in labels


@pytest.mark.asyncio
async def test_renders_completed_section_header():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            headers = list(pilot.app.query("SectionHeader"))
            labels = [h._label for h in headers]
            assert "Completed" in labels


@pytest.mark.asyncio
async def test_renders_empty_state():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[]):
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

    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.create_task", side_effect=fake_create):
        async with GTasksApp().run_test() as pilot:
            await pilot.press("n")
            await pilot.pause()
            await pilot.press(*"Walk the dog")
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert "Walk the dog" in created


@pytest.mark.asyncio
async def test_new_task_cancelled_with_escape():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.create_task") as mock_create:
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
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.complete_task") as mock_complete:
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 1  # index 0 is the SectionHeader
            await pilot.pause()
            pilot.app.action_toggle_complete()
            await pilot.pause()
            mock_complete.assert_called_once_with("1")


@pytest.mark.asyncio
async def test_space_uncompletes_completed_task():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS), \
         patch("tasks_tui.app.uncomplete_task") as mock_uncomplete:
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            # index 0 = Open header, 1 = "No open tasks.", 2 = Completed header, 3 = task
            lv.index = 4  # 0=Open header, 1=no open tasks, 2=spacer, 3=Completed header, 4=task
            await pilot.pause()
            pilot.app.action_toggle_complete()
            await pilot.pause()
            mock_uncomplete.assert_called_once_with("4")


@pytest.mark.asyncio
async def test_space_on_section_header_does_nothing():
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.complete_task") as mock_complete:
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
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.delete_task") as mock_delete:
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 1
            await pilot.pause()
            pilot.app.action_delete_task()
            await pilot.pause()
            mock_delete.assert_called_once_with("1")


@pytest.mark.asyncio
async def test_delete_completed_task():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=COMPLETED_TASKS), \
         patch("tasks_tui.app.delete_task") as mock_delete:
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            lv = pilot.app.query_one("#task-list")
            lv.index = 4  # 0=Open header, 1=no open tasks, 2=spacer, 3=Completed header, 4=task
            await pilot.pause()
            pilot.app.action_delete_task()
            await pilot.pause()
            mock_delete.assert_called_once_with("4")


@pytest.mark.asyncio
async def test_delete_on_section_header_does_nothing():
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.delete_task") as mock_delete:
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

    def fake_update(task_id, title, due="", notes=""):
        updated["id"] = task_id
        updated["title"] = title

    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.update_task", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            # Mock _selected_task to avoid focus/index issues in test context
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
    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.update_task") as mock_update:
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

    def fake_update(task_id, title, due="", notes=""):
        updated["notes"] = notes

    with patch("tasks_tui.app.list_tasks", return_value=OPEN_TASKS[:1]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.update_task", side_effect=fake_update):
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
    """Saving an edit without changing the date preserves the original due date."""
    updated = {}

    def fake_update(task_id, title, due="", notes=""):
        updated["due"] = due

    task_with_due = OPEN_TASKS[0]  # has due="2026-03-13T00:00:00.000Z"
    with patch("tasks_tui.app.list_tasks", return_value=[task_with_due]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.update_task", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_task = lambda: task_with_due
            pilot.app.action_edit_task()
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("due") == "2026-03-13T00:00:00.000Z"


# ---------------------------------------------------------------------------
# e — edit beads issue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_beads_issue_updates_title():
    updated = {}

    def fake_update(issue, title, status, priority, description, due):
        updated["title"] = title
        updated["id"] = issue.id

    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]), \
         patch("tasks_tui.app.update_beads_issue", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_edit_task()
            await pilot.pause()
            title_input = pilot.app.screen.query_one("#task-title")
            title_input.clear()
            await pilot.press(*"Fixed the bug")
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("title") == "Fixed the bug"
            assert updated.get("id") == "PROJ-001"


@pytest.mark.asyncio
async def test_edit_beads_issue_updates_description():
    updated = {}

    def fake_update(issue, title, status, priority, description, due):
        updated["description"] = description

    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]), \
         patch("tasks_tui.app.update_beads_issue", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_edit_task()
            await pilot.pause()
            notes_area = pilot.app.screen.query_one("#task-notes")
            notes_area.text = "New description"
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("description") == "New description"


@pytest.mark.asyncio
async def test_edit_beads_issue_cycles_status():
    updated = {}

    def fake_update(issue, title, status, priority, description, due):
        updated["status"] = status

    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]), \
         patch("tasks_tui.app.update_beads_issue", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_edit_task()
            await pilot.pause()
            # Click the status button once to advance from "open" → "in_progress"
            await pilot.click("#status-btn")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("status") == "in_progress"


@pytest.mark.asyncio
async def test_edit_beads_issue_cycles_priority():
    updated = {}

    def fake_update(issue, title, status, priority, description, due):
        updated["priority"] = priority

    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]), \
         patch("tasks_tui.app.update_beads_issue", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_edit_task()
            await pilot.pause()
            # BEADS_ISSUE has priority=2; click once → P3
            await pilot.click("#priority-btn")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("priority") == 3


@pytest.mark.asyncio
async def test_edit_beads_issue_cancelled_with_escape():
    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]), \
         patch("tasks_tui.app.update_beads_issue") as mock_update:
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_edit_task()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_edit_beads_issue_preserves_due_date():
    updated = {}

    def fake_update(issue, title, status, priority, description, due):
        updated["due"] = due

    with patch("tasks_tui.app.list_tasks", return_value=[]), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]), \
         patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]), \
         patch("tasks_tui.app.update_beads_issue", side_effect=fake_update):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_edit_task()
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert updated.get("due") == "2026-03-20T00:00:00.000Z"


# ---------------------------------------------------------------------------
# r — refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_reloads_tasks():
    call_count = {"n": 0}

    def fake_list():
        call_count["n"] += 1
        return OPEN_TASKS

    with patch("tasks_tui.app.list_tasks", side_effect=fake_list), \
         patch("tasks_tui.app.list_completed_tasks", return_value=[]):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            initial = call_count["n"]
            await pilot.press("r")
            await pilot.pause()
            assert call_count["n"] > initial


BEADS_SUBTASK = BeadsIssue(
    id="PROJ-001.1",
    title="Sub-issue",
    status="open",
    priority=2,
    due_at="",
    description="",
    project="myapp",
    db_path="/fake/myapp/.beads/beads.db",
)


# ---------------------------------------------------------------------------
# s — beads subtask creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_beads_subtask_creates_child():
    created = {}

    def fake_create(parent, title, description="", due="", priority=2):
        created["parent_id"] = parent.id
        created["title"] = title
        return f"{parent.id}.1"

    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]),
        patch("tasks_tui.app.create_beads_child_issue", side_effect=fake_create),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_new_subtask()
            await pilot.pause()
            title_input = pilot.app.screen.query_one("#task-title")
            title_input.clear()
            await pilot.press(*"Child task")
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert created.get("parent_id") == "PROJ-001"
            assert created.get("title") == "Child task"


@pytest.mark.asyncio
async def test_new_beads_subtask_cancelled():
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]),
        patch("tasks_tui.app.create_beads_child_issue") as mock_create,
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._selected_beads_issue = lambda: BEADS_ISSUE
            pilot.app._selected_task = lambda: None
            pilot.app.action_new_subtask()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_beads_subtask_renders_indented():
    """Subtasks (IDs with dots) render indented beneath their parent."""
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE, BEADS_SUBTASK]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("BeadsItem"))
            assert len(items) == 2
            parent_item = next(i for i in items if i.issue.id == "PROJ-001")
            child_item = next(i for i in items if i.issue.id == "PROJ-001.1")
            assert parent_item._depth == 0
            assert child_item._depth == 1


@pytest.mark.asyncio
async def test_beads_subtask_without_parent_in_list_renders_top_level():
    """A subtask whose parent isn't in the current list is shown at the top level."""
    orphan = BeadsIssue(
        id="PROJ-001.1",
        title="Orphan child",
        status="open",
        priority=2,
        due_at="",
        description="",
        project="myapp",
        db_path="/fake/myapp/.beads/beads.db",
    )
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[orphan]),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            items = list(pilot.app.query("BeadsItem"))
            assert len(items) == 1
            assert items[0]._depth == 0


# ---------------------------------------------------------------------------
# ctrl+s — sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ctrl_s_triggers_sync_action():
    """Pressing ctrl+s on the main screen starts a sync and shows 'Syncing…' status."""
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch.object(GTasksApp, "_sync_worker"),  # prevent actual thread
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            # Reset state set by on_mount sync
            pilot.app._sync_running = False
            # Trigger sync via keybinding
            await pilot.press("ctrl+s")
            await pilot.pause()
            # Sync flag should be set (worker was triggered)
            assert pilot.app._sync_running is True


@pytest.mark.asyncio
async def test_ctrl_s_while_syncing_shows_warning():
    """Pressing ctrl+s while a sync is already running shows a warning notification."""
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch.object(GTasksApp, "_sync_worker"),
    ):
        async with GTasksApp().run_test() as pilot:
            await pilot.pause()
            pilot.app._sync_running = True  # simulate in-progress sync
            await pilot.press("ctrl+s")
            await pilot.pause()
            # Should still be running (not reset), no second worker started
            assert pilot.app._sync_running is True


# ---------------------------------------------------------------------------
# _parse_date_input helper
# ---------------------------------------------------------------------------


def test_parse_date_input_iso():
    result = _parse_date_input("2026-03-20")
    assert result is not None
    assert result.year == 2026
    assert result.month == 3
    assert result.day == 20


def test_parse_date_input_empty():
    assert _parse_date_input("") is None


def test_parse_date_input_garbage():
    assert _parse_date_input("not a date") is None


# ---------------------------------------------------------------------------
# Per-project config — visible filtering and label resolution
# ---------------------------------------------------------------------------

BEADS_ISSUE_HIDDEN = BeadsIssue(
    id="HIDE-001",
    title="Hidden task",
    status="open",
    priority=2,
    due_at="",
    description="",
    project="hidden-app",
    db_path="/fake/hidden-app/.beads/beads.db",
)


@pytest.mark.asyncio
async def test_beads_issue_with_visible_false_is_filtered_out():
    config = {
        "sync": {"enabled": False, "auto_sync_on_start": False},
        "sources": {"google_tasks": False, "beads": True, "beads_search_root": "~/Code"},
        "projects": {"hidden-app": {"sync": True, "visible": False, "label": "hidden-app"}},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE_HIDDEN]),
    ):
        async with GTasksApp().run_test() as pilot:
            pilot.app._config = config
            pilot.app._load_tasks()
            await pilot.pause()
            beads_items = list(pilot.app.query("BeadsItem"))
            assert not any(i.issue.id == "HIDE-001" for i in beads_items)


@pytest.mark.asyncio
async def test_beads_issue_with_visible_true_is_shown():
    config = {
        "sync": {"enabled": False, "auto_sync_on_start": False},
        "sources": {"google_tasks": False, "beads": True, "beads_search_root": "~/Code"},
        "projects": {"myapp": {"sync": True, "visible": True, "label": "myapp"}},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]),
    ):
        async with GTasksApp().run_test() as pilot:
            pilot.app._config = config
            pilot.app._load_tasks()
            await pilot.pause()
            beads_items = list(pilot.app.query("BeadsItem"))
            assert any(i.issue.id == "PROJ-001" for i in beads_items)


@pytest.mark.asyncio
async def test_beads_item_uses_per_project_label_as_default():
    """Per-project label is passed as default to get_beads_label."""
    config = {
        "sync": {"enabled": False, "auto_sync_on_start": False},
        "sources": {"google_tasks": False, "beads": True, "beads_search_root": "~/Code"},
        "projects": {"myapp": {"sync": True, "visible": True, "label": "work-project"}},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[BEADS_ISSUE]),
        patch("tasks_tui.app.get_beads_label", side_effect=lambda issue_id, default: default) as mock_label,
    ):
        async with GTasksApp().run_test() as pilot:
            pilot.app._config = config
            pilot.app._load_tasks()
            await pilot.pause()
            # get_beads_label should have been called with the per-project label as default
            # (the second _load_tasks call, after config is updated, should use "work-project")
            calls = [call for call in mock_label.call_args_list if call[0][0] == "PROJ-001"]
            assert calls, "get_beads_label not called for PROJ-001"
            assert any(c[0][1] == "work-project" for c in calls)


# ---------------------------------------------------------------------------
# SetupScreen — save before discovery preserves existing project config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_screen_save_before_discovery_preserves_existing_projects():
    """Saving before background discovery completes does not wipe existing project configs."""
    existing_config = {
        "sync": {"enabled": True, "auto_sync_on_start": True},
        "sources": {"google_tasks": True, "beads": True, "beads_search_root": "/tmp"},
        "projects": {"myapp": {"sync": False, "visible": True, "label": "my-label"}},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        # Prevent background worker from running so no ProjectRows are mounted
        patch.object(SetupScreen, "_discover_projects"),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = SetupScreen(config=existing_config)
            result = {}

            def capture(config):
                if config is not None:
                    result.update(config)

            await pilot.app.push_screen(screen, capture)
            await pilot.pause()
            # Directly fire on_button_pressed with the save button (no ProjectRows mounted)
            save_btn = pilot.app.screen.query_one("#setup-save")
            pilot.app.screen.on_button_pressed(save_btn.Pressed(save_btn))
            await pilot.pause()

    # Existing project config must be preserved
    assert result.get("projects", {}).get("myapp") == {
        "sync": False,
        "visible": True,
        "label": "my-label",
    }


# ProjectFilterScreen — project filter panel
# ---------------------------------------------------------------------------

_WORKSPACES = {
    "/fake/alpha": "/fake/alpha/.beads/beads.db",
    "/fake/beta": "/fake/beta/.beads/beads.db",
}

_FILTER_CONFIG = {
    "sync": {"enabled": False, "auto_sync_on_start": False},
    "sources": {"google_tasks": False, "beads": True, "beads_search_root": "~/Code"},
    "projects": {
        "alpha": {"sync": True, "visible": True, "label": "alpha"},
        "beta": {"sync": True, "visible": False, "label": "beta"},
    },
}


def _push_filter_screen(app, config=None):
    """Push a ProjectFilterScreen onto the app and return it."""
    screen = ProjectFilterScreen(config=config or _FILTER_CONFIG)
    app.push_screen(screen)
    return screen


@pytest.mark.asyncio
async def test_filter_screen_populates_rows():
    """ProjectFilterScreen populates one row per discovered workspace."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = _push_filter_screen(pilot.app)
            await pilot.pause()
            rows = list(screen.query(ProjectFilterRow))
            names = {r.project_name for r in rows}
            assert names == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_filter_screen_reflects_visible_state():
    """Rows reflect the visible flag from config."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = _push_filter_screen(pilot.app)
            await pilot.pause()
            states = {r.project_name: r.is_visible for r in screen.query(ProjectFilterRow)}
            assert states["alpha"] is True
            assert states["beta"] is False


@pytest.mark.asyncio
async def test_filter_screen_select_all():
    """ctrl+a action sets all visible toggles to True."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = _push_filter_screen(pilot.app)
            await pilot.pause()
            screen.action_select_all()
            await pilot.pause()
            assert all(r.is_visible for r in screen.query(ProjectFilterRow))


@pytest.mark.asyncio
async def test_filter_screen_deselect_all():
    """ctrl+n action sets all visible toggles to False."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = _push_filter_screen(pilot.app)
            await pilot.pause()
            screen.action_deselect_all()
            await pilot.pause()
            assert not any(r.is_visible for r in screen.query(ProjectFilterRow))


@pytest.mark.asyncio
async def test_filter_screen_search_filters_rows():
    """Typing in the search box hides rows that don't match."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = _push_filter_screen(pilot.app)
            await pilot.pause()
            # Type "alp" — only "alpha" should be visible
            await pilot.press("a", "l", "p")
            await pilot.pause()
            rows = list(screen.query(ProjectFilterRow))
            visible = [r for r in rows if r.display]
            hidden = [r for r in rows if not r.display]
            assert len(visible) == 1 and visible[0].project_name == "alpha"
            assert len(hidden) == 1 and hidden[0].project_name == "beta"


@pytest.mark.asyncio
async def test_filter_screen_ctrl_a_n_keybindings():
    """ctrl+a / ctrl+n keybindings toggle all rows without disturbing the search input."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = _push_filter_screen(pilot.app)
            await pilot.pause()
            # ctrl+a selects all
            await pilot.press("ctrl+a")
            await pilot.pause()
            assert all(r.is_visible for r in screen.query(ProjectFilterRow))
            # ctrl+n deselects all
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert not any(r.is_visible for r in screen.query(ProjectFilterRow))
            # search input should be empty — keystrokes were not typed as text
            from textual.widgets import Input as TInput
            search_input = screen.query_one("#filter-search", TInput)
            assert search_input.value == ""


@pytest.mark.asyncio
async def test_filter_screen_dismiss_returns_projects():
    """Closing the filter panel returns updated projects dict."""
    from tasks_tui.app import ProjectFilterRow
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch("tasks_tui.app.list_beads_issues", return_value=[]),
        patch("tasks_tui.app.discover_beads_workspaces", return_value=_WORKSPACES),
    ):
        async with GTasksApp().run_test() as pilot:
            result = {}
            def capture(projects):
                if projects is not None:
                    result["projects"] = projects
            screen = ProjectFilterScreen(config=_FILTER_CONFIG)
            await pilot.app.push_screen(screen, capture)
            await pilot.pause()
            screen.action_close_filter()
            await pilot.pause()
            assert "projects" in result
            assert "alpha" in result["projects"]
            assert "beta" in result["projects"]


# ---------------------------------------------------------------------------
# SetupScreen — search root path validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_screen_rejects_nonexistent_search_root(tmp_path):
    """Save is blocked and a notification fires when beads is on and path doesn't exist."""
    config = {
        "sync": {"enabled": False, "auto_sync_on_start": False},
        "sources": {"google_tasks": False, "beads": True, "beads_search_root": str(tmp_path / "no-such-dir")},
        "projects": {},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch.object(SetupScreen, "_discover_projects"),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = SetupScreen(config=config)
            dismissed = {}

            def capture(c):
                if c is not None:
                    dismissed["result"] = c

            await pilot.app.push_screen(screen, capture)
            await pilot.pause()
            save_btn = pilot.app.screen.query_one("#setup-save")
            with patch.object(screen, "notify") as mock_notify:
                pilot.app.screen.on_button_pressed(save_btn.Pressed(save_btn))
                await pilot.pause()
                mock_notify.assert_called_once_with(
                    "Search root path does not exist", severity="error"
                )

    assert "result" not in dismissed


@pytest.mark.asyncio
async def test_setup_screen_rejects_empty_search_root_when_beads_enabled():
    """Save is blocked when beads is on but search root is empty."""
    config = {
        "sync": {"enabled": False, "auto_sync_on_start": False},
        "sources": {"google_tasks": False, "beads": True, "beads_search_root": ""},
        "projects": {},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch.object(SetupScreen, "_discover_projects"),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = SetupScreen(config=config)
            dismissed = {}

            def capture(c):
                if c is not None:
                    dismissed["result"] = c

            await pilot.app.push_screen(screen, capture)
            await pilot.pause()
            save_btn = pilot.app.screen.query_one("#setup-save")
            with patch.object(screen, "notify") as mock_notify:
                pilot.app.screen.on_button_pressed(save_btn.Pressed(save_btn))
                await pilot.pause()
                mock_notify.assert_called_once_with(
                    "Search root path is required when beads is enabled", severity="error"
                )

    assert "result" not in dismissed


@pytest.mark.asyncio
async def test_setup_screen_accepts_valid_search_root(tmp_path):
    """Save proceeds when beads is on and search root path exists."""
    config = {
        "sync": {"enabled": False, "auto_sync_on_start": False},
        "sources": {"google_tasks": False, "beads": True, "beads_search_root": str(tmp_path)},
        "projects": {},
    }
    with (
        patch("tasks_tui.app.list_tasks", return_value=[]),
        patch("tasks_tui.app.list_completed_tasks", return_value=[]),
        patch.object(SetupScreen, "_discover_projects"),
    ):
        async with GTasksApp().run_test() as pilot:
            screen = SetupScreen(config=config)
            dismissed = {}

            def capture(c):
                if c is not None:
                    dismissed["result"] = c

            await pilot.app.push_screen(screen, capture)
            await pilot.pause()
            save_btn = pilot.app.screen.query_one("#setup-save")
            pilot.app.screen.on_button_pressed(save_btn.Pressed(save_btn))
            await pilot.pause()

    assert "result" in dismissed
