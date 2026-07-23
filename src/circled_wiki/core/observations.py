"""Local operational issue records used as input for later OS improvements."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Dict, List, Optional
from uuid import uuid4

from circled_wiki.core.receipts import validate_issue_verification_receipts

ISSUE_AREAS = (
    "runtime", "cli", "agent_rules", "mcp", "validator", "workflow",
    "data", "integration", "bootstrap", "other",
)
ISSUE_SEVERITIES = ("low", "medium", "high", "critical")
ISSUE_REPORTERS = ("user", "agent", "operator", "automation")
ISSUE_STATUSES = ("open", "triaged", "mitigated", "verified", "resolved", "wont_fix")
ISSUE_CLASSIFICATIONS = (
    "product_defect", "installation_config", "data_quality",
    "operational_procedure", "external_dependency",
)
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
    impact: str = "Not recorded.",
    hypothesis: str = "Not recorded.",
    release_observed: Optional[str] = None,
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
    observed_release = release_observed or _installed_release(project_root)
    issue_id = f"issue-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    issue_path = project_root / "workspace" / "issues" / f"{issue_id}-{_slug(title)}.md"
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
- Release observed: {observed_release}
- Status: open

## Summary

{summary.strip()}

## Expected result

{expected.strip()}

## Actual result

{actual.strip()}

## Impact

{impact.strip()}

## Reproduction or context

{reproduction.strip()}

## Related paths or artifacts

{related_section}

## Improvement hint

{improvement_hint.strip()}

## Cause hypothesis

{hypothesis.strip()}

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
    deployed_release: Optional[str] = None,
    deployment_receipt: Optional[str] = None,
    verification_receipt: Optional[str] = None,
    classification: Optional[str] = None,
    next_action: Optional[str] = None,
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
    if status == "triaged":
        if classification not in ISSUE_CLASSIFICATIONS or not next_action or not next_action.strip():
            raise ValueError("triaged status requires classification and next_action")
    if status == "mitigated" and not fixed_release:
        raise ValueError("mitigated status requires fixed_release")
    if status == "verified":
        if not all((
            fixed_release,
            verification,
            deployed_release,
            deployment_receipt,
            verification_receipt,
        )):
            raise ValueError(
                "verified status requires fixed_release, deployed_release, "
                "deployment_receipt, verification, and verification_receipt"
            )
        if fixed_release.strip() != deployed_release.strip():
            raise ValueError("verified status requires deployed_release to match fixed_release")
        validate_issue_verification_receipts(
            project_root,
            fixed_release=fixed_release.strip(),
            deployed_release=deployed_release.strip(),
            actor=actor.strip(),
            deployment_receipt=deployment_receipt.strip(),
            verification_receipt=verification_receipt.strip(),
        )
        implemented_by = _history_actor(content, "mitigated")
        if implemented_by and actor.strip() == implemented_by:
            raise ValueError("verified status requires an independent actor")
    if status == "resolved":
        if not _history_has_release_and_verification(content):
            raise ValueError("resolved status requires prior fixed_release and verification evidence")
    timestamp = datetime.now(timezone.utc).isoformat()
    content = content[:match.start(1)] + status + content[match.end(1):]
    history = (
        "\n## Status history\n\n"
        if "## Status history\n" not in content
        else ""
    )
    release_line = f"; fixed release: `{fixed_release.strip()}`" if fixed_release else ""
    deployed_line = (
        f"; deployed release: `{deployed_release.strip()}`" if deployed_release else ""
    )
    deployment_line = (
        f"; deployment receipt: `{deployment_receipt.strip()}`"
        if deployment_receipt
        else ""
    )
    verification_line = f"; verification: {verification.strip()}" if verification else ""
    verification_receipt_line = (
        f"; verification receipt: `{verification_receipt.strip()}`"
        if verification_receipt
        else ""
    )
    classification_line = (
        f"; classification: `{classification}`" if classification else ""
    )
    next_action_line = f"; next action: {next_action.strip()}" if next_action else ""
    history += (
        f"- {timestamp}: `{current}` -> `{status}` by `{actor.strip()}` — "
        f"{note.strip()}{release_line}{deployed_line}{deployment_line}"
        f"{verification_line}{verification_receipt_line}{classification_line}"
        f"{next_action_line}\n"
    )
    issue_path.write_text(content.rstrip() + "\n" + history, encoding="utf-8")
    return {
        "issue_ref": issue_ref,
        "path": issue_path.as_posix(),
        "previous_status": current,
        "status": status,
    }


def migrate_legacy_system_issues(
    project_root: Path,
    *,
    issue_refs: Optional[List[str]] = None,
    apply: bool = False,
) -> Dict[str, object]:
    """Plan or explicitly move legacy Issue records into the user-owned working plane."""
    project_root = project_root.resolve()
    legacy_root = project_root / ".circled-wiki" / "issues"
    destination_root = project_root / "workspace" / "issues"
    candidates = sorted(legacy_root.glob("issue-*.md"))
    if issue_refs:
        selected = []
        for reference in issue_refs:
            matches = [
                path
                for path in candidates
                if path.name.startswith(reference)
                or f"`{reference}`" in path.read_text(encoding="utf-8")
            ]
            if len(matches) != 1:
                raise ValueError(
                    "each legacy issue_ref must resolve to exactly one Issue record"
                )
            if matches[0] not in selected:
                selected.append(matches[0])
        candidates = selected
    actions = []
    for source in candidates:
        destination = destination_root / source.name
        if destination.exists():
            raise ValueError(f"legacy Issue migration destination exists: {destination.name}")
        actions.append({
            "issue": source.name,
            "source": source.as_posix(),
            "destination": destination.as_posix(),
            "action": "move",
        })
    moved: List[tuple[Path, Path]] = []
    if apply:
        destination_root.mkdir(parents=True, exist_ok=True)
        try:
            for action in actions:
                source = Path(action["source"])
                destination = Path(action["destination"])
                source.replace(destination)
                moved.append((source, destination))
        except OSError as error:
            for source, destination in reversed(moved):
                if destination.exists() and not source.exists():
                    destination.replace(source)
            raise RuntimeError(
                "legacy Issue migration failed; completed moves were rolled back"
            ) from error
    return {
        "applied": apply,
        "actions": actions,
        "moved": len(moved),
        "legacy_root": legacy_root.as_posix(),
        "destination_root": destination_root.as_posix(),
    }


def _history_actor(content: str, target_status: str) -> Optional[str]:
    matches = re.findall(rf"`[^`]+` -> `{re.escape(target_status)}` by `([^`]+)`", content)
    return matches[-1] if matches else None


def _history_has_release_and_verification(content: str) -> bool:
    return all(
        marker in content
        for marker in (
            "fixed release: `",
            "deployed release: `",
            "deployment receipt: `",
            "; verification: ",
            "verification receipt: `",
        )
    )


def _find_issue_path(project_root: Path, issue_ref: str) -> Path:
    project_root = project_root.resolve()
    issue_roots = (
        project_root / "workspace" / "issues",
        project_root / ".circled-wiki" / "issues",
    )
    candidate = Path(issue_ref)
    if candidate.is_file() and any(root in candidate.resolve().parents for root in issue_roots):
        return candidate.resolve()
    matches = [
        path
        for issues_root in issue_roots
        for path in issues_root.glob("issue-*.md")
        if path.name.startswith(issue_ref) or f"`{issue_ref}`" in path.read_text(encoding="utf-8")
    ]
    if len(matches) != 1:
        raise ValueError("issue_ref must resolve to exactly one Issue record")
    return matches[0]


def _installed_release(project_root: Path) -> str:
    manifest = project_root / ".circled-wiki" / "manifest.json"
    if not manifest.is_file():
        return "unknown"
    try:
        release = json.loads(manifest.read_text(encoding="utf-8")).get("os_release")
    except (OSError, ValueError, AttributeError):
        return "unknown"
    return release if isinstance(release, str) and release.strip() else "unknown"
