"""Unified, checksum-bound receipt for Inbox data protection decisions.

The Inbox-to-Evidence boundary has one security decision: the candidate that
was scanned, optionally masked by the Agent, and accepted in its final form.
The nested PII receipt is retained as a compatibility projection for existing
Evidence validators, but this document is the canonical transition receipt.
"""

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from .pii import pii_scan_receipt_errors


DATA_PROTECTION_RECEIPT_VERSION = 1
DATA_PROTECTION_RESULTS = {"passed", "masked", "awaiting_user"}
SENSITIVITY_DECISIONS = {"completed", "not_applicable", "awaiting_user"}
_CHECKSUM = re.compile(r"^sha256:[0-9a-f]{64}$")


def data_protection_candidate_checksum(data: Dict[str, object], content: object) -> str:
    """Fingerprint the exact Inbox candidate, including copied metadata.

    The ordinary Inbox checksum covers the body/payload.  This additional
    fingerprint prevents a later metadata edit (for example, a phone number
    added to a title) from reusing an otherwise valid security Receipt.
    """
    candidate = {
        "content_checksum": str(data.get("checksum", ""))
        if not isinstance(content, str) else content,
        "title": data.get("title", ""),
        "why_collected": data.get("why_collected", ""),
        "source_url": data.get("source_url", ""),
        "source_locator": data.get("source_locator", ""),
        "intended_use": data.get("intended_use", []),
    }
    encoded = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_data_protection_receipt(
    *,
    source_checksum: str,
    candidate_checksum: str,
    pii_scan: Dict[str, object],
    policy_ref: str,
    policy_config: str,
    policy_config_version: int,
    actor: str,
    sensitivity_decision: str,
    context: str,
    matched_categories: Iterable[str],
    agent_masked_findings: Iterable[Dict[str, object]],
    resolution: str,
    receipt: Optional[str] = None,
) -> Dict[str, object]:
    """Build one safe receipt without copying Agent-observed source values."""
    if not isinstance(source_checksum, str) or not source_checksum.startswith("sha256:"):
        raise ValueError("data protection receipt source_checksum is invalid")
    if not isinstance(candidate_checksum, str) or not _CHECKSUM.fullmatch(candidate_checksum):
        raise ValueError("data protection receipt candidate_checksum is invalid")
    if not isinstance(pii_scan, dict):
        raise ValueError("data protection receipt pii_scan must be an object")
    if sensitivity_decision not in SENSITIVITY_DECISIONS:
        raise ValueError("data protection receipt sensitivity decision is invalid")
    if policy_config_version != DATA_PROTECTION_RECEIPT_VERSION:
        raise ValueError("data protection receipt policy_config_version is invalid")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("data protection receipt actor must be non-empty")
    if not isinstance(context, str):
        raise ValueError("data protection receipt context must be a string")
    normalized_findings: List[Dict[str, object]] = []
    for finding in agent_masked_findings:
        if not isinstance(finding, dict):
            raise ValueError("data protection receipt masked finding is invalid")
        category = finding.get("category")
        count = finding.get("count")
        if not isinstance(category, str) or not category.strip() or not isinstance(count, int) or count < 1:
            raise ValueError("data protection receipt masked finding is invalid")
        normalized_findings.append({"category": category.strip(), "count": count})
    pii_result = str(pii_scan.get("result", ""))
    masked = pii_result == "masked" or bool(normalized_findings)
    status = "awaiting_user" if sensitivity_decision == "awaiting_user" or pii_result == "needs_review" else (
        "masked" if masked else "passed"
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "schema_version": DATA_PROTECTION_RECEIPT_VERSION,
        "source_checksum": source_checksum,
        "candidate_checksum": candidate_checksum,
        "policy_ref": policy_ref,
        "policy_config": policy_config,
        "policy_config_version": policy_config_version,
        "actor": actor.strip(),
        "recorded_at": now,
        "status": status,
        "receipt": receipt or f"runtime://data-protection/{source_checksum}",
        "pii_scan": dict(pii_scan),
        "sensitivity": {
            "decision": sensitivity_decision,
            "context": context,
            "matched_categories": sorted({str(item) for item in matched_categories}),
            "agent_masked_findings": normalized_findings,
            "resolution": resolution,
        },
    }


