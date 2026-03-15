"""Shared fixtures for gtasks-tui tests."""

from datetime import date
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def no_beads_issues():
    """Prevent live beads discovery and skip setup screen in all app tests."""
    with patch("tasks_tui.app.list_beads_issues", return_value=[]), \
         patch("tasks_tui.app.CONFIG_PATH") as mock_path:
        mock_path.exists.return_value = True
        yield


@pytest.fixture
def freezegun_today():
    """Freeze datetime.now() to 2026-03-12 for deterministic date tests."""
    fixed_date = date(2026, 3, 12)
    with patch("tasks_tui.tasks_api.datetime") as mock_dt, \
         patch("tasks_tui.app.datetime") as mock_app_dt, \
         patch("tasks_tui.date_utils.datetime") as mock_du_dt:
        mock_dt.fromisoformat.side_effect = lambda s: __import__("datetime").datetime.fromisoformat(s)
        mock_dt.now.return_value.date.return_value = fixed_date
        mock_app_dt.now.return_value.date.return_value = fixed_date
        mock_app_dt.strptime.side_effect = __import__("datetime").datetime.strptime
        mock_du_dt.now.return_value.date.return_value = fixed_date
        mock_du_dt.strptime.side_effect = __import__("datetime").datetime.strptime
        mock_du_dt.fromisoformat.side_effect = lambda s: __import__("datetime").datetime.fromisoformat(s)
        yield
