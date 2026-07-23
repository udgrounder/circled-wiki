"""Protect immutable organization namespaces in installation-local knowledge."""

from pathlib import Path
import re
from typing import Dict, Optional, Set

from circled_wiki.config.settings import organization_id_for

from .frontmatter import FrontmatterError, parse_markdown


ORGANIZATION_URI = re.compile(r"^(?:knowledge|evidence|inbox)://([^/]+)/")


def inspect_organization_namespace(
    knowledge_root: Path, configured_id: Optional[str] = None
) -> Dict[str, object]:
    """Compare configured identity with namespaces already present in managed data."""
    configured = configured_id or organization_id_for(knowledge_root)
    observed: Set[str] = set()
    for section in ("bundles", "evidence", "inbox"):
        root = knowledge_root / section
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if path.name in {"index.md", "log.md"}:
                continue
            try:
                document = parse_markdown(path)
            except (OSError, FrontmatterError):
                continue
            document_id = document.frontmatter.get("id")
            match = ORGANIZATION_URI.match(document_id) if isinstance(document_id, str) else None
            if match:
                observed.add(match.group(1))
    observed_ids = tuple(sorted(observed))
    return {
        "configured_id": configured,
        "observed_ids": observed_ids,
        "compatible": not observed_ids or observed_ids == (configured,),
    }


def require_stable_organization_id(
    knowledge_root: Path, configured_id: Optional[str] = None
) -> str:
    """Return the configured ID only when it matches all existing managed IDs."""
    report = inspect_organization_namespace(knowledge_root, configured_id)
    if not report["compatible"]:
        observed = ", ".join(report["observed_ids"])
        raise ValueError(
            "organization.id cannot change after managed knowledge exists; "
            f"configured={report['configured_id']} observed={observed}"
        )
    return str(report["configured_id"])