def data_protection_receipt_errors(
    receipt: Any, *, checksum: str, candidate_checksum: Optional[str] = None,
    require_resolved: bool = False,
) -> List[str]:
    """Return structural errors for a unified Inbox transition receipt."""
    errors: List[str] = []
    if not isinstance(receipt, dict):
        return ["data_protection_receipt must be an object"]
    if receipt.get("schema_version") != DATA_PROTECTION_RECEIPT_VERSION:
        errors.append("data_protection_receipt schema_version is unsupported")
    if receipt.get("source_checksum") != checksum:
        errors.append("data_protection_receipt source_checksum must equal Inbox checksum")
    receipt_candidate_checksum = receipt.get("candidate_checksum")
    if not isinstance(receipt_candidate_checksum, str) or not _CHECKSUM.fullmatch(receipt_candidate_checksum):
        errors.append("data_protection_receipt candidate_checksum is invalid")
    elif candidate_checksum is not None and receipt_candidate_checksum != candidate_checksum:
        errors.append("data_protection_receipt candidate_checksum must equal Inbox candidate")
    for field in ("policy_ref", "policy_config", "actor", "recorded_at", "receipt"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            errors.append(f"data_protection_receipt.{field} must be non-empty")
    if receipt.get("policy_config_version") != DATA_PROTECTION_RECEIPT_VERSION:
        errors.append("data_protection_receipt.policy_config_version is unsupported")
    status = receipt.get("status")
    if status not in DATA_PROTECTION_RESULTS:
        errors.append("data_protection_receipt.status is invalid")
    recorded_at = receipt.get("recorded_at")
    if isinstance(recorded_at, str):
        try:
            datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("data_protection_receipt.recorded_at must be ISO 8601")
    pii_scan = receipt.get("pii_scan")
    if not isinstance(pii_scan, dict):
        errors.append("data_protection_receipt.pii_scan must be an object")
    else:
        probe = {
            "checksum": checksum,
            "extensions": {
                "pii_scan": pii_scan,
                "pii_scanned": pii_scan.get("result") in {"passed", "masked"},
                "pii_masked": pii_scan.get("result") == "masked",
            },
        }
        errors.extend(pii_scan_receipt_errors(probe))
    sensitivity = receipt.get("sensitivity")
    sensitivity_decision = None
    finding_count = 0
    if not isinstance(sensitivity, dict):
        errors.append("data_protection_receipt.sensitivity must be an object")
    else:
        decision = sensitivity.get("decision")
        sensitivity_decision = decision
        if decision not in SENSITIVITY_DECISIONS:
            errors.append("data_protection_receipt.sensitivity.decision is invalid")
        if not isinstance(sensitivity.get("context"), str):
            errors.append("data_protection_receipt.sensitivity.context must be a string")
        categories = sensitivity.get("matched_categories")
        if not isinstance(categories, list) or any(not isinstance(item, str) or not item.strip() for item in categories):
            errors.append("data_protection_receipt.sensitivity.matched_categories is invalid")
        findings = sensitivity.get("agent_masked_findings")
        if not isinstance(findings, list):
            errors.append("data_protection_receipt.sensitivity.agent_masked_findings is invalid")
        else:
            for finding in findings:
                if (
                    not isinstance(finding, dict)
                    or not isinstance(finding.get("category"), str)
                    or not finding.get("category", "").strip()
                    or not isinstance(finding.get("count"), int)
                    or isinstance(finding.get("count"), bool)
                    or finding.get("count", 0) < 1
                    or "value" in finding
                ):
                    errors.append("data_protection_receipt.sensitivity.agent_masked_findings is invalid")
                    break
                finding_count += int(finding["count"])
        resolution = sensitivity.get("resolution")
        if not isinstance(resolution, str) or not resolution.strip():
            errors.append("data_protection_receipt.sensitivity.resolution must be non-empty")
        if require_resolved and decision == "awaiting_user":
            errors.append("data_protection_receipt is awaiting user")
    pii_result = pii_scan.get("result") if isinstance(pii_scan, dict) else None
    expected_status = (
        "awaiting_user" if sensitivity_decision == "awaiting_user" or pii_result == "needs_review"
        else "masked" if pii_result == "masked" or finding_count else "passed"
    )
    if status != expected_status:
        errors.append("data_protection_receipt.status does not match its nested decisions")
    if require_resolved and (status == "awaiting_user" or pii_result == "needs_review"):
        errors.append("data_protection_receipt is not resolved")
    return errors
