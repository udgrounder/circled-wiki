"""Product-workspace intake, review, triage, and archival for operational issues."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Dict, List, Optional
from uuid import uuid4

from circled_wiki.core.frontmatter import parse_markdown, render_markdown


REVIEW_DECISIONS = ("accepted", "needs_information", "duplicate", "rejected", "blocked")
HISTORY_RELATIONS = (
    "recurrence", "regression", "duplicate", "related", "new", "undetermined",
)
ISSUE_CLASSIFICATIONS = (
    "product_defect", "installation_config", "data_quality",
    "operational_procedure", "external_dependency",
)
ARCHIVE_DISPOSITIONS = ("resolved", "wont_fix", "duplicate", "rejected", "deferred")
_SAFE_REF = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def intake_operational_issue(
    workspace_root: Path,
    source_project_root: Path,
    *,
    project_ref: str,
    issue_ref: str,
    requested_by: str,
    moved_by: str,
) -> Dict[str, object]:
    """Atomically move one committed operational issue into the product inbox."""
    workspace_root = workspace_root.resolve()
    source_project_root = source_project_root.resolve()
    if not _SAFE_REF.fullmatch(project_ref):
        raise ValueError("project_ref must be a lowercase safe alias")
    if not issue_ref.strip() or not requested_by.strip() or not moved_by.strip():
        raise ValueError("issue_ref, requested_by, and moved_by must be non-empty")
    installed_release = _require_circled_install(source_project_root)
    source = _find_operational_issue(source_project_root, issue_ref)
    revision = _require_committed_clean_issue(source_project_root, source)
    original = source.read_text(encoding="utf-8")
    source_issue_id = _source_issue_id(original, source)
    destination = workspace_root / "issues" / "inbox" / project_ref / f"{source_issue_id}.md"
    if destination.exists():
        raise ValueError("Workspace Inbox already contains this operational issue")
    if _find_workspace_issue(workspace_root, source_issue_id):
        raise ValueError("Workspace Archive already contains this operational issue")

    similar = find_similar_archive_history(
        workspace_root,
        source_issue_id=source_issue_id,
        source_text=original,
    )
    now = datetime.now(timezone.utc).isoformat()
    frontmatter = {
        "type": "workspace_issue",
        "status": "pending_review",
        "workspace_issue_id": f"workspace-issue-{uuid4().hex}",
        "source_project_ref": project_ref,
        "source_issue_id": source_issue_id,
        "source_release": _field_value(original, "Release observed") or installed_release,
        "source_git_revision": revision,
        "moved_at": now,
        "moved_by": moved_by.strip(),
        "requested_by": requested_by.strip(),
        "canonical_issue_key": None,
        "occurrence": 1,
        "review": {
            "reviewed_by": None,
            "reviewed_at": None,
            "decision": None,
            "note": None,
        },
        "processing": {
            "classification": None,
            "disposition": None,
            "history_relation": None,
            "similar_history": similar,
            "linked_work": [],
            "linked_release": None,
            "linked_deployment_receipt": None,
            "linked_verification_receipt": None,
        },
        "archive": {
            "archived_at": None,
            "archived_by": None,
            "reason": None,
            "restore_condition": None,
        },
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source.replace(destination)
    except OSError as error:
        if not source.exists():
            raise RuntimeError("Issue move failed and source preservation could not be confirmed") from error
        raise RuntimeError("Issue move failed; the source Issue remains at its original path") from error
    try:
        destination.write_text(render_markdown(frontmatter, original), encoding="utf-8")
    except OSError:
        destination.replace(source)
        raise
    return {
        "workspace_issue_id": frontmatter["workspace_issue_id"],
        "source_issue_id": source_issue_id,
        "path": destination.as_posix(),
        "status": "pending_review",
        "source_git_revision": revision,
        "similar_history": similar,
    }


def review_workspace_issue(
    item_path: Path,
    *,
    reviewed_by: str,
    decision: str,
    history_relation: str,
    canonical_issue_key: Optional[str] = None,
    note: str = "",
) -> Dict[str, object]:
    """Record the identified user's review receipt before triage."""
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"decision must be one of: {', '.join(REVIEW_DECISIONS)}")
    if history_relation not in HISTORY_RELATIONS:
        raise ValueError(
            f"history_relation must be one of: {', '.join(HISTORY_RELATIONS)}"
        )
    if not reviewed_by.strip():
        raise ValueError("reviewed_by must be non-empty")
    if decision == "accepted" and history_relation == "undetermined":
        raise ValueError("accepted review requires a determined history relation")
    if decision == "duplicate" and history_relation != "duplicate":
        raise ValueError("duplicate review requires duplicate history_relation")
    document = parse_markdown(item_path)
    metadata = document.frontmatter
    if metadata.get("status") != "pending_review":
        raise ValueError("only pending_review Workspace Issues can be reviewed")
    if canonical_issue_key is not None and not _SAFE_REF.fullmatch(canonical_issue_key):
        raise ValueError("canonical_issue_key must be a lowercase safe alias")
    if history_relation in {"recurrence", "regression", "duplicate", "related"}:
        if not canonical_issue_key:
            raise ValueError("selected history relation requires canonical_issue_key")
    metadata["canonical_issue_key"] = canonical_issue_key
    metadata["review"] = {
        "reviewed_by": reviewed_by.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "note": note.strip() or None,
    }
    metadata["processing"]["history_relation"] = history_relation
    metadata["status"] = decision
    item_path.write_text(render_markdown(metadata, document.body), encoding="utf-8")
    return {
        "workspace_issue_id": metadata["workspace_issue_id"],
        "path": item_path.as_posix(),
        "status": decision,
        "history_relation": history_relation,
    }


