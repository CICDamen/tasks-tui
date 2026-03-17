"""Filter screen for the task list."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, SelectionList, Static
from textual.widgets.selection_list import Selection


_DAYS_OPTIONS: list[tuple[str, int | None]] = [
    ("All time", None),
    ("Last 7 days", 7),
    ("Last 14 days", 14),
    ("Last 30 days", 30),
    ("Last 90 days", 90),
]


class FilterScreen(ModalScreen):
    """Filter by completed-task recency and/or task list."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("ctrl+s", "close", "Save"),
    ]

    def __init__(
        self,
        filter_days: int | None = None,
        available_lists: list[str] | None = None,
        selected_lists: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._filter_days = filter_days
        self._available_lists = available_lists or []
        # None means "all selected"; convert to explicit set for the widget
        self._selected_lists = (
            selected_lists if selected_lists is not None else set(self._available_lists)
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-dialog"):
            yield Label("FILTER", id="filter-title")
            yield Select(
                [(label, val) for label, val in _DAYS_OPTIONS],
                value=self._filter_days,
                id="filter-days",
                prompt="Show completed",
            )
            if self._available_lists:
                yield Label("Lists", id="filter-lists-label")
                with Horizontal(id="filter-lists-buttons"):
                    yield Button("All", id="filter-lists-all", variant="default")
                    yield Button("None", id="filter-lists-none", variant="default")
                yield SelectionList[str](
                    *[
                        Selection(name, name, name in self._selected_lists)
                        for name in self._available_lists
                    ],
                    id="filter-lists",
                )
            yield Static("ctrl+s save", id="filter-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        sl = self.query_one("#filter-lists", SelectionList)
        if event.button.id == "filter-lists-all":
            sl.select_all()
        elif event.button.id == "filter-lists-none":
            sl.deselect_all()

    def action_close(self) -> None:
        days_select = self.query_one("#filter-days", Select)
        days = days_select.value if days_select.value is not Select.BLANK else None

        selected: set[str] | None = None
        if self._available_lists:
            sl = self.query_one("#filter-lists", SelectionList)
            selected_values = set(sl.selected)
            # None signals "show all" — avoids unnecessary filtering
            selected = (
                None
                if selected_values == set(self._available_lists)
                else selected_values
            )

        self.dismiss({"days": days, "lists": selected})
