"""Access to local Beads issue databases via ~/.beads/registry.json."""

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REGISTRY_PATH = Path.home() / ".beads" / "registry.json"
LABELS_FILE = Path.home() / ".config" / "tasks-tui" / "labels.json"


def _beads_search_root() -> Path:
    """Return the directory to scan for beads workspaces, from config or default ~/Code."""
    try:
        from tasks_tui.config import CONFIG_PATH
        import json as _json
        if CONFIG_PATH.exists():
            data = _json.loads(CONFIG_PATH.read_text())
            root = data.get("sources", {}).get("beads_search_root", "~/Code")
            return Path(root).expanduser()
    except Exception:
        pass
    return Path.home() / "Code"

STATUSES = ["open", "in_progress", "blocked", "deferred"]


@dataclass
class BeadsIssue:
    id: str
    title: str
    status: str  # open | in_progress | blocked | deferred
    priority: int  # 0 (highest) – 4 (lowest)
    due_at: str  # ISO datetime string or ""
    description: str
    project: str  # last path component of workspace_path
    db_path: str  # path to the .beads/beads.db for this issue

    @property
    def status_icon(self) -> str:
        return {"open": "○", "in_progress": "◐", "blocked": "●", "deferred": "❄"}.get(
            self.status, "○"
        )

    @property
    def status_css_class(self) -> str:
        return {
            "open": "beads-open",
            "in_progress": "beads-inprogress",
            "blocked": "beads-blocked",
            "deferred": "beads-deferred",
        }.get(self.status, "beads-open")

    @property
    def priority_label(self) -> str:
        return f"P{self.priority}"

    @property
    def due_label(self) -> str:
        if not self.due_at:
            return "today"
        try:
            due_dt = datetime.fromisoformat(self.due_at.replace("Z", "+00:00")).date()
            days = (due_dt - datetime.now().date()).days
            if days < 0:
                return "overdue"
            if days == 0:
                return "today"
            if days == 1:
                return "tomorrow"
            if days < 7:
                return f"in {days}d"
            return due_dt.strftime("%b %-d")
        except ValueError:
            return ""

    @property
    def due_css_class(self) -> str:
        if not self.due_at:
            return "due-urgent"
        try:
            due_dt = datetime.fromisoformat(self.due_at.replace("Z", "+00:00")).date()
            days = (due_dt - datetime.now().date()).days
            if days < 0:
                return "due-overdue"
            if days <= 1:
                return "due-urgent"
            if days <= 4:
                return "due-soon"
            return "due-label"
        except ValueError:
            return "due-label"

    @property
    def parent_id(self) -> str | None:
        """Return parent issue ID by stripping the last .N suffix, or None if top-level."""
        idx = self.id.rfind(".")
        return self.id[:idx] if idx != -1 else None

    @property
    def depth(self) -> int:
        """Hierarchy depth: 0 for top-level, 1 for child, 2 for grandchild, etc."""
        return self.id.count(".")


def get_beads_label(issue_id: str, default: str) -> str:
    """Return the display label for a beads issue, falling back to project name."""
    if not LABELS_FILE.exists():
        return default
    try:
        return json.loads(LABELS_FILE.read_text()).get(issue_id, default)
    except (json.JSONDecodeError, OSError):
        return default


def set_beads_label(issue_id: str, label: str, default: str) -> None:
    """Persist a custom label for a beads issue. Removes entry if label equals default."""
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    labels: dict = {}
    if LABELS_FILE.exists():
        try:
            labels = json.loads(LABELS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    if label == default or not label:
        labels.pop(issue_id, None)
    else:
        labels[issue_id] = label
    tmp = LABELS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(labels, indent=2))
    os.replace(tmp, LABELS_FILE)


