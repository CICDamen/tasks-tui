"""Date utility helpers shared across screens and the main app."""

from datetime import date as DateType
from datetime import datetime


def _iso_to_date(iso: str) -> DateType | None:
    """Convert ISO 8601 string to date, or None."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _format_date_label(iso: str) -> str:
    """Format an ISO date string for display in the date button."""
    d = _iso_to_date(iso)
    if d is None:
        return "📅  No date"
    return f"📅  {d.strftime('%b %-d, %Y')}"
