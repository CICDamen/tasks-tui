"""Shared fixtures for gtasks-tui tests."""

from datetime import date
from unittest.mock import patch

import pytest

import gtasks_tui.tasks_api


@pytest.fixture(autouse=True)
def reset_tasklists_cache():
    """Reset the module-level tasklist cache before each test for isolation."""
    gtasks_tui.tasks_api._cached_tasklists = None
    yield
    gtasks_tui.tasks_api._cached_tasklists = None


@pytest.fixture
def freezegun_today():
    """Freeze datetime.now() to 2026-03-12 for deterministic date tests."""
    fixed_date = date(2026, 3, 12)
    with (
        patch("gtasks_tui.tasks_api.datetime") as mock_dt,
        patch("gtasks_tui.date_utils.datetime") as mock_du_dt,
    ):
        mock_dt.fromisoformat.side_effect = lambda s: __import__(
            "datetime"
        ).datetime.fromisoformat(s)
        mock_dt.now.return_value.date.return_value = fixed_date
        mock_du_dt.now.return_value.date.return_value = fixed_date
        mock_du_dt.strptime.side_effect = __import__("datetime").datetime.strptime
        mock_du_dt.fromisoformat.side_effect = lambda s: __import__(
            "datetime"
        ).datetime.fromisoformat(s)
        yield