def triage_workspace_issue(
    item_path: Path,
    *,
    classification: str,
    disposition: Optional[str] = None,
    linked_work: Optional[List[str]] = None,
) -> Dict[str, object]:
    """Classify a user-accepted issue without granting unrelated authority."""
    if classification not in ISSUE_CLASSIFICATIONS:
        raise ValueError(
            f"classification must be one of: {', '.join(ISSUE_CLASSIFICATIONS)}"
        )
    document = parse_markdown(item_path)
    metadata = document.frontmatter
    review = metadata.get("review") or {}
    if metadata.get("status") != "accepted" or not all(
        review.get(field) for field in ("reviewed_by", "reviewed_at", "decision")
    ):
        raise ValueError("triage requires an accepted user review receipt")
    processing = metadata["processing"]
    processing["classification"] = classification
    if disposition is not None:
        if disposition not in ARCHIVE_DISPOSITIONS:
            raise ValueError(
                f"disposition must be one of: {', '.join(ARCHIVE_DISPOSITIONS)}"
            )
        processing["disposition"] = disposition
    processing["linked_work"] = list(linked_work or processing.get("linked_work") or [])
    metadata["status"] = "triaged"
    item_path.write_text(render_markdown(metadata, document.body), encoding="utf-8")
    return {
        "workspace_issue_id": metadata["workspace_issue_id"],
        "path": item_path.as_posix(),
        "status": "triaged",
        "classification": classification,
    }


def link_workspace_issue_resolution(
    item_path: Path,
    *,
    disposition: str,
    release: Optional[str] = None,
    deployment_receipt: Optional[str] = None,
    verification_receipt: Optional[str] = None,
) -> Dict[str, object]:
    """Attach processing results which the archive gate can verify."""
    if disposition not in ARCHIVE_DISPOSITIONS:
        raise ValueError(f"disposition must be one of: {', '.join(ARCHIVE_DISPOSITIONS)}")
    document = parse_markdown(item_path)
    metadata = document.frontmatter
    if metadata.get("status") not in {"accepted", "triaged", "duplicate", "rejected"}:
        raise ValueError("processing results require a reviewed processable issue")
    processing = metadata["processing"]
    processing["disposition"] = disposition
    processing["linked_release"] = release
    processing["linked_deployment_receipt"] = deployment_receipt
    processing["linked_verification_receipt"] = verification_receipt
    item_path.write_text(render_markdown(metadata, document.body), encoding="utf-8")
    return {"path": item_path.as_posix(), "disposition": disposition}


