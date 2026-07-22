"""Evidence PII scan receipts bound to immutable source checksums."""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from .frontmatter import parse_markdown, render_markdown


PII_SCAN_RESULTS = ("passed", "masked", "needs_review")
_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")


def pii_scan_receipt_errors(frontmatter: Dict[str, Any]) -> List[str]:
    """Return consistency errors for an Evidence PII scan attestation."""
    errors: List[str] = []
    extensions = frontmatter.get("extensions")
    if not isinstance(extensions, dict):
        return ["extensions must be an object for Evidence PII scan state"]

    scanned = extensions.get("pii_scanned", False)
    masked = extensions.get("pii_masked", False)
    receipt = extensions.get("pii_scan")
    if not isinstance(scanned, bool):
        errors.append("extensions.pii_scanned must be boolean")
    if not isinstance(masked, bool):
        errors.append("extensions.pii_masked must be boolean")
    if receipt is None:
        if scanned is True:
            errors.append("extensions.pii_scan receipt is required when pii_scanned is true")
        if masked is True:
            errors.append("extensions.pii_scan receipt is required when pii_masked is true")
        return errors
    if not isinstance(receipt, dict):
        errors.append("extensions.pii_scan must be an object")
        return errors

    for field in ("scanner", "scanner_version", "scanned_at", "result", "reviewed_by", "receipt", "source_checksum"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"extensions.pii_scan.{field} must be non-empty")
    result = receipt.get("result")
    if result not in PII_SCAN_RESULTS:
        errors.append("extensions.pii_scan.result is invalid")
    scanned_at = receipt.get("scanned_at")
    if isinstance(scanned_at, str) and scanned_at.strip():
        try:
            datetime.fromisoformat(scanned_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("extensions.pii_scan.scanned_at must be an ISO 8601 timestamp")
    source_checksum = receipt.get("source_checksum")
    if isinstance(source_checksum, str) and not _CHECKSUM.fullmatch(source_checksum):
        errors.append("extensions.pii_scan.source_checksum must be a sha256 checksum")
    if source_checksum != frontmatter.get("checksum"):
        errors.append("extensions.pii_scan.source_checksum must equal Evidence checksum")
    if result in {"passed", "masked"} and scanned is not True:
        errors.append("successful PII scan receipt requires pii_scanned: true")
    if result == "needs_review" and scanned is not False:
        errors.append("needs_review PII scan receipt requires pii_scanned: false")
    if masked is not (result == "masked"):
        errors.append("extensions.pii_masked must match a masked PII scan result")
    return errors


def record_pii_scan_receipt(
    knowledge_root: Path,
    evidence_id: str,
    *,
    scanner: str,
    scanner_version: str,
    result: str,
    reviewed_by: str,
    receipt: str,
    scanned_at: Optional[str] = None,
) -> Dict[str, object]:
    """Record an external/manual scan result; this function does not perform a scan."""
    values = {
        "scanner": scanner,
        "scanner_version": scanner_version,
        "reviewed_by": reviewed_by,
        "receipt": receipt,
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("scanner, scanner_version, reviewed_by, and receipt must be non-empty")
    if result not in PII_SCAN_RESULTS:
        raise ValueError("result must be passed, masked, or needs_review")
    timestamp = scanned_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    target = None
    for path in sorted((knowledge_root / "evidence").rglob("*.md")):
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        if document.frontmatter.get("id") == evidence_id:
            target = document
            break
    if target is None or target.frontmatter.get("type") != "evidence":
        raise ValueError("evidence_id must refer to an existing Evidence Record")

    updated = dict(target.frontmatter)
    extensions = dict(updated.get("extensions", {}))
    extensions["pii_scanned"] = result in {"passed", "masked"}
    extensions["pii_masked"] = result == "masked"
    extensions["pii_scan"] = {
        "scanner": scanner.strip(),
        "scanner_version": scanner_version.strip(),
        "scanned_at": timestamp,
        "result": result,
        "reviewed_by": reviewed_by.strip(),
        "receipt": receipt.strip(),
        "source_checksum": updated.get("checksum"),
    }
    updated["extensions"] = extensions
    errors = pii_scan_receipt_errors(updated)
    if errors:
        raise ValueError("; ".join(errors))
    target.path.write_text(render_markdown(updated, target.body), encoding="utf-8")
    return {
        "evidence_id": evidence_id,
        "pii_scanned": extensions["pii_scanned"],
        "pii_masked": extensions["pii_masked"],
        "pii_scan": extensions["pii_scan"],
        "path": target.path.relative_to(knowledge_root.parent).as_posix(),
    }
