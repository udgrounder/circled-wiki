"""Explicit, reviewed duplicate recovery with durable, conflict-aware rollback."""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from circled_wiki.config.settings import load_settings

from .bundle_types import BUNDLE_TYPES, DIRECT_DRAFT_TYPES
from .curation_safety import curation_body_safety_errors
from .frontmatter import parse_markdown, render_markdown
from .repository import find_document_by_id, evidence_markdown_link
from .search import search_knowledge
from .sensitive_data import redact_sensitive_data
from .validator import validate_repository


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("request, actor, reviewer, and security receipt must be non-empty")
    return redact_sensitive_data(value.strip(), mask_policy_categories=True).content


def _path(project, relative):
    path = project / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("recovery paths must remain inside the project")
    current = project
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("recovery does not follow symbolic links")
    return path


def _validate(root):
    if any(not result.is_valid for result in validate_repository(root)):
        raise ValueError("repository validation failed")


def _snapshot(project, document):
    relative = document.path.relative_to(project).as_posix()
    path = _path(project, relative)
    data = document.frontmatter
    revision = data.get("extensions", {}).get("knowledge_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("Bundle must have a positive knowledge_revision")
    return dict(id=data["id"], uuid=data.get("bundle_uuid"), path=relative,
                status=data.get("status"), revision=revision, mode=stat.S_IMODE(path.stat().st_mode), checksum=_sha(path.read_bytes()))


def _references(root, source, target, merged_body, archive_only):
    project = root.parent
    relative = source.path.relative_to(root).as_posix()
    needles = {relative, source.path.relative_to(project).as_posix(), source.path.name}
    if any(needle in merged_body for needle in needles):
        raise ValueError("merged body still contains a path reference to the duplicate")
    found = []
    for base in (root, project / "workspace/task"):
        for path in sorted(base.rglob("*.md")):
            if path == source.path or any(part in {".archive", ".quarantine"} for part in path.relative_to(base).parts):
                continue
            _path(project, path.relative_to(project).as_posix())
            text = path.read_text(encoding="utf-8")
            if path == target.path and not archive_only:
                # Only the reviewed body is replaced; other Frontmatter is
                # preserved and can still contain path-based references.
                text = json.dumps(target.frontmatter, ensure_ascii=False)
            if any(needle in text for needle in needles):
                found.append(path.relative_to(project).as_posix())
    return found


def plan_duplicate_bundle_recovery(root: Path, *, source_id: str, target_id: str, merged_body: str, archive_only: bool = False) -> dict:
    """Read-only plan: no lock, snapshot, receipt, or directory is created."""
    root = root.resolve()
    if not isinstance(archive_only, bool):
        raise ValueError("archive_only must be boolean")
    if source_id == target_id:
        raise ValueError("source and target must differ")
    if not isinstance(merged_body, str) or not merged_body.strip() or curation_body_safety_errors(merged_body):
        raise ValueError("merged body must be non-empty and pass content safety review")
    source = find_document_by_id(root, source_id)
    target = find_document_by_id(root, target_id)
    for document in (source, target):
        if document is None or root / "bundles" not in document.path.parents or ".archive" in document.path.relative_to(root).parts:
            raise ValueError("source and target must be live Bundles")
        data = document.frontmatter
        if data.get("type") not in BUNDLE_TYPES:
            raise ValueError("source and target must be Bundles")
        if data.get("type") not in DIRECT_DRAFT_TYPES and not archive_only:
            raise ValueError("runbook and manual recovery requires the dedicated Curation Review workflow")
        if data.get("status") not in {"active", "draft"} or data.get("extensions", {}).get("visibility") == "restricted":
            raise ValueError("only unrestricted active or draft Bundles can be recovered")
    if source.frontmatter["type"] != target.frontmatter["type"]:
        raise ValueError("recovery must preserve a shared Bundle type")
    if source.frontmatter["status"] == "active" and target.frontmatter["status"] != "active":
        raise ValueError("an active duplicate requires an active canonical target; use the Promotion Gate first")
    required_owner = None
    if target.frontmatter["type"] not in DIRECT_DRAFT_TYPES:
        required_owner = load_settings(root.parent).approval.knowledge_owner
        if not required_owner:
            raise ValueError("runbook and manual recovery requires approval.knowledge_owner")
    source_snapshot = _snapshot(root.parent, source)
    target_snapshot = _snapshot(root.parent, target)
    archive = root / "bundles/.archive" / source.path.relative_to(root / "bundles")
    _path(root.parent, archive.relative_to(root.parent).as_posix())
    if archive.exists():
        raise ValueError("archive destination already exists")
    evidence_ids = list(dict.fromkeys(target.frontmatter.get("evidence", []) + source.frontmatter.get("evidence", [])))
    if archive_only and (merged_body != target.body or evidence_ids != target.frontmatter.get("evidence")):
        raise ValueError("archive-only requires reviewed content and all Evidence already integrated in the target")
    evidence = []
    for identifier in evidence_ids:
        document = find_document_by_id(root, identifier)
        if document is None or document.frontmatter.get("type") != "evidence" or document.frontmatter.get("extensions", {}).get("visibility") == "restricted":
            raise ValueError("all union Evidence must resolve and be unrestricted")
        evidence.append(dict(id=identifier, checksum=document.frontmatter.get("checksum"),
                             manifest_checksum=_sha(document.path.read_bytes())))
    _validate(root)
    references = _references(root, source, target, merged_body, archive_only)
    plan = dict(version=1, archive_only=archive_only, required_owner=required_owner, source=source_snapshot, target=target_snapshot,
                archive_path=archive.relative_to(root.parent).as_posix(), evidence=evidence,
                merged_body_checksum=_sha(merged_body.encode()), path_references=references,
                external_references="The requester must review external consumers separately.")
    plan["plan_checksum"] = _sha(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode())
    return plan


def _atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    try:
        with temporary.open("xb") as handle:
            os.chmod(temporary, mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json(path, value):
    _atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode())


@contextmanager
def _lock(project):
    path = _path(project, ".runtime/locks/bundle-recovery.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another Bundle recovery is running") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _require_bytes(path, checksum, mode=None):
    if not path.is_file() or _sha(path.read_bytes()) != checksum:
        raise ValueError("Bundle changed; re-plan recovery")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise ValueError("Bundle permissions changed; re-plan recovery")


def _rollback(project, journal, directory, *, actor):
    journal.setdefault("rollback_attempts", []).append(dict(actor=actor, at=_now()))
    conflicts = []
    source = _path(project, journal["plan"]["source"]["path"])
    target = _path(project, journal["plan"]["target"]["path"])
    archive = _path(project, journal["plan"]["archive_path"])
    for name, path in (("source", source), ("target", target)):
        snapshot = journal["plan"][name]
        backup = _path(project, (directory / (name + ".md")).relative_to(project).as_posix())
        data = backup.read_bytes()
        if _sha(data) != snapshot["checksum"]:
            conflicts.append(name + " backup checksum mismatch")
            continue
        actual = _sha(path.read_bytes()) if path.exists() else None
        if path.exists() and stat.S_IMODE(path.stat().st_mode) != journal["modes"][name]:
            conflicts.append(name + " permissions changed after recovery; preserved")
            continue
        if actual is None and (name == "target" or not archive.exists()):
            conflicts.append(name + " was removed by another writer; preserved")
            continue
        allowed = {snapshot["checksum"], journal["written"][name]}
        if actual is not None and actual not in allowed:
            conflicts.append(name + " changed after recovery; preserved")
            continue
        if name == "source" and archive.exists():
            archive_stat = archive.stat()
            identity = [archive_stat.st_dev, archive_stat.st_ino]
            if (_sha(archive.read_bytes()) != journal["written"]["source"]
                    or identity != journal.get("source_written_identity")):
                conflicts.append("archive changed after recovery; preserved")
                if actual is not None and actual != snapshot["checksum"]:
                    _atomic(path, data, journal["modes"][name])
            else:
                if stat.S_IMODE(archive_stat.st_mode) != journal["modes"][name]:
                    conflicts.append("archive permissions changed after recovery; preserved")
                    continue
                # Restore the live original before removing our archive.
                _atomic(path, data, journal["modes"][name])
                archive.unlink()
        elif actual != snapshot["checksum"]:
            _atomic(path, data, journal["modes"][name])
    journal["status"] = "partial_rollback" if conflicts else "rolled_back"
    journal["rollback_conflicts"] = conflicts
    journal["updated_at"] = _now()
    _json(directory / "journal.json", journal)
    return journal["status"]


def _receipt(project, journal):
    return dict(transaction_id=journal["transaction_id"], status=journal["status"],
                request_ref=journal["request_ref"], actor=journal["actor"], reviewed_by=journal["reviewed_by"],
                security_receipt=journal["security_receipt"], plan=journal["plan"],
                written_checksums=journal["written"], updated_at=journal["updated_at"],
                rollback_conflicts=journal.get("rollback_conflicts", []),
                failure=journal.get("failure"),
                rollback_attempts=journal.get("rollback_attempts", []),
                snapshot_ref=".runtime/bundle-recoveries/" + journal["transaction_id"],
                note="No Evidence originals were changed; no external links were automatically rewritten.")


def recover_duplicate_bundle(
    root: Path, *, source_id: str, target_id: str, merged_body: str,
    expected_source_revision: int, expected_target_revision: int, approved_plan_checksum: str,
    actor: str, reviewed_by: str, request_ref: str, security_receipt: str,
    archive_only: bool = False,
) -> dict:
    """Apply exactly a reviewed plan, or restore our writes without clobbering others."""
    root = root.resolve()
    actor, reviewed_by, request_ref, security_receipt = map(_safe, (actor, reviewed_by, request_ref, security_receipt))
    if actor == reviewed_by:
        raise ValueError("reviewer must differ from the applying actor")
    project = root.parent
    with _lock(project):
        plan = plan_duplicate_bundle_recovery(root, source_id=source_id, target_id=target_id, merged_body=merged_body, archive_only=archive_only)
        if plan["path_references"]:
            raise ValueError("duplicate has path references; repair them explicitly before recovery")
        if plan["required_owner"] is not None and reviewed_by != plan["required_owner"]:
            raise ValueError("runbook and manual recovery must be reviewed by the configured knowledge-owner")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (expected_source_revision, expected_target_revision)):
            raise ValueError("expected revisions must be integers")
        if (plan["source"]["revision"], plan["target"]["revision"]) != (expected_source_revision, expected_target_revision):
            raise ValueError("Bundle revision conflict; re-plan recovery")
        if plan["plan_checksum"] != approved_plan_checksum:
            raise ValueError("approved plan is stale or does not match this recovery")
        source_path, target_path = (_path(project, plan[name]["path"]) for name in ("source", "target"))
        source, target = parse_markdown(source_path), parse_markdown(target_path)
        now = _now()
        transaction_id = "recovery-" + uuid4().hex
        target_data = deepcopy(target.frontmatter)
        target_data["evidence"] = [item["id"] for item in plan["evidence"]]
        target_data["evidence_links"] = [evidence_markdown_link(root, find_document_by_id(root, identifier)) for identifier in target_data["evidence"]]
        target_data["updated_at"] = now
        extension = target_data.setdefault("extensions", {})
        extension.update(knowledge_revision=expected_target_revision + 1, updated_by=actor)
        checksums = {item["id"]: item["checksum"] for item in plan["evidence"]}
        if isinstance(extension.get("curation"), dict):
            extension["curation"]["evidence_checksums"] = checksums
        history = extension.setdefault("bundle_recovery_history", [])
        history.append(dict(source_id=source_id, reviewed_by=reviewed_by, applied_by=actor,
                            applied_at=now, approved_plan_checksum=approved_plan_checksum,
                            request_ref=request_ref, security_receipt=security_receipt, evidence_checksums=checksums,
                            evidence_manifest_checksums={item["id"]: item["manifest_checksum"] for item in plan["evidence"]},
                            recovery_transaction=transaction_id))
        source_data = deepcopy(source.frontmatter)
        source_data.update(status="archived", updated_at=now)
        source_ext = source_data.setdefault("extensions", {})
        source_ext.update(knowledge_revision=expected_source_revision + 1, updated_by=actor)
        source_ext["archive"] = dict(archived_at=now, archived_by=actor,
                                     reason="Duplicate merged into " + target_id,
                                     restore_condition="Explicit rollback of this reviewed recovery; preserve later edits.",
                                     recovery_transaction=transaction_id)
        source_ext["review_state"] = "merged"
        source_ext.setdefault("curation", {})["merged_into"] = target_id
        target_bytes = (render_markdown(target_data, "") + merged_body).encode()
        if archive_only:
            target_bytes = target_path.read_bytes()
        source_bytes = (render_markdown(source_data, "") + source.body).encode()
        directory = _path(project, ".runtime/bundle-recoveries/" + transaction_id)
        receipt_path = _path(project, "workspace/bundle-rebuilds/" + transaction_id + ".json")
        directory.mkdir(parents=True, mode=0o700)
        modes = {}
        for name, path in (("source", source_path), ("target", target_path)):
            original = path.read_bytes()
            if _sha(original) != plan[name]["checksum"]:
                raise ValueError("Bundle changed before snapshot; re-plan recovery")
            modes[name] = plan[name]["mode"]
            _require_bytes(path, plan[name]["checksum"], modes[name])
            _atomic(directory / (name + ".md"), original)
        journal = dict(transaction_id=transaction_id, status="prepared", plan=plan,
                       actor=actor, reviewed_by=reviewed_by, request_ref=request_ref, security_receipt=security_receipt,
                       written=dict(source=_sha(source_bytes), target=_sha(target_bytes)), modes=modes, updated_at=now)
        _json(directory / "journal.json", journal)
        archive = _path(project, plan["archive_path"])
        try:
            _require_bytes(target_path, plan["target"]["checksum"], modes["target"])
            if not archive_only:
                _atomic(target_path, target_bytes, modes["target"])
            _validate(root)  # Never archive before the merged result is valid.
            _require_bytes(source_path, plan["source"]["checksum"], modes["source"])
            _atomic(source_path, source_bytes, modes["source"])
            source_stat = source_path.stat()
            journal["source_written_identity"] = [source_stat.st_dev, source_stat.st_ino]
            _json(directory / "journal.json", journal)
            archive.parent.mkdir(parents=True, exist_ok=True)
            # link/unlink is a same-filesystem move that cannot overwrite a
            # destination created between planning and execution.
            os.link(source_path, archive)
            source_path.unlink()
            _validate(root)
            if any(hit.document_id == source_id for hit in search_knowledge(root, str(source.frontmatter["title"]))):
                raise ValueError("archived duplicate is still in default search")
            _require_bytes(target_path, journal["written"]["target"], modes["target"])
            _require_bytes(archive, journal["written"]["source"], modes["source"])
            journal.update(status="applied", updated_at=_now())
            _json(receipt_path, _receipt(project, journal))
            _json(directory / "journal.json", journal)
        except Exception as error:
            journal["failure"] = _safe(str(error) or type(error).__name__)
            try:
                _rollback(project, journal, directory, actor=actor)
                _json(receipt_path, _receipt(project, journal))
            except Exception:
                journal.update(status="rollback_failed", updated_at=_now())
                try:
                    _json(directory / "journal.json", journal)
                except Exception:
                    pass
                return dict(status="rollback_failed", transaction_id=transaction_id,
                            snapshot_ref=directory.relative_to(project).as_posix())
        return dict(status=journal["status"], transaction_id=transaction_id,
                    receipt=receipt_path.relative_to(project).as_posix(), rollback_conflicts=journal.get("rollback_conflicts", []))


