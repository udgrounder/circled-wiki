"""Evidence ingestion that preserves originals and creates an OKF manifest."""

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from functools import wraps
import hashlib
import inspect
from pathlib import Path
import re
import shutil
from typing import Any, Callable, Dict, Iterator, List, Optional
from uuid import uuid4

from .frontmatter import parse_markdown, render_markdown
from .evidence import (
    ORIGINAL_CONTENT_END,
    ORIGINAL_CONTENT_START,
    evidence_original_path,
    render_embedded_body,
)
from .validator import validate_document


MAX_GIT_EVIDENCE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class IngestResult:
    source_uuid: str
    original_path: Path
    manifest_path: Path
    evidence_id: str
    reused: bool = False


@dataclass(frozen=True)
class CaptureResult:
    intake_id: Optional[str]
    inbox_path: Optional[Path]
    checksum: str
    reused: bool = False
    evidence_id: Optional[str] = None
    evidence_path: Optional[Path] = None


class CaptureIdempotencyConflict(ValueError):
    """A safe, recoverable description of a changed capture retry."""

    def __init__(
        self,
        *,
        intake_id: Optional[str] = None,
        inbox_path: Optional[Path] = None,
        evidence_id: Optional[str] = None,
        evidence_path: Optional[Path] = None,
        existing_checksum: str,
        supplied_checksum: str,
    ) -> None:
        if bool(intake_id and inbox_path) == bool(evidence_id and evidence_path):
            raise ValueError("exactly one existing capture identity must be supplied")
        self.intake_id = intake_id
        self.inbox_path = inbox_path
        self.evidence_id = evidence_id
        self.evidence_path = evidence_path
        self.existing_checksum = existing_checksum
        self.supplied_checksum = supplied_checksum
        existing_kind = "intake" if intake_id else "evidence"
        existing_id = intake_id or evidence_id
        super().__init__(
            "idempotency_key already exists with a different checksum; "
            f"existing {existing_kind} is {existing_id}"
        )

    def as_dict(self, project_root: Path) -> Dict[str, object]:
        """Return recovery data without exposing captured source content."""
        payload = {
            "error": "idempotency_checksum_conflict",
            "stage": "inbox_capture",
            "message": str(self),
            "existing_checksum": self.existing_checksum,
            "supplied_checksum": self.supplied_checksum,
            "recovery": "Inspect the existing intake. Use a new source revision in the idempotency key only when the changed source is intentional.",
        }
        if self.intake_id and self.inbox_path:
            payload.update({
                "existing_intake_id": self.intake_id,
                "existing_inbox_path": self.inbox_path.resolve().relative_to(
                    project_root.resolve()
                ).as_posix(),
            })
        elif self.evidence_id and self.evidence_path:
            payload.update({
                "existing_evidence_id": self.evidence_id,
                "existing_evidence_path": self.evidence_path.resolve().relative_to(
                    project_root.resolve()
                ).as_posix(),
            })
            payload["recovery"] = (
                "Inspect the existing Evidence. Use a new source revision in the "
                "idempotency key only when the changed source is intentional."
            )
        return payload


