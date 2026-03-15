"""Date utility helpers shared across screens and the main app."""

from datetime import date as DateType
from datetime import datetime, timedelta


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


def _parse_date_input(raw: str) -> DateType | None:
    """Parse a due date input string to a date object, for pre-populating the picker."""
    iso = _parse_due(raw.strip())
    if iso:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return None


def _parse_due(raw: str) -> str:
    """Parse a human-readable date into ISO 8601 string, or return ''."""
    if not raw:
        return ""
    raw = raw.strip().lower()
    today = datetime.now().date()
    if raw == "today":
        return today.isoformat() + "T00:00:00.000Z"
    if raw == "tomorrow":
        return (today + timedelta(days=1)).isoformat() + "T00:00:00.000Z"
    for fmt in ("%Y-%m-%d", "%b %d %Y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            return parsed.isoformat() + "T00:00:00.000Z"
        except ValueError:
            continue
    # "Mar 15" — no year, infer current or next year
    try:
        parsed = datetime.strptime(f"{raw} {today.year}", "%b %d %Y").date()
        if parsed < today:
            parsed = parsed.replace(year=today.year + 1)
        return parsed.isoformat() + "T00:00:00.000Z"
    except ValueError:
        pass
    return ""
