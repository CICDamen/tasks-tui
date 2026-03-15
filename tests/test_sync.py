"""Tests for sync.py — mapping I/O and sync engine logic."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tasks_tui.beads_api import BeadsIssue
from tasks_tui.sync import (
    SyncEngine,
    _beads_due_to_gtask_due,
    _has_bd_marker,
    _strip_bd_marker,
    fields_from_issue,
    load_mapping,
    save_mapping,
)
from tasks_tui.tasks_api import Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(
    id="PROJ-001",
    title="Do the thing",
    status="open",
    priority=2,
    due_at="",
    description="Some notes",
    project="myapp",
    db_path="/fake/myapp/.beads/beads.db",
) -> BeadsIssue:
    return BeadsIssue(
        id=id,
        title=title,
        status=status,
        priority=priority,
        due_at=due_at,
        description=description,
        project=project,
        db_path=db_path,
    )


def _make_task(id="gtask1", title="Do the thing") -> Task:
    return Task(id=id, title=title, status="needsAction")


# ---------------------------------------------------------------------------
# load_mapping / save_mapping
# ---------------------------------------------------------------------------


class TestLoadMapping:
    def test_returns_empty_when_file_absent(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        with patch("tasks_tui.sync.MAPPING_FILE", missing):
            result = load_mapping()
        assert result == {"projects": {}, "mappings": []}

    def test_loads_valid_file(self, tmp_path):
        f = tmp_path / "sync.json"
        data = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl1", "tasklist_name": "myapp"}
            },
            "mappings": [
                {
                    "beads_id": "P-1",
                    "gtask_id": "g1",
                    "beads_db_path": "/db",
                    "gtask_list_id": "tl1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        f.write_text(json.dumps(data))
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            result = load_mapping()
        assert result["projects"]["/work/myapp"]["tasklist_id"] == "tl1"
        assert result["mappings"][0]["beads_id"] == "P-1"

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        f = tmp_path / "sync.json"
        f.write_text("not json {{{")
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            result = load_mapping()
        assert result == {"projects": {}, "mappings": []}

    def test_returns_empty_when_file_is_not_dict(self, tmp_path):
        f = tmp_path / "sync.json"
        f.write_text("[1, 2, 3]")
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            result = load_mapping()
        assert result == {"projects": {}, "mappings": []}

    def test_sets_defaults_for_missing_keys(self, tmp_path):
        f = tmp_path / "sync.json"
        f.write_text("{}")
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            result = load_mapping()
        assert result["projects"] == {}
        assert result["mappings"] == []


class TestSaveMapping:
    def test_writes_json_to_disk(self, tmp_path):
        f = tmp_path / "sync.json"
        mapping = {"projects": {}, "mappings": [{"beads_id": "X-1"}]}
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            save_mapping(mapping)
        assert f.exists()
        assert json.loads(f.read_text())["mappings"][0]["beads_id"] == "X-1"

    def test_creates_parent_directory(self, tmp_path):
        f = tmp_path / "nested" / "dir" / "sync.json"
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            save_mapping({"projects": {}, "mappings": []})
        assert f.exists()

    def test_atomic_write_removes_tmp(self, tmp_path):
        f = tmp_path / "sync.json"
        tmp = f.with_suffix(".json.tmp")
        with patch("tasks_tui.sync.MAPPING_FILE", f):
            save_mapping({"projects": {}, "mappings": []})
        assert not tmp.exists()
        assert f.exists()


# ---------------------------------------------------------------------------
# Field conversion
# ---------------------------------------------------------------------------


class TestBreadsDueToGtaskDue:
    def test_empty_string_returns_empty(self):
        assert _beads_due_to_gtask_due("") == ""

    def test_converts_datetime_to_midnight_utc(self):
        result = _beads_due_to_gtask_due("2026-03-15T00:00:00.000Z")
        assert result == "2026-03-15T00:00:00.000Z"

    def test_invalid_string_returns_empty(self):
        assert _beads_due_to_gtask_due("not-a-date") == ""


class TestFieldsFromIssue:
    def test_maps_all_fields(self):
        issue = _make_issue(
            title="Hello", description="Notes", due_at="2026-04-01T00:00:00.000Z"
        )
        fields = fields_from_issue(issue)
        assert fields["title"] == "Hello"
        assert fields["notes"] == "Notes"
        assert fields["due"] == "2026-04-01T00:00:00.000Z"

    def test_none_description_becomes_empty_string(self):
        issue = _make_issue(description=None)
        fields = fields_from_issue(issue)
        assert fields["notes"] == ""

    def test_empty_due_at_becomes_empty_string(self):
        issue = _make_issue(due_at="")
        fields = fields_from_issue(issue)
        assert fields["due"] == ""


# ---------------------------------------------------------------------------
# SyncEngine
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_mapping(tmp_path):
    """Patch MAPPING_FILE to use tmp_path."""
    mapping_file = tmp_path / "gtasks-sync.json"
    with patch("tasks_tui.sync.MAPPING_FILE", mapping_file):
        yield {"mapping_file": mapping_file, "tmp": tmp_path}


class TestSyncEngineNoRegistry:
    def test_does_nothing_when_no_workspaces(self, tmp_mapping):
        messages = []
        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={}),
            patch("tasks_tui.sync.load_mapping", return_value={"projects": {}, "mappings": []}),
        ):
            engine = SyncEngine()
            engine.run(progress=messages.append)
        assert any("No beads workspaces" in m for m in messages)


class TestSyncEngineFirstSync:
    def test_creates_tasklist_and_pushes_new_issue(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        issue = _make_issue(id="P-1", title="First task", db_path=db_path)
        mock_tasklist = {"id": "tl-new", "title": "myapp"}
        mock_gtask = Task(id="g-1", title="First task", status="needsAction")

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[issue]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value=mock_tasklist) as mock_create_tl,
            patch("tasks_tui.sync.create_task_in_list", return_value=mock_gtask) as mock_create_task,
            patch("tasks_tui.sync.update_task_in_list") as mock_update,
        ):
            engine = SyncEngine()
            engine.run()

        mock_create_tl.assert_called_once_with("myapp")
        mock_create_task.assert_called_once()
        mock_update.assert_not_called()

        mapping = json.loads(tmp_mapping["mapping_file"].read_text())
        assert mapping["projects"]["/work/myapp"]["tasklist_id"] == "tl-new"
        assert len(mapping["mappings"]) == 1
        assert mapping["mappings"][0]["beads_id"] == "P-1"
        assert mapping["mappings"][0]["gtask_id"] == "g-1"


class TestSyncEngineUpdateExisting:
    def test_updates_existing_mapped_issue(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        issue = _make_issue(id="P-1", title="Updated title", db_path=db_path)

        existing_mapping = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl-1", "tasklist_name": "myapp"}
            },
            "mappings": [
                {
                    "beads_id": "P-1",
                    "beads_db_path": db_path,
                    "gtask_id": "g-1",
                    "gtask_list_id": "tl-1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[issue]),
            patch("tasks_tui.sync.create_task_in_list") as mock_create,
            patch("tasks_tui.sync.update_task_in_list") as mock_update,
        ):
            engine = SyncEngine()
            engine.run()

        mock_create.assert_not_called()
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] == "tl-1"  # tasklist_id
        assert call_args[0][1] == "g-1"  # task_id
        assert call_args[1]["title"] == "Updated title"


class TestSyncEngineClosedIssue:
    def test_completes_google_task_when_beads_issue_closed(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"

        existing_mapping = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl-1", "tasklist_name": "myapp"}
            },
            "mappings": [
                {
                    "beads_id": "P-1",
                    "beads_db_path": db_path,
                    "gtask_id": "g-1",
                    "gtask_list_id": "tl-1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        closed_issue = _make_issue(id="P-1", title="Done", status="closed", db_path=db_path)
        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[closed_issue]),
            patch("tasks_tui.sync.create_task_in_list") as mock_create,
            patch("tasks_tui.sync.update_task_in_list") as mock_update,
            patch("tasks_tui.sync.complete_task_in_list") as mock_complete,
        ):
            engine = SyncEngine()
            engine.run()

        mock_create.assert_not_called()
        mock_update.assert_not_called()
        mock_complete.assert_called_once_with("tl-1", "g-1")

        # Mapping entry should be removed
        mapping = json.loads(tmp_mapping["mapping_file"].read_text())
        assert mapping["mappings"] == []

    def test_complete_api_error_is_reported_in_progress(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"

        existing_mapping = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl-1", "tasklist_name": "myapp"}
            },
            "mappings": [
                {
                    "beads_id": "P-1",
                    "beads_db_path": db_path,
                    "gtask_id": "g-1",
                    "gtask_list_id": "tl-1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        closed_issue = _make_issue(id="P-1", title="Done", status="closed", db_path=db_path)
        messages = []
        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[closed_issue]),
            patch("tasks_tui.sync.complete_task_in_list", side_effect=Exception("API down")),
        ):
            engine = SyncEngine()
            engine.run(progress=messages.append)

        assert any("error" in m.lower() for m in messages)
        assert any("P-1" in m or "complete" in m for m in messages)


class TestSyncEngineOrphanedEntry:
    def test_completes_google_task_for_orphaned_entry(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"

        existing_mapping = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl-1", "tasklist_name": "myapp"}
            },
            "mappings": [
                {
                    "beads_id": "P-ORPHAN",
                    "beads_db_path": db_path,
                    "gtask_id": "g-orphan",
                    "gtask_list_id": "tl-1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.complete_task_in_list") as mock_complete,
        ):
            engine = SyncEngine()
            engine.run()

        mock_complete.assert_called_once_with("tl-1", "g-orphan")

        mapping = json.loads(tmp_mapping["mapping_file"].read_text())
        assert mapping["mappings"] == []

    def test_orphan_api_error_is_reported_in_progress(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"

        existing_mapping = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl-1", "tasklist_name": "myapp"}
            },
            "mappings": [
                {
                    "beads_id": "P-ORPHAN",
                    "beads_db_path": db_path,
                    "gtask_id": "g-orphan",
                    "gtask_list_id": "tl-1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        messages = []
        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.complete_task_in_list", side_effect=Exception("API down")),
        ):
            engine = SyncEngine()
            engine.run(progress=messages.append)

        assert any("error" in m.lower() for m in messages)
        assert any("P-ORPHAN" in m or "orphan" in m for m in messages)


class TestSyncEngineTasklistReuse:
    def test_reuses_existing_tasklist_from_mapping(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"

        existing_mapping = {
            "projects": {
                "/work/myapp": {"tasklist_id": "tl-stored", "tasklist_name": "myapp"}
            },
            "mappings": [],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_tasklists") as mock_list_tl,
            patch("tasks_tui.sync.create_tasklist") as mock_create_tl,
        ):
            engine = SyncEngine()
            engine.run()

        mock_list_tl.assert_not_called()
        mock_create_tl.assert_not_called()


class TestSyncEngineProjectNameCollision:
    def test_two_workspaces_same_name_get_separate_lists(self, tmp_mapping):
        db1 = "/fake/work/myapp/.beads/beads.db"
        db2 = "/fake/personal/myapp/.beads/beads.db"
        tl1 = {"id": "tl-work", "title": "myapp"}
        tl2 = {"id": "tl-personal", "title": "myapp"}

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db1, "/personal/myapp": db2}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", side_effect=[tl1, tl2]) as mock_create,
        ):
            engine = SyncEngine()
            engine.run()

        assert mock_create.call_count == 2
        mapping = json.loads(tmp_mapping["mapping_file"].read_text())
        assert mapping["projects"]["/work/myapp"]["tasklist_id"] == "tl-work"
        assert mapping["projects"]["/personal/myapp"]["tasklist_id"] == "tl-personal"


class TestSyncEnginePerProjectConfig:
    def test_skips_workspace_when_sync_disabled(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        issue = _make_issue(id="P-1", db_path=db_path)
        config = {"projects": {"myapp": {"sync": False, "visible": True, "label": "myapp"}}}

        messages = []
        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[issue]),
            patch("tasks_tui.sync.create_task_in_list") as mock_create,
            patch("tasks_tui.sync.update_task_in_list") as mock_update,
        ):
            engine = SyncEngine(config=config)
            engine.run(progress=messages.append)

        mock_create.assert_not_called()
        mock_update.assert_not_called()
        assert any("Skipping" in m and "myapp" in m for m in messages)

    def test_syncs_workspace_when_sync_enabled(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        issue = _make_issue(id="P-1", db_path=db_path)
        mock_gtask = _make_task(id="g-1")
        config = {"projects": {"myapp": {"sync": True, "visible": True, "label": "myapp"}}}

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[issue]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value={"id": "tl-1", "title": "myapp"}),
            patch("tasks_tui.sync.create_task_in_list", return_value=mock_gtask),
            patch("tasks_tui.sync.update_task_in_list"),
        ):
            engine = SyncEngine(config=config)
            engine.run()

        # If we reach here without error, the workspace was not skipped


class TestSyncEngineApiError:
    def test_error_in_one_project_does_not_prevent_save(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        issue = _make_issue(id="P-1", db_path=db_path)

        messages = []
        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[issue]),
            patch("tasks_tui.sync.list_tasklists", side_effect=Exception("auth error")),
            patch("tasks_tui.sync.create_tasklist", side_effect=Exception("auth error")),
        ):
            engine = SyncEngine()
            engine.run(progress=messages.append)

        # Mapping file should still be saved (even if empty/unchanged)
        assert tmp_mapping["mapping_file"].exists()
        assert any("error" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# BD marker helpers
# ---------------------------------------------------------------------------


class TestHasBdMarker:
    def test_returns_true_when_marker_present(self):
        assert _has_bd_marker("Fix the bug (bd) asap")

    def test_returns_true_when_only_marker(self):
        assert _has_bd_marker("(bd)")

    def test_returns_false_when_marker_absent(self):
        assert not _has_bd_marker("Fix the bug asap")

    def test_returns_false_for_empty_string(self):
        assert not _has_bd_marker("")

    def test_returns_false_for_none(self):
        assert not _has_bd_marker(None)


class TestStripBdMarker:
    def test_removes_marker_from_middle(self):
        assert _strip_bd_marker("Fix bug (bd) now") == "Fix bug now"

    def test_removes_marker_from_end(self):
        assert _strip_bd_marker("Fix bug (bd)") == "Fix bug"

    def test_removes_marker_from_start(self):
        assert _strip_bd_marker("(bd) Fix bug") == "Fix bug"

    def test_returns_empty_for_marker_only(self):
        assert _strip_bd_marker("(bd)") == ""

    def test_returns_empty_for_empty_input(self):
        assert _strip_bd_marker("") == ""

    def test_returns_empty_for_none(self):
        assert _strip_bd_marker(None) == ""

    def test_collapses_extra_whitespace(self):
        assert _strip_bd_marker("Fix  (bd)  bug") == "Fix bug"


# ---------------------------------------------------------------------------
# SyncEngine — Google Tasks → beads reverse sync
# ---------------------------------------------------------------------------


class TestSyncEngineGtasksToBeads:
    def test_creates_beads_issue_for_task_with_bd_marker(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        task_with_bd = Task(id="g-new", title="New feature", status="needsAction", notes="Some notes (bd)")

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value={"id": "tl-1", "title": "myapp"}),
            patch("tasks_tui.sync.list_tasks_in_list", return_value=[task_with_bd]),
            patch("tasks_tui.sync.create_beads_issue", return_value="MYAPP-1") as mock_create,
        ):
            engine = SyncEngine()
            engine.run()

        mock_create.assert_called_once_with(
            workspace_path="/work/myapp",
            db_path=db_path,
            title="New feature",
            description="Some notes",
            due="",
        )
        mapping = json.loads(tmp_mapping["mapping_file"].read_text())
        assert len(mapping["mappings"]) == 1
        entry = mapping["mappings"][0]
        assert entry["beads_id"] == "MYAPP-1"
        assert entry["gtask_id"] == "g-new"

    def test_does_not_create_beads_issue_without_bd_marker(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        task_no_bd = Task(id="g-1", title="Non-coding task", status="needsAction", notes="Just a reminder")

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value={"id": "tl-1", "title": "myapp"}),
            patch("tasks_tui.sync.list_tasks_in_list", return_value=[task_no_bd]),
            patch("tasks_tui.sync.create_beads_issue") as mock_create,
        ):
            engine = SyncEngine()
            engine.run()

        mock_create.assert_not_called()

    def test_skips_already_mapped_gtask(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        existing_mapping = {
            "projects": {"/work/myapp": {"tasklist_id": "tl-1", "tasklist_name": "myapp"}},
            "mappings": [
                {
                    "beads_id": "MYAPP-1",
                    "beads_db_path": db_path,
                    "gtask_id": "g-existing",
                    "gtask_list_id": "tl-1",
                    "last_synced_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        tmp_mapping["mapping_file"].write_text(json.dumps(existing_mapping))

        already_mapped_task = Task(
            id="g-existing", title="Old task", status="needsAction", notes="(bd) already synced"
        )

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.list_tasks_in_list", return_value=[already_mapped_task]),
            patch("tasks_tui.sync.create_beads_issue") as mock_create,
        ):
            engine = SyncEngine()
            engine.run()

        mock_create.assert_not_called()

    def test_bd_marker_stripped_from_description(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        task = Task(id="g-2", title="Add feature", status="needsAction", notes="(bd) implement login")

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value={"id": "tl-1", "title": "myapp"}),
            patch("tasks_tui.sync.list_tasks_in_list", return_value=[task]),
            patch("tasks_tui.sync.create_beads_issue", return_value="MYAPP-2") as mock_create,
        ):
            engine = SyncEngine()
            engine.run()

        _, kwargs = mock_create.call_args
        assert "(bd)" not in kwargs["description"]
        assert kwargs["description"] == "implement login"

    def test_list_tasks_api_error_reported_in_progress(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        messages = []

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value={"id": "tl-1", "title": "myapp"}),
            patch("tasks_tui.sync.list_tasks_in_list", side_effect=Exception("auth error")),
        ):
            engine = SyncEngine()
            engine.run(progress=messages.append)

        assert any("error" in m.lower() for m in messages)

    def test_create_beads_issue_error_reported_and_continues(self, tmp_mapping):
        db_path = "/fake/myapp/.beads/beads.db"
        task1 = Task(id="g-1", title="Task 1", status="needsAction", notes="(bd) first")
        task2 = Task(id="g-2", title="Task 2", status="needsAction", notes="(bd) second")
        messages = []

        def side_effect(**kwargs):
            if kwargs["title"] == "Task 1":
                raise Exception("bd create failed")
            return "MYAPP-2"

        with (
            patch("tasks_tui.sync.discover_beads_workspaces", return_value={"/work/myapp": db_path}),
            patch("tasks_tui.sync.list_issues_via_cli", return_value=[]),
            patch("tasks_tui.sync.list_closed_mapped_issues", return_value=[]),
            patch("tasks_tui.sync.list_tasklists", return_value=[]),
            patch("tasks_tui.sync.create_tasklist", return_value={"id": "tl-1", "title": "myapp"}),
            patch("tasks_tui.sync.list_tasks_in_list", return_value=[task1, task2]),
            patch("tasks_tui.sync.create_beads_issue", side_effect=side_effect),
        ):
            engine = SyncEngine()
            engine.run(progress=messages.append)

        assert any("error" in m.lower() for m in messages)
        mapping = json.loads(tmp_mapping["mapping_file"].read_text())
        # Task 2 should still be mapped despite Task 1 failing
        assert any(e["gtask_id"] == "g-2" for e in mapping["mappings"])