INBOX_CONTENT_START = "<!-- INBOX_CONTENT_START -->"
INBOX_CONTENT_END = "<!-- INBOX_CONTENT_END -->"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "evidence"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _content_checksum(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


@contextmanager
def _capture_idempotency_lock(
    knowledge_root: Path, provider: str, idempotency_key: str
) -> Iterator[None]:
    """Serialize one capture identity across local processes."""
    digest = hashlib.sha256(
        f"{provider}\0{idempotency_key}".encode("utf-8")
    ).hexdigest()
    lock_root = knowledge_root.resolve().parent / ".runtime" / "locks" / "capture"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{digest}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _synchronized_capture(function: Callable[..., CaptureResult]) -> Callable[..., CaptureResult]:
    """Hold the capture-key lock across lookup, conflict checking, and write."""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(knowledge_root: Path, *args: Any, **kwargs: Any) -> CaptureResult:
        bound = signature.bind_partial(knowledge_root, *args, **kwargs)
        provider = str(bound.arguments.get("provider", ""))
        idempotency_key = bound.arguments.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return function(knowledge_root, *args, **kwargs)
        with _capture_idempotency_lock(
            knowledge_root, provider, idempotency_key.strip()
        ):
            return function(knowledge_root, *args, **kwargs)
    return wrapped


def _reuse_ingested_capture(
    knowledge_root: Path, provider: str, idempotency_key: str, checksum: str
) -> Optional[CaptureResult]:
    """Reuse or safely reject a capture key already preserved as Evidence."""
    evidence_root = knowledge_root.resolve() / "evidence"
    if not evidence_root.is_dir():
        return None
    for manifest_path in sorted(evidence_root.rglob("*.md")):
        if manifest_path.name in {"index.md", "log.md"}:
            continue
        try:
            document = parse_markdown(manifest_path)
        except (OSError, ValueError):
            continue
        data = document.frontmatter
        extensions = data.get("extensions", {})
        ingest = extensions.get("ingest", {}) if isinstance(extensions, dict) else {}
        if (
            data.get("type") != "evidence"
            or data.get("provider") != provider
            or not isinstance(ingest, dict)
            or ingest.get("idempotency_key") != idempotency_key
        ):
            continue
        existing_checksum = str(data.get("checksum", ""))
        if existing_checksum != checksum:
            raise CaptureIdempotencyConflict(
                evidence_id=str(data.get("id", "")),
                evidence_path=manifest_path,
                existing_checksum=existing_checksum,
                supplied_checksum=checksum,
            )
        original_path = evidence_original_path(document)
        if not original_path.is_file():
            raise ValueError("idempotent Evidence original is unavailable")
        return CaptureResult(
            None,
            None,
            checksum,
            True,
            evidence_id=str(data.get("id", "")),
            evidence_path=manifest_path,
        )
    return None


def read_conversation_intake(path: Path) -> tuple[Dict[str, object], object]:
    """Validate and return one self-contained conversation or document Inbox item."""
    document = parse_markdown(path)
    data = document.frontmatter
    if data.get("type") != "inbox_item" or data.get("content_type") not in {"conversation", "document", "file"}:
        raise ValueError("Inbox item content_type is invalid")
    for field in ("id", "title", "provider", "captured_at", "idempotency_key", "why_collected"):
        if not isinstance(data.get(field), str) or not str(data[field]).strip():
            raise ValueError(f"Inbox item {field} must be non-empty")
    if data.get("status") not in {"pending", "accepted", "needs_review"}:
        raise ValueError("Inbox item status is invalid")
    if data.get("sensitivity_review") not in {"completed", "required", "not_applicable"}:
        raise ValueError("Inbox item sensitivity_review is invalid")
    intended_use = data.get("intended_use")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("Inbox item intended_use must be a non-empty string array")
    if data.get("content_type") == "file":
        payload_name = data.get("payload_file")
        if not isinstance(payload_name, str) or not payload_name or Path(payload_name).name != payload_name:
            raise ValueError("Inbox file payload_file is invalid")
        payload_path = path.parent / payload_name
        if not payload_path.is_file():
            raise ValueError("Inbox file payload is missing")
        if _sha256(payload_path) != data.get("checksum"):
            raise ValueError("Inbox file checksum does not match payload")
        return data, payload_path
    start = document.body.find(INBOX_CONTENT_START)
    end = document.body.find(INBOX_CONTENT_END, start + len(INBOX_CONTENT_START))
    if start < 0 or end < 0:
        raise ValueError("Inbox item content markers are missing")
    content = document.body[start + len(INBOX_CONTENT_START):end]
    if not content.strip():
        raise ValueError("Inbox item content must be non-empty")
    if _content_checksum(content) != data.get("checksum"):
        raise ValueError("Inbox item checksum does not match content")
    provider = data.get("provider")
    if not isinstance(provider, str) or not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("Inbox item provider is invalid")
    if path.parent.name != provider:
        raise ValueError("Inbox item provider must match its source folder")
    return data, content


def accept_conversation_intake(
    knowledge_root: Path, intake_id: str, actor: str
) -> Dict[str, object]:
    """Apply the inspection gate to one valid pending conversation Inbox item."""
    if not isinstance(intake_id, str) or not intake_id.strip():
        raise ValueError("intake_id must be non-empty")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    knowledge_root = knowledge_root.resolve()
    inbox_root = knowledge_root / "inbox"
    for path in sorted(inbox_root.glob("*/*.md")):
        try:
            document = parse_markdown(path)
        except (OSError, ValueError):
            continue
        if document.frontmatter.get("id") != intake_id:
            continue
        data, _ = read_conversation_intake(path)
        if data.get("status") == "accepted":
            return {"intake_id": intake_id, "status": "accepted", "reused": True}
        if data.get("status") != "pending":
            raise ValueError("only pending Inbox items can be accepted")
        if data.get("sensitivity_review") == "required":
            raise ValueError("sensitivity review must be completed before acceptance")
        updated = dict(data)
        updated["status"] = "accepted"
        updated["inspection"] = {
            "actor": actor.strip(),
            "inspected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "checks": [
                "required_metadata",
                "provider_folder",
                "content_checksum",
                "sensitivity_review",
            ],
        }
        path.write_text(render_markdown(updated, document.body), encoding="utf-8")
        return {
            "intake_id": intake_id,
            "status": "accepted",
            "inbox_path": path.relative_to(knowledge_root.parent.resolve()).as_posix(),
            "reused": False,
        }
    raise ValueError("intake_id must refer to an existing Inbox item")


