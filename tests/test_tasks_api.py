"""Tests for tasks_api — pure logic, no gws CLI calls."""

from unittest.mock import patch

from gtasks_tui.tasks_api import Task, create_task, list_tasks


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------


class TestTaskDueLabel:
    def _task(self, due: str = "") -> Task:
        return Task(id="1", title="Test", status="needsAction", due=due)

    def test_no_due_returns_today(self):
        assert self._task().due_label == "today"

    def test_today(self, freezegun_today):
        assert self._task("2026-03-12T00:00:00.000Z").due_label == "today"

    def test_tomorrow(self, freezegun_today):
        assert self._task("2026-03-13T00:00:00.000Z").due_label == "tomorrow"

    def test_overdue(self, freezegun_today):
        assert self._task("2026-03-10T00:00:00.000Z").due_label == "overdue"

    def test_future_date(self, freezegun_today):
        assert self._task("2026-03-20T00:00:00.000Z").due_label == "Mar 20"

    def test_invalid_due_returns_empty(self):
        assert self._task("not-a-date").due_label == ""


class TestTaskProperties:
    def test_completed_status(self):
        t = Task(id="1", title="T", status="completed")
        assert t.completed is True

    def test_pending_status(self):
        t = Task(id="1", title="T", status="needsAction")
        assert t.completed is False

    def test_is_overdue_no_due(self):
        t = Task(id="1", title="T", status="needsAction")
        assert t.is_overdue is False

    def test_is_overdue_past_due(self, freezegun_today):
        t = Task(
            id="1", title="T", status="needsAction", due="2026-03-10T00:00:00.000Z"
        )
        assert t.is_overdue is True

    def test_is_overdue_future_due(self, freezegun_today):
        t = Task(
            id="1", title="T", status="needsAction", due="2026-03-20T00:00:00.000Z"
        )
        assert t.is_overdue is False


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------


class TestListTasks:
    def test_returns_tasks(self):
        fake_response = {
            "items": [
                {
                    "id": "abc",
                    "title": "Buy milk",
                    "status": "needsAction",
                    "due": "2026-03-13T00:00:00.000Z",
                },
                {"id": "def", "title": "Call dentist", "status": "needsAction"},
            ]
        }
        with patch("gtasks_tui.tasks_api._gws", return_value=fake_response):
            tasks = list_tasks()
        assert len(tasks) == 2
        assert tasks[0].title == "Buy milk"
        assert tasks[0].due == "2026-03-13T00:00:00.000Z"
        assert tasks[1].title == "Call dentist"

    def test_skips_tasks_without_title(self):
        fake_response = {"items": [{"id": "abc", "title": "", "status": "needsAction"}]}
        with patch("gtasks_tui.tasks_api._gws", return_value=fake_response):
            tasks = list_tasks()
        assert tasks == []

    def test_empty_list(self):
        with patch("gtasks_tui.tasks_api._gws", return_value={}):
            tasks = list_tasks()
        assert tasks == []


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_creates_with_title_only(self):
        fake_response = {"id": "new1", "title": "Foo", "status": "needsAction"}
        with patch("gtasks_tui.tasks_api._gws", return_value=fake_response) as mock:
            task = create_task("Foo")
        mock.assert_called_once()
        assert task.title == "Foo"
        assert task.id == "new1"

    def test_creates_with_due_date(self):
        fake_response = {
            "id": "new2",
            "title": "Bar",
            "status": "needsAction",
            "due": "2026-03-15T00:00:00.000Z",
        }
        with patch("gtasks_tui.tasks_api._gws", return_value=fake_response):
            task = create_task("Bar", due="2026-03-15T00:00:00.000Z")
        assert task.due == "2026-03-15T00:00:00.000Z"

    def test_body_excludes_empty_due(self):
        fake_response = {"id": "new3", "title": "Baz", "status": "needsAction"}
        with patch("gtasks_tui.tasks_api._gws", return_value=fake_response) as mock:
            create_task("Baz", due="")
        body = mock.call_args[1]["body"] if mock.call_args[1] else mock.call_args[0][3]
        assert "due" not in body
