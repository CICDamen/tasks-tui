"""Google Tasks terminal UI — application entry point."""

from datetime import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, ListView, Static

from tasks_tui.beads_api import (
    BeadsIssue,
    create_beads_child_issue,
    list_beads_issues,
    set_beads_label,
    update_beads_issue,
)
from tasks_tui.config import CONFIG_PATH, get_project_config, load_config, save_config
from tasks_tui.date_utils import _parse_date_input, _parse_due  # re-exported for backward compat
from tasks_tui.screens import (
    BeadsDetailScreen,
    BeadsEditScreen,
    EditTaskScreen,
    NewTaskScreen,
    ProjectFilterRow,
    ProjectFilterScreen,
    SetupScreen,
    TaskDetailScreen,
)
from tasks_tui.sync import SyncEngine
from tasks_tui.task_list import render_task_list
from tasks_tui.tasks_api import (
    Task,
    complete_task,
    create_subtask,
    create_task,
    delete_task,
    list_completed_tasks,
    list_tasks,
    uncomplete_task,
    update_task,
)
from tasks_tui.widgets import BeadsItem, TaskItem

__all__ = [
    "GTasksApp",
    "ProjectFilterRow",
    "ProjectFilterScreen",
    "SetupScreen",
    "_parse_date_input",
    "_parse_due",
]