def complete_inbox_sensitivity_review(
    knowledge_root: Path, intake_id: str, actor: str, decision: str
) -> Dict[str, object]:
    """Record a human sensitivity review before Inbox acceptance.

    Collection never asserts that a source is safe.  This distinct operation makes
    the reviewer and their explicit decision auditable before acceptance.
    """
    if not isinstance(intake_id, str) or not intake_id.strip():
        raise ValueError("intake_id must be non-empty")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor must be non-empty")
    if decision not in {"completed", "not_applicable"}:
        raise ValueError("decision must be completed or not_applicable")
    knowledge_root = knowledge_root.resolve()
    for path in sorted((knowledge_root / "inbox").glob("*/*.md")):
        try:
            document = parse_markdown(path)
        except (OSError, ValueError):
            continue
        if document.frontmatter.get("id") != intake_id:
            continue
        data, _ = read_conversation_intake(path)
        if data.get("status") != "pending":
            raise ValueError("only pending Inbox items can be sensitivity-reviewed")
        if data.get("sensitivity_review") != "required":
            raise ValueError("Inbox sensitivity review is already resolved")
        updated = dict(data)
        updated["sensitivity_review"] = decision
        updated["sensitivity_inspection"] = {
            "actor": actor.strip(),
            "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "decision": decision,
        }
        path.write_text(render_markdown(updated, document.body), encoding="utf-8")
        return {"intake_id": intake_id, "sensitivity_review": decision, "status": "pending"}
    raise ValueError("intake_id must refer to an existing Inbox item")