def discover_beads_workspaces() -> dict[str, str]:
    """Return {workspace_path: db_path} from registry + ~/Code scan (deduped)."""
    found: dict[str, str] = {}

    # Registered workspaces (SQLite-backed daemons)
    if REGISTRY_PATH.exists():
        try:
            registry: list[dict] = json.loads(REGISTRY_PATH.read_text())
            for entry in registry:
                wp = entry.get("workspace_path", "")
                dp = entry.get("database_path", "")
                if wp and dp:
                    found[wp] = dp
        except (json.JSONDecodeError, OSError):
            pass

    # Scan search root for beads workspaces not in the registry
    search_root = _beads_search_root()
    if search_root.exists():
        # SQLite-backed workspaces
        for db in search_root.glob("*/.beads/beads.db"):
            workspace = str(db.parent.parent)
            if workspace not in found:
                found[workspace] = str(db)
        # Dolt-backed workspaces (marker file created by bd init)
        for marker in search_root.glob("*/.beads/dolt/.bd-dolt-ok"):
            dolt_dir = marker.parent
            workspace = str(dolt_dir.parent.parent)
            if workspace not in found:
                found[workspace] = str(dolt_dir)

    return found


def list_issues_via_cli(workspace_path: str, db_path: str) -> list[BeadsIssue]:
    """Use bd list --json --db to fetch active issues (works for SQLite and dolt)."""
    project = Path(workspace_path).name
    try:
        result = subprocess.run(
            ["bd", "list", "--json", "--db", db_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return []
        items: list[dict] = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return []

    issues = []
    for item in items:
        status = item.get("status", "open")
        if status in ("closed", "tombstone"):
            continue
        issues.append(
            BeadsIssue(
                id=item["id"],
                title=item.get("title", ""),
                status=status,
                priority=item.get("priority", 2),
                due_at=item.get("due_at", "") or "",
                description=item.get("description", "") or "",
                project=project,
                db_path=db_path,
            )
        )
    return issues


def list_beads_issues() -> list[BeadsIssue]:
    """Return all active issues across all discovered beads workspaces."""
    workspaces = discover_beads_workspaces()
    issues: list[BeadsIssue] = []
    for workspace_path, db_path in workspaces.items():
        if not Path(db_path).exists():
            continue
        issues.extend(list_issues_via_cli(workspace_path, db_path))
    return issues


def list_closed_mapped_issues(beads_ids: set[str], db_path: str) -> list[BeadsIssue]:
    """Return closed/deleted issues from db_path whose IDs are in beads_ids."""
    if not beads_ids or not Path(db_path).exists():
        return []
    project = Path(db_path).parent.parent.name
    try:
        result = subprocess.run(
            ["bd", "list", "--json", "--status=closed", "--db", db_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return []
        items: list[dict] = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return []

    return [
        BeadsIssue(
            id=item["id"],
            title=item.get("title", ""),
            status=item.get("status", "closed"),
            priority=item.get("priority", 2),
            due_at=item.get("due_at", "") or "",
            description=item.get("description", "") or "",
            project=project,
            db_path=db_path,
        )
        for item in items
        if item.get("id") in beads_ids
    ]


def update_beads_issue(
    issue: BeadsIssue,
    title: str,
    status: str,
    priority: int,
    description: str,
    due: str,
) -> None:
    """Update a beads issue via the bd CLI."""
    cmd = [
        "bd",
        "update",
        issue.id,
        "--db",
        issue.db_path,
        "--title",
        title,
        "--status",
        status,
        "--priority",
        str(priority),
        "--description",
        description,
    ]
    if due:
        cmd += ["--due", due]
    else:
        cmd += ["--due", ""]
    subprocess.run(cmd, check=True, capture_output=True)


def create_beads_issue(
    workspace_path: str,
    db_path: str,
    title: str,
    description: str = "",
    due: str = "",
    priority: int = 2,
) -> str:
    """Create a top-level beads issue via the bd CLI. Returns the new issue ID."""
    cmd = ["bd", "create", title, "--db", db_path, "--silent"]
    if description:
        cmd += ["--description", description]
    if due:
        cmd += ["--due", due]
    if priority != 2:
        cmd += ["--priority", str(priority)]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def create_beads_child_issue(
    parent: BeadsIssue,
    title: str,
    description: str = "",
    due: str = "",
    priority: int = 2,
) -> str:
    """Create a child issue under parent via the bd CLI. Returns the new issue ID."""
    cmd = ["bd", "create", title, "--parent", parent.id, "--db", parent.db_path, "--silent"]
    if description:
        cmd += ["--description", description]
    if due:
        cmd += ["--due", due]
    if priority != 2:
        cmd += ["--priority", str(priority)]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()