def rollback_duplicate_bundle_recovery(root: Path, *, transaction_id: str, actor: str) -> dict:
    """Recover after interruption, or undo a completed operation if files are unchanged."""
    if not isinstance(transaction_id, str) or not re.fullmatch(r"recovery-[0-9a-f]{32}", transaction_id):
        raise ValueError("invalid recovery transaction ID")
    actor = _safe(actor)
    root = root.resolve()
    project = root.parent
    with _lock(project):
        directory = _path(project, ".runtime/bundle-recoveries/" + transaction_id)
        journal_path = _path(project, (directory / "journal.json").relative_to(project).as_posix())
        journal = json.loads(journal_path.read_text())
        plan = journal["plan"]
        prefix = root.relative_to(project).as_posix() + "/bundles/"
        for name in ("source", "target"):
            if not plan[name]["path"].startswith(prefix) or ".archive" in Path(plan[name]["path"]).parts:
                raise ValueError("invalid Bundle path in recovery journal")
        expected_archive = prefix + ".archive/" + plan["source"]["path"][len(prefix):]
        if plan["archive_path"] != expected_archive or plan["source"]["path"] == plan["target"]["path"]:
            raise ValueError("invalid archive path in recovery journal")
        receipt = _path(project, "workspace/bundle-rebuilds/" + transaction_id + ".json")
        try:
            _rollback(project, journal, directory, actor=actor)
            if journal["status"] == "rolled_back":
                _validate(root)
            _json(receipt, _receipt(project, journal))
        except Exception as error:
            journal.update(status="rollback_failed", updated_at=_now(), failure=_safe(str(error) or type(error).__name__))
            try:
                _json(directory / "journal.json", journal)
            except Exception:
                pass
        return dict(status=journal["status"], transaction_id=transaction_id,
                    receipt=receipt.relative_to(project).as_posix(), rollback_conflicts=journal.get("rollback_conflicts", []))
