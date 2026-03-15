"""Shared screen components used across multiple screen types."""

import calendar as cal_mod
from datetime import date as DateType
from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class DatePickerScreen(ModalScreen[str | None]):
    """Calendar date picker modal."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select_date", "Select"),
        Binding("left", "prev_day", show=False),
        Binding("right", "next_day", show=False),
        Binding("up", "prev_week", show=False),
        Binding("down", "next_week", show=False),
        Binding("pageup", "prev_month", "Prev month"),
        Binding("pagedown", "next_month", "Next month"),
    ]

    def __init__(self, initial: DateType | None = None) -> None:
        super().__init__()
        self._selected = initial or datetime.now().date()

    def compose(self) -> ComposeResult:
        with Vertical(id="datepicker-dialog"):
            yield Label("", id="datepicker-month")
            yield Static("", id="datepicker-cal")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        d = self._selected
        self.query_one("#datepicker-month", Label).update(
            f"{cal_mod.month_name[d.month]} {d.year}"
        )
        lines = ["Mo Tu We Th Fr Sa Su"]
        for week in cal_mod.monthcalendar(d.year, d.month):
            row = []
            for day in week:
                if day == 0:
                    row.append("  ")
                elif day == d.day:
                    row.append(f"[reverse]{day:2}[/reverse]")
                else:
                    row.append(f"{day:2}")
            lines.append(" ".join(row))
        self.query_one("#datepicker-cal", Static).update("\n".join(lines))

    def _move(self, days: int) -> None:
        self._selected += timedelta(days=days)
        self._refresh()

    def _move_month(self, delta: int) -> None:
        d = self._selected
        month = d.month + delta
        year = d.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        max_day = cal_mod.monthrange(year, month)[1]
        self._selected = d.replace(year=year, month=month, day=min(d.day, max_day))
        self._refresh()

    def action_prev_day(self) -> None:
        self._move(-1)

    def action_next_day(self) -> None:
        self._move(1)

    def action_prev_week(self) -> None:
        self._move(-7)

    def action_next_week(self) -> None:
        self._move(7)

    def action_prev_month(self) -> None:
        self._move_month(-1)

    def action_next_month(self) -> None:
        self._move_month(1)

    def action_select_date(self) -> None:
        self.dismiss(self._selected.isoformat())

    def action_cancel(self) -> None:
        self.dismiss(None)
