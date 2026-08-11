"""Human-friendly CLI without domain logic."""

import argparse
import json
from pathlib import Path
import sys
import unicodedata

from circled_wiki.config.paths import project_root
from circled_wiki.config.settings import load_settings
from circled_wiki.config.data_protection import load_data_protection_policy
from circled_wiki.config.curation_taxonomy import load_curation_taxonomy
from circled_wiki.core.ingest import CaptureIdempotencyConflict
from circled_wiki.core.repository import apply_bundle_revision, create_bundle, find_document_by_id
from circled_wiki.core.evidence import evidence_original_path
from circled_wiki.core.search import search_knowledge
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.bundle_types import DIRECT_DRAFT_TYPES
from circled_wiki.core.publisher import PublishError
from circled_wiki.core.validator import validate_repository
from circled_wiki.core.bootstrap import (
    bootstrap_circled_wiki,
    initialize_operational_workspace,
)
from circled_wiki.core.observations import (
    ISSUE_AREAS, ISSUE_CLASSIFICATIONS, ISSUE_REPORTERS, ISSUE_SEVERITIES, ISSUE_STATUSES,
    migrate_legacy_system_issues, record_system_issue, update_system_issue_status,
)
from circled_wiki.core.open_questions import (
    claim_slack_decision_delivery,
    list_open_questions,
    queue_slack_decision,
    reconcile_open_question_deliveries,
    record_open_question,
    resolve_open_question,
)
from circled_wiki.core.notification_store import (
    acknowledge_user_notification,
    archive_user_notification,
    list_user_notifications,
)


class StructuredArgumentParser(argparse.ArgumentParser):
    """Route usage errors through the CLI's stable JSON error contract."""

    def error(self, message: str) -> None:
        raise ValueError(message)


def _bootstrap_configuration(args: argparse.Namespace) -> dict[str, object]:
    """Prompt for first-install identity, while keeping automation explicit."""
    target = Path(args.target).expanduser()
    if (target / ".circled-wiki" / "config.yaml").is_file():
        return {
            "organization_id": args.organization_id or "example-org",
            "organization_name": args.organization_name or "Example Organization",
            "operator_agent": args.operator_agent or "hermes",
            "graphify_enabled": args.graphify == "enabled",
        }
    supplied = (args.organization_id, args.organization_name, args.operator_agent, args.graphify)
    if not sys.stdin.isatty() and any(value is None for value in supplied):
        raise ValueError(
            "first installation requires --organization-id, --organization-name, "
            "--operator-agent, and --graphify enabled|disabled in non-interactive mode"
        )

    def ask(label: str, current: object, default: str) -> str:
        if current is not None:
            return str(current)
        answer = input(f"{label} [{default}]: ").strip()
        return answer or default

    organization_id = ask("Organization ID", args.organization_id, "example-org")
    organization_name = ask("Organization name", args.organization_name, "Example Organization")
    operator_agent = ask("Operator agent", args.operator_agent, "hermes")
    graphify = ask("Enable separately installed Graphify? (yes/no)", args.graphify, "no")
    normalized = graphify.casefold()
    if normalized not in {"enabled", "disabled", "yes", "no", "y", "n"}:
        raise ValueError("Graphify answer must be enabled/disabled or yes/no")
    return {
        "organization_id": organization_id,
        "organization_name": organization_name,
        "operator_agent": operator_agent,
        "graphify_enabled": normalized in {"enabled", "yes", "y"},
    }