def ingest_evidence(
    knowledge_root: Path,
    source_path: Path,
    provider: str,
    *,
    why_collected: str,
    intended_use: List[str],
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    source_locator: Optional[str] = None,
    captured_from: str = "manual",
    captured_at: Optional[datetime] = None,
    reuse_value: str = "medium",
    retention_class: str = "general_reference",
    sensitivity_review: str = "required",
    idempotency_key: Optional[str] = None,
    content_mode: str = "external_file",
    capture_fidelity: Optional[str] = None,
    pii_scanned: bool = False,
    capture_details: Optional[Dict[str, object]] = None,
    original_stem: Optional[str] = None,
) -> IngestResult:
    """Move an inbox original through `.raw` and preserve it as new Evidence.

    Only originals up to 10 MiB are handled in this local Git-backed MVP. Oversized
    originals remain in `.raw` so an operator can place them in approved external
    storage and create a manifest with `extensions.storage.class: external`.
    """
    knowledge_root = knowledge_root.resolve()
    inbox_root = (knowledge_root / "inbox").resolve()
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"inbox file does not exist: {source_path}")
    if inbox_root not in source_path.parents:
        raise ValueError("source_path must be inside knowledge/inbox/")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider must contain only lowercase letters, digits, underscores, or hyphens")
    if captured_from not in {"api", "webhook", "manual", "upload", "sync"}:
        raise ValueError("captured_from is invalid")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if reuse_value not in {"high", "medium", "low"}:
        raise ValueError("reuse_value is invalid")
    if retention_class not in {
        "workflow_reference", "decision_record", "outcome", "general_reference", "ephemeral"
    }:
        raise ValueError("retention_class is invalid")
    if sensitivity_review not in {"completed", "required", "not_applicable"}:
        raise ValueError("sensitivity_review is invalid")
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str)
        or not idempotency_key.strip()
        or len(idempotency_key) > 200
    ):
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    if content_mode not in {"external_file", "embedded"}:
        raise ValueError("content_mode must be external_file or embedded")
    if content_mode == "embedded":
        if source_path.suffix.lower() != ".md":
            raise ValueError("embedded Evidence source must be a Markdown file")
        try:
            embedded_source = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("embedded Evidence source must be valid UTF-8") from error
        if ORIGINAL_CONTENT_START in embedded_source or ORIGINAL_CONTENT_END in embedded_source:
            raise ValueError("embedded Evidence source contains a reserved integrity marker")
    if not isinstance(pii_scanned, bool):
        raise ValueError("pii_scanned must be boolean")
    if capture_details is not None and not isinstance(capture_details, dict):
        raise ValueError("capture_details must be an object")

    source_checksum = _sha256(source_path)
    if idempotency_key is not None:
        for manifest_path in sorted((knowledge_root / "evidence").rglob("*.md")):
            if manifest_path.name in {"index.md", "log.md"}:
                continue
            document = parse_markdown(manifest_path)
            extensions = document.frontmatter.get("extensions", {})
            ingest = extensions.get("ingest", {}) if isinstance(extensions, dict) else {}
            if (
                document.frontmatter.get("provider") != provider
                or not isinstance(ingest, dict)
                or ingest.get("idempotency_key") != idempotency_key
            ):
                continue
            if document.frontmatter.get("checksum") != source_checksum:
                raise ValueError("idempotency_key already exists with a different checksum")
            original_path = evidence_original_path(document)
            if not original_path.is_file():
                raise ValueError("idempotent Evidence original is unavailable")
            source_path.unlink()
            return IngestResult(
                str(document.frontmatter["source_uuid"]), original_path, manifest_path,
                str(document.frontmatter["id"]), True,
            )

    source_uuid = str(uuid4())
    raw_root = knowledge_root / ".raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    source_stem = _slug(original_stem or source_path.stem)
    raw_path = raw_root / f"{source_stem}_{source_uuid}{source_path.suffix.lower()}"
    shutil.move(str(source_path), str(raw_path))

    if raw_path.stat().st_size > MAX_GIT_EVIDENCE_BYTES:
        raise ValueError(
            "original is larger than 10 MiB and remains in knowledge/.raw/; "
            "store it externally before creating its manifest"
        )

    now = captured_at or datetime.now(timezone.utc)
    date_path = now.strftime("%Y/%m/%d")
    name = source_stem
    evidence_root = knowledge_root / "evidence" / provider / date_path
    evidence_root.mkdir(parents=True, exist_ok=True)
    original_name = f"{name}_{source_uuid}{raw_path.suffix.lower()}"
    original_path = evidence_root / original_name
    manifest_path = evidence_root / f"{name}_{source_uuid}.md"
    evidence_id = f"evidence://campingtalk/{provider}/{date_path}/{source_uuid}"
    timestamp = now.isoformat(timespec="seconds")
    source_ref = {
        "provider": provider,
        "provider_url": source_url or "",
        "captured_from": captured_from,
        "snapshot_at": timestamp,
    }
    if source_locator:
        source_ref["locator"] = source_locator
    frontmatter = {
        "type": "evidence",
        "id": evidence_id,
        "title": title or source_path.stem,
        "source_uuid": source_uuid,
        "provider": provider,
        "source_ref": source_ref,
        "captured_at": timestamp,
        "status": "new",
        "processed_at": None,
        "curated_into": [],
        "checksum": source_checksum,
        "language": "ko",
        "original_file_git_tracked": True,
        "derived_files": [],
        "extensions": {
            "availability": "available",
            "capture_context": {
                "why_collected": why_collected.strip(),
                "intended_use": [item.strip() for item in intended_use],
                "reuse_value": reuse_value,
                "retention_class": retention_class,
                "sensitivity_review": sensitivity_review,
            },
            "review_state": "pending",
            "visibility": "internal",
            "pii_scanned": pii_scanned,
            "pii_masked": False,
            "storage": {"class": "git"},
            "ingest": {"idempotency_key": idempotency_key} if idempotency_key else {},
        },
    }
    if content_mode == "embedded":
        frontmatter["extensions"]["content_mode"] = "embedded"
        frontmatter["extensions"]["checksum_scope"] = "original_content"
        frontmatter["extensions"]["capture_fidelity"] = capture_fidelity or "verbatim"
        if capture_details:
            frontmatter["extensions"]["conversation_capture"] = capture_details
        embedded_content = raw_path.read_text(encoding="utf-8")
        manifest_path.write_text(
            render_markdown(frontmatter, render_embedded_body(embedded_content)),
            encoding="utf-8",
        )
        original_path = manifest_path
    else:
        frontmatter["original_file"] = original_name
        frontmatter["extensions"]["content_mode"] = "external_file"
        frontmatter["extensions"]["checksum_scope"] = "original_file"
        manifest_path.write_text(
            render_markdown(frontmatter, "# Summary\n\nPending curation.\n"), encoding="utf-8"
        )
        shutil.move(str(raw_path), str(original_path))
    validation = validate_document(manifest_path, knowledge_root)
    if not validation.is_valid:
        manifest_path.unlink(missing_ok=True)
        if content_mode == "external_file" and original_path.is_file():
            shutil.move(str(original_path), str(raw_path))
        raise ValueError("manifest validation failed: " + "; ".join(validation.profile_errors))
    if content_mode == "embedded":
        raw_path.unlink(missing_ok=True)
    return IngestResult(source_uuid, original_path, manifest_path, evidence_id)


