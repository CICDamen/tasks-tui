"""Configuration and project-management screens."""

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static, Switch

from tasks_tui.beads_api import discover_beads_workspaces
from tasks_tui.config import DEFAULTS, get_project_config


class ProjectFilterRow(Widget):
    """One row in the project filter panel: project name + visible toggle."""

    def __init__(self, name: str, visible: bool) -> None:
        super().__init__(classes="filter-row")
        self._name = name
        self._visible = visible

    def compose(self) -> ComposeResult:
        yield Static(self._name, classes="filter-name")
        yield Switch(value=self._visible, classes="filter-switch")

    @property
    def project_name(self) -> str:
        return self._name

    @property
    def is_visible(self) -> bool:
        return self.query_one(Switch).value


class ProjectFilterScreen(ModalScreen):
    """Quick project visibility filter — toggle which beads projects appear in the task view."""

    BINDINGS = [
        Binding("escape", "close_filter", "Close"),
        Binding("ctrl+a", "select_all", "All", priority=True),
        Binding("ctrl+n", "deselect_all", "None", priority=True),
    ]

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-dialog"):
            yield Label("PROJECTS", id="filter-title")
            yield Input(placeholder="Search…", id="filter-search")
            yield Vertical(id="filter-rows")
            yield Static("ctrl+a all · ctrl+n none · esc close", id="filter-hint")

    def on_mount(self) -> None:
        self.query_one("#filter-search", Input).focus()
        self._discover()

    @work(thread=True)
    def _discover(self) -> None:
        workspaces = discover_beads_workspaces()
        self.app.call_from_thread(self._populate, workspaces)

    def _populate(self, workspaces: dict[str, str]) -> None:
        rows = self.query_one("#filter-rows", Vertical)
        for workspace_path in sorted(workspaces):
            name = Path(workspace_path).name
            proj = get_project_config(name, self._config)
            rows.mount(ProjectFilterRow(name=name, visible=proj["visible"]))

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.lower()
        for row in self.query(ProjectFilterRow):
            row.display = not query or query in row.project_name.lower()

    def action_select_all(self) -> None:
        for row in self.query(ProjectFilterRow):
            row.query_one(Switch).value = True

    def action_deselect_all(self) -> None:
        for row in self.query(ProjectFilterRow):
            row.query_one(Switch).value = False

    def action_close_filter(self) -> None:
        projects: dict[str, dict] = dict(self._config.get("projects", {}))
        for row in self.query(ProjectFilterRow):
            proj = get_project_config(row.project_name, self._config)
            projects[row.project_name] = {**proj, "visible": row.is_visible}
        self.dismiss(projects)


class ProjectRow(Widget):
    """One row per beads workspace shown in the SetupScreen PROJECTS section."""

    def __init__(self, name: str, sync: bool, visible: bool, label: str) -> None:
        super().__init__(classes="project-row")
        self._name = name
        self._sync = sync
        self._visible = visible
        self._label = label

    def compose(self) -> ComposeResult:
        yield Static(self._name, classes="project-name")
        yield Switch(value=self._sync, classes="project-sync-switch")
        yield Switch(value=self._visible, classes="project-visible-switch")
        yield Input(value=self._label, classes="project-label-input")

    @property
    def project_name(self) -> str:
        return self._name

    def get_values(self) -> dict:
        switches = list(self.query(Switch))
        return {
            "sync": switches[0].value,
            "visible": switches[1].value,
            "label": self.query_one(Input).value or self._name,
        }