def main() -> int:
    parser = StructuredArgumentParser(prog="circled-wiki")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("validate-configuration")
    subparsers.add_parser("get-collection-handoff")
    evidence_links = subparsers.add_parser("backfill-evidence-links")
    evidence_links.add_argument("--apply", action="store_true", help="write only validated Evidence file-link repairs")
    migrate_ids = subparsers.add_parser("migrate-document-ids")
    migrate_ids.add_argument("--apply", action="store_true", help="write the validated legacy-ID migration")
    subparsers.add_parser("inspect-legacy-evidence-backlinks")
    system_issue = subparsers.add_parser("record-system-issue")
    system_issue.add_argument("--title", required=True)
    system_issue.add_argument("--summary", required=True)
    system_issue.add_argument("--reported-by", required=True)
    system_issue.add_argument("--reported-from", choices=ISSUE_REPORTERS, default="operator")
    system_issue.add_argument("--area", choices=ISSUE_AREAS, default="other")
    system_issue.add_argument("--severity", choices=ISSUE_SEVERITIES, default="medium")
    system_issue.add_argument("--expected", default="Not recorded.")
    system_issue.add_argument("--actual", default="Not recorded.")
    system_issue.add_argument("--reproduction", default="Not recorded.")
    system_issue.add_argument("--improvement-hint", default="Not recorded.")
    system_issue.add_argument("--impact", default="Not recorded.")
    system_issue.add_argument("--hypothesis", default="Not recorded.")
    system_issue.add_argument("--release-observed")
    system_issue.add_argument("--related-path", action="append", default=[])
    update_issue = subparsers.add_parser("update-system-issue")
    update_issue.add_argument("--issue", required=True)
    update_issue.add_argument("--status", required=True, choices=ISSUE_STATUSES)
    update_issue.add_argument("--actor", required=True)
    update_issue.add_argument("--note", required=True)
    update_issue.add_argument("--fixed-release")
    update_issue.add_argument("--verification")
    update_issue.add_argument("--deployed-release")
    update_issue.add_argument("--deployment-receipt")
    update_issue.add_argument("--verification-receipt")
    update_issue.add_argument("--classification", choices=ISSUE_CLASSIFICATIONS)
    update_issue.add_argument("--next-action")
    migrate_issues = subparsers.add_parser("migrate-legacy-system-issues")
    migrate_issues.add_argument("--issue", action="append", default=[])
    migrate_issues.add_argument("--apply", action="store_true")
    open_question = subparsers.add_parser("record-open-question")
    open_question.add_argument("--question", required=True)
    open_question.add_argument("--asked-of", required=True)
    open_question.add_argument("--context", required=True)
    open_question.add_argument("--related-bundle")
    open_question.add_argument("--related-evidence")
    list_questions = subparsers.add_parser("list-open-questions")
    list_questions.add_argument("--asked-of")
    resolve_question = subparsers.add_parser("resolve-open-question")
    resolve_question.add_argument("--question", required=True)
    resolve_question.add_argument("--answer", required=True)
    resolve_question.add_argument("--actor", required=True)
    slack_question = subparsers.add_parser("queue-slack-decision")
    slack_question.add_argument("--question", required=True)
    slack_question.add_argument("--recipient", required=True)
    claim_slack = subparsers.add_parser("claim-slack-decision")
    claim_slack.add_argument("--delivery", required=True)
    subparsers.add_parser("reconcile-open-questions")
    notifications = subparsers.add_parser("list-user-notifications")
    notifications.add_argument("--include-acknowledged", action="store_true")
    acknowledge_notification = subparsers.add_parser("acknowledge-user-notification")
    acknowledge_notification.add_argument("--notification", required=True)
    acknowledge_notification.add_argument("--actor", required=True)
    archive_notification = subparsers.add_parser("archive-user-notification")
    archive_notification.add_argument("--notification", required=True)
    archive_notification.add_argument("--reason", required=True)
    bootstrap = subparsers.add_parser("bootstrap-circled-wiki")
    bootstrap.add_argument("--target", required=True, help="Knowledge root to install or safely upgrade")
    bootstrap.add_argument("--apply", action="store_true", help="Apply the planned changes")
    bootstrap.add_argument("--organization-id")
    bootstrap.add_argument("--organization-name")
    bootstrap.add_argument("--operator-agent")
    bootstrap.add_argument("--graphify", choices=("enabled", "disabled"))
    bootstrap.add_argument("--runtime-python", help="Python executable used by the installed Runtime")
    initialize_workspace = subparsers.add_parser("initialize-operational-workspace")
    initialize_workspace.add_argument("--apply", action="store_true")
    inbox_pii = subparsers.add_parser("record-inbox-pii-scan")
    inbox_pii.add_argument("--intake", required=True)
    inbox_pii.add_argument("--scanner", required=True)
    inbox_pii.add_argument("--scanner-version", required=True)
    inbox_pii.add_argument("--result", choices=("passed", "masked", "needs_review"), required=True)
    inbox_pii.add_argument("--reviewed-by", required=True)
    inbox_pii.add_argument("--receipt", required=True)
    inbox_pii.add_argument("--scanned-at")
    capture = subparsers.add_parser("capture-conversation")
    capture.add_argument("--provider", required=True)
    capture.add_argument("--file", required=True, help="UTF-8 Markdown transcript to capture")
    capture.add_argument("--title", required=True)
    capture.add_argument("--why-collected", required=True)
    capture.add_argument("--intended-use", action="append", required=True)
    capture.add_argument("--idempotency-key", required=True)
    capture.add_argument("--thread-ref")
    capture.add_argument("--turn-from", type=int)
    capture.add_argument("--turn-to", type=int)
    capture.add_argument("--artifacts", default="[]", help="JSON array of artifact metadata")
    capture_document = subparsers.add_parser("capture-document")
    capture_document.add_argument("--provider", required=True)
    capture_document.add_argument("--file", required=True, help="UTF-8 source document")
    capture_document.add_argument("--title", required=True)
    capture_document.add_argument("--why-collected", required=True)
    capture_document.add_argument("--intended-use", action="append", required=True)
    capture_document.add_argument("--idempotency-key", required=True)
    capture_document.add_argument("--source-url")
    capture_document.add_argument("--source-locator")
    capture_document.add_argument(
        "--captured-from", choices=("api", "webhook", "manual", "upload", "sync"), default="sync"
    )
    capture_file = subparsers.add_parser("capture-file")
    capture_file.add_argument("--provider", required=True)
    capture_file.add_argument("--file", help="Binary or text source file to preserve")
    capture_file.add_argument(
        "--inbox-file",
        help=(
            "Path relative to knowledge/inbox, exactly as reported by "
            "inspect-inbox (for example: 신규 입사자 요청서.txt); "
            "Unicode-normalized matching is supported"
        ),
    )
    capture_file.add_argument("--title", required=True)
    capture_file.add_argument("--why-collected", required=True)
    capture_file.add_argument("--intended-use", action="append", required=True)
    capture_file.add_argument("--idempotency-key", required=True)
    capture_file.add_argument("--source-url")
    capture_file.add_argument("--source-locator")
    capture_file.add_argument(
        "--captured-from", choices=("api", "webhook", "manual", "upload", "sync"), default="upload"
    )
    search = subparsers.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--type")
    read = subparsers.add_parser("read-bundle")
    read.add_argument("--bundle", required=True)
    original = subparsers.add_parser("get-evidence-original")
    original.add_argument("--evidence", required=True)
    proposal = subparsers.add_parser("propose-update")
    proposal.add_argument("--evidence", required=True)
    pending = subparsers.add_parser("propose-pending")
    pending.add_argument("--limit", type=int, default=100)
    inspect_inbox = subparsers.add_parser("inspect-inbox")
    inspect_inbox.add_argument("--limit", type=int, default=100)
    subparsers.add_parser("list-inbox-review-queue")
    quarantine_inbox = subparsers.add_parser("quarantine-inbox-item")
    quarantine_inbox.add_argument("--intake", required=True)
    quarantine_inbox.add_argument("--classifier", required=True)
    quarantine_inbox.add_argument("--rule-version", required=True)
    quarantine_inbox.add_argument("--reason", required=True)
    subparsers.add_parser("list-inbox-disposals")
    decide_disposal = subparsers.add_parser("decide-inbox-disposal")
    decide_disposal.add_argument("--intake", required=True)
    decide_disposal.add_argument("--decision", required=True, choices=("recover", "dispose"))
    decide_disposal.add_argument("--actor", required=True)
    accept_inbox = subparsers.add_parser("accept-inbox")
    accept_inbox.add_argument("--intake", required=True)
    accept_inbox.add_argument("--actor", required=True)
    accept_ready_inbox = subparsers.add_parser("accept-ready-inbox")
    accept_ready_inbox.add_argument("--actor", required=True)
    accept_ready_inbox.add_argument("--limit", type=int, default=100)
    reconcile_inbox = subparsers.add_parser("reconcile-inbox")
    reconcile_inbox.add_argument("--actor", required=True)
    reconcile_inbox.add_argument("--limit", type=int, default=100)
    reconcile_inbox_curation = subparsers.add_parser("reconcile-inbox-then-curation")
    reconcile_inbox_curation.add_argument("--actor", required=True)
    reconcile_inbox_curation.add_argument("--limit", type=int, default=100)
    reconcile_curation = subparsers.add_parser("reconcile-curation")
    reconcile_curation.add_argument("--limit", type=int, default=100)
    review_protection = subparsers.add_parser("review-data-protection")
    review_protection.add_argument("--intake", required=True)
    review_protection.add_argument("--actor", required=True)
    review_protection.add_argument("--context", required=True)
    review_protection.add_argument("--checks", required=True, help="JSON array of four data-protection checks")
    review_protection.add_argument("--rationale", required=True)
    review_protection.add_argument("--findings", default="[]", help="JSON array of Agent-identified restricted text findings")
    request_sensitivity = subparsers.add_parser("request-inbox-sensitivity-decision")
    request_sensitivity.add_argument("--intake", required=True)
    request_sensitivity.add_argument("--actor", required=True)
    request_sensitivity.add_argument("--question", required=True)
    request_sensitivity.add_argument("--missing-procedure", required=True)
    request_sensitivity.add_argument("--safe-next-action", required=True)
    request_sensitivity.add_argument("--facts", required=True, help="JSON array of observed facts")
    request_sensitivity.add_argument("--hypotheses", required=True, help="JSON array of hypotheses")
    ingest_accepted = subparsers.add_parser("ingest-accepted")
    ingest_accepted.add_argument("--limit", type=int, default=100)
    publish = subparsers.add_parser("publish-changes")
    publish.add_argument("--message", required=True)
    push = subparsers.add_parser("push-changes")
    push.add_argument("--commit", required=True)
    subparsers.add_parser("resume-pending-push")
    workflow = subparsers.add_parser("find-workflow")
    workflow.add_argument("--request", required=True)
    task = subparsers.add_parser("prepare-task")
    task.add_argument("--workflow", required=True)
    task.add_argument("--request", required=True)
    task.add_argument("--inputs", default="{}", help="JSON object with known workflow inputs")
    refresh = subparsers.add_parser("prepare-runbook-refresh")
    refresh.add_argument("--workflow", required=True)
    refresh.add_argument("--request", required=True)
    refresh.add_argument("--requested-by", required=True)
    refresh.add_argument(
        "--reason",
        default="user_requested",
        choices=("expired", "user_requested", "user_reference", "owner_requested", "source_change", "outcome_signal", "security_or_compliance"),
    )
    reference = subparsers.add_parser("submit-runbook-reference")
    reference.add_argument("--workflow", required=True)
    reference.add_argument("--evidence", required=True)
    reference.add_argument("--submitted-by", required=True)
    reference.add_argument("--note", required=True)
    assessment = subparsers.add_parser("record-reference-assessment")
    assessment.add_argument("--task", required=True)
    assessment.add_argument("--evidence", required=True)
    assessment.add_argument("--authority", required=True, choices=("primary", "official_secondary", "internal_experience", "informal"))
    assessment.add_argument("--recency", required=True, choices=("newer", "same_period", "older", "unknown"))
    assessment.add_argument("--applicability", required=True, choices=("full", "partial", "out_of_scope"))
    assessment.add_argument("--corroboration", required=True, choices=("corroborated", "single_source", "conflicting"))
    assessment.add_argument("--disposition", required=True, choices=("accept", "partial_accept", "reject", "needs_more_evidence"))
    assessment.add_argument("--rationale", required=True)
    assessment.add_argument("--assessed-by", required=True)
    assessment.add_argument("--verified-by", required=True)
    assessment.add_argument("--conflict", action="append", default=[])
    confirmation = subparsers.add_parser("confirm-runbook-revision")
    confirmation.add_argument("--task", required=True)
    confirmation.add_argument("--revision-ref", required=True)
    subparsers.add_parser("audit-knowledge")
    inventory = subparsers.add_parser("list-knowledge-inventory")
    inventory.add_argument("--domain")
    inventory.add_argument("--type")
    inventory.add_argument("--status")
    inventory.add_argument("--owner")
    inventory.add_argument("--freshness-state", choices=("valid", "expired", "unknown"))
    claims = subparsers.add_parser("validate-claim-support")
    claims.add_argument("--claims", required=True, help="JSON array of claim support records")
    effectiveness = subparsers.add_parser("measure-runbook-effectiveness")
    effectiveness.add_argument("--workflow", required=True)
    get_task = subparsers.add_parser("get-task")
    get_task.add_argument("--task", required=True)
    update_inputs = subparsers.add_parser("update-task-inputs")
    update_inputs.add_argument("--task", required=True)
    update_inputs.add_argument("--inputs", required=True, help="JSON object with supplied inputs")
    step = subparsers.add_parser("record-task-step")
    step.add_argument("--task", required=True)
    step.add_argument("--step", required=True)
    step.add_argument("--status", required=True, choices=("completed", "failed", "needs_review", "approved", "rejected"))
    step.add_argument("--result", required=True)
    step.add_argument("--actor", required=True)
    refresh_decision = subparsers.add_parser("record-refresh-decision")
    refresh_decision.add_argument("--task", required=True)
    refresh_decision.add_argument(
        "--decision",
        required=True,
        choices=("update_required", "no_change", "insufficient_evidence"),
    )
    refresh_decision.add_argument("--rationale", required=True)
    refresh_decision.add_argument("--evidence", action="append", required=True)
    refresh_decision.add_argument("--actor", required=True)
    outcome = subparsers.add_parser("record-outcome")
    outcome.add_argument("--task", required=True)
    outcome.add_argument("--status", required=True, choices=("completed", "failed", "needs_review"))
    outcome.add_argument("--summary", required=True)
    outcome.add_argument("--feedback", default="")
    outcome.add_argument("--learning", action="append", default=[])
    outcome.add_argument(
        "--artifacts", default="[]",
        help="JSON array; each item requires name, availability, and uri when available or metadata_only",
    )
    outcome.add_argument(
        "--decisions", default="[]",
        help="JSON array; each item requires decision, decided_by, rationale, and non-empty evidence_ids",
    )
    outcome.add_argument(
        "--action-items", default="[]",
        help="JSON array; each item requires title, owner, and completion_criteria; due_at is optional ISO 8601",
    )
    outcome.add_argument(
        "--open-questions", default="[]",
        help="JSON array; each item requires question and owner",
    )
    bundle = subparsers.add_parser("create-bundle")
    bundle.add_argument("--domain", required=True); bundle.add_argument("--slug", required=True)
    bundle.add_argument("--title", required=True); bundle.add_argument(
        "--type", required=True,
        help="Direct Draft types: policy, guide, decision, spec, reference, report. manual and runbook require curation review.",
    )
    bundle.add_argument("--summary", required=True); bundle.add_argument("--evidence", required=True)
    bundle.add_argument("--tag", action="append", required=True)
    bundle.add_argument("--body-file", help="UTF-8 Markdown body for a curator-authored draft")
    bundle.add_argument("--curated-by", default="manual")
    subparsers.add_parser("list-curation-candidates")
    list_reviews = subparsers.add_parser("list-curation-reviews")
    list_reviews.add_argument("--include-resolved", action="store_true")
    list_queue = subparsers.add_parser("list-curation-queue")
    list_queue.add_argument("--include-resolved", action="store_true")
    subparsers.add_parser("refresh-curation-queue")
    decide_review = subparsers.add_parser("decide-curation-review")
    decide_review.add_argument("--review", required=True)
    decide_review.add_argument("--action", required=True, choices=("approve", "no_bundle", "needs_changes", "needs_review"))
    decide_review.add_argument("--actor", required=True)
    decide_review.add_argument("--note", default="")
    apply_review_update = subparsers.add_parser("apply-approved-curation-update")
    apply_review_update.add_argument("--review", required=True)
    apply_review_update.add_argument("--actor", required=True)
    create_review = subparsers.add_parser("create-curation-review")
    create_review.add_argument("--evidence", required=True)
    create_review_output = create_review.add_mutually_exclusive_group(required=True)
    create_review_output.add_argument("--output", help="Validated inline CurationOutput JSON")
    create_review_output.add_argument("--output-file", help="UTF-8 file containing validated CurationOutput JSON")
    create_review.add_argument("--generated-by", required=True)
    create_review.add_argument("--curation-receipt", required=True)
    create_review.add_argument(
        "--user-review-request",
        help="Runtime-captured ID for a user's explicit Review request; required for types other than manual/runbook.",
    )
    automatic_update = subparsers.add_parser("apply-automatic-curation-update")
    automatic_update.add_argument("--evidence", required=True)
    automatic_update.add_argument("--existing-bundle", required=True)
    automatic_update.add_argument("--update-mode", choices=("append",), default="append")
    automatic_update.add_argument("--body-file", required=True, help="UTF-8 Markdown delta to append")
    automatic_update.add_argument("--actor", required=True)
    automatic_update.add_argument("--curation-receipt", required=True)
    automatic_update.add_argument("--security-receipt", required=True)
    subparsers.add_parser(
        "verify-curation-commit",
        help="Verify staged Curation Queue deletions include matching Archive additions",
    )
    curation_batch = subparsers.add_parser("run-configured-curation-batch")
    curation_batch.add_argument("--limit", type=int, default=100)
    review_candidate = subparsers.add_parser("review-curation-candidate")
    review_candidate.add_argument("--bundle", required=True)
    review_candidate.add_argument("--action", required=True, choices=("needs_changes", "approve", "reject", "merge"))
    review_candidate.add_argument("--actor", required=True)
    review_candidate.add_argument("--note", default="")
    review_candidate.add_argument("--merged-into")
    promote_candidate = subparsers.add_parser("promote-curation-candidate")
    promote_candidate.add_argument("--bundle", required=True)
    promote_candidate.add_argument("--actor", required=True)
    promote_candidate.add_argument("--security-receipt", required=True)
    promote_candidate.add_argument(
        "--automated", action="store_true",
        help="Use the RB-CUR-006 automatic Gate for policy, guide, decision, spec, reference, or report.",
    )
    revise_bundle = subparsers.add_parser("apply-bundle-revision")
    revise_bundle.add_argument("--bundle", required=True)
    revise_bundle.add_argument("--expected-revision", required=True, type=int)
    revise_bundle.add_argument("--frontmatter-file", required=True, help="UTF-8 JSON frontmatter proposal")
    revise_bundle.add_argument("--body-file", required=True, help="UTF-8 Markdown body")
    revise_bundle.add_argument("--actor", required=True)
    reclassify_proposal = subparsers.add_parser("propose-bundle-reclassification")
    reclassify_proposal.add_argument("--bundle", required=True); reclassify_proposal.add_argument("--domain", required=True); reclassify_proposal.add_argument("--type", required=True)
    reclassify = subparsers.add_parser("apply-bundle-reclassification")
    reclassify.add_argument("--bundle", required=True); reclassify.add_argument("--expected-revision", required=True, type=int)
    reclassify.add_argument("--domain", required=True); reclassify.add_argument("--type", required=True); reclassify.add_argument("--actor", required=True); reclassify.add_argument("--rationale", required=True); reclassify.add_argument("--approval-notification", required=True)
    args = parser.parse_args()
    if args.command == "bootstrap-circled-wiki":
        configuration = _bootstrap_configuration(args)
        report = bootstrap_circled_wiki(
            Path(args.target), project_root(), apply=args.apply,
            runtime_python=args.runtime_python,
            **configuration,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    if args.command == "initialize-operational-workspace":
        report = initialize_operational_workspace(project_root(), apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    project = project_root()
    root = project / "knowledge"
    service = KnowledgeService(root)
    if args.command == "record-system-issue":
        result = record_system_issue(
            root.parent,
            title=args.title,
            summary=args.summary,
            reported_by=args.reported_by,
            reported_from=args.reported_from,
            area=args.area,
            severity=args.severity,
            expected=args.expected,
            actual=args.actual,
            reproduction=args.reproduction,
            improvement_hint=args.improvement_hint,
            impact=args.impact,
            hypothesis=args.hypothesis,
            release_observed=args.release_observed,
            related_paths=args.related_path,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "update-system-issue":
        result = update_system_issue_status(
            root.parent, issue_ref=args.issue, status=args.status, actor=args.actor,
            note=args.note, fixed_release=args.fixed_release, verification=args.verification,
            deployed_release=args.deployed_release,
            deployment_receipt=args.deployment_receipt,
            verification_receipt=args.verification_receipt,
            classification=args.classification,
            next_action=args.next_action,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "migrate-legacy-system-issues":
        result = migrate_legacy_system_issues(
            root.parent,
            issue_refs=args.issue or None,
            apply=args.apply,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "record-open-question":
        result = record_open_question(
            root.parent / ".runtime", question=args.question, asked_of=args.asked_of,
            context=args.context, related_bundle=args.related_bundle,
            related_evidence=args.related_evidence,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "list-open-questions":
        print(json.dumps(list_open_questions(root.parent / ".runtime", asked_of=args.asked_of), ensure_ascii=False, indent=2)); return 0
    if args.command == "resolve-open-question":
        result = resolve_open_question(
            root.parent / ".runtime", question_id=args.question,
            answer=args.answer, actor=args.actor,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "queue-slack-decision":
        result = queue_slack_decision(
            root.parent / ".runtime", question_id=args.question, recipient=args.recipient,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "claim-slack-decision":
        result = claim_slack_decision_delivery(
            root.parent / ".runtime", delivery_id=args.delivery,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "reconcile-open-questions":
        result = reconcile_open_question_deliveries(root.parent / ".runtime")
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "list-user-notifications":
        print(json.dumps(
            list_user_notifications(root.parent / "workspace", include_acknowledged=args.include_acknowledged),
            ensure_ascii=False, indent=2,
        )); return 0
    if args.command == "acknowledge-user-notification":
        result = acknowledge_user_notification(
            root.parent / "workspace", notification_id=args.notification, actor=args.actor,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "archive-user-notification":
        result = archive_user_notification(
            root.parent / "workspace", notification_id=args.notification, reason=args.reason,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "validate":
        results = validate_repository(root); invalid = [r for r in results if not r.is_valid]
        for result in results:
            for error in result.okf_errors + result.profile_errors: print(f"ERROR {result.path}: {error}")
            for warning in result.warnings: print(f"WARN {result.path}: {warning}")
        print(f"validated={len(results)} invalid={len(invalid)}")
        return 1 if invalid else 0
    if args.command == "validate-configuration":
        settings = load_settings(project)
        policy = load_data_protection_policy(project)
        taxonomy = load_curation_taxonomy(project)
        print(json.dumps({
            "valid": True,
            "schema_version": 1,
            "organization_id": settings.organization_id,
            "data_protection_policy_ref": policy.policy_ref,
            "curation_taxonomy_configured": taxonomy.configured,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.command == "get-collection-handoff":
        print(json.dumps(service.get_collection_handoff(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "backfill-evidence-links":
        print(json.dumps(service.backfill_evidence_links(apply=args.apply), ensure_ascii=False, indent=2))
        return 0
    if args.command == "migrate-document-ids":
        print(json.dumps(service.migrate_document_ids(apply=args.apply), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-legacy-evidence-backlinks":
        print(json.dumps(service.inspect_legacy_evidence_backlinks(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "record-inbox-pii-scan":
        print(json.dumps(service.record_inbox_pii_scan(
            args.intake, scanner=args.scanner, scanner_version=args.scanner_version,
            result=args.result, reviewed_by=args.reviewed_by, receipt=args.receipt,
            scanned_at=args.scanned_at,
        ), ensure_ascii=False, indent=2)); return 0
    if args.command == "capture-conversation":
        content = Path(args.file).read_text(encoding="utf-8")
        try:
            result = service.capture_conversation(
                content,
                args.provider,
                title=args.title,
                why_collected=args.why_collected,
                intended_use=args.intended_use,
                idempotency_key=args.idempotency_key,
                thread_ref=args.thread_ref,
                turn_from=args.turn_from,
                turn_to=args.turn_to,
                artifacts=json.loads(args.artifacts),
            )
        except CaptureIdempotencyConflict as error:
            print(json.dumps(error.as_dict(project_root()), ensure_ascii=False, indent=2))
            return 3
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "capture-document":
        content = Path(args.file).read_text(encoding="utf-8")
        try:
            result = service.capture_document(
                content, args.provider, title=args.title,
                why_collected=args.why_collected, intended_use=args.intended_use,
                idempotency_key=args.idempotency_key, source_url=args.source_url,
                source_locator=args.source_locator, captured_from=args.captured_from,
            )
        except CaptureIdempotencyConflict as error:
            print(json.dumps(error.as_dict(project_root()), ensure_ascii=False, indent=2))
            return 3
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "capture-file":
        source_path = _resolve_capture_file(root, args.file, args.inbox_file)
        try:
            result = service.capture_file(
                source_path.read_bytes(), source_path.name, args.provider,
                title=args.title, why_collected=args.why_collected,
                intended_use=args.intended_use, idempotency_key=args.idempotency_key,
                source_url=args.source_url, source_locator=args.source_locator,
                captured_from=args.captured_from,
            )
        except CaptureIdempotencyConflict as error:
            print(json.dumps(error.as_dict(project_root()), ensure_ascii=False, indent=2))
            return 3
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if args.command == "search":
        filters = {"type": args.type} if args.type else None
        hits = search_knowledge(root, args.query, filters)
        if not hits:
            print(json.dumps({
                "results": [],
                "message": "No matching Knowledge was found.",
                "recovery": "Try shorter domain keywords or inspect draft Bundles explicitly.",
            }, ensure_ascii=False, indent=2))
            return 0
        for hit in hits: print(f"{hit.document_id}\t{hit.title}\t{hit.path}")
        return 0
    if args.command == "read-bundle":
        document = find_document_by_id(root, args.bundle)
        if document is None: print("Bundle not found"); return 1
        print(document.path.read_text(encoding="utf-8"), end=""); return 0
    if args.command == "get-evidence-original":
        document = find_document_by_id(root, args.evidence)
        if document is None or document.frontmatter.get("type") != "evidence":
            print("Evidence not found"); return 1
        original_path = evidence_original_path(document)
        if not original_path.is_file():
            print("Evidence original is unavailable"); return 1
        print(json.dumps({
            "evidence_id": document.frontmatter["id"],
            "title": document.frontmatter["title"],
            "original_path": original_path.relative_to(root.parent.resolve()).as_posix(),
            "checksum": document.frontmatter.get("checksum"),
        }, ensure_ascii=False, indent=2)); return 0
    if args.command == "propose-update":
        print(json.dumps(service.propose_update(args.evidence), ensure_ascii=False, indent=2))
        return 0
    if args.command == "propose-pending":
        print(json.dumps(service.propose_pending(args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-inbox":
        print(json.dumps(service.inspect_inbox(args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-inbox-review-queue":
        print(json.dumps(service.list_inbox_review_queue(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "quarantine-inbox-item":
        print(json.dumps(service.quarantine_inbox_item(
            args.intake, classifier=args.classifier,
            rule_version=args.rule_version, reason=args.reason,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-inbox-disposals":
        print(json.dumps(service.list_inbox_disposals(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "decide-inbox-disposal":
        print(json.dumps(service.decide_inbox_disposal(
            args.intake, decision=args.decision, actor=args.actor,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "accept-inbox":
        print(json.dumps(service.accept_inbox(args.intake, args.actor), ensure_ascii=False, indent=2))
        return 0
    if args.command == "accept-ready-inbox":
        print(json.dumps(service.accept_ready_inbox(args.actor, args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "reconcile-inbox":
        print(json.dumps(service.reconcile_inbox(args.actor, args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "reconcile-inbox-then-curation":
        print(json.dumps(service.reconcile_inbox_then_curation(
            args.actor, args.limit,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "reconcile-curation":
        print(json.dumps(service.reconcile_curation(args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "review-data-protection":
        print(json.dumps(service.review_data_protection(
            args.intake, args.actor, context=args.context,
            checks=json.loads(args.checks), rationale=args.rationale,
            findings=json.loads(args.findings),
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "request-inbox-sensitivity-decision":
        print(json.dumps(
            service.request_inbox_sensitivity_decision(
                args.intake, args.actor, question=args.question,
                missing_procedure=args.missing_procedure,
                safe_next_action=args.safe_next_action,
                facts=json.loads(args.facts), hypotheses=json.loads(args.hypotheses),
            ), ensure_ascii=False, indent=2,
        ))
        return 0
    if args.command == "ingest-accepted":
        print(json.dumps(service.ingest_accepted(args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "find-workflow":
        print(json.dumps(service.find_workflow(args.request), ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare-task":
        result = service.prepare_task(args.workflow, args.request, json.loads(args.inputs))
        task = result.get("task", {}) if isinstance(result, dict) else {}
        if isinstance(task, dict):
            result["task_id"] = task.get("task_id")
            result["status"] = task.get("status")
            result["missing_inputs"] = task.get("missing_inputs", [])
            result["next_action"] = (
                "request_missing_inputs" if task.get("missing_inputs") else "execute_first_pending_step"
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "prepare-runbook-refresh":
        print(json.dumps(service.prepare_runbook_refresh(
            args.workflow,
            args.request,
            requested_by=args.requested_by,
            reason=args.reason,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "submit-runbook-reference":
        print(json.dumps(service.submit_runbook_reference(
            args.workflow,
            args.evidence,
            submitted_by=args.submitted_by,
            note=args.note,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "record-reference-assessment":
        print(json.dumps(service.record_reference_assessment(
            args.task, evidence_id=args.evidence, authority=args.authority,
            recency=args.recency, applicability=args.applicability,
            corroboration=args.corroboration, disposition=args.disposition,
            rationale=args.rationale, assessed_by=args.assessed_by,
            verified_by=args.verified_by, conflicts=args.conflict,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "confirm-runbook-revision":
        print(json.dumps(service.confirm_runbook_revision(
            args.task, revision_ref=args.revision_ref,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "audit-knowledge":
        print(json.dumps(service.audit_knowledge(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-knowledge-inventory":
        print(json.dumps(service.list_knowledge_inventory(
            domain=args.domain, document_type=args.type, status=args.status,
            owner=args.owner, freshness_state=args.freshness_state,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate-claim-support":
        print(json.dumps(service.validate_claim_support(json.loads(args.claims)), ensure_ascii=False, indent=2))
        return 0
    if args.command == "measure-runbook-effectiveness":
        print(json.dumps(service.measure_runbook_effectiveness(args.workflow), ensure_ascii=False, indent=2))
        return 0
    if args.command == "get-task":
        print(json.dumps(service.get_task(args.task), ensure_ascii=False, indent=2))
        return 0
    if args.command == "update-task-inputs":
        print(json.dumps(service.update_task_inputs(args.task, json.loads(args.inputs)), ensure_ascii=False, indent=2))
        return 0
    if args.command == "record-task-step":
        print(json.dumps(service.record_task_step(
            args.task,
            args.step,
            status=args.status,
            result=args.result,
            actor=args.actor,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "record-refresh-decision":
        print(json.dumps(service.record_refresh_decision(
            args.task,
            decision=args.decision,
            rationale=args.rationale,
            evidence_ids=args.evidence,
            actor=args.actor,
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "record-outcome":
        print(json.dumps(service.record_outcome(
            args.task,
            status=args.status,
            summary=args.summary,
            feedback=args.feedback,
            learnings=args.learning,
            artifacts=json.loads(args.artifacts),
            decisions=json.loads(args.decisions),
            action_items=json.loads(args.action_items),
            open_questions=json.loads(args.open_questions),
        ), ensure_ascii=False, indent=2))
        return 0
    if args.command == "publish-changes":
        try:
            print(json.dumps(service.publish_changes(args.message), ensure_ascii=False))
        except PublishError as error:
            parser.exit(1, f"ERROR: {error}\n")
        return 0
    if args.command == "push-changes":
        try:
            print(json.dumps(service.push_committed_changes(args.commit), ensure_ascii=False))
        except PublishError as error:
            parser.exit(1, f"ERROR: {error}\n")
        return 0
    if args.command == "resume-pending-push":
        try:
            print(json.dumps(service.resume_pending_push(), ensure_ascii=False))
        except PublishError as error:
            parser.exit(1, f"ERROR: {error}\n")
        return 0
    if args.command == "apply-bundle-revision":
        proposal = json.loads(Path(args.frontmatter_file).read_text(encoding="utf-8"))
        document = apply_bundle_revision(
            root, bundle_id=args.bundle, expected_revision=args.expected_revision,
            proposed_frontmatter=proposal,
            body=Path(args.body_file).read_text(encoding="utf-8"), actor=args.actor,
        )
        print(json.dumps({
            "bundle_id": document.frontmatter["id"],
            "status": document.frontmatter["status"],
            "knowledge_revision": document.frontmatter["extensions"]["knowledge_revision"],
        }, ensure_ascii=False, indent=2)); return 0
    if args.command == "propose-bundle-reclassification":
        print(json.dumps(service.propose_bundle_reclassification(args.bundle, domain=args.domain, bundle_type=args.type), ensure_ascii=False, indent=2)); return 0
    if args.command == "apply-bundle-reclassification":
        print(json.dumps(service.apply_bundle_reclassification(args.bundle, expected_revision=args.expected_revision, domain=args.domain, bundle_type=args.type, actor=args.actor, rationale=args.rationale, approval_notification_id=args.approval_notification), ensure_ascii=False, indent=2)); return 0
    if args.command == "list-curation-candidates":
        print(json.dumps(service.list_curation_candidates(), ensure_ascii=False, indent=2)); return 0
    if args.command == "list-curation-reviews":
        print(json.dumps(service.list_curation_reviews(include_resolved=args.include_resolved), ensure_ascii=False, indent=2)); return 0
    if args.command == "list-curation-queue":
        print(json.dumps(service.list_curation_queue(include_resolved=args.include_resolved), ensure_ascii=False, indent=2)); return 0
    if args.command == "refresh-curation-queue":
        print(json.dumps(service.refresh_curation_queue(), ensure_ascii=False, indent=2)); return 0
    if args.command == "decide-curation-review":
        print(json.dumps(service.decide_curation_review(args.review, action=args.action, actor=args.actor, note=args.note), ensure_ascii=False, indent=2)); return 0
    if args.command == "apply-approved-curation-update":
        print(json.dumps(service.apply_approved_curation_update(args.review, actor=args.actor), ensure_ascii=False, indent=2)); return 0
    if args.command == "create-curation-review":
        output_json = Path(args.output_file).read_text(encoding="utf-8") if args.output_file else args.output
        print(json.dumps(service.create_curation_review(args.evidence, json.loads(output_json), generated_by=args.generated_by, curation_receipt=args.curation_receipt, user_review_request=args.user_review_request), ensure_ascii=False, indent=2)); return 0
    if args.command == "apply-automatic-curation-update":
        body = Path(args.body_file).read_text(encoding="utf-8")
        print(json.dumps(service.apply_automatic_curation_append(
            args.evidence,
            existing_bundle_id=args.existing_bundle,
            body=body,
            actor=args.actor,
            curation_receipt=args.curation_receipt,
            security_receipt=args.security_receipt,
            update_mode=args.update_mode,
        ), ensure_ascii=False, indent=2)); return 0
    if args.command == "verify-curation-commit":
        result = service.verify_curation_commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("passed") is True else 1
    if args.command == "run-configured-curation-batch":
        print(json.dumps(service.run_configured_curation_batch(args.limit), ensure_ascii=False, indent=2)); return 0
    if args.command == "review-curation-candidate":
        print(json.dumps(service.review_curation_candidate(
            args.bundle, action=args.action, actor=args.actor, note=args.note,
            merged_into=args.merged_into,
        ), ensure_ascii=False, indent=2)); return 0
    if args.command == "promote-curation-candidate":
        print(json.dumps(service.promote_curation_candidate(
            args.bundle, actor=args.actor, security_receipt=args.security_receipt,
            automated=args.automated,
        ), ensure_ascii=False, indent=2)); return 0
    if args.command == "create-bundle":
        if args.type not in DIRECT_DRAFT_TYPES:
            parser.error(
                "direct Draft creation is not allowed for this type; "
                "manual and runbook require a curation review"
            )
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else None
    document = create_bundle(
        root, domain=args.domain, slug=args.slug, title=args.title,
        bundle_type=args.type, summary=args.summary, evidence_id=args.evidence,
        body=body, curated_by=args.curated_by,
        tags=args.tag,
    )
    print(document.frontmatter["id"]); return 0


def _resolve_capture_file(root: Path, file_value: object, inbox_value: object) -> Path:
    if bool(file_value) == bool(inbox_value):
        raise ValueError("provide exactly one of --file or --inbox-file")
    if file_value:
        return Path(str(file_value))
    requested = str(inbox_value).replace("\\", "/").lstrip("/")
    inbox_root = (root / "inbox").resolve()
    normalized = unicodedata.normalize("NFD", requested)
    matches = [
        path for path in inbox_root.rglob("*") if path.is_file()
        and unicodedata.normalize("NFD", path.relative_to(inbox_root).as_posix()) == normalized
    ]
    if len(matches) != 1:
        raise ValueError("--inbox-file must resolve to exactly one file under knowledge/inbox")
    return matches[0]


def run_cli() -> int:
    """Return safe structured Runtime errors instead of Python tracebacks."""
    try:
        return main()
    except (KeyError, OSError, PublishError, TypeError, ValueError) as error:
        command = sys.argv[1] if len(sys.argv) > 1 else "cli"
        print(json.dumps({
            "error": "operation_failed",
            "stage": command,
            "message": str(error),
            "recovery": "Review the command inputs and current resource state, then retry.",
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
