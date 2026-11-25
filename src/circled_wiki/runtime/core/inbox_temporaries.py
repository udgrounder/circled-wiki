"""Preserve interrupted ingest sources outside the active Inbox namespace."""

from contextlib import contextmanager
import fcntl
from functools import wraps
from pathlib import Path
import re
import time
from uuid import uuid4


@contextmanager
def ingest_temporary_lock(knowledge_root):
    lock = Path(knowledge_root).resolve().parent / ".runtime/locks/inbox-ingest.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Inbox ingestion or temporary recovery is already running") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def inbox_ingest_session(function):
    @wraps(function)
    def wrapped(knowledge_root, *args, **kwargs):
        with ingest_temporary_lock(knowledge_root):
            return function(knowledge_root, *args, **kwargs)
    return wrapped


def ingest_temporary_path(knowledge_root: Path, suffix: str) -> Path:
    directory = knowledge_root / "inbox/.quarantine/ingest-staging"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f".ingest-{uuid4()}{suffix}"


def recover_inbox_temporaries(
    knowledge_root: Path, *, apply: bool = False, older_than_seconds: int = 86400,
) -> dict:
    """Preview or quarantine old ingest leftovers without parsing or deleting them.

    The lock excludes product ingestion. The explicit apply flag is required
    for legacy leftovers created by older workers that did not hold this lock.
    """
    if isinstance(older_than_seconds, bool) or not isinstance(older_than_seconds, int) or older_than_seconds < 3600:
        raise ValueError("older_than_seconds must be an integer of at least 3600")
    if not isinstance(apply, bool):
        raise ValueError("apply must be boolean")
    knowledge_root = knowledge_root.resolve()
    inbox = knowledge_root / "inbox"
    pattern = re.compile(r"^\.ingest-(?:removed-)?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.[a-zA-Z0-9]+$")
    items = []
    failures = []
    with ingest_temporary_lock(knowledge_root):
        for path in sorted(inbox.rglob(".ingest-*")):
            relative = path.relative_to(inbox)
            if "ingest-recovered" in relative.parts or not pattern.fullmatch(path.name):
                continue
            if path.is_symlink() or inbox not in path.resolve().parents or not path.is_file():
                continue
            if ".quarantine" in relative.parts and relative.parts[:2] != (".quarantine", "ingest-staging"):
                continue
            stat = path.stat()
            if time.time() - stat.st_mtime < older_than_seconds:
                continue
            # A valid capture bearing a staging-like name is user data, not a
            # recoverable ingest scratch file.
            if path.suffix == ".md":
                from .ingest import read_conversation_intake
                try:
                    read_conversation_intake(path)
                except (OSError, ValueError):
                    pass
                else:
                    continue
            item = {"path": relative.as_posix(), "status": "candidate"}
            if apply:
                destination = inbox / ".quarantine/ingest-recovered" / str(uuid4()) / relative
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    current = path.stat()
                    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                    if any(getattr(current, field) != getattr(stat, field) for field in fields):
                        raise ValueError("temporary file changed during recovery")
                    path.rename(destination)
                    item.update(status="quarantined", destination=destination.relative_to(inbox).as_posix())
                except (OSError, ValueError) as error:
                    failures.append({"path": relative.as_posix(), "error": str(error)})
                    continue
            items.append(item)
    return {"applied": apply, "item_count": len(items), "items": items, "failures": failures}
