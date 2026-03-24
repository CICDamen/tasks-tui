"""Google Tasks terminal UI — application entry point."""

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, ListView

from gtasks_tui.screens import (
    EditTaskScreen,
    FilterScreen,
    NewTaskScreen,
    TaskDetailScreen,
)
from gtasks_tui.task_list import render_task_list
from gtasks_tui.tasks_api import (
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
from gtasks_tui.widgets import TaskItem


class GTasksApp(App):
    CSS_PATH = [
        "styles/base.tcss",
        "styles/widgets.tcss",
        "styles/task_screens.tcss",
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
        Binding("r", "refresh", "Refresh"),
        Binding("f", "filter", "Filter"),
    ]

    TITLE = "Google Tasks"

    def __init__(self) -> None:
        super().__init__()
        self._tasks: list[Task] = []
        self._completed_tasks: list[Task] = []
        self._filter_days: int | None = None
        self._filter_lists: set[str] | None = None
        self._available_lists: list[str] = []
        self._load_generation: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield ListView(id="task-list")
        yield Footer()

    def on_mount(self) -> None:
        self._load_tasks()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_tasks(self) -> None:
        self._load_generation += 1
        self._load_worker(self._load_generation)

    @work(thread=True)
    def _load_worker(self, generation: int) -> None:
        try:
            tasks = list_tasks()
            completed = list_completed_tasks()
        except Exception as e:
            self.call_from_thread(
                self.notify, f"Failed to load tasks: {e}", severity="error"
            )
            return
        self.call_from_thread(self._apply_loaded_tasks, tasks, completed, generation)

    def _apply_loaded_tasks(
        self,
        tasks: list[Task],
        completed_tasks: list[Task],
        generation: int | None = None,
    ) -> None:
        if generation is not None and generation != self._load_generation:
            return  # Discard stale response from an older worker
        self._tasks = tasks
        self._completed_tasks = completed_tasks
        seen: set[str] = set()
        self._available_lists = [
            t.list_title
            for t in tasks + completed_tasks
            if t.list_title and not (t.list_title in seen or seen.add(t.list_title))
        ]
        render_task_list(
            self.query_one("#task-list", ListView),
            self._tasks,
            self._completed_tasks,
            filter_days=self._filter_days,
            filter_lists=self._filter_lists,
        )

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _selected_task(self) -> Task | None:
        lv = self.query_one("#task-list", ListView)
        item = lv.highlighted_child
        return item.gtask if isinstance(item, TaskItem) else None

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._load_tasks()
        self.notify("Refreshing...")

    def action_open_task(self) -> None:
        task = self._selected_task()
        if task:
            self.push_screen(
                TaskDetailScreen(task), lambda e: e and self.action_edit_task()
            )

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
        task = self._selected_task()
        if not task:
            self.notify("Select a task first", severity="warning")
            return
        parent_id = task.parent_id if task.parent_id else task.id
        list_id = task.list_id

        def on_result(result: dict | None) -> None:
            if result:
                try:
                    create_subtask(
                        result["title"],
                        parent_id,
                        list_id=list_id,
                        due=result.get("due", ""),
                    )
                    self._load_tasks()
                    self.notify(f"Subtask created: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(NewTaskScreen(), on_result)

    def action_toggle_complete(self) -> None:
        task = self._selected_task()
        if not task:
            return
        try:
            if task.completed:
                uncomplete_task(task.id, list_id=task.list_id)
                self._load_tasks()
                self.notify(f"Reopened: {task.title}")
            else:
                complete_task(task.id, list_id=task.list_id)
                self._load_tasks()
                self.notify(f"Completed: {task.title}")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")

    def action_edit_task(self) -> None:
        task = self._selected_task()
        if not task:
            return

        def on_result(result: dict | None) -> None:
            if result:
                try:
                    update_task(
                        task.id,
                        result["title"],
                        list_id=task.list_id,
                        due=result.get("due", ""),
                        notes=result.get("notes", ""),
                    )
                    self._load_tasks()
                    self.notify(f"Updated: {result['title']}")
                except Exception as e:
                    self.notify(f"Failed: {e}", severity="error")

        self.push_screen(EditTaskScreen(task), on_result)

    def action_delete_task(self) -> None:
        task = self._selected_task()
        if not task:
            return
        try:
            delete_task(task.id, list_id=task.list_id)
            self._load_tasks()
            self.notify(f"Deleted: {task.title}")
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")

    def action_filter(self) -> None:
        def on_result(result: dict | None) -> None:
            if result is not None:
                self._filter_days = result["days"]
                self._filter_lists = result.get("lists")
                self._apply_loaded_tasks(self._tasks, self._completed_tasks)

        self.push_screen(
            FilterScreen(
                filter_days=self._filter_days,
                available_lists=self._available_lists,
                selected_lists=self._filter_lists,
            ),
            on_result,
        )


def main() -> None:
    GTasksApp().run()


if __name__ == "__main__":
    main()