class GTasksApp(App):
    CSS_PATH = [
        "styles/base.tcss",
        "styles/widgets.tcss",
        "styles/task_screens.tcss",
        "styles/beads_screens.tcss",
        "styles/config_screens.tcss",
    ]

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("n", "new_task", "New"),
        Binding("s", "new_subtask", "Subtask"),
        Binding("enter", "open_task", "Open"),
        Binding("e", "edit_task", "Edit"),
        Binding("space", "toggle_complete", "Check/Uncheck"),
        Binding("d", "delete_task", "Delete"),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("ctrl+s", "sync", "Sync"),
        Binding("f", "filter_projects", "Filter"),
        Binding("p", "config", "Prefs"),
    ]

    TITLE = "Google Tasks"

    def __init__(self) -> None:
        super().__init__()
        self._config = load_config()
        self._tasks: list[Task] = []
        self._completed_tasks: list[Task] = []
        self._beads_issues: list[BeadsIssue] = []
        self._sync_running: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield ListView(id="task-list")
        yield Static("", id="sync-status", classes="sync-status")
        yield Footer()

    def on_mount(self) -> None:
        if not CONFIG_PATH.exists():
            self.push_screen(SetupScreen(first_run=True), self._on_setup_done)
        else:
            self._start_app()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _on_setup_done(self, config: dict | None) -> None:
        if config is not None:
            save_config(config)
            self._config = config
        self._start_app()

    def _start_app(self) -> None:
        self._load_tasks()
        if self._config["sync"]["enabled"] and self._config["sync"]["auto_sync_on_start"]:
            self.action_sync()

    def _load_tasks(self) -> None:
        if self._config["sources"]["google_tasks"]:
            try:
                self._tasks = list_tasks()
                self._completed_tasks = list_completed_tasks()
            except Exception as e:
                self.notify(f"Failed to load tasks: {e}", severity="error")
                self._tasks = []
                self._completed_tasks = []
        else:
            self._tasks = []
            self._completed_tasks = []

        if self._config["sources"]["beads"]:
            try:
                self._beads_issues = [
                    i for i in list_beads_issues()
                    if get_project_config(i.project, self._config)["visible"]
                ]
            except Exception:
                self._beads_issues = []
        else:
            self._beads_issues = []

        render_task_list(
            self.query_one("#task-list", ListView),
            self._tasks,
            self._completed_tasks,
            self._beads_issues,
            self._config,
        )

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _selected_task(self) -> Task | None:
        lv = self.query_one("#task-list", ListView)
        item = lv.highlighted_child
        return item.gtask if isinstance(item, TaskItem) else None

    def _selected_beads_issue(self) -> BeadsIssue | None:
        lv = self.query_one("#task-list", ListView)
        item = lv.highlighted_child
        return item.issue if isinstance(item, BeadsItem) else None

    # ── Sync ──────────────────────────────────────────────────────────────────

    def action_sync(self) -> None:
        if not self._config["sync"]["enabled"]:
            self.notify("Sync is disabled in config", severity="warning")
            return
        if self._sync_running:
            self.notify("Sync already in progress", severity="warning")
            return
        self._sync_running = True
        self._update_sync_status("Syncing…")
        self._sync_worker()

    @work(thread=True)
    def _sync_worker(self) -> None:
        messages: list[str] = []
        error = False
        try:
            SyncEngine(config=self._config).run(progress=messages.append)
        except Exception as e:
            messages.append(f"Sync error: {e}")
            error = True
        last_msg = messages[-1] if messages else "Sync complete"
        if error or "error" in last_msg.lower():
            self.call_from_thread(self._on_sync_done, last_msg, True)
        else:
            now = datetime.now().strftime("%H:%M")
            self.call_from_thread(self._on_sync_done, f"Last synced {now}", False)

    def _update_sync_status(self, msg: str) -> None:
        try:
            self.query_one("#sync-status", Static).update(msg)
        except Exception:
            pass

    def _on_sync_done(self, status_msg: str, error: bool) -> None:
        self._sync_running = False
        self._update_sync_status(status_msg)
        if not error:
            self._load_tasks()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load_tasks()
        self.notify("Refreshed")

    def action_open_task(self) -> None:
        issue = self._selected_beads_issue()
        if issue:
            self.push_screen(BeadsDetailScreen(issue), lambda e: e and self._open_beads_edit(issue))
            return
        task = self._selected_task()
        if task:
            self.push_screen(TaskDetailScreen(task), lambda e: e and self.action_edit_task())

    def action_new_task(self) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_task(result["title"], due=result.get("due", ""))
                    self._load_tasks()
                    self.notify(f"Created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed to create task: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def action_new_subtask(self) -> None:
        issue = self._selected_beads_issue()
        if issue:
            self._new_beads_subtask(issue)
            return
        task = self._selected_task()
        if not task:
            self.notify("Select a task first", severity="warning")
            return
        parent_id = task.parent_id if task.parent_id else task.id

        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_subtask(result["title"], parent_id, due=result.get("due", ""))
                    self._load_tasks()
                    self.notify(f"Subtask created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def _new_beads_subtask(self, parent: BeadsIssue) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_beads_child_issue(parent, result["title"], due=result.get("due", ""))
                    self._load_tasks()
                    self.notify(f"Subtask created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def action_toggle_complete(self) -> None:
        if self._selected_beads_issue():
            self.notify("Use e to edit status on Beads tasks", severity="warning")
            return
        task = self._selected_task()
        if not task:
            return
        try:
            if task.completed:
                uncomplete_task(task.id)
                self._load_tasks()
                self.notify(f"Reopened: {task.title}")
            else:
                complete_task(task.id)
                self._load_tasks()
                self.notify(f"Completed: {task.title}")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")

    def _open_beads_edit(self, issue: BeadsIssue) -> None:
        def on_result(result: dict | None) -> None:
            if result:
                try:
                    set_beads_label(issue.id, result["label"], issue.project)
                    update_beads_issue(
                        issue,
                        title=result["title"],
                        status=result["status"],
                        priority=result["priority"],
                        description=result["description"],
                        due=result["due"],
                    )
                    self._load_tasks()
                    self.notify(f"Updated: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(BeadsEditScreen(issue), on_result)

    def action_edit_task(self) -> None:
        issue = self._selected_beads_issue()
        if issue:
            self._open_beads_edit(issue)
            return
        task = self._selected_task()
        if not task:
            return

        def on_result(result: dict | None) -> None:
            if result:
                try:
                    update_task(
                        task.id,
                        result["title"],
                        due=result.get("due", ""),
                        notes=result.get("notes", ""),
                    )
                    self._load_tasks()
                    self.notify(f"Updated: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(EditTaskScreen(task), on_result)

    def action_delete_task(self) -> None:
        if self._selected_beads_issue():
            self.notify("Beads tasks are read-only", severity="warning")
            return
        task = self._selected_task()
        if not task:
            return
        try:
            delete_task(task.id)
            self._load_tasks()
            self.notify(f"Deleted: {task.title}")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")

    def action_filter_projects(self) -> None:
        def on_result(projects: dict | None) -> None:
            if projects is not None:
                self._config.setdefault("projects", {}).update(projects)
                save_config(self._config)
                self._load_tasks()

        self.push_screen(ProjectFilterScreen(config=self._config), on_result)

    def action_config(self) -> None:
        def on_result(config: dict | None) -> None:
            if config is not None:
                save_config(config)
                self._config = config
                self._load_tasks()
                self.notify("Configuration saved")

        self.push_screen(SetupScreen(config=self._config), on_result)


def main() -> None:
    GTasksApp().run()


if __name__ == "__main__":
    main()