@_synchronized_capture
def capture_conversation(
    knowledge_root: Path,
    content: str,
    provider: str,
    *,
    title: str,
    why_collected: str,
    intended_use: List[str],
    idempotency_key: str,
    thread_ref: Optional[str] = None,
    turn_from: Optional[int] = None,
    turn_to: Optional[int] = None,
    artifacts: Optional[List[Dict[str, object]]] = None,
    sensitivity_review: str = "required",
    captured_at: Optional[datetime] = None,
) -> CaptureResult:
    """Land a conversation in its provider Inbox without ingesting or curating it."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("conversation content must be non-empty")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError(
            "provider must contain only lowercase letters, digits, underscores, or hyphens"
        )
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if turn_from is not None and (isinstance(turn_from, bool) or turn_from < 0):
        raise ValueError("turn_from must be a non-negative integer")
    if turn_to is not None and (isinstance(turn_to, bool) or turn_to < 0):
        raise ValueError("turn_to must be a non-negative integer")
    if turn_from is not None and turn_to is not None and turn_to < turn_from:
        raise ValueError("turn_to must be greater than or equal to turn_from")
    if artifacts is not None and (
        not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts)
    ):
        raise ValueError("artifacts must be an array of objects")
    if sensitivity_review not in {"completed", "required", "not_applicable"}:
        raise ValueError("sensitivity_review is invalid")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")

    checksum = _content_checksum(content)
    ingested = _reuse_ingested_capture(
        knowledge_root, provider, idempotency_key.strip(), checksum
    )
    if ingested:
        return ingested
    inbox_root = knowledge_root.resolve() / "inbox" / provider
    inbox_root.mkdir(parents=True, exist_ok=True)
    for existing_path in sorted(inbox_root.glob("*.md")):
        try:
            existing, _ = read_conversation_intake(existing_path)
        except (OSError, ValueError):
            continue
        if existing.get("idempotency_key") != idempotency_key:
            continue
        if existing.get("checksum") != checksum:
            raise CaptureIdempotencyConflict(
                intake_id=str(existing["id"]),
                inbox_path=existing_path,
                existing_checksum=str(existing["checksum"]),
                supplied_checksum=checksum,
            )
        return CaptureResult(
            str(existing["id"]), existing_path, checksum, True
        )

    intake_uuid = str(uuid4())
    capture_path = inbox_root / f"{_slug(title)}-{intake_uuid}.md"
    details: Dict[str, object] = {"capture_type": "conversation"}
    if thread_ref:
        details["thread_ref"] = thread_ref
    if turn_from is not None:
        details["turn_from"] = turn_from
    if turn_to is not None:
        details["turn_to"] = turn_to
    if artifacts:
        details["artifacts"] = artifacts
    now = captured_at or datetime.now(timezone.utc)
    intake_id = f"inbox://campingtalk/{provider}/{intake_uuid}"
    frontmatter = {
        "type": "inbox_item",
        "id": intake_id,
        "title": title.strip(),
        "provider": provider,
        "content_type": "conversation",
        "captured_at": now.isoformat(timespec="seconds"),
        "status": "pending",
        "checksum": checksum,
        "idempotency_key": idempotency_key.strip(),
        "why_collected": why_collected.strip(),
        "intended_use": [item.strip() for item in intended_use],
        "sensitivity_review": sensitivity_review,
        "capture_details": details,
    }
    capture_path.write_text(
        render_markdown(
            frontmatter,
            "# Inbox Conversation\n\n"
            f"{INBOX_CONTENT_START}{content}{INBOX_CONTENT_END}\n",
        ),
        encoding="utf-8",
    )
    return CaptureResult(intake_id, capture_path, checksum)


@_synchronized_capture
def capture_document(
    knowledge_root: Path,
    content: str,
    provider: str,
    *,
    title: str,
    why_collected: str,
    intended_use: List[str],
    idempotency_key: str,
    source_url: Optional[str] = None,
    source_locator: Optional[str] = None,
    captured_from: str = "sync",
    sensitivity_review: str = "required",
    captured_at: Optional[datetime] = None,
    capture_details: Optional[Dict[str, object]] = None,
) -> CaptureResult:
    """Land an external document as an Inbox Item with source_ref, without ingesting it."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("document content must be non-empty")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider must contain only lowercase letters, digits, underscores, or hyphens")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if captured_from not in {"api", "webhook", "manual", "upload", "sync"}:
        raise ValueError("captured_from is invalid")
    if sensitivity_review not in {"completed", "required", "not_applicable"}:
        raise ValueError("sensitivity_review is invalid")
    if capture_details is not None and not isinstance(capture_details, dict):
        raise ValueError("capture_details must be an object")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    checksum = _content_checksum(content)
    ingested = _reuse_ingested_capture(
        knowledge_root, provider, idempotency_key.strip(), checksum
    )
    if ingested:
        return ingested
    inbox_root = knowledge_root.resolve() / "inbox" / provider
    inbox_root.mkdir(parents=True, exist_ok=True)
    for existing_path in sorted(inbox_root.glob("*.md")):
        try:
            existing, _ = read_conversation_intake(existing_path)
        except (OSError, ValueError):
            continue
        if existing.get("idempotency_key") != idempotency_key:
            continue
        if existing.get("checksum") != checksum:
            raise CaptureIdempotencyConflict(
                intake_id=str(existing["id"]), inbox_path=existing_path,
                existing_checksum=str(existing["checksum"]), supplied_checksum=checksum,
            )
        return CaptureResult(str(existing["id"]), existing_path, checksum, True)
    intake_uuid = str(uuid4())
    now = captured_at or datetime.now(timezone.utc)
    intake_id = f"inbox://campingtalk/{provider}/{intake_uuid}"
    path = inbox_root / f"{_slug(title)}-{intake_uuid}.md"
    frontmatter = {
        "type": "inbox_item",
        "id": intake_id,
        "title": title.strip(),
        "provider": provider,
        "content_type": "document",
        "captured_at": now.isoformat(timespec="seconds"),
        "captured_from": captured_from,
        "source_url": source_url or "",
        "source_locator": source_locator or "",
        "status": "pending",
        "checksum": checksum,
        "idempotency_key": idempotency_key.strip(),
        "why_collected": why_collected.strip(),
        "intended_use": [item.strip() for item in intended_use],
        "sensitivity_review": sensitivity_review,
    }
    if capture_details:
        frontmatter["capture_details"] = capture_details
    path.write_text(
        render_markdown(
            frontmatter,
            "# Inbox Document\n\n"
            f"{INBOX_CONTENT_START}{content}{INBOX_CONTENT_END}\n",
        ),
        encoding="utf-8",
    )
    return CaptureResult(intake_id, path, checksum)


