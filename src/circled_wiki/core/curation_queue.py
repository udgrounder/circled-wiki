"""Minimal, rebuildable curation work items stored outside immutable Evidence."""

from pathlib import Path
from typing import Dict, List
from uuid import UUID, uuid4

from .frontmatter import parse_markdown, render_markdown


def enqueue_curation_work(knowledge_root: Path, evidence_id: str, evidence_path: Path) -> Path:
    """Atomically register one immutable Evidence record for later curation."""
    knowledge_root = knowledge_root.resolve()
    evidence_path = evidence_path.resolve()
    try:
        relative = evidence_path.relative_to(knowledge_root)
        evidence_path.relative_to(knowledge_root / "evidence")
    except ValueError as error:
        raise ValueError("curation queue path must refer to knowledge/evidence") from error
    if not evidence_id:
        raise ValueError("curation queue evidence_id must be non-empty")
    target = _item_path(knowledge_root, evidence_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"evidence_id": evidence_id, "evidence_path": relative.as_posix()}
    temporary = target.with_name(f".{target.name}.{uuid4()}.tmp")
    temporary.write_text(render_markdown(payload), encoding="utf-8")
    temporary.replace(target)
    return target


def complete_curation_work(knowledge_root: Path, evidence_id: str) -> bool:
    """Remove a work item only after a Bundle or Review card was created."""
    target = _item_path(knowledge_root.resolve(), evidence_id)
    existed = target.exists()
    target.unlink(missing_ok=True)
    return existed


def list_curation_queue(knowledge_root: Path, *, include_resolved: bool = False) -> List[Dict[str, object]]:
    """List pending work-item files; file existence is the only queue status."""
    del include_resolved  # Compatibility: completed items no longer exist.
    knowledge_root = knowledge_root.resolve()
    root = _queue_root(knowledge_root)
    rows: List[Dict[str, object]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.md")):
        data = parse_markdown(path).frontmatter
        evidence_id = data.get("evidence_id")
        evidence_path = data.get("evidence_path")
        if not isinstance(evidence_id, str) or not isinstance(evidence_path, str):
            continue
        rows.append({
            "evidence_id": evidence_id,
            "path": evidence_path,
            "status": "pending",
            "queue_path": path.relative_to(knowledge_root.parent).as_posix(),
        })
    return rows


def refresh_curation_queue(knowledge_root: Path) -> Dict[str, object]:
    """Repair pending work items by scanning immutable Evidence and outcomes."""
    knowledge_root = knowledge_root.resolve()
    completed = _completed_evidence_ids(knowledge_root)
    expected: Dict[str, Path] = {}
    for path in sorted((knowledge_root / "evidence").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        data = parse_markdown(path).frontmatter
        evidence_id = data.get("id")
        if (
            data.get("type") == "evidence"
            and isinstance(evidence_id, str)
            and evidence_id not in completed
        ):
            expected[evidence_id] = path

    root = _queue_root(knowledge_root)
    existing_paths = set(root.glob("*.md")) if root.is_dir() else set()
    expected_paths = {_item_path(knowledge_root, evidence_id) for evidence_id in expected}
    created = 0
    repaired = 0
    removed = 0
    for evidence_id, path in expected.items():
        target = _item_path(knowledge_root, evidence_id)
        relative = path.relative_to(knowledge_root).as_posix()
        if not target.exists():
            enqueue_curation_work(knowledge_root, evidence_id, path)
            created += 1
            continue
        try:
            data = parse_markdown(target).frontmatter
        except (OSError, ValueError):
            data = {}
        if data != {"evidence_id": evidence_id, "evidence_path": relative}:
            enqueue_curation_work(knowledge_root, evidence_id, path)
            repaired += 1
    for path in existing_paths - expected_paths:
        path.unlink(missing_ok=True)
        removed += 1
    return {
        "path": root.relative_to(knowledge_root.parent).as_posix(),
        "pending_count": len(expected),
        "created_count": created,
        "repaired_count": repaired,
        "removed_count": removed,
    }


def _completed_evidence_ids(knowledge_root: Path) -> set[str]:
    from .validator import validate_document

    bundle_completed: set[str] = set()
    review_completed: set[str] = set()
    stale: set[str] = set()
    for path in sorted((knowledge_root / "bundles").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        if not validate_document(path, knowledge_root).is_valid:
            continue
        refs = parse_markdown(path).frontmatter.get("evidence")
        if isinstance(refs, list):
            bundle_completed.update(item for item in refs if isinstance(item, str))
    reviews = knowledge_root / "curation-reviews"
    if reviews.is_dir():
        for path in sorted(reviews.rglob("*.md")):
            if path.name in {"README.md", "index.md", "log.md"}:
                continue
            if not validate_document(path, knowledge_root).is_valid:
                continue
            review = parse_markdown(path).frontmatter
            refs = review.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, dict) and isinstance(ref.get("evidence_id"), str):
                        if review.get("status") == "stale":
                            stale.add(ref["evidence_id"])
                        else:
                            review_completed.add(ref["evidence_id"])
    return (bundle_completed - stale) | review_completed


def _queue_root(knowledge_root: Path) -> Path:
    return knowledge_root.parent / "workspace" / "task" / "curation-queue"


def _item_path(knowledge_root: Path, evidence_id: str) -> Path:
    source_uuid = Path(evidence_id).stem.rsplit("_", 1)[-1]
    try:
        canonical_uuid = str(UUID(source_uuid))
    except ValueError as error:
        raise ValueError("curation queue evidence_id must contain a source UUID") from error
    return _queue_root(knowledge_root) / f"{canonical_uuid}.md"