def archive_workspace_issue(
    workspace_root: Path,
    item_path: Path,
    *,
    archived_by: str,
    reason: str,
    restore_condition: str,
) -> Dict[str, object]:
    """Move a reviewed, processed item to a date-organized Archive path."""
    workspace_root = workspace_root.resolve()
    item_path = item_path.resolve()
    inbox_root = workspace_root / "issues" / "inbox"
    if inbox_root not in item_path.parents:
        raise ValueError("Workspace Issue must be inside workspace/issues/inbox")
    if not archived_by.strip() or not reason.strip() or not restore_condition.strip():
        raise ValueError("archive actor, reason, and restore condition are required")
    document = parse_markdown(item_path)
    metadata = document.frontmatter
    review = metadata.get("review") or {}
    processing = metadata.get("processing") or {}
    if not all(review.get(field) for field in ("reviewed_by", "reviewed_at", "decision")):
        raise ValueError("archive requires an identified user review receipt")
    disposition = processing.get("disposition")
    if disposition not in ARCHIVE_DISPOSITIONS:
        raise ValueError("archive requires a final disposition")
    canonical_key = metadata.get("canonical_issue_key")
    if not canonical_key:
        canonical_key = _default_canonical_key(metadata.get("source_issue_id", "issue"))
        metadata["canonical_issue_key"] = canonical_key
    if disposition == "resolved" and not all(
        processing.get(field)
        for field in (
            "linked_release",
            "linked_deployment_receipt",
            "linked_verification_receipt",
        )
    ):
        raise ValueError(
            "resolved archive requires release, deployment, and verification receipts"
        )
    archived_at = datetime.now(timezone.utc)
    archive_root = workspace_root / "issues" / "archived"
    occurrence = _next_occurrence(workspace_root, str(canonical_key))
    destination = (
        archive_root
        / archived_at.strftime("%Y")
        / archived_at.strftime("%m")
        / f"{archived_at.strftime('%Y%m%dT%H%M%SZ')}-{canonical_key}-v{occurrence:04d}.md"
    )
    if destination.exists():
        raise ValueError("Archive occurrence already exists")
    workspace_issue_id = metadata.get("workspace_issue_id")
    if _archived_workspace_id(workspace_root, workspace_issue_id):
        raise ValueError("Workspace Issue already exists in Archive")
    metadata["occurrence"] = occurrence
    metadata["status"] = "archived"
    metadata["archive"] = {
        "archived_at": archived_at.isoformat(),
        "archived_by": archived_by.strip(),
        "reason": reason.strip(),
        "restore_condition": restore_condition.strip(),
    }
    rendered = render_markdown(metadata, document.body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        item_path.replace(destination)
        destination.write_text(rendered, encoding="utf-8")
    except OSError:
        if destination.exists() and not item_path.exists():
            destination.replace(item_path)
        raise
    return {
        "workspace_issue_id": workspace_issue_id,
        "path": destination.as_posix(),
        "status": "archived",
        "canonical_issue_key": canonical_key,
        "occurrence": occurrence,
    }


def find_similar_archive_history(
    workspace_root: Path,
    *,
    source_issue_id: str,
    source_text: str,
) -> List[Dict[str, object]]:
    """Return explainable candidates; similarity never makes the relationship decision."""
    archive_root = workspace_root.resolve() / "issues" / "archived"
    candidates: List[Dict[str, object]] = []
    source_area = _field_value(source_text, "Area")
    source_title = _first_heading(source_text)
    for path in sorted(archive_root.rglob("*.md")):
        try:
            document = parse_markdown(path)
        except (OSError, ValueError):
            continue
        metadata = document.frontmatter
        reasons = []
        if metadata.get("source_issue_id") == source_issue_id:
            reasons.append("same source_issue_id")
        archived_area = _field_value(document.body, "Area")
        if source_area and archived_area == source_area:
            reasons.append(f"same area: {source_area}")
        archived_title = _first_heading(document.body)
        if source_title and archived_title and source_title.casefold() == archived_title.casefold():
            reasons.append("same normalized title")
        if reasons:
            processing = metadata.get("processing") or {}
            candidates.append({
                "archive_ref": path.relative_to(archive_root).as_posix(),
                "similarity_reasons": reasons,
                "previous_resolution": processing.get("disposition"),
                "previous_fixed_release": processing.get("linked_release"),
                "previous_verification": processing.get("linked_verification_receipt"),
                "previous_regression_tests": processing.get("linked_work") or [],
            })
    return candidates


def _run_git(project_root: Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(project_root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def _require_circled_install(project_root: Path) -> str:
    manifest_path = project_root / ".circled-wiki" / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("source project must be a Circled Wiki installation")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("source Circled Wiki manifest is invalid") from error
    release = manifest.get("os_release")
    if not isinstance(release, str) or not release.strip():
        raise ValueError("source Circled Wiki manifest must identify os_release")
    return release.strip()


def _require_committed_clean_issue(project_root: Path, issue_path: Path) -> str:
    relative = issue_path.relative_to(project_root).as_posix()
    tracked = _run_git(project_root, "ls-files", "--error-unmatch", "--", relative)
    if tracked.returncode != 0:
        raise ValueError("operational Issue must be tracked by Git")
    status = _run_git(project_root, "status", "--porcelain", "--", relative)
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("operational Issue must not have uncommitted changes")
    revision = _run_git(project_root, "log", "-1", "--format=%H", "--", relative)
    if revision.returncode != 0 or not revision.stdout.strip():
        raise ValueError("operational Issue must exist in a Git commit")
    return revision.stdout.strip()


def _find_operational_issue(project_root: Path, issue_ref: str) -> Path:
    roots = (
        project_root / "workspace" / "issues",
        project_root / ".circled-wiki" / "issues",
    )
    matches = [
        path
        for root in roots
        for path in root.glob("issue-*.md")
        if path.name.startswith(issue_ref)
        or f"`{issue_ref}`" in path.read_text(encoding="utf-8")
    ]
    if len(matches) != 1:
        raise ValueError("issue_ref must resolve to exactly one operational Issue")
    return matches[0]


def _find_workspace_issue(workspace_root: Path, source_issue_id: str) -> bool:
    for root in (
        workspace_root / "issues" / "inbox",
        workspace_root / "issues" / "archived",
    ):
        for path in root.rglob("*.md"):
            try:
                metadata = parse_markdown(path).frontmatter
            except (OSError, ValueError):
                continue
            if metadata.get("source_issue_id") == source_issue_id:
                return True
    return False


def _archived_workspace_id(workspace_root: Path, workspace_issue_id: object) -> bool:
    if not workspace_issue_id:
        return False
    for path in (workspace_root / "issues" / "archived").rglob("*.md"):
        try:
            if parse_markdown(path).frontmatter.get("workspace_issue_id") == workspace_issue_id:
                return True
        except (OSError, ValueError):
            continue
    return False


def _next_occurrence(workspace_root: Path, canonical_issue_key: str) -> int:
    values = []
    for path in (workspace_root / "issues" / "archived").rglob("*.md"):
        try:
            metadata = parse_markdown(path).frontmatter
        except (OSError, ValueError):
            continue
        if metadata.get("canonical_issue_key") == canonical_issue_key:
            occurrence = metadata.get("occurrence")
            if isinstance(occurrence, int) and occurrence > 0:
                values.append(occurrence)
    return max(values, default=0) + 1


def _source_issue_id(content: str, path: Path) -> str:
    match = re.search(r"^- Issue ID: `([^`]+)`$", content, flags=re.MULTILINE)
    return match.group(1) if match else path.stem


def _field_value(content: str, field: str) -> Optional[str]:
    match = re.search(rf"^- {re.escape(field)}: (.+)$", content, flags=re.MULTILINE)
    return match.group(1).strip().strip("`") if match else None


def _first_heading(content: str) -> Optional[str]:
    match = re.search(r"^# (.+)$", content, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _default_canonical_key(source_issue_id: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", source_issue_id.casefold()).strip("-")
    return key or f"issue-{uuid4().hex[:8]}"