@_synchronized_capture
def capture_file(
    knowledge_root: Path, payload: bytes, original_filename: str, provider: str, *,
    title: str, why_collected: str, intended_use: List[str], idempotency_key: str,
    source_url: Optional[str] = None, source_locator: Optional[str] = None,
    captured_from: str = "upload", sensitivity_review: str = "required",
) -> CaptureResult:
    """Land a binary or arbitrary file with a self-contained Inbox envelope."""
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("file payload must be non-empty bytes")
    if not isinstance(original_filename, str) or Path(original_filename).name != original_filename:
        raise ValueError("original_filename must be a basename")
    if not re.fullmatch(r"[a-z0-9_-]+", provider):
        raise ValueError("provider must contain only lowercase letters, digits, underscores, or hyphens")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be a non-empty string")
    if not isinstance(intended_use, list) or not intended_use or any(
        not isinstance(item, str) or not item.strip() for item in intended_use
    ):
        raise ValueError("intended_use must be a non-empty string array")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must be a non-empty string up to 200 characters")
    if captured_from not in {"api", "webhook", "manual", "upload", "sync"}:
        raise ValueError("captured_from is invalid")
    if sensitivity_review not in {"completed", "required", "not_applicable"}:
        raise ValueError("sensitivity_review is invalid")
    checksum = "sha256:" + hashlib.sha256(payload).hexdigest()
    ingested = _reuse_ingested_capture(
        knowledge_root, provider, idempotency_key.strip(), checksum
    )
    if ingested:
        return ingested
    inbox_root = knowledge_root.resolve() / "inbox" / provider
    inbox_root.mkdir(parents=True, exist_ok=True)
    for existing_path in sorted(inbox_root.glob("*.md")):
        try:
            existing, _ = read_conversation_intake(existing_path)
        except (OSError, ValueError):
            continue
        if existing.get("idempotency_key") == idempotency_key:
            if existing.get("checksum") != checksum:
                raise CaptureIdempotencyConflict(
                    intake_id=str(existing["id"]), inbox_path=existing_path,
                    existing_checksum=str(existing["checksum"]), supplied_checksum=checksum,
                )
            return CaptureResult(str(existing["id"]), existing_path, checksum, True)
    intake_uuid = str(uuid4())
    suffix = Path(original_filename).suffix.lower()
    payload_name = f"{_slug(Path(original_filename).stem)}-{intake_uuid}{suffix}"
    payload_path = inbox_root / payload_name
    payload_path.write_bytes(payload)
    intake_id = f"inbox://campingtalk/{provider}/{intake_uuid}"
    envelope = inbox_root / f"{_slug(Path(original_filename).stem)}-{intake_uuid}.inbox.md"
    frontmatter = {
        "type": "inbox_item", "id": intake_id, "title": title.strip(), "provider": provider,
        "content_type": "file", "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "captured_from": captured_from, "source_url": source_url or "", "source_locator": source_locator or "",
        "status": "pending", "checksum": checksum, "payload_file": payload_name,
        "idempotency_key": idempotency_key.strip(), "why_collected": why_collected.strip(),
        "intended_use": [item.strip() for item in intended_use], "sensitivity_review": sensitivity_review,
    }
    envelope.write_text(render_markdown(frontmatter, "# Inbox File\n\nPending inspection.\n"), encoding="utf-8")
    return CaptureResult(intake_id, envelope, checksum)
