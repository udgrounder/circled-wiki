"""Source-only remediation for legacy Evidence PII receipt gaps.

This module is intentionally exposed only through ``circled_wiki.product_cli``.
It is not a Runtime command and must not be packaged into a Wiki release.
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Dict, List

from circled_wiki.core.evidence import evidence_content_mode, evidence_original_bytes, render_embedded_body
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.pii import pii_scan_receipt_errors
from circled_wiki.core.sensitive_data import detect_sensitive_data_categories, redact_sensitive_data


SCANNER = "circled-wiki-legacy-pii-remediation"
SCANNER_VERSION = "1"


def remediate_legacy_pii_receipts(
    knowledge_root: Path, *, reviewed_by: str, apply: bool = False,
) -> Dict[str, object]:
    """Re-scan legacy Evidence and update only its PII frontmatter fields.

    A detected high-risk category is never masked or exposed: it remains
    ``needs_review``.  Undecodable or unavailable originals also remain under
    review.  This is a one-off Product maintenance operation, not ingestion.
    """
    if not reviewed_by.strip():
        raise ValueError("reviewed_by must be non-empty")
    findings: List[Dict[str, object]] = []
    for path in sorted((knowledge_root / "evidence").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        if pii_scan_receipt_errors(document.frontmatter) == []:
            continue
        original = evidence_original_bytes(document)
        categories: tuple[str, ...] = ()
        reason = "passed"
        if original is None:
            reason = "needs_review"
        else:
            try:
                categories = detect_sensitive_data_categories(original.decode("utf-8"))
            except UnicodeDecodeError:
                reason = "needs_review"
            if categories:
                reason = "needs_review"
        checksum = str(document.frontmatter.get("checksum", ""))
        findings.append({"path": str(path), "result": reason, "categories": list(categories)})
        if not apply:
            continue
        data = dict(document.frontmatter)
        extensions = dict(data.get("extensions") or {})
        extensions["pii_scanned"] = True
        extensions["pii_masked"] = False
        extensions["pii_scan"] = {
            "scanner": SCANNER,
            "scanner_version": SCANNER_VERSION,
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "result": reason,
            "reviewed_by": reviewed_by.strip(),
            "receipt": f"legacy-remediation:{checksum}",
            "source_checksum": checksum,
        }
        data["extensions"] = extensions
        path.write_text(render_markdown(data, document.body), encoding="utf-8")
    return {"apply": apply, "reviewed": len(findings), "passed": sum(item["result"] == "passed" for item in findings), "needs_review": sum(item["result"] == "needs_review" for item in findings), "findings": findings}


def mask_legacy_pii_evidence(knowledge_root: Path, *, reviewed_by: str) -> Dict[str, object]:
    """Mask detected legacy originals; preserve IDs and all non-PII metadata."""
    changed = 0
    for path in sorted((knowledge_root / "evidence").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        original = evidence_original_bytes(document)
        if original is None:
            continue
        try:
            text = original.decode("utf-8")
        except UnicodeDecodeError:
            continue
        redacted = redact_sensitive_data(text)
        if not redacted.categories:
            continue
        checksum = "sha256:" + hashlib.sha256(redacted.content.encode("utf-8")).hexdigest()
        data = dict(document.frontmatter)
        extensions = dict(data.get("extensions") or {})
        extensions.update({"pii_scanned": True, "pii_masked": True, "pii_scan": {"scanner": SCANNER, "scanner_version": SCANNER_VERSION, "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "result": "masked", "reviewed_by": reviewed_by, "receipt": f"legacy-remediation:{checksum}", "source_checksum": checksum}})
        data["checksum"] = checksum
        data["extensions"] = extensions
        if evidence_content_mode(document) == "embedded":
            body = render_embedded_body(redacted.content)
            path.write_text(render_markdown(data, body), encoding="utf-8")
        else:
            original_path = path.parent / str(data["original_file"])
            original_path.write_text(redacted.content, encoding="utf-8")
            path.write_text(render_markdown(data, document.body), encoding="utf-8")
        changed += 1
    return {"masked": changed}
