---
title: "feat: Add custom task sort to filter modal"
type: feat
status: active
date: 2026-05-12
---

# feat: Add Custom Task Sort to Filter Modal

Add a sort selector to the existing filter modal (`f`) so users can choose between **Due date** (default) and **Label** ordering for the open task list. State is in-memory only and resets to the default on restart.

## Acceptance Criteria

- [ ] Filter modal contains a "Sort by" `Select` widget with options: "Due date" and "Label"
- [ ] Default selection is "Due date" — preserves existing sort behavior exactly
- [ ] "Due date" sort: `(days_until_due is None, days_until_due or 0, label)` — tasks without due dates last, urgency ascending, label as tiebreaker
- [ ] "Label" sort: tasks grouped alphabetically by `[label]` prefix; tasks with no label appear **last**; within a label, secondary sort by due date ascending
- [ ] Modal opens with the currently active sort pre-selected (consistent with how `filter_days` works today)
- [ ] Subtasks are not independently sorted — they continue to follow their parent (existing behavior)
- [ ] Completed tasks section sort order is unchanged
- [ ] Sort state resets to "Due date" on app restart (no persistence)

## Implementation

Three files change. No new files needed.

### 1. `src/gtasks_tui/task_list.py`

Add `sort_key: str = "due_date"` parameter to `render_task_list` (line 12).

Replace the hardcoded sort at lines 46–48:

```python
# task_list.py:46
if sort_key == "label":
    top_level.sort(key=lambda t: (
        not t.label,              # unlabeled tasks last
        t.label or "",            # alphabetical among labeled
        t.days_until_due is None,
        t.days_until_due or 0,
    ))
else:  # "due_date" (default)
    top_level.sort(
        key=lambda t: (t.days_until_due is None, t.days_until_due or 0, t.label)
    )
```

### 2. `src/gtasks_tui/screens/config_screens.py`

Add options constant near `_DAYS_OPTIONS` (line ~11):

```python
# config_screens.py
_SORT_OPTIONS: list[tuple[str, str]] = [
    ("Due date", "due_date"),
    ("Label", "label"),
]
```

Extend `FilterScreen.__init__` with `sort_key: str = "due_date"`, store as `self._sort_key`.

Add a "Sort by" `Select` widget to `compose()` alongside the existing `"filter-days"` Select:

```python
# config_screens.py — inside compose()
yield Label("Sort by")
yield Select(
    [(label, value) for label, value in _SORT_OPTIONS],
    value=self._sort_key,
    id="sort-key",
)
```

Extend `action_close` to read and include the sort value in the dismiss dict:

```python
# config_screens.py — action_close
sort_key = self.query_one("#sort-key", Select).value or "due_date"
self.dismiss({"days": days, "lists": selected, "sort_key": sort_key})
```

### 3. `src/gtasks_tui/app.py`

Add state field in `__init__` (after `self._filter_lists`, line ~57):

```python
# app.py — __init__
self._sort_key: str = "due_date"
```

In `action_filter`, pass `sort_key=self._sort_key` to `FilterScreen` and read it back in `on_result`:

```python
# app.py — action_filter
def on_result(result: dict | None) -> None:
    if result is not None:
        self._filter_days = result["days"]
        self._filter_lists = result.get("lists")
        self._sort_key = result.get("sort_key", "due_date")  # add this line
        self._apply_loaded_tasks(self._tasks, self._completed_tasks)

self.push_screen(
    FilterScreen(
        filter_days=self._filter_days,
        available_lists=self._available_lists,
        selected_lists=self._filter_lists,
        sort_key=self._sort_key,          # add this argument
    ),
    on_result,
)
```

Forward `sort_key` in all `render_task_list` calls (lines ~104 and inside `_apply_loaded_tasks`):

```python
# app.py — render_task_list call sites
render_task_list(
    self.query_one("#task-list", ListView),
    self._tasks,
    self._completed_tasks,
    filter_days=self._filter_days,
    filter_lists=self._filter_lists,
    sort_key=self._sort_key,    # add this argument
)
```

## References

- Current sort logic: `src/gtasks_tui/task_list.py:46-48`
- Filter modal: `src/gtasks_tui/screens/config_screens.py:20-87`
- App state + filter wiring: `src/gtasks_tui/app.py:52-59, 217-231`
- Brainstorm: `docs/brainstorms/2026-05-12-custom-task-sort-brainstorm.md`
