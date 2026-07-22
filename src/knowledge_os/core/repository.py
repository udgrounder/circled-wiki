"""Repository reads and deterministic Bundle creation."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, Optional
from uuid import uuid4

from knowledge_os.config.settings import load_settings

from .frontmatter import parse_markdown, render_markdown
from .models import MarkdownDocument
from .namespace import require_stable_organization_id
from .validator import validate_document, validate_repository


SAFE_PATH_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def iter_documents(knowledge_root: Path):
    for section in ("bundles", "evidence"):
        yield from sorted((knowledge_root / section).rglob("*.md"))


def find_document_by_id(knowledge_root: Path, document_id: str) -> Optional[MarkdownDocument]:
    for path in iter_documents(knowledge_root):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        if document.frontmatter.get("id") == document_id:
            return document
    return None


def knowledge_root_path(knowledge_root: Path, document: MarkdownDocument) -> str:
    """Return an Obsidian-friendly absolute path within the knowledge_root vault."""
    return document.path.relative_to(knowledge_root).as_posix()


def evidence_markdown_link(knowledge_root: Path, document: MarkdownDocument) -> str:
    """Return an Obsidian-compatible Markdown link, not an opaque identifier."""
    path = knowledge_root_path(knowledge_root, document)
    return f"[{document.path.name}]({path})"


def backfill_evidence_links(knowledge_root: Path, *, apply: bool = False) -> Dict[str, object]:
    """Plan or apply Obsidian Evidence-link backfill for existing Bundles.

    ``evidence`` remains the durable URI reference.  This repair only derives the
    vault-root path used by Obsidian from that URI; it never guesses a filename,
    UUID prefix, or provider path.  A blocked Bundle is left unchanged.
    """
    changes: list[Dict[str, object]] = []
    blocked: list[Dict[str, object]] = []
    scanned = 0
    unchanged = 0
    for path in sorted((knowledge_root / "bundles").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        if document.frontmatter.get("type") == "inbox_item":
            continue
        scanned += 1
        evidence_ids = document.frontmatter.get("evidence")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            blocked.append({
                "path": path.relative_to(knowledge_root).as_posix(),
                "reason": "Bundle has no Evidence URI references",
            })
            continue
        evidence_links: list[str] = []
        unresolved: list[str] = []
        for evidence_id in evidence_ids:
            evidence = find_document_by_id(knowledge_root, str(evidence_id))
            if evidence is None or evidence.frontmatter.get("type") != "evidence":
                unresolved.append(str(evidence_id))
            else:
                evidence_links.append(evidence_markdown_link(knowledge_root, evidence))
        if unresolved:
            blocked.append({
                "path": path.relative_to(knowledge_root).as_posix(),
                "reason": "Bundle Evidence URI does not resolve",
                "unresolved_evidence_ids": unresolved,
            })
            continue
        if document.frontmatter.get("evidence_links") == evidence_links:
            unchanged += 1
            continue
        changes.append({
            "path": path.relative_to(knowledge_root).as_posix(),
            "bundle_id": document.frontmatter.get("id"),
            "evidence_links": evidence_links,
        })

    report: Dict[str, object] = {
        "mode": "apply" if apply else "dry_run",
        "scanned": scanned,
        "unchanged": unchanged,
        "change_count": len(changes),
        "blocked_count": len(blocked),
        "changes": changes,
        "blocked": blocked,
    }
    if not apply or not changes:
        return report

    backups: Dict[Path, str] = {}
    try:
        for change in changes:
            path = knowledge_root / str(change["path"])
            document = parse_markdown(path)
            backups[path] = path.read_text(encoding="utf-8")
            data = dict(document.frontmatter)
            data["evidence_links"] = list(change["evidence_links"])
            path.write_text(render_markdown(data, document.body), encoding="utf-8")
            validation = validate_document(path, knowledge_root)
            if not validation.is_valid:
                raise ValueError("Evidence-link backfill validation failed: " + "; ".join(validation.profile_errors))
    except Exception:
        for path, content in backups.items():
            path.write_text(content, encoding="utf-8")
        raise
    report["applied_count"] = len(changes)
    return report


def migrate_document_ids(knowledge_root: Path, *, apply: bool = False) -> Dict[str, object]:
    """Migrate legacy URI IDs to stable organization-and-filename IDs.

    The operation is deliberately explicit because it changes reference values;
    both Frontmatter references and literal body references are updated together.
    """
    settings = load_settings(knowledge_root.resolve().parent)
    documents = [
        parse_markdown(path) for path in iter_documents(knowledge_root)
        if path.name not in {"index.md", "log.md"}
    ]
    id_map: Dict[str, str] = {}
    for document in documents:
        document_id = document.frontmatter.get("id")
        if not isinstance(document_id, str):
            continue
        kind = document.frontmatter.get("type")
        if kind == "evidence":
            new_id = f"evidence/{settings.organization_id}/{document.path.name}"
        elif "bundles" in document.path.parts:
            new_id = f"bundle/{settings.organization_id}/{document.path.name}"
        else:
            continue
        if document_id != new_id:
            id_map[document_id] = new_id
    report: Dict[str, object] = {
        "mode": "apply" if apply else "dry_run", "change_count": len(id_map),
        "id_map": id_map,
    }
    if not apply or not id_map:
        return report
    backups = {document.path: document.path.read_text(encoding="utf-8") for document in documents}
    try:
        for document in documents:
            data = _replace_identifier_references(deepcopy(document.frontmatter), id_map)
            body = _replace_identifier_text(document.body, id_map)
            document.path.write_text(render_markdown(data, body), encoding="utf-8")
        invalid = [item for item in validate_repository(knowledge_root) if not item.is_valid]
        if invalid:
            messages = [error for item in invalid for error in item.profile_errors]
            raise ValueError("ID migration validation failed: " + "; ".join(messages))
    except Exception:
        for path, content in backups.items():
            path.write_text(content, encoding="utf-8")
        raise
    report["applied_count"] = len(id_map)
    return report


def _replace_identifier_references(value: Any, id_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        return id_map.get(value, value)
    if isinstance(value, list):
        return [_replace_identifier_references(item, id_map) for item in value]
    if isinstance(value, dict):
        return {key: _replace_identifier_references(item, id_map) for key, item in value.items()}
    return value


def _replace_identifier_text(body: str, id_map: Dict[str, str]) -> str:
    for old, new in id_map.items():
        body = body.replace(old, new)
    return body


def create_bundle(
    knowledge_root: Path, *, domain: str, slug: str, title: str, bundle_type: str,
    summary: str, evidence_id: str, body: str = "", curated_by: str = "manual",
) -> MarkdownDocument:
    """Create a draft Bundle only when its Evidence Record already exists."""
    if not SAFE_PATH_SEGMENT.fullmatch(domain) or not SAFE_PATH_SEGMENT.fullmatch(slug):
        raise ValueError("domain and slug must be safe lowercase path segments")
    if not title.strip() or not summary.strip() or not curated_by.strip():
        raise ValueError("title, summary, and curated_by must be non-empty")
    evidence = find_document_by_id(knowledge_root, evidence_id)
    if evidence is None or evidence.frontmatter.get("type") != "evidence":
        raise ValueError("evidence_id must refer to an existing Evidence Record")
    bundle_uuid = str(uuid4())
    settings = load_settings(knowledge_root.resolve().parent)
    organization_id = require_stable_organization_id(
        knowledge_root, settings.organization_id
    )
    bundle_directory = knowledge_root / "bundles" / domain
    if bundle_type == "runbook":
        bundle_directory = bundle_directory / "runbooks"
    path = bundle_directory / f"{slug}_{bundle_uuid}.md"
    bundle_id = f"bundle/{organization_id}/{path.name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = {
        "type": bundle_type, "id": bundle_id, "bundle_uuid": bundle_uuid, "title": title,
        "status": "draft", "summary": summary, "updated_at": now, "evidence": [evidence_id],
        "evidence_links": [evidence_markdown_link(knowledge_root, evidence)],
        "tags": ["bundles", bundle_type, domain],
        "owners": list(settings.workflow.default_owners),
        "extensions": {
            "source_uuids": [evidence.frontmatter["source_uuid"]],
            "curated_by": curated_by,
            "review_state": "pending",
            "confidence": "draft",
            "knowledge_revision": 1,
            "governance": {
                "reviewed_at": None,
                "review_due_at": None,
                "freshness_policy": "on_change",
                "supersedes": [],
                "superseded_by": None,
            },
        },
    }
    evidence_backup = evidence.path.read_text(encoding="utf-8")
    try:
        path.write_text(
            render_markdown(data, body or "# Summary\n\n" + summary + "\n"),
            encoding="utf-8",
        )
        result = validate_document(path, knowledge_root)
        if not result.is_valid:
            raise ValueError("Bundle validation failed: " + "; ".join(result.profile_errors))
        evidence_data = dict(evidence.frontmatter)
        evidence_data["status"] = "processed"
        evidence_data["processed_at"] = now
        evidence_data["curated_into"] = sorted(
            set(evidence_data.get("curated_into", []) + [bundle_id])
        )
        evidence.path.write_text(
            render_markdown(evidence_data, evidence.body), encoding="utf-8"
        )
        invalid = [result for result in validate_repository(knowledge_root) if not result.is_valid]
        if invalid:
            messages = [
                message
                for validation in invalid
                for message in validation.okf_errors + validation.profile_errors
            ]
            raise ValueError("Bundle creation validation failed: " + "; ".join(messages))
    except Exception:
        path.unlink(missing_ok=True)
        evidence.path.write_text(evidence_backup, encoding="utf-8")
        raise
    return parse_markdown(path)


def apply_bundle_revision(
    knowledge_root: Path,
    *,
    bundle_id: str,
    expected_revision: int,
    proposed_frontmatter: Dict[str, Any],
    body: str,
    actor: str,
) -> MarkdownDocument:
    """Atomically apply one validated Bundle revision and maintain Evidence backlinks."""
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise ValueError("expected_revision must be an integer")
    if not isinstance(proposed_frontmatter, dict) or not actor.strip():
        raise ValueError("proposed_frontmatter and actor are required")
    existing = find_document_by_id(knowledge_root, bundle_id)
    if existing is None or "bundles" not in existing.path.parts:
        raise ValueError("bundle_id must resolve to an existing Bundle")
    if existing.frontmatter.get("extensions", {}).get("visibility") == "restricted":
        raise ValueError("restricted Bundle cannot be changed through this interface")
    current_extensions = existing.frontmatter.get("extensions")
    current_revision = (
        current_extensions.get("knowledge_revision")
        if isinstance(current_extensions, dict) else None
    )
    if current_revision != expected_revision:
        raise ValueError("Bundle revision conflict; reload before applying the update")

    proposed = deepcopy(proposed_frontmatter)
    for field in ("id", "bundle_uuid", "type"):
        if proposed.get(field) != existing.frontmatter.get(field):
            raise ValueError(f"immutable Bundle field changed: {field}")
    evidence_ids = proposed.get("evidence")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise ValueError("Bundle revision requires at least one Evidence reference")
    if len(set(map(str, evidence_ids))) != len(evidence_ids):
        raise ValueError("Bundle Evidence references must be unique")

    existing_extensions = existing.frontmatter.get("extensions")
    current_curation = existing_extensions.get("curation") if isinstance(existing_extensions, dict) else None
    if isinstance(current_curation, dict) and proposed.get("status") == "active":
        raise ValueError(
            "curation candidates cannot be promoted through apply_bundle_revision; "
            "use the Owner and Security publication Gate"
        )

    evidence_documents = {}
    for evidence_id in set(map(str, [*existing.frontmatter.get("evidence", []), *evidence_ids])):
        evidence = find_document_by_id(knowledge_root, evidence_id)
        if evidence is None or evidence.frontmatter.get("type") != "evidence":
            raise ValueError(f"Bundle Evidence does not resolve: {evidence_id}")
        if evidence.frontmatter.get("extensions", {}).get("visibility") == "restricted":
            raise ValueError("restricted Evidence cannot be linked through this interface")
        evidence_documents[evidence_id] = evidence

    proposed["evidence_links"] = [
        evidence_markdown_link(knowledge_root, evidence_documents[str(evidence_id)])
        for evidence_id in map(str, evidence_ids)
    ]

    extensions = proposed.get("extensions")
    if not isinstance(extensions, dict):
        raise ValueError("Bundle extensions must be an object")
    extensions["knowledge_revision"] = expected_revision + 1
    extensions["updated_by"] = actor.strip()
    proposed["extensions"] = extensions
    proposed["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    backups = {existing.path: existing.path.read_text(encoding="utf-8")}
    backups.update({
        evidence.path: evidence.path.read_text(encoding="utf-8")
        for evidence in evidence_documents.values()
    })
    try:
        existing.path.write_text(render_markdown(proposed, body), encoding="utf-8")
        selected_ids = set(map(str, evidence_ids))
        for evidence_id, evidence in evidence_documents.items():
            evidence_data = deepcopy(evidence.frontmatter)
            curated_into = set(map(str, evidence_data.get("curated_into", [])))
            if evidence_id in selected_ids:
                curated_into.add(bundle_id)
                evidence_data["status"] = "processed"
                evidence_data["processed_at"] = proposed["updated_at"]
            else:
                curated_into.discard(bundle_id)
            evidence_data["curated_into"] = sorted(curated_into)
            evidence.path.write_text(
                render_markdown(evidence_data, evidence.body), encoding="utf-8"
            )
        results = validate_repository(knowledge_root)
        invalid = [result for result in results if not result.is_valid]
        if invalid:
            messages = [
                message
                for result in invalid
                for message in result.okf_errors + result.profile_errors
            ]
            raise ValueError("Bundle revision validation failed: " + "; ".join(messages))
    except Exception:
        for path, content in backups.items():
            path.write_text(content, encoding="utf-8")
        raise
    return parse_markdown(existing.path)