class SetupScreen(ModalScreen):
    """Configuration screen — shown on first run and accessible via ','."""

    BINDINGS = [Binding("escape", "skip", "Cancel")]

    def __init__(self, config: dict | None = None, first_run: bool = False) -> None:
        super().__init__()
        self._initial = config or {}
        self._first_run = first_run

    def _get(self, section: str, key: str):
        return self._initial.get(section, {}).get(key, DEFAULTS[section][key])

    def compose(self) -> ComposeResult:
        title = "Welcome to tasks-tui  ✦" if self._first_run else "Configuration"
        desc = (
            "Let's set up your configuration.\n"
            "You can also edit ~/.config/tasks-tui/config.json directly."
            if self._first_run
            else "Toggle options and press Save. Takes effect immediately."
        )
        save_label = "Save & Start" if self._first_run else "Save"
        hint = "esc  skip and use defaults" if self._first_run else "esc  cancel"

        with Vertical(id="setup-dialog"):
            yield Label(title, id="setup-title")
            yield Static(desc, id="setup-desc")
            yield Static("", classes="setup-spacer")

            yield Static("DATA SOURCES", classes="setup-section")
            with Horizontal(classes="setup-row"):
                yield Static("Google Tasks", classes="setup-option-label")
                yield Switch(value=self._get("sources", "google_tasks"), id="sw-google-tasks")
            with Horizontal(classes="setup-row"):
                yield Static("Beads issues", classes="setup-option-label")
                yield Switch(value=self._get("sources", "beads"), id="sw-beads")
            with Horizontal(classes="setup-row"):
                yield Static("Search root", classes="setup-option-label")
                yield Input(
                    value=self._get("sources", "beads_search_root"),
                    placeholder="e.g. ~/Code",
                    id="sw-search-root",
                )

            yield Static("", classes="setup-spacer")
            yield Static("SYNC  (Beads → Google Tasks)", classes="setup-section")
            with Horizontal(classes="setup-row"):
                yield Static("Enable sync", classes="setup-option-label")
                yield Switch(value=self._get("sync", "enabled"), id="sw-sync-enabled")
            with Horizontal(classes="setup-row"):
                yield Static("Auto-sync on start", classes="setup-option-label")
                yield Switch(value=self._get("sync", "auto_sync_on_start"), id="sw-auto-sync")

            if not self._first_run:
                yield Static("", classes="setup-spacer")
                yield Static("PROJECTS  (sync  visible  label)", classes="setup-section")
                yield Static("Discovering projects…", id="projects-loading")

            yield Static("", classes="setup-spacer")
            yield Button(save_label, id="setup-save", variant="primary")
            yield Static(hint, id="setup-hint")

    def on_mount(self) -> None:
        if not self._first_run:
            self._discover_projects()

    @work(thread=True)
    def _discover_projects(self) -> None:
        workspaces = discover_beads_workspaces()
        self.app.call_from_thread(self._populate_projects, workspaces)

    def _populate_projects(self, workspaces: dict[str, str]) -> None:
        loading = self.query_one("#projects-loading", Static)
        loading.remove()
        dialog = self.query_one("#setup-dialog", Vertical)
        save_btn = self.query_one("#setup-save", Button)
        for workspace_path in sorted(workspaces):
            name = Path(workspace_path).name
            proj = get_project_config(name, self._initial)
            row = ProjectRow(name=name, sync=proj["sync"], visible=proj["visible"], label=proj["label"])
            dialog.mount(row, before=save_btn)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-save":
            beads_on = self.query_one("#sw-beads", Switch).value
            search_root = self.query_one("#sw-search-root", Input).value.strip()
            if beads_on and search_root and not Path(search_root).expanduser().exists():
                self.notify("Search root path does not exist", severity="error")
                return
            if beads_on and not search_root:
                self.notify("Search root path is required when beads is enabled", severity="error")
                return
            projects: dict[str, dict] = dict(self._initial.get("projects", {}))
            for row in self.query(ProjectRow):
                projects[row.project_name] = row.get_values()
            self.dismiss({
                "sync": {
                    "enabled": self.query_one("#sw-sync-enabled", Switch).value,
                    "auto_sync_on_start": self.query_one("#sw-auto-sync", Switch).value,
                },
                "sources": {
                    "google_tasks": self.query_one("#sw-google-tasks", Switch).value,
                    "beads": self.query_one("#sw-beads", Switch).value,
                    "beads_search_root": search_root,
                },
                "projects": projects,
            })

    def action_skip(self) -> None:
        self.dismiss(None)
