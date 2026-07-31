"""Runtime-side validation of Product-created deployment receipts."""

import json
from pathlib import Path
from typing import Dict


def validate_issue_verification_receipts(
    project_root: Path,
    *,
    fixed_release: str,
    deployed_release: str,
    actor: str,
    deployment_receipt: str,
    verification_receipt: str,
) -> None:
    """Cross-check receipts before an installed Wiki marks an Issue verified."""
    deployment_path = _safe_project_receipt(project_root, deployment_receipt)
    verification_path = _safe_project_receipt(project_root, verification_receipt)
    deployment = _read_json(deployment_path, "deployment receipt")
    verification = _read_json(verification_path, "verification receipt")
    if deployment.get("receipt_type") != "deployment":
        raise ValueError("deployment_receipt does not identify a Deployment Receipt")
    if verification.get("receipt_type") != "verification":
        raise ValueError("verification_receipt does not identify a Verification Receipt")
    if not all(
        release == fixed_release == deployed_release
        for release in (deployment.get("release_id"), verification.get("release_id"))
    ):
        raise ValueError("Issue release does not match deployment and verification receipts")
    if verification.get("status") != "verified" or verification.get("verified_by") != actor:
        raise ValueError("Verification Receipt must be verified by the Issue transition actor")
    recorded_deployment = verification.get("deployment_receipt")
    if not isinstance(recorded_deployment, str):
        raise ValueError("Verification Receipt does not reference a Deployment Receipt")
    if Path(recorded_deployment).resolve() != deployment_path:
        raise ValueError("Verification Receipt references a different Deployment Receipt")


def _read_json(path: Path, label: str) -> Dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} is missing or invalid") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _safe_project_receipt(project_root: Path, reference: str) -> Path:
    project_root = project_root.resolve()
    candidate = (project_root / reference).resolve()
    receipts_root = project_root / "workspace" / "receipts"
    if receipts_root not in candidate.parents or not candidate.is_file():
        raise ValueError("receipt reference must be an existing file below workspace/receipts")
    return candidate
