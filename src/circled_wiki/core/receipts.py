"""Typed, immutable receipts for releases, deployments, and runtime verification."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional


_SAFE_REF = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
DEPLOYMENT_STATUSES = (
    "planned", "applied", "failed", "rolled_back", "verification_pending", "verified",
)


def record_release_receipt(
    receipts_root: Path,
    *,
    manifest_path: Path,
    source_revision: str,
    included_issue_ids: Iterable[str],
    validation: Dict[str, str],
    verified_by: str,
    verified_at: Optional[str] = None,
) -> Dict[str, object]:
    """Validate an installed-asset manifest and record one immutable release receipt."""
    manifest = _read_json(manifest_path, "release manifest")
    release_id = _required_text(manifest, "os_release")
    profiles = manifest.get("runtime_profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("release manifest must contain runtime_profiles")
    prohibited = {"repository-engineering.md", "bootstrap-circled-wiki.md"}
    if prohibited.intersection(str(item) for item in profiles):
        raise ValueError("release manifest contains a Product Profile")
    router_checksum = _required_text(manifest, "router_checksum")
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        raise ValueError("release manifest assets must be a mapping")
    if assets.get(".circled-wiki/AGENT_ROUTER.md") != router_checksum:
        raise ValueError("release Router checksum does not match the manifest asset")
    required_validation = {"unit", "integration", "repository_validator"}
    if set(validation) != required_validation or any(
        validation[key] != "passed" for key in required_validation
    ):
        raise ValueError("release validation must pass unit, integration, and repository_validator")
    receipt = {
        "receipt_type": "release",
        "release_id": release_id,
        "source_revision": _non_empty(source_revision, "source_revision"),
        "runtime_checksum": _runtime_checksum(assets),
        "router_checksum": router_checksum,
        "runtime_profiles": sorted(str(item) for item in profiles),
        "included_issue_ids": sorted(set(str(item) for item in included_issue_ids)),
        "validation": validation,
        "verified_by": _non_empty(verified_by, "verified_by"),
        "verified_at": verified_at or datetime.now(timezone.utc).isoformat(),
    }
    path = receipts_root / "releases" / f"{release_id}.json"
    return _write_immutable(path, receipt)


def record_deployment_receipt(
    receipts_root: Path,
    *,
    release_receipt: Path,
    previous_release: str,
    target_ref: str,
    backup_ref: str,
    actions: Dict[str, List[str]],
    status: str = "verification_pending",
    applied_at: Optional[str] = None,
) -> Dict[str, object]:
    """Record what an approved bootstrap upgrade applied, preserved, and proposed."""
    release = _read_json(release_receipt, "release receipt")
    if release.get("receipt_type") != "release":
        raise ValueError("deployment requires a release receipt")
    if status not in DEPLOYMENT_STATUSES:
        raise ValueError(f"deployment status must be one of: {', '.join(DEPLOYMENT_STATUSES)}")
    if not _SAFE_REF.fullmatch(target_ref):
        raise ValueError("target_ref must be a non-secret safe alias")
    if set(actions) != {"applied", "preserved", "proposed"}:
        raise ValueError("deployment actions must contain applied, preserved, and proposed")
    for values in actions.values():
        if not isinstance(values, list):
            raise ValueError("deployment action groups must be lists")
        if any(_is_user_plane_path(str(path)) for path in values):
            raise ValueError("deployment receipt cannot contain knowledge/ or workspace/ actions")
    release_id = _required_text(release, "release_id")
    receipt = {
        "receipt_type": "deployment",
        "release_id": release_id,
        "previous_release": _non_empty(previous_release, "previous_release"),
        "target_ref": target_ref,
        "planned_at": datetime.now(timezone.utc).isoformat(),
        "applied_at": applied_at or datetime.now(timezone.utc).isoformat(),
        "backup_ref": _non_empty(backup_ref, "backup_ref"),
        "actions": actions,
        "status": status,
        "release_receipt": release_receipt.as_posix(),
    }
    path = receipts_root / "deployments" / target_ref / f"{release_id}.json"
    return _write_immutable(path, receipt)


def record_verification_receipt(
    receipts_root: Path,
    *,
    deployment_receipt: Path,
    expected_release: str,
    observed_release: str,
    verified_by: str,
    implemented_by: str,
    preflight_ready: bool,
    validator_passed: bool,
    config_preserved: bool,
    knowledge_preserved: bool,
    workspace_preserved: bool,
    reproduction_passed: bool,
) -> Dict[str, object]:
    """Record independent post-upgrade evidence only when every runtime gate passes."""
    deployment = _read_json(deployment_receipt, "deployment receipt")
    if deployment.get("receipt_type") != "deployment":
        raise ValueError("verification requires a deployment receipt")
    if deployment.get("status") not in {"applied", "verification_pending", "verified"}:
        raise ValueError("deployment is not ready for verification")
    if expected_release != observed_release or deployment.get("release_id") != expected_release:
        raise ValueError("verification release does not match deployment and runtime")
    verifier = _non_empty(verified_by, "verified_by")
    if verifier == _non_empty(implemented_by, "implemented_by"):
        raise ValueError("verification requires an independent actor")
    checks = {
        "preflight_ready": preflight_ready,
        "validator_passed": validator_passed,
        "config_preserved": config_preserved,
        "knowledge_preserved": knowledge_preserved,
        "workspace_preserved": workspace_preserved,
        "reproduction_passed": reproduction_passed,
    }
    failed = [name for name, passed in checks.items() if passed is not True]
    if failed:
        raise ValueError("verification gates failed: " + ", ".join(failed))
    target_ref = _required_text(deployment, "target_ref")
    receipt = {
        "receipt_type": "verification",
        "release_id": expected_release,
        "target_ref": target_ref,
        "deployment_receipt": deployment_receipt.as_posix(),
        "checks": checks,
        "verified_by": verifier,
        "implemented_by": implemented_by,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
    }
    path = receipts_root / "verifications" / target_ref / f"{expected_release}.json"
    return _write_immutable(path, receipt)


def validate_issue_verification_receipts(
    project_root: Path,
    *,
    fixed_release: str,
    deployed_release: str,
    actor: str,
    deployment_receipt: str,
    verification_receipt: str,
) -> None:
    """Cross-check Issue status inputs against receipts stored inside the project."""
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


def _runtime_checksum(assets: Dict[str, object]) -> str:
    digest = hashlib.sha256()
    for path, checksum in sorted(assets.items()):
        if path.startswith(".circled-wiki/runtime/"):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(checksum).encode("utf-8"))
            digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _write_immutable(path: Path, receipt: Dict[str, object]) -> Dict[str, object]:
    content = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("an immutable receipt already exists with different content")
        return {"path": path.as_posix(), **receipt}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": path.as_posix(), **receipt}


def _read_json(path: Path, label: str) -> Dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{label} is missing or invalid") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _required_text(payload: Dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a non-empty string")
    return _non_empty(value, field)


def _non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _is_user_plane_path(path: str) -> bool:
    normalized = path.lstrip("./")
    return normalized == "knowledge" or normalized.startswith("knowledge/") or (
        normalized == "workspace" or normalized.startswith("workspace/")
    )


def _safe_project_receipt(project_root: Path, reference: str) -> Path:
    project_root = project_root.resolve()
    candidate = (project_root / reference).resolve()
    receipts_root = project_root / "workspace" / "receipts"
    if receipts_root not in candidate.parents or not candidate.is_file():
        raise ValueError("receipt reference must be an existing file below workspace/receipts")
    return candidate
