# Custom Task Sort — Brainstorm

**Date:** 2026-05-12
**Status:** Ready for planning

---

## What We're Building

A way for users to choose how the open task list is sorted at runtime. The sort is controlled through the existing filter modal (key `f`) and resets to the default on each session start.

**Two sort options:**
1. **Due date** (current default) — tasks with a due date first, sorted by urgency (`days_until_due`), no-due-date tasks last
2. **Label** — group/sort by the `[label]` prefix alphabetically; within the same label, fall back to due date ordering

---

## Why This Approach

- Extending the filter modal keeps UX consistent — users already go to `f` for display preferences
- In-memory only matches how filters work today, avoiding a new config file dependency
- Two sort fields (due date + label) covers the primary use cases without over-engineering

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| Sort fields | Due date, Label | Most useful for the label-based workflow already in use |
| UX entry point | Filter modal (`f`) | Consistent with existing filter UX; no new keybinding |
| Persistence | In-memory, resets on restart | Simpler; consistent with existing filter behavior |
| Default sort | Due date | Preserves current behavior for existing users |

---

## Implementation Notes

- `task_list.py:46-48` — the sort key tuple to change based on selected sort
- `config_screens.py` — filter modal to extend with a sort `Select` widget
- `app.py` — pass `sort_by` state alongside `filter_days` / `filter_lists` to `render_task_list()`
- Sort state lives on `GTasksApp` (same pattern as `filter_days`)

---

## Open Questions

None.
