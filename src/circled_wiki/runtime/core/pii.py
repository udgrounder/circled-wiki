"""Evidence PII scan receipts bound to immutable source checksums."""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

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
    candidate_checksum = receipt.get("candidate_checksum")
    if candidate_checksum is not None and (
        not isinstance(candidate_checksum, str) or not _CHECKSUM.fullmatch(candidate_checksum)
    ):
        errors.append("extensions.pii_scan.candidate_checksum must be a sha256 checksum")
    if result in {"passed", "masked"} and scanned is not True:
        errors.append("successful PII scan receipt requires pii_scanned: true")
    if result == "needs_review" and scanned is not False:
        errors.append("needs_review PII scan receipt requires pii_scanned: false")
    if masked is not (result == "masked"):
        errors.append("extensions.pii_masked must match a masked PII scan result")
    return errors


def build_pii_scan_receipt(
    checksum: str, *, scanner: str, scanner_version: str, result: str,
    reviewed_by: str, receipt: str, scanned_at: Optional[str] = None,
    candidate_checksum: Optional[str] = None,
) -> Dict[str, object]:
    """Build a checksum-bound receipt before an immutable Evidence is created."""
    values = (scanner, scanner_version, reviewed_by, receipt)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("scanner, scanner_version, reviewed_by, and receipt must be non-empty")
    if result not in PII_SCAN_RESULTS:
        raise ValueError("result must be passed, masked, or needs_review")
    if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
        raise ValueError("checksum must be a sha256 checksum")
    if candidate_checksum is not None and (
        not isinstance(candidate_checksum, str) or not _CHECKSUM.fullmatch(candidate_checksum)
    ):
        raise ValueError("candidate_checksum must be a sha256 checksum")
    result_data = {
        "scanner": scanner.strip(), "scanner_version": scanner_version.strip(),
        "scanned_at": scanned_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "result": result, "reviewed_by": reviewed_by.strip(), "receipt": receipt.strip(),
        "source_checksum": checksum,
    }
    if candidate_checksum is not None:
        result_data["candidate_checksum"] = candidate_checksum
    return result_data
