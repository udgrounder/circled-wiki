"""Source-repository CLI for Product Agent operational-issue work."""

import argparse
import json
from pathlib import Path
import sys
from typing import Optional

from circled_wiki.core.issue_workspace import (
    ARCHIVE_DISPOSITIONS,
    HISTORY_RELATIONS,
    ISSUE_CLASSIFICATIONS,
    REVIEW_DECISIONS,
    archive_workspace_issue,
    intake_operational_issue,
    link_workspace_issue_resolution,
    review_workspace_issue,
    triage_workspace_issue,
)
from circled_wiki.core.receipts import (
    DEPLOYMENT_STATUSES,
    record_deployment_receipt,
    record_release_receipt,
    record_verification_receipt,
)


class ProductArgumentParser(argparse.ArgumentParser):
    """Return stable JSON errors instead of argparse's process exit output."""

    def error(self, message: str) -> None:
        raise ValueError(message)


def _workspace_root(value: Optional[str]) -> Path:
    root = Path(value).expanduser() if value else Path.cwd() / "workspace"
    return root.resolve()


def _workspace_path(workspace_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (workspace_root / path).resolve()
    if workspace_root not in resolved.parents:
        raise ValueError("Workspace item path must remain below the Product Workspace")
    return resolved


def _parse_validation(value: str) -> dict[str, str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("validation must be a JSON object") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(result, str)
        for key, result in payload.items()
    ):
        raise ValueError("validation must be a JSON string-to-string object")
    return payload


def _parse_actions(args: argparse.Namespace) -> dict[str, list[str]]:
    return {
        "applied": args.applied,
        "preserved": args.preserved,
        "proposed": args.proposed,
    }


def main() -> int:
    parser = ProductArgumentParser(prog="circled-wiki-product")
    parser.add_argument(
        "--workspace",
        help="Product Workspace root; defaults to ./workspace in the source repository",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    intake = commands.add_parser("intake-operational-issue")
    intake.add_argument("--source-project", required=True)
    intake.add_argument("--project-ref", required=True)
    intake.add_argument("--issue", required=True)
    intake.add_argument("--requested-by", required=True)
    intake.add_argument("--moved-by", required=True)

    review = commands.add_parser("review-workspace-issue")
    review.add_argument("--item", required=True)
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--decision", required=True, choices=REVIEW_DECISIONS)
    review.add_argument("--history-relation", required=True, choices=HISTORY_RELATIONS)
    review.add_argument("--canonical-issue-key")
    review.add_argument("--note", default="")

    triage = commands.add_parser("triage-workspace-issue")
    triage.add_argument("--item", required=True)
    triage.add_argument("--classification", required=True, choices=ISSUE_CLASSIFICATIONS)
    triage.add_argument("--disposition", choices=ARCHIVE_DISPOSITIONS)
    triage.add_argument("--linked-work", action="append", default=[])

    resolution = commands.add_parser("link-workspace-resolution")
    resolution.add_argument("--item", required=True)
    resolution.add_argument("--disposition", required=True, choices=ARCHIVE_DISPOSITIONS)
    resolution.add_argument("--release")
    resolution.add_argument("--deployment-receipt")
    resolution.add_argument("--verification-receipt")

    archive = commands.add_parser("archive-workspace-issue")
    archive.add_argument("--item", required=True)
    archive.add_argument("--archived-by", required=True)
    archive.add_argument("--reason", required=True)
    archive.add_argument("--restore-condition", required=True)

    release = commands.add_parser("record-release-receipt")
    release.add_argument("--manifest", required=True)
    release.add_argument("--source-revision", required=True)
    release.add_argument("--included-issue", action="append", default=[])
    release.add_argument("--validation", required=True)
    release.add_argument("--verified-by", required=True)

    deployment = commands.add_parser("record-deployment-receipt")
    deployment.add_argument("--release-receipt", required=True)
    deployment.add_argument("--previous-release", required=True)
    deployment.add_argument("--target-ref", required=True)
    deployment.add_argument("--backup-ref", required=True)
    deployment.add_argument("--status", choices=DEPLOYMENT_STATUSES, default="verification_pending")
    deployment.add_argument("--applied", action="append", default=[])
    deployment.add_argument("--preserved", action="append", default=[])
    deployment.add_argument("--proposed", action="append", default=[])

    verification = commands.add_parser("record-verification-receipt")
    verification.add_argument("--deployment-receipt", required=True)
    verification.add_argument("--expected-release", required=True)
    verification.add_argument("--observed-release", required=True)
    verification.add_argument("--verified-by", required=True)
    verification.add_argument("--implemented-by", required=True)
    for flag in (
        "preflight-ready", "validator-passed", "config-preserved",
        "knowledge-preserved", "workspace-preserved", "reproduction-passed",
    ):
        verification.add_argument(f"--{flag}", action="store_true", required=True)

    args = parser.parse_args()
    workspace_root = _workspace_root(args.workspace)
    if args.command == "intake-operational-issue":
        result = intake_operational_issue(
            workspace_root,
            Path(args.source_project),
            project_ref=args.project_ref,
            issue_ref=args.issue,
            requested_by=args.requested_by,
            moved_by=args.moved_by,
        )
    elif args.command == "review-workspace-issue":
        result = review_workspace_issue(
            _workspace_path(workspace_root, args.item),
            reviewed_by=args.reviewed_by,
            decision=args.decision,
            history_relation=args.history_relation,
            canonical_issue_key=args.canonical_issue_key,
            note=args.note,
        )
    elif args.command == "triage-workspace-issue":
        result = triage_workspace_issue(
            _workspace_path(workspace_root, args.item),
            classification=args.classification,
            disposition=args.disposition,
            linked_work=args.linked_work,
        )
    elif args.command == "link-workspace-resolution":
        result = link_workspace_issue_resolution(
            _workspace_path(workspace_root, args.item),
            disposition=args.disposition,
            release=args.release,
            deployment_receipt=args.deployment_receipt,
            verification_receipt=args.verification_receipt,
        )
    elif args.command == "archive-workspace-issue":
        result = archive_workspace_issue(
            workspace_root,
            _workspace_path(workspace_root, args.item),
            archived_by=args.archived_by,
            reason=args.reason,
            restore_condition=args.restore_condition,
        )
    elif args.command == "record-release-receipt":
        result = record_release_receipt(
            workspace_root / "receipts",
            manifest_path=Path(args.manifest),
            source_revision=args.source_revision,
            included_issue_ids=args.included_issue,
            validation=_parse_validation(args.validation),
            verified_by=args.verified_by,
        )
    elif args.command == "record-deployment-receipt":
        result = record_deployment_receipt(
            workspace_root / "receipts",
            release_receipt=_workspace_path(workspace_root, args.release_receipt),
            previous_release=args.previous_release,
            target_ref=args.target_ref,
            backup_ref=args.backup_ref,
            actions=_parse_actions(args),
            status=args.status,
        )
    else:
        result = record_verification_receipt(
            workspace_root / "receipts",
            deployment_receipt=_workspace_path(workspace_root, args.deployment_receipt),
            expected_release=args.expected_release,
            observed_release=args.observed_release,
            verified_by=args.verified_by,
            implemented_by=args.implemented_by,
            preflight_ready=args.preflight_ready,
            validator_passed=args.validator_passed,
            config_preserved=args.config_preserved,
            knowledge_preserved=args.knowledge_preserved,
            workspace_preserved=args.workspace_preserved,
            reproduction_passed=args.reproduction_passed,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_product_cli() -> int:
    """Use the same compact JSON error shape as the Runtime CLI."""
    try:
        return main()
    except (ValueError, FileNotFoundError, OSError) as error:
        print(
            json.dumps(
                {
                    "error": "product_operation_failed",
                    "stage": sys.argv[1] if len(sys.argv) > 1 else "argument_parsing",
                    "message": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run_product_cli())
