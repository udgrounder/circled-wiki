"""Local operational issue records used as input for later OS improvements."""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, List, Optional
from uuid import uuid4


ISSUE_AREAS = ("runtime", "cli", "agent_rules", "workflow", "integration", "bootstrap", "other")
ISSUE_SEVERITIES = ("low", "medium", "high", "critical")
ISSUE_REPORTERS = ("user", "agent", "operator", "automation")
ISSUE_STATUSES = ("open", "triaged", "mitigated", "verified", "resolved", "wont_fix")
_STATUS_TRANSITIONS = {
    "open": {"triaged", "wont_fix"},
    "triaged": {"mitigated", "wont_fix"},
    "mitigated": {"verified", "triaged"},
    "verified": {"resolved", "triaged"},
    "resolved": set(),
    "wont_fix": set(),
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "issue"


def record_system_issue(
    project_root: Path,
    *,
    title: str,
    summary: str,
    reported_by: str,
    reported_from: str = "operator",
    area: str = "other",
    severity: str = "medium",
    expected: str = "Not recorded.",
    actual: str = "Not recorded.",
    reproduction: str = "Not recorded.",
    improvement_hint: str = "Not recorded.",
    related_paths: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Write one local issue record without changing Knowledge data or OS assets."""
    if not title.strip() or not summary.strip() or not reported_by.strip():
        raise ValueError("title, summary, and reported_by must be non-empty")
    if area not in ISSUE_AREAS:
        raise ValueError(f"area must be one of: {', '.join(ISSUE_AREAS)}")
    if severity not in ISSUE_SEVERITIES:
        raise ValueError(f"severity must be one of: {', '.join(ISSUE_SEVERITIES)}")
    if reported_from not in ISSUE_REPORTERS:
        raise ValueError(f"reported_from must be one of: {', '.join(ISSUE_REPORTERS)}")
    timestamp = datetime.now(timezone.utc)
    issue_id = f"issue-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    issue_path = project_root / ".circled-wiki" / "issues" / f"{issue_id}-{_slug(title)}.md"
    issue_path.parent.mkdir(parents=True, exist_ok=True)
    related = related_paths or []
    related_section = "\n".join(f"- `{path}`" for path in related) or "- None recorded."
    content = f"""# {title.strip()}

- Issue ID: `{issue_id}`
- Recorded at: {timestamp.isoformat()}
- Reported by: {reported_by.strip()}
- Reported from: {reported_from}
- Area: {area}
- Severity: {severity}
- Status: open

## Summary

{summary.strip()}

## Expected result

{expected.strip()}

## Actual result

{actual.strip()}

## Reproduction or context

{reproduction.strip()}

## Related paths or artifacts

{related_section}

## Improvement hint

{improvement_hint.strip()}

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
"""
    issue_path.write_text(content, encoding="utf-8")
    return {"issue_id": issue_id, "path": issue_path.as_posix(), "status": "open"}


def update_system_issue_status(
    project_root: Path,
    *,
    issue_ref: str,
    status: str,
    actor: str,
    note: str,
    fixed_release: Optional[str] = None,
    verification: Optional[str] = None,
) -> Dict[str, object]:
    """Append an auditable Issue status transition without changing its facts."""
    if status not in ISSUE_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(ISSUE_STATUSES)}")
    if not issue_ref.strip() or not actor.strip() or not note.strip():
        raise ValueError("issue_ref, actor, and note must be non-empty")
    issue_path = _find_issue_path(project_root, issue_ref)
    content = issue_path.read_text(encoding="utf-8")
    match = re.search(r"^- Status: (.+)$", content, flags=re.MULTILINE)
    if match is None:
        raise ValueError("Issue record does not contain a Status field")
    current = match.group(1).strip()
    if current not in ISSUE_STATUSES:
        raise ValueError("Issue record has an unsupported current status")
    if status not in _STATUS_TRANSITIONS[current]:
        raise ValueError(f"invalid Issue status transition: {current} -> {status}")
    timestamp = datetime.now(timezone.utc).isoformat()
    content = content[:match.start(1)] + status + content[match.end(1):]
    history = (
        "\n## Status history\n\n"
        if "## Status history\n" not in content
        else ""
    )
    release_line = f"; fixed release: `{fixed_release.strip()}`" if fixed_release else ""
    verification_line = f"; verification: {verification.strip()}" if verification else ""
    history += f"- {timestamp}: `{current}` -> `{status}` by `{actor.strip()}` — {note.strip()}{release_line}{verification_line}\n"
    issue_path.write_text(content.rstrip() + "\n" + history, encoding="utf-8")
    return {
        "issue_ref": issue_ref,
        "path": issue_path.as_posix(),
        "previous_status": current,
        "status": status,
    }


def _find_issue_path(project_root: Path, issue_ref: str) -> Path:
    issues_root = project_root.resolve() / ".circled-wiki" / "issues"
    candidate = Path(issue_ref)
    if candidate.is_file() and issues_root in candidate.resolve().parents:
        return candidate.resolve()
    matches = [
        path for path in issues_root.glob("issue-*.md")
        if path.name.startswith(issue_ref) or f"`{issue_ref}`" in path.read_text(encoding="utf-8")
    ]
    if len(matches) != 1:
        raise ValueError("issue_ref must resolve to exactly one Issue record")
    return matches[0]
