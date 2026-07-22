"""Validation for the OKF v0.1 minimum and the configured organization Profile."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hashlib
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Set
from uuid import UUID

from knowledge_os.config.settings import organization_id_for

from .frontmatter import FrontmatterError, parse_markdown
from .pii import pii_scan_receipt_errors
from .evidence import evidence_content_mode, evidence_original_bytes
from .models import MarkdownDocument, ValidationResult


RESERVED_FILENAMES = {"README.md", "index.md", "log.md"}
BUNDLE_TYPES = {"policy", "guide", "runbook", "decision", "spec", "reference"}
BUNDLE_STATUSES = {"draft", "active", "deprecated", "archived"}
EVIDENCE_STATUSES = {"new", "processing", "processed", "ignored", "failed", "needs_review"}
EVIDENCE_AVAILABILITY = {
    "available", "metadata_only", "temporarily_unavailable", "access_denied", "missing"
}
WORKFLOW_EXECUTION_MODES = {"guided", "agent_assisted", "automated"}
WORKFLOW_STEP_KINDS = {"action", "decision", "approval", "validation"}
INQUIRY_STATUSES = {"open", "investigating", "resolved", "wont_fix"}
RUNBOOK_RISK_MAX_DAYS = {"critical": 7, "high": 30, "medium": 90, "low": 180}
SOURCE_VOLATILITY = {"volatile", "periodic", "stable"}
SOURCE_VOLATILITY_FACTOR = {"volatile": 0.5, "periodic": 1.0, "stable": 1.0}
RUNBOOK_CHANGE_TRIGGERS = {
    "user_requested", "user_reference", "owner_requested", "source_change", "outcome_signal",
    "security_or_compliance",
}
RUNBOOK_MATURITY = {"pilot", "operational", "optimized"}
ARTIFACT_PROFILE_TYPES = {
    "decision_report", "work_guide", "registration_package", "design_brief",
    "review_report", "comparison_report",
}
EVIDENCE_REUSE_VALUE = {"high", "medium", "low"}
EVIDENCE_RETENTION_CLASS = {
    "workflow_reference", "decision_record", "outcome", "general_reference", "ephemeral",
}
def _evidence_uri(organization_id: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(?:evidence/{re.escape(organization_id)}/[^/]+_[0-9a-fA-F-]{{36}}\.md|evidence://{re.escape(organization_id)}/[a-z0-9_-]+/\d{{4}}/\d{{2}}/\d{{2}}/[0-9a-fA-F-]{{36}})$"
    )


def _bundle_uri(organization_id: str) -> re.Pattern[str]:
    return re.compile(
        rf"^(?:(?:bundle|knowledge)/{re.escape(organization_id)}/[^/]+_[0-9a-fA-F-]{{36}}\.md|knowledge://{re.escape(organization_id)}/[a-z0-9][a-z0-9._~/-]*_[0-9a-fA-F-]{{36}})$"
    )


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_uuid(value: Any) -> bool:
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _is_timestamp(value: Any) -> bool:
    if isinstance(value, (datetime, date)):
        return True
    if not _is_nonempty_string(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _as_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    elif _is_nonempty_string(value):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def verify_evidence_original(document: MarkdownDocument) -> Optional[str]:
    """Return an integrity error for Evidence declared available, otherwise None."""
    data = document.frontmatter
    extensions = data.get("extensions")
    availability = extensions.get("availability") if isinstance(extensions, dict) else None
    if availability != "available":
        return None
    content_mode = evidence_content_mode(document)
    if content_mode == "external_file":
        original_file = data.get("original_file")
        if not _is_nonempty_string(original_file):
            return "available external-file Evidence original_file must be non-empty"
        original_path = (document.path.parent / str(original_file)).resolve()
        if original_path.parent != document.path.parent.resolve():
            return "Evidence original_file must stay beside its manifest"
        if not original_path.is_file():
            return "available Evidence original file is missing"
    elif content_mode == "embedded":
        extensions = data.get("extensions", {})
        if extensions.get("checksum_scope") != "original_content":
            return "embedded Evidence checksum_scope must be original_content"
    original = evidence_original_bytes(document)
    if original is None:
        return "available Evidence original content is missing"
    checksum = str(data.get("checksum", ""))
    if not re.match(r"^sha256:[0-9a-f]{64}$", checksum):
        return None
    digest = hashlib.sha256(original)
    if "sha256:" + digest.hexdigest() != checksum:
        return "Evidence original checksum does not match manifest"
    return None


def _path_kind(path: Path, knowledge_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(knowledge_root.resolve())
    except ValueError:
        return "other"
    if relative.parts and relative.parts[0] == "bundles":
        return "bundle"
    if relative.parts and relative.parts[0] == "evidence" and path.suffix == ".md":
        return "evidence"
    return "other"


def _is_valid_evidence_link(value: Any, knowledge_root: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    match = re.fullmatch(r"\[[^\]\r\n]+\]\(([^()\r\n]+)\)", value.strip())
    if match is None:
        return False
    link = Path(match.group(1))
    if link.is_absolute() or ".." in link.parts:
        return False
    if not link.parts or link.parts[0] != "evidence" or link.suffix != ".md":
        return False
    target = (knowledge_root / link).resolve()
    try:
        target.relative_to(knowledge_root.resolve())
    except ValueError:
        return False
    return target.is_file()


def validate_document(path: Path, knowledge_root: Path) -> ValidationResult:
    """Validate a single managed Markdown document without repository lookups."""
    result = ValidationResult(path=path)
    if path.name in RESERVED_FILENAMES:
        return result
    try:
        document = parse_markdown(path)
    except (OSError, FrontmatterError) as error:
        result.okf_errors.append(str(error))
        return result

    data = document.frontmatter
    if not _is_nonempty_string(data.get("type")):
        result.okf_errors.append("type must be a non-empty string")

    kind = _path_kind(path, knowledge_root)
    organization_id = organization_id_for(knowledge_root)
    if kind == "bundle":
        _validate_bundle(document, result, organization_id, knowledge_root)
    elif kind == "evidence":
        _validate_evidence(document, result, organization_id)
    return result


def _validate_bundle(
    document: MarkdownDocument, result: ValidationResult, organization_id: str,
    knowledge_root: Path,
) -> None:
    data = document.frontmatter
    required = ("id", "bundle_uuid", "title", "type", "status", "summary", "updated_at", "evidence")
    for field in required:
        if field not in data:
            result.profile_errors.append(f"missing required Bundle field: {field}")
    for field in ("id", "title", "type", "status", "summary"):
        if field in data and not _is_nonempty_string(data[field]):
            result.profile_errors.append(f"{field} must be a non-empty string")
    if "bundle_uuid" in data and not _is_uuid(data["bundle_uuid"]):
        result.profile_errors.append("bundle_uuid must be a UUID")
    if "id" in data and not _bundle_uri(organization_id).match(str(data["id"])):
        result.profile_errors.append(
            f"id must be a knowledge URI for organization '{organization_id}'"
        )
    if "status" in data and data["status"] not in BUNDLE_STATUSES:
        result.profile_errors.append("status must be one of draft, active, deprecated, archived")
    if "type" in data and data["type"] not in BUNDLE_TYPES:
        result.warnings.append("unknown Bundle type is allowed but not in the repository recommended set")
    if "updated_at" in data and not _is_timestamp(data["updated_at"]):
        result.profile_errors.append("updated_at must be an ISO 8601 timestamp")
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        result.profile_errors.append("evidence must be a non-empty array")
    elif any(not _evidence_uri(organization_id).match(str(item)) for item in evidence):
        result.profile_errors.append(
            f"every evidence item must use organization '{organization_id}'"
        )
    evidence_links = data.get("evidence_links")
    if evidence_links is not None:
        if not isinstance(evidence_links, list) or not evidence_links:
            result.profile_errors.append("evidence_links must be a non-empty array when present")
        elif any(not _is_valid_evidence_link(item, knowledge_root) for item in evidence_links):
            result.profile_errors.append("evidence_links must contain Markdown links to knowledge-root Evidence Markdown paths")
    if "bundle_uuid" in data and _is_uuid(data["bundle_uuid"]):
        suffix = "_" + str(data["bundle_uuid"])
        identifier = str(data.get("id", ""))
        if identifier.startswith(("bundle/", "knowledge/")):
            if not identifier.endswith(suffix + ".md"):
                result.profile_errors.append("new Bundle id must end with _{bundle_uuid}.md")
        elif not identifier.endswith(suffix):
            result.profile_errors.append("legacy Bundle id must end with _{bundle_uuid}")
        if not document.path.stem.endswith(suffix):
            result.profile_errors.append("Bundle filename must end with _{bundle_uuid}")
    _validate_bundle_placement(document, result)
    _validate_curation(data, result, organization_id)
    _validate_governance(data, result)
    _validate_archive(data, result)
    _validate_rulebook(data, result)
    _validate_inquiry(data, result)
    _validate_workflow(data, result, organization_id)
    _warn_unscoped_extensions(data, result)


def _validate_curation(
    data: Dict[str, Any], result: ValidationResult, organization_id: str
) -> None:
    """Validate review provenance when a Bundle is managed as a candidate."""
    extensions = data.get("extensions")
    if not isinstance(extensions, dict):
        return
    review_state = extensions.get("review_state")
    curation = extensions.get("curation")
    candidate_states = {"pending", "needs_changes", "approved", "rejected", "merged"}
    if review_state is not None and review_state not in candidate_states:
        result.profile_errors.append("extensions.review_state is invalid for a curation candidate")
    if curation is None:
        return
    if not isinstance(curation, dict):
        result.profile_errors.append("extensions.curation must be an object")
        return
    # Legacy active Bundles may use review_state=approved as a publication label.
    # Candidate lifecycle rules apply only once curation provenance is present.
    if review_state in {"pending", "needs_changes"} and data.get("status") != "draft":
        result.profile_errors.append("pending and needs_changes candidates must remain draft")
    if review_state == "approved" and data.get("status") not in {"draft", "active"}:
        result.profile_errors.append("approved candidates must be draft or active")
    if review_state == "approved" and data.get("status") == "active":
        promotion = curation.get("promotion")
        if not isinstance(promotion, dict):
            result.profile_errors.append("active approved candidates must define extensions.curation.promotion")
        else:
            for field in ("approved_by", "approved_at", "security_receipt"):
                if not _is_nonempty_string(promotion.get(field)):
                    result.profile_errors.append(f"extensions.curation.promotion.{field} must be non-empty")
            if "approved_at" in promotion and not _is_timestamp(promotion["approved_at"]):
                result.profile_errors.append("extensions.curation.promotion.approved_at must be ISO 8601")
    if review_state in {"rejected", "merged"} and data.get("status") != "archived":
        result.profile_errors.append("rejected and merged candidates must be archived")
    for field in ("generated_by", "generation_reason"):
        if field in curation and not _is_nonempty_string(curation[field]):
            result.profile_errors.append(f"extensions.curation.{field} must be non-empty")
    if "generated_by" in curation:
        for field in ("generated_at", "generation_reason", "evidence_checksum", "curation_receipt", "recommendation", "profile_version"):
            if not _is_nonempty_string(curation.get(field)):
                result.profile_errors.append(f"extensions.curation.{field} must be non-empty")
        checksum = curation.get("evidence_checksum")
        if isinstance(checksum, str) and not re.fullmatch(r"sha256:[0-9a-f]{64}", checksum):
            result.profile_errors.append("extensions.curation.evidence_checksum must be a sha256 checksum")
    if "generated_at" in curation and not _is_timestamp(curation["generated_at"]):
        result.profile_errors.append("extensions.curation.generated_at must be ISO 8601")
    _validate_curation_receipt(
        curation.get("receipt"), result,
        expected_checksum=curation.get("evidence_checksum"), prefix="extensions.curation.receipt",
    )
    reviewed_by = curation.get("reviewed_by")
    reviewed_at = curation.get("reviewed_at")
    if (reviewed_by is None) != (reviewed_at is None):
        result.profile_errors.append("extensions.curation.reviewed_by and reviewed_at must appear together")
    if reviewed_by is not None and not _is_nonempty_string(reviewed_by):
        result.profile_errors.append("extensions.curation.reviewed_by must be non-empty")
    if reviewed_at is not None and not _is_timestamp(reviewed_at):
        result.profile_errors.append("extensions.curation.reviewed_at must be ISO 8601")
    history = curation.get("review_history")
    if history is not None:
        if not isinstance(history, list) or not history:
            result.profile_errors.append("extensions.curation.review_history must be a non-empty array")
        else:
            for entry in history:
                if not isinstance(entry, dict):
                    result.profile_errors.append("extensions.curation.review_history items must be objects")
                    continue
                if entry.get("action") not in {"needs_changes", "approve", "reject", "merge"}:
                    result.profile_errors.append("extensions.curation.review_history.action is invalid")
                if not _is_nonempty_string(entry.get("actor")):
                    result.profile_errors.append("extensions.curation.review_history.actor must be non-empty")
                if not _is_timestamp(entry.get("at")):
                    result.profile_errors.append("extensions.curation.review_history.at must be ISO 8601")
                if not isinstance(entry.get("note", ""), str):
                    result.profile_errors.append("extensions.curation.review_history.note must be a string")
    merged_into = curation.get("merged_into")
    if review_state == "merged":
        if not isinstance(merged_into, str) or not _bundle_uri(organization_id).match(merged_into):
            result.profile_errors.append("merged candidates must define a valid extensions.curation.merged_into")
    elif merged_into is not None:
        result.profile_errors.append("extensions.curation.merged_into is only allowed for merged candidates")


def _validate_bundle_placement(document: MarkdownDocument, result: ValidationResult) -> None:
    parts = document.path.parts
    try:
        bundles_index = parts.index("bundles")
    except ValueError:
        return
    relative_parts = parts[bundles_index + 1:]
    in_runbooks = len(relative_parts) >= 3 and relative_parts[1] == "runbooks"
    if document.frontmatter.get("type") == "runbook" and not in_runbooks:
        result.profile_errors.append("Runbook must be stored in bundles/<domain>/runbooks/")
    if in_runbooks and document.frontmatter.get("type") != "runbook":
        result.profile_errors.append("only type runbook is allowed in bundles/<domain>/runbooks/")


def _validate_governance(data: Dict[str, Any], result: ValidationResult) -> None:
    if data.get("status") != "active":
        return
    owners = data.get("owners")
    if not isinstance(owners, list) or not owners or any(
        not _is_nonempty_string(owner) for owner in owners
    ):
        result.profile_errors.append("active Bundle owners must be a non-empty string array")
    extensions = data.get("extensions")
    governance = extensions.get("governance") if isinstance(extensions, dict) else None
    if not isinstance(governance, dict):
        result.profile_errors.append("active Bundle must define extensions.governance")
        return
    for field in ("reviewed_at", "review_due_at"):
        if not _is_timestamp(governance.get(field)):
            result.profile_errors.append(f"extensions.governance.{field} must be an ISO 8601 timestamp")
    if not _is_nonempty_string(governance.get("freshness_policy")):
        result.profile_errors.append("extensions.governance.freshness_policy must be non-empty")
    if data.get("type") != "runbook":
        return
    if governance.get("freshness_policy") != "risk_based":
        result.profile_errors.append("active Runbook freshness_policy must be risk_based")
    risk_tier = governance.get("risk_tier")
    if risk_tier not in RUNBOOK_RISK_MAX_DAYS:
        result.profile_errors.append("extensions.governance.risk_tier is invalid")
    if governance.get("source_volatility") not in SOURCE_VOLATILITY:
        result.profile_errors.append("extensions.governance.source_volatility is invalid")
    validity_days = governance.get("validity_days")
    if isinstance(validity_days, bool) or not isinstance(validity_days, int) or validity_days < 1:
        result.profile_errors.append("extensions.governance.validity_days must be a positive integer")
    elif risk_tier in RUNBOOK_RISK_MAX_DAYS and governance.get("source_volatility") in SOURCE_VOLATILITY:
        max_days = math.ceil(
            RUNBOOK_RISK_MAX_DAYS[risk_tier]
            * SOURCE_VOLATILITY_FACTOR[governance["source_volatility"]]
        )
        if validity_days > max_days:
            result.profile_errors.append(
                "extensions.governance.validity_days exceeds risk and volatility maximum"
            )
    triggers = governance.get("change_triggers")
    if not isinstance(triggers, list) or not triggers or any(
        not _is_nonempty_string(item) for item in triggers
    ):
        result.profile_errors.append("extensions.governance.change_triggers must be non-empty")
    elif any(item not in RUNBOOK_CHANGE_TRIGGERS for item in triggers):
        result.profile_errors.append("extensions.governance.change_triggers contains an invalid value")
    elif "user_requested" not in triggers:
        result.profile_errors.append("extensions.governance.change_triggers must include user_requested")
    reviewed_at = _as_datetime(governance.get("reviewed_at"))
    review_due_at = _as_datetime(governance.get("review_due_at"))
    if reviewed_at is not None and review_due_at is not None and isinstance(validity_days, int):
        if review_due_at > reviewed_at + timedelta(days=validity_days):
            result.profile_errors.append("review_due_at exceeds reviewed_at plus validity_days")


def _validate_archive(data: Dict[str, Any], result: ValidationResult) -> None:
    if data.get("status") != "archived":
        return
    extensions = data.get("extensions")
    archive = extensions.get("archive") if isinstance(extensions, dict) else None
    if not isinstance(archive, dict):
        result.profile_errors.append("archived Bundle must define extensions.archive")
        return
    if not _is_timestamp(archive.get("archived_at")):
        result.profile_errors.append("extensions.archive.archived_at must be ISO 8601")
    for field in ("archived_by", "reason", "restore_condition"):
        if not _is_nonempty_string(archive.get(field)):
            result.profile_errors.append(f"extensions.archive.{field} must be non-empty")


def _validate_rulebook(data: Dict[str, Any], result: ValidationResult) -> None:
    extensions = data.get("extensions")
    rulebook = extensions.get("rulebook") if isinstance(extensions, dict) else None
    if rulebook is None:
        return
    if data.get("type") != "guide":
        result.profile_errors.append("extensions.rulebook is only allowed on type guide")
    if not isinstance(rulebook, dict):
        result.profile_errors.append("extensions.rulebook must be an object")
        return
    if not _is_nonempty_string(rulebook.get("rulebook_id")):
        result.profile_errors.append("extensions.rulebook.rulebook_id must be non-empty")
    for field in ("policies", "runbooks", "guides"):
        value = rulebook.get(field, [])
        if not isinstance(value, list) or any(not _is_nonempty_string(item) for item in value):
            result.profile_errors.append(f"extensions.rulebook.{field} must be a string array")


def _validate_inquiry(data: Dict[str, Any], result: ValidationResult) -> None:
    extensions = data.get("extensions")
    inquiry = extensions.get("inquiry") if isinstance(extensions, dict) else None
    if inquiry is None:
        return
    if data.get("type") != "reference":
        result.profile_errors.append("extensions.inquiry is only allowed on type reference")
    if not isinstance(inquiry, dict):
        result.profile_errors.append("extensions.inquiry must be an object")
        return
    if not _is_nonempty_string(inquiry.get("question_id")):
        result.profile_errors.append("extensions.inquiry.question_id must be non-empty")
    if inquiry.get("status") not in INQUIRY_STATUSES:
        result.profile_errors.append("extensions.inquiry.status is invalid")
    if not _is_nonempty_string(inquiry.get("owner")):
        result.profile_errors.append("extensions.inquiry.owner must be non-empty")
    if inquiry.get("status") == "resolved" and not _is_nonempty_string(inquiry.get("resolution")):
        result.profile_errors.append("resolved inquiry must include a resolution")


def _validate_workflow(
    data: Dict[str, Any], result: ValidationResult, organization_id: str
) -> None:
    extensions = data.get("extensions")
    workflow = extensions.get("workflow") if isinstance(extensions, dict) else None
    if data.get("type") == "runbook" and data.get("status") == "active" and not isinstance(workflow, dict):
        result.profile_errors.append("active Runbook must define extensions.workflow")
        return
    if workflow is None:
        return
    if not isinstance(workflow, dict):
        result.profile_errors.append("extensions.workflow must be an object")
        return

    workflow_id = workflow.get("workflow_id")
    if not _is_nonempty_string(workflow_id) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", workflow_id):
        result.profile_errors.append("extensions.workflow.workflow_id must be a lowercase slug")
    version = workflow.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        result.profile_errors.append("extensions.workflow.version must be a positive integer")
    if workflow.get("execution_mode") not in WORKFLOW_EXECUTION_MODES:
        result.profile_errors.append(
            "extensions.workflow.execution_mode must be guided, agent_assisted, or automated"
        )

    required_inputs = workflow.get("required_inputs")
    input_names: List[str] = []
    if not isinstance(required_inputs, list):
        result.profile_errors.append("extensions.workflow.required_inputs must be an array")
    else:
        for item in required_inputs:
            if not isinstance(item, dict) or not _is_nonempty_string(item.get("name")):
                result.profile_errors.append("every required input must have a non-empty name")
                continue
            input_names.append(item["name"])
        if len(input_names) != len(set(input_names)):
            result.profile_errors.append("required input names must be unique")

    steps = workflow.get("steps")
    step_ids: List[str] = []
    step_kinds: Dict[str, str] = {}
    if not isinstance(steps, list) or not steps:
        result.profile_errors.append("extensions.workflow.steps must be a non-empty array")
    else:
        for step in steps:
            if not isinstance(step, dict):
                result.profile_errors.append("every workflow step must be an object")
                continue
            step_id = step.get("id")
            if not _is_nonempty_string(step_id) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", step_id):
                result.profile_errors.append("every workflow step must have a lowercase slug id")
                continue
            step_ids.append(step_id)
            step_kinds[step_id] = str(step.get("kind", ""))
            if not _is_nonempty_string(step.get("title")):
                result.profile_errors.append(f"workflow step '{step_id}' must have a title")
            if step.get("kind") not in WORKFLOW_STEP_KINDS:
                result.profile_errors.append(f"workflow step '{step_id}' has an invalid kind")
        if len(step_ids) != len(set(step_ids)):
            result.profile_errors.append("workflow step ids must be unique")

    approval_gates = workflow.get("approval_gates", [])
    if not isinstance(approval_gates, list):
        result.profile_errors.append("extensions.workflow.approval_gates must be an array")
    else:
        for gate in approval_gates:
            if gate not in step_ids:
                result.profile_errors.append(f"approval gate references an unknown step: {gate}")
            elif step_kinds.get(gate) != "approval":
                result.profile_errors.append(f"approval gate step must use kind approval: {gate}")

    criteria = workflow.get("completion_criteria")
    if not isinstance(criteria, list) or not criteria or any(
        not _is_nonempty_string(item) for item in criteria
    ):
        result.profile_errors.append(
            "extensions.workflow.completion_criteria must be a non-empty string array"
        )
    artifact_profile = workflow.get("artifact_profile")
    if artifact_profile is not None:
        if not isinstance(artifact_profile, dict):
            result.profile_errors.append("extensions.workflow.artifact_profile must be an object")
        else:
            if artifact_profile.get("type") not in ARTIFACT_PROFILE_TYPES:
                result.profile_errors.append("extensions.workflow.artifact_profile.type is invalid")
            sections = artifact_profile.get("required_sections")
            if not isinstance(sections, list) or not sections or any(
                not _is_nonempty_string(item) for item in sections
            ):
                result.profile_errors.append(
                    "extensions.workflow.artifact_profile.required_sections must be non-empty"
                )
    for field in ("applies_to", "excludes"):
        value = workflow.get(field, [])
        if not isinstance(value, list) or any(not _is_nonempty_string(item) for item in value):
            result.profile_errors.append(f"extensions.workflow.{field} must be a string array")
    examples = workflow.get("examples", {})
    if not isinstance(examples, dict):
        result.profile_errors.append("extensions.workflow.examples must be an object")
    else:
        for field in ("successful", "failed"):
            value = examples.get(field, [])
            if not isinstance(value, list) or any(
                not _evidence_uri(organization_id).match(str(item)) for item in value
            ):
                result.profile_errors.append(
                    f"extensions.workflow.examples.{field} must be an Evidence URI array"
                )
    learning = workflow.get("learning")
    if data.get("type") == "runbook" and data.get("status") == "active" and not isinstance(learning, dict):
        result.profile_errors.append("active Runbook must define extensions.workflow.learning")
    elif learning is not None:
        if not isinstance(learning, dict):
            result.profile_errors.append("extensions.workflow.learning must be an object")
        else:
            if learning.get("maturity") not in RUNBOOK_MATURITY:
                result.profile_errors.append("extensions.workflow.learning.maturity is invalid")
            threshold = learning.get("min_outcomes_for_review")
            if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
                result.profile_errors.append(
                    "extensions.workflow.learning.min_outcomes_for_review must be positive"
                )
            for field in ("review_on_failure", "review_on_feedback"):
                if not isinstance(learning.get(field), bool):
                    result.profile_errors.append(
                        f"extensions.workflow.learning.{field} must be boolean"
                    )


def _validate_evidence(
    document: MarkdownDocument, result: ValidationResult, organization_id: str
) -> None:
    data = document.frontmatter
    required = (
        "id", "title", "source_uuid", "provider", "source_ref", "captured_at", "status",
        "checksum", "original_file_git_tracked",
    )
    if data.get("type") != "evidence":
        result.profile_errors.append("Evidence Record type must be evidence")
    for field in required:
        if field not in data:
            result.profile_errors.append(f"missing required Evidence field: {field}")
    if "id" in data and not _evidence_uri(organization_id).match(str(data["id"])):
        result.profile_errors.append(
            f"id must be an Evidence URI for organization '{organization_id}'"
        )
    if "source_uuid" in data and not _is_uuid(data["source_uuid"]):
        result.profile_errors.append("source_uuid must be a UUID")
    if "provider" in data and not _is_nonempty_string(data["provider"]):
        result.profile_errors.append("provider must be a non-empty string")
    if "captured_at" in data and not _is_timestamp(data["captured_at"]):
        result.profile_errors.append("captured_at must be an ISO 8601 timestamp")
    if "status" in data and data["status"] not in EVIDENCE_STATUSES:
        result.profile_errors.append("Evidence status is invalid")
    if "checksum" in data and not re.match(r"^sha256:[0-9a-f]{64}$", str(data["checksum"])):
        result.profile_errors.append("checksum must be sha256:<64 lowercase hexadecimal characters>")
    if "original_file_git_tracked" in data and not isinstance(data["original_file_git_tracked"], bool):
        result.profile_errors.append("original_file_git_tracked must be boolean")
    source_ref = data.get("source_ref")
    if not isinstance(source_ref, dict) or not _is_nonempty_string(source_ref.get("provider")):
        result.profile_errors.append("source_ref.provider is required")
    elif source_ref["provider"] != data.get("provider"):
        result.profile_errors.append("source_ref.provider must equal provider")
    if not isinstance(source_ref, dict) or source_ref.get("captured_from") not in {"api", "webhook", "manual", "upload", "sync"}:
        result.profile_errors.append("source_ref.captured_from is invalid")
    extensions = data.get("extensions")
    availability = extensions.get("availability") if isinstance(extensions, dict) else None
    if availability not in EVIDENCE_AVAILABILITY:
        result.profile_errors.append("extensions.availability is invalid")
    content_mode = evidence_content_mode(document)
    if content_mode == "external_file" and not _is_nonempty_string(data.get("original_file")):
        result.profile_errors.append("external-file Evidence must define original_file")
    if content_mode == "embedded" and "original_file" in data:
        result.profile_errors.append("embedded Evidence must not define original_file")
    original_error = verify_evidence_original(document)
    if original_error:
        result.profile_errors.append(original_error)
    capture_context = extensions.get("capture_context") if isinstance(extensions, dict) else None
    if not isinstance(capture_context, dict):
        result.profile_errors.append("Evidence must define extensions.capture_context")
    else:
        if not _is_nonempty_string(capture_context.get("why_collected")):
            result.profile_errors.append("extensions.capture_context.why_collected must be non-empty")
        intended_use = capture_context.get("intended_use")
        if not isinstance(intended_use, list) or not intended_use or any(
            not _is_nonempty_string(item) for item in intended_use
        ):
            result.profile_errors.append(
                "extensions.capture_context.intended_use must be a non-empty string array"
            )
        reuse_value = capture_context.get("reuse_value")
        if reuse_value is not None and reuse_value not in EVIDENCE_REUSE_VALUE:
            result.profile_errors.append("extensions.capture_context.reuse_value is invalid")
        retention_class = capture_context.get("retention_class")
        if retention_class is not None and retention_class not in EVIDENCE_RETENTION_CLASS:
            result.profile_errors.append("extensions.capture_context.retention_class is invalid")
        sensitivity_review = capture_context.get("sensitivity_review")
        if sensitivity_review is not None and sensitivity_review not in {"completed", "required", "not_applicable"}:
            result.profile_errors.append("extensions.capture_context.sensitivity_review is invalid")
    result.profile_errors.extend(pii_scan_receipt_errors(data))
    if isinstance(extensions, dict):
        attempt = extensions.get("curation_attempt")
        if attempt is not None and not isinstance(attempt, dict):
            result.profile_errors.append("extensions.curation_attempt must be an object")
        elif isinstance(attempt, dict):
            _validate_curation_receipt(
                attempt.get("receipt"), result,
                expected_checksum=data.get("checksum"), prefix="extensions.curation_attempt.receipt",
            )
    _warn_unscoped_extensions(data, result)


def _validate_curation_receipt(
    receipt: object, result: ValidationResult, *, expected_checksum: object, prefix: str,
) -> None:
    """Validate optional structured curation provenance without exposing adapter output."""
    if receipt is None:
        return
    if not isinstance(receipt, dict):
        result.profile_errors.append(f"{prefix} must be an object")
        return
    for field in ("evidence_checksum", "provider", "model", "profile_version", "prompt_template_version", "result_schema_version", "started_at", "status"):
        if not _is_nonempty_string(receipt.get(field)):
            result.profile_errors.append(f"{prefix}.{field} must be non-empty")
    if receipt.get("evidence_checksum") != expected_checksum:
        result.profile_errors.append(f"{prefix}.evidence_checksum must match the current Evidence checksum")
    for field in ("started_at", "completed_at"):
        if field in receipt and not _is_timestamp(receipt[field]):
            result.profile_errors.append(f"{prefix}.{field} must be ISO 8601")


def _warn_unscoped_extensions(data: Dict[str, Any], result: ValidationResult) -> None:
    custom_fields = {
        "curated_by", "confidence", "decision_status", "review_state", "knowledge_revision",
        "visibility", "pii_masked", "review_requested", "review_reason", "review_requested_by",
        "review_requested_at",
    }
    for field in sorted(custom_fields.intersection(data)):
        result.warnings.append(f"organization metadata '{field}' should be under extensions")


def managed_markdown_files(knowledge_root: Path) -> Iterable[Path]:
    """Yield only Markdown files governed by the documented OKF management rule."""
    for section in ("bundles", "evidence"):
        root = knowledge_root / section
        if root.exists():
            yield from sorted(root.rglob("*.md"))
    os_root = knowledge_root.parent / ".circled-wiki"
    for section in ("templates", "schemas", "policies"):
        root = os_root / section
        if root.exists():
            yield from sorted(root.rglob("*.md"))


def validate_repository(knowledge_root: Path) -> List[ValidationResult]:
    """Validate every managed document and then check Bundle/Evidence references."""
    results = [validate_document(path, knowledge_root) for path in managed_markdown_files(knowledge_root)]
    by_path = {result.path: result for result in results}
    evidence_ids: Set[str] = set()
    bundle_ids: Set[str] = set()
    evidence_by_id: Dict[str, MarkdownDocument] = {}
    bundle_by_id: Dict[str, MarkdownDocument] = {}
    documents: Dict[Path, MarkdownDocument] = {}
    for path in by_path:
        if path.name in RESERVED_FILENAMES:
            continue
        try:
            document = parse_markdown(path)
        except FrontmatterError:
            continue
        documents[path] = document
        if _path_kind(path, knowledge_root) == "evidence":
            document_id = str(document.frontmatter.get("id", ""))
            evidence_ids.add(document_id)
            evidence_by_id[document_id] = document
        if _path_kind(path, knowledge_root) == "bundle":
            document_id = str(document.frontmatter.get("id", ""))
            bundle_ids.add(document_id)
            bundle_by_id[document_id] = document
    for path, document in documents.items():
        result = by_path[path]
        kind = _path_kind(path, knowledge_root)
        if kind == "bundle":
            is_active = document.frontmatter.get("status") == "active"
            evidence_refs = document.frontmatter.get("evidence", [])
            if not isinstance(evidence_refs, list):
                continue
            for evidence_id in evidence_refs:
                if not isinstance(evidence_id, str):
                    # _validate_bundle already records the shape failure; never crash validation.
                    continue
                if evidence_id not in evidence_ids:
                    message = f"referenced Evidence Record not found: {evidence_id}"
                    (result.profile_errors if is_active else result.warnings).append(message)
                elif document.frontmatter.get("id") not in evidence_by_id[evidence_id].frontmatter.get("curated_into", []):
                    message = f"Evidence Record does not reference this Bundle: {evidence_id}"
                    (result.profile_errors if is_active else result.warnings).append(message)
        elif kind == "evidence":
            bundle_refs = document.frontmatter.get("curated_into", []) or []
            if not isinstance(bundle_refs, list):
                continue
            for bundle_id in bundle_refs:
                if not isinstance(bundle_id, str):
                    continue
                if bundle_id not in bundle_ids:
                    result.warnings.append(f"referenced Bundle not found: {bundle_id}")
                elif document.frontmatter.get("id") not in bundle_by_id[bundle_id].frontmatter.get("evidence", []):
                    message = f"Bundle does not reference this Evidence Record: {bundle_id}"
                    if bundle_by_id[bundle_id].frontmatter.get("status") == "active":
                        result.profile_errors.append(message)
                    else:
                        result.warnings.append(message)
    return results
