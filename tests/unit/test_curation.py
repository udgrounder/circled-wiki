import tempfile
import unittest
import sys
import json
import hashlib
import multiprocessing
import threading
from datetime import datetime, timezone
from dataclasses import replace
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path

from circled_wiki.core.curation import (
    _is_eligible_automatic_update,
    apply_automatic_curation_append,
    materialize_curation_candidate,
)
from circled_wiki.core.curation import run_configured_curation, run_configured_curation_batch
from circled_wiki.core.curator import propose_update
from circled_wiki.core.curation_contract import validate_curation_output
from circled_wiki.core.ingest import ingest_evidence
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.pii import build_pii_scan_receipt
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.candidates import list_curation_candidates
from circled_wiki.core.repository import apply_bundle_revision, create_bundle, find_document_by_id, propose_bundle_reclassification, apply_bundle_reclassification
from circled_wiki.core.validator import validate_document
from circled_wiki.core.candidates import promote_curation_candidate, review_curation_candidate
from circled_wiki.core.curation_reviews import (
    AUTOMATIC_UPDATE_TYPES,
    apply_approved_curation_update,
    apply_automatic_curation_update,
    decide_curation_review,
    generate_curation_review,
    list_curation_reviews,
)
from circled_wiki.core.bundle_types import DIRECT_DRAFT_TYPES
from circled_wiki.core.curation_queue import (
    curation_queue_transaction,
    enqueue_curation_work,
    list_curation_queue,
    refresh_curation_queue,
)
from circled_wiki.core.notification_store import acknowledge_user_notification
from circled_wiki.core.taxonomy_proposals import record_taxonomy_change_proposal
import circled_wiki.core.curation_queue as curation_queue
from circled_wiki.worker.jobs import reconcile_curation


def _acquire_queue_transaction(knowledge_root, started, acquired):
    started.set()
    with curation_queue_transaction(Path(knowledge_root)):
        acquired.set()


class CurationMaterializationTests(unittest.TestCase):
    def test_explicit_reclassification_moves_bundle_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            (root.parent / ".circled-wiki").mkdir()
            (root.parent / ".circled-wiki" / "curation-taxonomy.yaml").write_text(
                """schema_version: 1
domains:
  - id: cs
    description: Customer support knowledge.
routing_rules: []
""",
                encoding="utf-8",
            )
            bundle = create_bundle(root, domain="operations", slug="customer-inquiry", title="Customer inquiry", bundle_type="guide", summary="Summary", evidence_id=evidence_id, tags=["customer"])
            proposal = propose_bundle_reclassification(root, bundle_id=bundle.frontmatter["id"], domain="cs", bundle_type="manual")
            self.assertTrue(proposal["requires_explicit_approval"])
            change = record_taxonomy_change_proposal(
                root, evidence_id=evidence_id, domain="cs", bundle_type="manual",
                rationale="The approved taxonomy change identifies this existing Bundle.",
                impacted_bundle_ids=[bundle.frontmatter["id"]],
            )
            approval_id = str(change["reclassification_notification"]["notification_id"])
            acknowledge_user_notification(root.parent / "workspace", notification_id=approval_id, actor="owner")
            moved = apply_bundle_reclassification(root, bundle_id=bundle.frontmatter["id"], expected_revision=proposal["expected_revision"], domain="cs", bundle_type="manual", actor="operator", rationale="The local taxonomy classifies this as a manual.", approval_notification_id=approval_id)
        self.assertEqual(moved.frontmatter["id"], bundle.frontmatter["id"])
        self.assertEqual(moved.frontmatter["bundle_uuid"], bundle.frontmatter["bundle_uuid"])
        self.assertEqual(moved.path.parts[-3:], ("cs", "manuals", "customer-inquiry.md"))
        self.assertEqual(moved.frontmatter["type"], "manual")
        self.assertEqual(moved.frontmatter["extensions"]["reclassification_history"][0]["reclassified_by"], "operator")
    def test_proposal_returns_matching_install_local_routing_hint_without_selecting_target(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".circled-wiki").mkdir()
            (project / ".circled-wiki" / "curation-taxonomy.yaml").write_text(
                """schema_version: 1
domains:
  - id: operations
    description: Customer-facing operational guidance.
routing_rules:
  - match_terms: [customer, inquiry]
    description: Customer inquiry guidance.
    domain: operations
    bundle_type: guide
    auto_create: true
    slug_prefix: customer-inquiry
""",
                encoding="utf-8",
            )
            root = project / "knowledge"
            source = root / "inbox" / "manual" / "source.txt"
            source.parent.mkdir(parents=True)
            source.write_text("customer inquiry", encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            evidence = ingest_evidence(
                root, source, "manual", title="Customer inquiry",
                why_collected="test", intended_use=["customer", "inquiry"],
                pii_scan_receipt=build_pii_scan_receipt(
                    checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii",
                ),
            )
            proposal = propose_update(root, evidence.evidence_id)
        self.assertEqual(proposal["routing_hints"], [{
            "match_terms": ["customer", "inquiry"], "description": "Customer inquiry guidance.", "domain": "operations",
            "bundle_type": "guide", "auto_create": True, "slug_prefix": "customer-inquiry",
        }])
        self.assertEqual(proposal["recommended_action"], "create_draft_bundle")
        self.assertTrue(proposal["creation_authorized"])
        self.assertIn("Installation-local taxonomy", proposal["proposal_interpretation"]["routing_hints"])
        self.assertIn("Non-binding heuristic", proposal["proposal_interpretation"]["suggested_bundle_type"])
        self.assertIn("empty list is not proof", proposal["proposal_interpretation"]["candidate_bundles"])

    def test_proposal_requests_taxonomy_review_when_installation_taxonomy_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            proposal = propose_update(root, evidence_id)
        self.assertEqual(proposal["taxonomy_status"]["configured"], False)
        self.assertIn("do not create it automatically", proposal["taxonomy_status"]["next_action"])

    def test_proposal_keeps_taxonomy_policy_distinct_from_heuristic_type_hint(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".circled-wiki").mkdir()
            (project / ".circled-wiki" / "curation-taxonomy.yaml").write_text(
                """schema_version: 1
domains:
  - id: operations
    description: Operational knowledge.
routing_rules:
  - match_terms: [executive, meeting]
    description: Executive meeting records are retained as guides.
    domain: operations
    bundle_type: guide
    auto_create: true
""",
                encoding="utf-8",
            )
            root = project / "knowledge"
            source = root / "inbox" / "manual" / "report.txt"
            source.parent.mkdir(parents=True)
            source.write_text("Weekly report from the executive meeting.", encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            evidence = ingest_evidence(
                root, source, "manual", title="Executive meeting weekly report",
                why_collected="test", intended_use=["executive", "meeting"],
                pii_scan_receipt=build_pii_scan_receipt(
                    checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii",
                ),
            )

            proposal = propose_update(root, evidence.evidence_id)

        self.assertEqual(proposal["routing_hints"][0]["bundle_type"], "guide")
        self.assertEqual(proposal["suggested_bundle_type"], "report")
        self.assertTrue(proposal["creation_authorized"])
        self.assertIn("does not authorize creation", proposal["proposal_interpretation"]["suggested_bundle_type"])
    def test_automatic_update_policy_excludes_only_runbook_and_manual(self):
        self.assertEqual(AUTOMATIC_UPDATE_TYPES, DIRECT_DRAFT_TYPES)
        self.assertNotIn("runbook", AUTOMATIC_UPDATE_TYPES)
        self.assertNotIn("manual", AUTOMATIC_UPDATE_TYPES)

    def test_non_runbook_manual_review_requires_explicit_user_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            with self.assertRaisesRegex(ValueError, "explicit user_review_request"):
                generate_curation_review(
                    root, evidence_id, self._output(evidence_id, "guide"),
                    generated_by="curator", curation_receipt="test://curation",
                )

            review = generate_curation_review(
                root, evidence_id, self._output(evidence_id, "guide"),
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/123",
            )
            metadata = parse_markdown(root.parent / review["path"]).frontmatter["extensions"]["curation_review"]
            self.assertEqual(metadata["review_route"], "explicit_user_request")
            self.assertEqual(metadata["user_review_request"], "user-request://test/123")
            notification_files = list((root.parent / "workspace" / "notifications" / "inbox").glob("notification-*.json"))
            self.assertEqual(len(notification_files), 1)
            self.assertEqual(json.loads(notification_files[0].read_text(encoding="utf-8"))["event"], "review_requested")

    def test_frontmatter_candidate_uses_latest_evidence_for_automatic_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            old_source = root / "inbox" / "manual" / "old.txt"
            old_source.parent.mkdir(parents=True)
            old_source.write_text("old campaign policy", encoding="utf-8")
            old_checksum = "sha256:" + hashlib.sha256(old_source.read_bytes()).hexdigest()
            old_evidence = ingest_evidence(
                root, old_source, "manual", title="Campaign policy",
                why_collected="old policy", intended_use=["campaign", "policy"],
                captured_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                pii_scan_receipt=build_pii_scan_receipt(
                    old_checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii-old",
                ),
            )
            target = create_bundle(
                root, domain="marketing", slug="campaign-policy", title="Campaign policy",
                bundle_type="guide", summary="Current campaign policy.",
                evidence_id=old_evidence.evidence_id, tags=["campaign", "policy"],
            )
            new_source = root / "inbox" / "manual" / "new.txt"
            new_source.write_text("new campaign policy", encoding="utf-8")
            new_checksum = "sha256:" + hashlib.sha256(new_source.read_bytes()).hexdigest()
            new_evidence = ingest_evidence(
                root, new_source, "manual", title="Campaign policy",
                why_collected="new policy", intended_use=["campaign", "policy"],
                captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                pii_scan_receipt=build_pii_scan_receipt(
                    new_checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii-new",
                ),
            )
            proposal = propose_update(root, new_evidence.evidence_id)
            candidate = next(item for item in proposal["candidate_bundles"] if item["id"] == target.frontmatter["id"])
            self.assertEqual(candidate["domain"], "marketing")
            self.assertEqual(candidate["tags"], ["bundles", "guide", "marketing", "campaign", "policy"])
            self.assertEqual(candidate["latest_evidence_at"], "2025-01-01T00:00:00+00:00")
            self.assertEqual(proposal["evidence_freshness"]["effective_at"], "2026-01-01T00:00:00+00:00")

            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Campaign policy", "summary": "New policy.", "body": "# Policy",
                "evidence_ids": [new_evidence.evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "append",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "tags": ["campaign", "policy"],
            }, [new_evidence.evidence_id])
            self.assertTrue(_is_eligible_automatic_update(root, output, proposal))
            proposal["evidence_freshness"]["effective_at"] = "2024-01-01T00:00:00+00:00"
            self.assertFalse(_is_eligible_automatic_update(root, output, proposal))

    def _install_curation_contract(self, root):
        source = Path(__file__).resolve().parents[2] / "agent-rules" / "contracts"
        target = root.parent / "agent-rules" / "contracts"
        target.mkdir(parents=True)
        for name in ("index.yaml", "curation.yaml"):
            (target / name).write_bytes((source / name).read_bytes())

    def _evidence(self, directory):
        root = Path(directory) / "knowledge"
        source = root / "inbox" / "manual" / "source.txt"
        source.parent.mkdir(parents=True); source.write_text("campaign procedure", encoding="utf-8")
        checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        scan = build_pii_scan_receipt(
            checksum, scanner="test", scanner_version="1", result="passed",
            reviewed_by="security", receipt="test://pii",
        )
        evidence = ingest_evidence(
            root, source, "manual", why_collected="test", intended_use=["marketing"],
            pii_scan_receipt=scan,
        )
        return root, evidence.evidence_id

    def _output(self, evidence_id, kind="guide"):
        payload = {"action": kind, "domain": "marketing", "bundle_type": kind, "title": "SNS campaign launch", "summary": "Launch a campaign.", "body": "# Steps\n\n1. Define audience.", "evidence_ids": [evidence_id], "rationale": "repeatable process", "limitations": "budget omitted", "existing_bundle_candidates": [], "confidence": "medium", "tags": ["sns", "campaign"]}
        if kind in {"manual", "runbook"}:
            payload["slug"] = "campaign-launch"
        return validate_curation_output(payload, [evidence_id])

    def test_creates_candidate_and_reuses_same_evidence_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence_path = find_document_by_id(root, evidence_id).path
            evidence_before = evidence_path.read_bytes()
            first = materialize_curation_candidate(root, evidence_id, self._output(evidence_id), generated_by="curator", curation_receipt="test://curation")
            second = materialize_curation_candidate(root, evidence_id, self._output(evidence_id), generated_by="curator", curation_receipt="test://curation")
            self.assertEqual(first["action"], "created")
            self.assertEqual(second["action"], "reused")
            bundle = find_document_by_id(root, first["bundle_id"])
            self.assertEqual(bundle.frontmatter["tags"], ["bundles", "guide", "marketing", "sns", "campaign"])
            self.assertEqual(evidence_path.read_bytes(), evidence_before)

    def test_reused_candidate_consumes_a_repaired_queue_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence = find_document_by_id(root, evidence_id)
            first = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id),
                generated_by="curator", curation_receipt="test://curation",
            )
            enqueue_curation_work(root, evidence_id, evidence.path)

            reused = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id),
                generated_by="curator", curation_receipt="test://curation",
            )

            self.assertEqual(first["bundle_id"], reused["bundle_id"])
            self.assertEqual(reused["action"], "reused")
            self.assertEqual(list_curation_queue(root), [])

    def test_uses_the_installation_operator_when_no_default_owner_is_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)

            result = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id),
                generated_by="curator", curation_receipt="test://curation",
            )

            bundle = find_document_by_id(root, result["bundle_id"])
            self.assertEqual(bundle.frontmatter["owners"], ["hermes"])

    def test_allows_draft_candidate_without_optional_pii_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            source = root / "inbox" / "manual" / "source.txt"; source.parent.mkdir(parents=True); source.write_text("source", encoding="utf-8")
            evidence = ingest_evidence(root, source, "manual", why_collected="test", intended_use=["marketing"])
            result = materialize_curation_candidate(
                root, evidence.evidence_id, self._output(evidence.evidence_id),
                generated_by="curator", curation_receipt="test://curation",
            )
            self.assertEqual(result["action"], "created")

    def test_service_rejects_direct_candidate_materialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            with self.assertRaisesRegex(ValueError, "direct candidate materialization is disabled"):
                KnowledgeService(root).materialize_curation_candidate(
                    evidence_id, output={"action": "runbook", "domain": "marketing", "bundle_type": "runbook", "title": "SNS campaign launch", "summary": "Launch a campaign.", "body": "# Steps", "evidence_ids": [evidence_id]},
                    generated_by="curator", curation_receipt="test://curation",
                )
            self.assertEqual(list_curation_candidates(root), [])

    def test_manual_and_runbook_require_pre_creation_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            for bundle_type in ("manual", "runbook"):
                with self.subTest(bundle_type=bundle_type):
                    with self.assertRaisesRegex(ValueError, "approved pre-creation review"):
                        materialize_curation_candidate(
                            root, evidence_id, self._output(evidence_id, bundle_type),
                            generated_by="curator", curation_receipt="test://curation",
                        )
                    self.assertEqual(list_curation_candidates(root), [])

    def test_repository_cannot_bypass_pre_creation_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)

            with self.assertRaisesRegex(ValueError, "approved pre-creation review"):
                create_bundle(
                    root, domain="marketing", slug="operator-manual",
                    title="Operator Manual", bundle_type="manual",
                    summary="Operate the system.", evidence_id=evidence_id,
                )

    def test_approved_manual_review_creates_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = replace(
                self._output(evidence_id, "manual"),
                title="운영자 매뉴얼", slug="operator-manual",
            )
            review = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
            )
            UUID(review["review_id"].removeprefix("review-"))
            review_card = parse_markdown(root.parent / review["path"])
            attempt_id = review_card.frontmatter["extensions"]["curation_review"]["verification_attempt_id"]

            applied = decide_curation_review(
                root, review["review_id"], action="approve", actor="manual-owner",
            )

            bundle = find_document_by_id(root, applied["result"]["bundle_id"])
            self.assertEqual(bundle.frontmatter["type"], "manual")
            self.assertIn("/manuals/", bundle.path.as_posix())
            self.assertEqual(bundle.path.stem, "operator-manual")
            self.assertEqual(
                bundle.frontmatter["extensions"]["curation"]["review_decision"]["review_id"],
                review["review_id"],
            )
            self.assertEqual(
                bundle.frontmatter["extensions"]["curation"]["review_decision"]["verification_attempt_id"],
                attempt_id,
            )
            self.assertEqual(
                bundle.frontmatter["extensions"]["curation"]["review_receipts"][0]["review_id"],
                review["review_id"],
            )
            self.assertTrue(applied["review_deleted"])
            review_path = root.parent / review["path"]
            self.assertFalse(review_path.exists())

    def test_manual_requires_a_content_derived_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = replace(self._output(evidence_id, "manual"), title="운영자 매뉴얼", slug="")

            with self.assertRaisesRegex(ValueError, "requires a slug derived from the content"):
                materialize_curation_candidate(
                    root, evidence_id, output,
                    generated_by="curator", curation_receipt="test://curation",
                    approved_review_id="review-test",
                )

    def test_general_revision_api_cannot_promote_any_draft_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            result = materialize_curation_candidate(root, evidence_id, self._output(evidence_id), generated_by="curator", curation_receipt="test://curation")
            bundle = find_document_by_id(root, result["bundle_id"])
            proposed = dict(bundle.frontmatter)
            proposed["status"] = "active"
            with self.assertRaisesRegex(ValueError, "status transitions require"):
                apply_bundle_revision(root, bundle_id=result["bundle_id"], expected_revision=1, proposed_frontmatter=proposed, body=bundle.body, actor="reviewer")

    def test_configured_owner_with_security_receipt_promotes_approved_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text("schema_version: 1\napproval:\n  knowledge_owner: alice\n", encoding="utf-8")
            review = generate_curation_review(
                root, evidence_id, self._output(evidence_id, "guide"),
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/guide",
            )
            applied = decide_curation_review(
                root, review["review_id"], action="approve", actor="reviewer",
            )
            created = applied["result"]
            review_curation_candidate(root, created["bundle_id"], action="approve", actor="reviewer")
            result = promote_curation_candidate(root, created["bundle_id"], actor="mallory", security_receipt="security://1")
            self.assertEqual(result["status"], "active")

    def test_candidate_review_rejects_generating_actor_self_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            review = generate_curation_review(
                root, evidence_id, self._output(evidence_id, "guide"),
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/guide",
            )
            created = decide_curation_review(
                root, review["review_id"], action="approve", actor="reviewer",
            )["result"]

            with self.assertRaisesRegex(ValueError, "reviewer must differ"):
                review_curation_candidate(root, created["bundle_id"], action="approve", actor="curator")

            candidate = list_curation_candidates(root)[0]
            self.assertEqual(candidate["review_state"], "pending")

    def test_non_runbook_candidate_promotion_does_not_require_configured_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            review = generate_curation_review(
                root, evidence_id, self._output(evidence_id, "guide"),
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/guide",
            )
            created = decide_curation_review(
                root, review["review_id"], action="approve", actor="reviewer",
            )["result"]
            review_curation_candidate(root, created["bundle_id"], action="approve", actor="reviewer")

            result = promote_curation_candidate(root, created["bundle_id"], actor="reviewer", security_receipt="security://1")
            self.assertEqual(result["promotion_mode"], "review_approved")


    def test_direct_no_bundle_result_does_not_change_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = validate_curation_output(
                {"action": "no_bundle", "rationale": "Not reusable.", "recheck_condition": "More sources arrive."},
                [evidence_id],
            )
            result = materialize_curation_candidate(root, evidence_id, output, generated_by="curator", curation_receipt="test://curation")
            evidence = find_document_by_id(root, evidence_id)
            self.assertFalse(result["stored"])
            self.assertNotIn("status", evidence.frontmatter)
            self.assertNotIn("curation_no_bundle", evidence.frontmatter["extensions"])

    def test_korean_title_uses_checksum_slug_without_uuid_prefix_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide", "title": "한국어 SNS 가이드",
                "summary": "요약", "body": "# 본문", "evidence_ids": [evidence_id], "tags": ["sns", "marketing"],
            }, [evidence_id])
            result = materialize_curation_candidate(root, evidence_id, output, generated_by="curator", curation_receipt="test://curation")
            filename = Path(result["path"]).name
            self.assertTrue(filename.startswith("sns-"))
            self.assertNotIn(evidence_id.rsplit("/", 1)[-1][:8], filename)

    def test_disabled_configured_adapter_preserves_evidence_as_needs_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            result = run_configured_curation(root, evidence_id)
            self.assertEqual(result["action"], "needs_review")
            self.assertTrue(result["stored"])
            self.assertEqual(result["reason"], "adapter_disabled")
            queue = list_curation_queue(root)
            self.assertEqual(queue[0]["reason"], "adapter_disabled")
            self.assertEqual(queue[0]["next_action"], "configure_curation_adapter")
            self.assertEqual(queue[0]["reason_category"], "configuration")

    def test_refresh_discards_a_malformed_blocker_before_reporting_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            task_path = next((root.parent / "workspace" / "task" / "curation_reconciliation").glob("*.md"))
            task = parse_markdown(task_path)
            data = dict(task.frontmatter)
            data["last_blocker"] = {
                "reason": "adapter_disabled",
                "next_action": "configure_curation_adapter",
            }
            task_path.write_text(render_markdown(data), encoding="utf-8")

            refreshed = refresh_curation_queue(root)

            self.assertEqual(refreshed["repaired_count"], 1)
            repaired = parse_markdown(task_path).frontmatter
            self.assertNotIn("last_blocker", repaired)
            self.assertEqual(repaired["current"]["next_action"], "run_configured_curation_batch")
            self.assertEqual(repaired["step_receipts"][-1]["outcome"], "blocker_repaired")
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

    def test_reconcile_curation_closes_contract_valid_no_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: curated\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "no_bundle", "evidence_ids": [evidence_id],
                "rationale": "The Evidence duplicates existing knowledge.",
                "recheck_condition": "New non-duplicate Evidence arrives.",
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()

            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "no_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = reconcile_curation(root, limit=1)

            self.assertEqual(result["actions"]["counts"]["no_bundle"], 1)
            self.assertEqual(result["actions"]["items"][0]["evidence_id"], evidence_id)
            self.assertEqual(result["outcomes"][0]["outcome"], "no_bundle")
            self.assertEqual(result["outcomes"][0]["next_stage"], "no_bundle_recorded")
            self.assertEqual(result["outcomes"][0]["queue_disposition"], "complete")
            self.assertEqual(result["after"]["items"], [])
            self.assertEqual(list_curation_queue(root), [])
            self.assertEqual(list_curation_reviews(root, include_resolved=True)[0]["status"], "no_bundle")

    def test_reconcile_curation_hands_manual_result_to_review_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: curated\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "manual", "domain": "marketing", "bundle_type": "manual",
                "title": "Curated manual", "summary": "Summary.", "body": "# Manual",
                "evidence_ids": [evidence_id], "tags": ["curated", "manual"],
                "slug": "curated-manual",
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()

            with patch("circled_wiki.core.curation.propose_update", return_value={
                "recommended_action": "create_draft_bundle", "blocking_conditions": [],
                "routing_hints": [{"domain": "operations", "bundle_type": "guide"}],
            }):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = reconcile_curation(root, limit=1)

            item = result["actions"]["items"][0]["result"]
            self.assertEqual(item["action"], "created_review")
            self.assertEqual(item["handoff"]["status"], "queued_for_review")
            self.assertEqual(result["outcomes"][0]["outcome"], "review_handoff")
            self.assertEqual(len(list_curation_reviews(root)), 1)
            self.assertEqual(list_curation_candidates(root), [])

    def test_reconcile_curation_keeps_disabled_adapter_work_in_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)

            result = reconcile_curation(root, limit=1)

            self.assertEqual(result["status"], "configuration_required")
            self.assertEqual(result["reason"], "adapter_disabled")
            self.assertEqual(result["next_action"], "configure_curation_adapter")
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

    def test_reconcile_curation_never_applies_an_approved_update(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing",
                bundle_type="guide", summary="Existing summary.", evidence_id=evidence_id,
            )
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Reviewed update", "summary": "Updated summary.",
                "body": "# Reviewed update\n", "evidence_ids": [evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "replace_full",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "replace_reason": "Reviewer approved a complete rewrite.",
                "tags": ["marketing", "reviewed-update"],
            }, [evidence_id])
            review = generate_curation_review(
                root, evidence_id, output, generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/update",
            )
            decide_curation_review(root, review["review_id"], action="approve", actor="verifier")

            result = reconcile_curation(root, limit=1)

            self.assertEqual(result["actions"]["attempted"], 0)
            bundle = find_document_by_id(root, target.frontmatter["id"])
            self.assertEqual(bundle.frontmatter["title"], "Existing")
            self.assertEqual(bundle.frontmatter["extensions"]["knowledge_revision"], 1)
            self.assertEqual(len(list_curation_reviews(root)), 1)

    def test_reconcile_curation_records_automatic_promotion_as_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: reference\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "reference", "domain": "marketing", "bundle_type": "reference",
                "title": "Campaign reference", "summary": "Reference summary.",
                "body": "# Reference", "evidence_ids": [evidence_id],
                "confidence": "high", "existing_bundle_candidates": [],
                "tags": ["campaign", "reference"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "create_draft_bundle", "blocking_conditions": [], "candidate_bundles": []}

            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = reconcile_curation(root, limit=1)

            self.assertEqual(result["outcomes"][0]["outcome"], "published")
            self.assertEqual(result["outcomes"][0]["next_stage"], "published")
            self.assertEqual(result["after"]["items"], [])

    def test_reconcile_curation_records_failed_automatic_promotion_as_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: reference\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "reference", "domain": "marketing", "bundle_type": "reference",
                "title": "Campaign reference", "summary": "Reference summary.",
                "body": "# Reference", "evidence_ids": [evidence_id],
                "confidence": "high", "existing_bundle_candidates": [],
                "tags": ["campaign", "reference"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "create_draft_bundle", "blocking_conditions": [], "candidate_bundles": []}

            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    with patch("circled_wiki.core.curation.promote_curation_candidate", side_effect=ValueError("security gate blocked")):
                        result = reconcile_curation(root, limit=1)

            self.assertEqual(result["outcomes"][0]["outcome"], "draft_created")
            self.assertEqual(result["outcomes"][0]["next_stage"], "draft_created")
            self.assertEqual(result["after"]["items"], [])
            self.assertEqual(len(list_curation_candidates(root)), 1)

    def test_approved_update_review_applies_revision_and_archives_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing",
                bundle_type="guide", summary="Existing summary.", evidence_id=evidence_id,
            )
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Reviewed update", "summary": "Updated summary.",
                "body": "# Reviewed update\n", "evidence_ids": [evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "replace_full",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "replace_reason": "Reviewer approved a complete rewrite.",
                "tags": ["marketing", "reviewed-update"],
            }, [evidence_id])
            review = generate_curation_review(
                root, evidence_id, output, generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/update",
            )
            decided = decide_curation_review(root, review["review_id"], action="approve", actor="verifier")
            self.assertEqual(decided["result"]["action"], "approved_update")

            applied = apply_approved_curation_update(root, review["review_id"], actor="editor")

            self.assertEqual(applied["status"], "applied")
            bundle = find_document_by_id(root, target.frontmatter["id"])
            self.assertEqual(bundle.frontmatter["title"], "Reviewed update")
            self.assertEqual(bundle.frontmatter["extensions"]["knowledge_revision"], 2)
            receipt = bundle.frontmatter["extensions"]["curation"]["review_receipts"][-1]
            self.assertEqual(receipt["review_id"], review["review_id"])
            self.assertEqual(receipt["kind"], "update")
            self.assertEqual(receipt["applied_revision"], 2)
            self.assertFalse((root.parent / review["path"]).exists())

            data = dict(bundle.frontmatter)
            extensions = dict(data["extensions"])
            curation = dict(extensions["curation"])
            receipts = list(curation["review_receipts"])
            receipts[-1] = {**receipts[-1], "applied_revision": "two"}
            curation["review_receipts"] = receipts
            extensions["curation"] = curation
            data["extensions"] = extensions
            bundle.path.write_text(render_markdown(data, bundle.body), encoding="utf-8")
            errors = validate_document(bundle.path, root).profile_errors
            self.assertIn(
                "extensions.curation.review_receipts.applied_revision must be a positive integer",
                errors,
            )

    def test_append_update_preserves_the_existing_bundle_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing",
                bundle_type="guide", summary="Existing summary.", evidence_id=evidence_id,
                body="# Existing guidance\n\nKeep this section.\n",
            )
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Existing", "summary": "Updated summary.",
                "body": "## New evidence\n\nAdd this section.",
                "evidence_ids": [evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "append",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "tags": ["marketing", "guide"],
            }, [evidence_id])
            review = generate_curation_review(
                root, evidence_id, output, generated_by="curator",
                curation_receipt="test://curation", user_review_request="user-request://test/append",
            )
            decide_curation_review(root, review["review_id"], action="approve", actor="reviewer")
            apply_approved_curation_update(root, review["review_id"], actor="editor")

            updated = find_document_by_id(root, target.frontmatter["id"])
            self.assertIn("Keep this section.", updated.body)
            self.assertIn("## New evidence", updated.body)

    def test_automatic_update_rejects_full_body_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing",
                bundle_type="guide", summary="Existing summary.", evidence_id=evidence_id,
                body="# Existing guidance\n\nKeep this section.\n",
            )
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Existing", "summary": "Replacement.", "body": "# Replacement",
                "evidence_ids": [evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "replace_full",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "replace_reason": "A complete rewrite was proposed.",
                "tags": ["marketing", "guide"],
            }, [evidence_id])
            with self.assertRaisesRegex(ValueError, "requires append update_mode"):
                apply_automatic_curation_update(
                    root, evidence_id, output, actor="curator",
                    curation_receipt="test://curation", security_receipt="test://security",
                )
            self.assertIn("Keep this section.", find_document_by_id(root, target.frontmatter["id"]).body)

    def test_cli_append_update_reuses_target_metadata_and_completes_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            extra_source = root / "inbox" / "manual" / "extra.txt"
            extra_source.write_text("additional campaign evidence", encoding="utf-8")
            extra_checksum = "sha256:" + hashlib.sha256(extra_source.read_bytes()).hexdigest()
            extra_evidence = ingest_evidence(
                root, extra_source, "manual", why_collected="test", intended_use=["marketing"],
                pii_scan_receipt=build_pii_scan_receipt(
                    extra_checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii-extra",
                ),
            )
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing",
                bundle_type="guide", summary="Existing summary.", evidence_id=evidence_id,
                body="# Existing guidance\n\nKeep this section.\n",
            )
            result = apply_automatic_curation_append(
                root, extra_evidence.evidence_id,
                existing_bundle_id=target.frontmatter["id"],
                body="## New evidence\n\nAdd this section.",
                actor="curator",
                curation_receipt="curation://manual/append",
                security_receipt="security://manual/append",
            )

            self.assertEqual(result["action"], "updated")
            self.assertEqual(result["update_mode"], "append")
            self.assertTrue(result["queue_completed"])
            updated = find_document_by_id(root, target.frontmatter["id"])
            self.assertEqual(updated.frontmatter["title"], "Existing")
            self.assertEqual(updated.frontmatter["summary"], "Existing summary.")
            self.assertIn("Keep this section.", updated.body)
            self.assertIn("## New evidence", updated.body)
            self.assertEqual(
                updated.frontmatter["extensions"]["curation"]["evidence_checksums"],
                {
                    evidence_id: find_document_by_id(root, evidence_id).frontmatter["checksum"],
                    extra_evidence.evidence_id: extra_checksum,
                },
            )
            self.assertEqual(list_curation_queue(root), [])
            self.assertEqual(list((root.parent / "workspace" / "task" / "curation_reconciliation").glob("*.md")), [])

    def test_cli_append_update_requires_pending_queue_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing",
                bundle_type="guide", summary="Existing summary.", evidence_id=evidence_id,
            )
            from circled_wiki.core.curation_queue import complete_curation_work

            evidence = find_document_by_id(root, evidence_id)
            enqueue_curation_work(root, evidence_id, evidence.path)
            self.assertTrue(complete_curation_work(root, evidence_id))
            with self.assertRaisesRegex(ValueError, "pending Curation Queue item"):
                apply_automatic_curation_append(
                    root, evidence_id,
                    existing_bundle_id=target.frontmatter["id"], body="## Delta",
                    actor="curator", curation_receipt="curation://manual/append",
                    security_receipt="security://manual/append",
                )

    def test_configured_curation_automatically_updates_existing_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            self._install_curation_contract(root)
            target = create_bundle(
                root, domain="marketing", slug="existing-reference", title="Existing reference",
                bundle_type="reference", summary="Before update.", evidence_id=evidence_id,
            )
            source = root / "inbox" / "manual" / "reference-update.txt"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("new reference source", encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            scan = build_pii_scan_receipt(
                checksum, scanner="test", scanner_version="1", result="passed",
                reviewed_by="security", receipt="test://pii-update",
            )
            update_evidence_id = ingest_evidence(
                root, source, "manual", why_collected="update", intended_use=["marketing"],
                pii_scan_receipt=scan,
            ).evidence_id
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: reference\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "reference", "domain": "marketing", "bundle_type": "reference",
                "title": "Updated reference", "summary": "After update.", "body": "# Updated reference",
                "evidence_ids": [update_evidence_id], "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "append",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "tags": ["updated", "reference"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {
                "recommended_action": "update_existing", "blocking_conditions": [],
                "candidate_bundles": [{"id": target.frontmatter["id"]}],
            }

            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = reconcile_curation(root, limit=1)

            self.assertEqual(result["outcomes"][0]["outcome"], "published")
            self.assertEqual(result["after"]["items"], [])
            updated = find_document_by_id(root, target.frontmatter["id"])
            self.assertEqual(updated.frontmatter["title"], "Updated reference")
            self.assertEqual(updated.frontmatter["extensions"]["knowledge_revision"], 2)
            receipt = updated.frontmatter["extensions"]["curation"]["automatic_update_receipts"][-1]
            self.assertEqual(receipt["evidence_checksum"], find_document_by_id(root, update_evidence_id).frontmatter["checksum"])
            self.assertTrue(validate_document(updated.path, root).is_valid)
            self.assertEqual(list_curation_reviews(root), [])

    def test_configured_curation_automatically_updates_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing-report", title="Existing report",
                bundle_type="report", summary="Before update.", evidence_id=evidence_id,
            )
            source = root / "inbox" / "manual" / "report-update.txt"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("new report source", encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            update_evidence_id = ingest_evidence(
                root, source, "manual", why_collected="update", intended_use=["marketing"],
                pii_scan_receipt=build_pii_scan_receipt(
                    checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii-report-update",
                ),
            ).evidence_id
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: report\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "report", "domain": "marketing", "bundle_type": "report",
                "title": "Updated report", "summary": "After update.", "body": "# Updated report",
                "evidence_ids": [update_evidence_id], "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "append",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "tags": ["updated", "report"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "update_existing", "blocking_conditions": [], "candidate_bundles": [{"id": target.frontmatter["id"]}]}

            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, update_evidence_id)

            self.assertEqual(result["action"], "updated")
            self.assertEqual(result["promotion_mode"], "automatic_update")
            updated = find_document_by_id(root, target.frontmatter["id"])
            self.assertEqual(updated.frontmatter["title"], "Updated report")
            self.assertEqual(updated.frontmatter["extensions"]["knowledge_revision"], 2)
            self.assertTrue(validate_document(updated.path, root).is_valid)
            self.assertEqual(list_curation_queue(root), [])

    def test_configured_curation_automatically_updates_existing_guide(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing guide",
                bundle_type="guide", summary="Before update.", evidence_id=evidence_id,
            )
            source = root / "inbox" / "manual" / "guide-update.txt"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("new guide source", encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            update_evidence_id = ingest_evidence(
                root, source, "manual", why_collected="update", intended_use=["marketing"],
                pii_scan_receipt=build_pii_scan_receipt(
                    checksum, scanner="test", scanner_version="1", result="passed",
                    reviewed_by="security", receipt="test://pii-guide-update",
                ),
            ).evidence_id
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: guide\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Updated guide", "summary": "After update.", "body": "# Updated guide",
                "evidence_ids": [update_evidence_id], "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "append",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "tags": ["updated", "guide"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "update_existing", "blocking_conditions": [], "candidate_bundles": [{"id": target.frontmatter["id"]}]}

            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    with patch(
                        "circled_wiki.core.curation_reviews.validate_document",
                        wraps=validate_document,
                    ) as validate_input:
                        result = run_configured_curation(root, update_evidence_id)

            self.assertEqual(result["action"], "updated")
            self.assertEqual(result["promotion_mode"], "automatic_update")
            self.assertEqual(find_document_by_id(root, target.frontmatter["id"]).frontmatter["title"], "Updated guide")
            self.assertEqual(list_curation_reviews(root), [])
            validated_paths = [call.args[0] for call in validate_input.call_args_list]
            self.assertNotIn(find_document_by_id(root, update_evidence_id).path, validated_paths)
            self.assertIn(target.path, validated_paths)

    def test_configured_curation_batch_reports_bounded_needs_review_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            report = run_configured_curation_batch(root, limit=1)

            self.assertEqual(report["attempted"], 1)
            self.assertEqual(report["counts"]["needs_review"], 1)
            self.assertEqual(report["items"][0]["evidence_id"], evidence_id)
            self.assertEqual(report["usage"]["tokens"], "unknown")

    def test_invalid_adapter_output_keeps_queue_retryable_without_review_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: bad-json\n"
                f"  command: '{sys.executable} -c \"print(\\\"not-json\\\")\"'\n",
                encoding="utf-8",
            )

            result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "needs_review")
            self.assertEqual(result["evidence_id"], evidence_id)
            self.assertFalse(result["stored"])
            self.assertEqual(result["reason"], "invalid_json")
            self.assertEqual(result["receipt"]["status"], "invalid_json")
            self.assertEqual(list_curation_candidates(root), [])
            evidence = find_document_by_id(root, evidence_id)
            self.assertNotIn("curation_attempt", evidence.frontmatter["extensions"])
            self.assertEqual(list_curation_reviews(root), [])
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

    def test_configured_adapter_auto_promotes_report_without_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence_path = find_document_by_id(root, evidence_id).path
            evidence_before = evidence_path.read_bytes()
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: curated\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "report", "domain": "marketing", "bundle_type": "report",
                "title": "Curated report", "summary": "Summary.", "body": "# Report",
                "evidence_ids": [evidence_id], "tags": ["curated", "report"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            with patch("circled_wiki.core.curation.propose_update", return_value={
                "recommended_action": "create_draft_bundle", "blocking_conditions": [],
                "routing_hints": [{"domain": "operations", "bundle_type": "guide"}],
            }):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed) as adapter:
                    result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "created")
            request = json.loads(adapter.call_args.kwargs["input"])
            self.assertEqual(
                {item["type"] for item in request["bundle_taxonomy"]},
                {"policy", "guide", "runbook", "manual", "decision", "spec", "reference", "report"},
            )
            self.assertEqual(request["pre_creation_review_types"], ["manual", "runbook"])
            self.assertEqual(request["proposal"]["routing_hints"], [{"domain": "operations", "bundle_type": "guide"}])
            self.assertEqual(request["proposal"]["interpretation"], {})
            self.assertIn("auto_create", request["routing_hint_rule"])
            self.assertIn("empty list is never conclusive", request["target_selection_rule"])
            self.assertIn("inspect the Evidence content", request["slug_rule"])
            self.assertIn("non-ASCII title", request["slug_rule"])
            self.assertEqual(result["promotion"]["promotion_mode"], "automatic")
            promoted = find_document_by_id(root, result["bundle_id"])
            self.assertEqual(promoted.frontmatter["status"], "active")
            self.assertEqual(list_curation_candidates(root), [])
            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    repeated = run_configured_curation(root, evidence_id)
            self.assertEqual(repeated["action"], "reused")
            self.assertTrue(repeated["promotion"]["reused"])
            self.assertEqual(list_curation_reviews(root, include_resolved=True), [])
            evidence = find_document_by_id(root, evidence_id)
            self.assertNotIn("curated_into", evidence.frontmatter)
            self.assertEqual(evidence_path.read_bytes(), evidence_before)
            batch = run_configured_curation_batch(root, limit=1)
            self.assertEqual(batch["attempted"], 0)

    def test_configured_adapter_creates_review_for_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: curated\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "manual", "domain": "marketing", "bundle_type": "manual",
                "title": "Curated manual", "summary": "Summary.", "body": "# Manual",
                "evidence_ids": [evidence_id], "tags": ["curated", "manual"],
                "slug": "curated-manual",
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()

            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "created_review")
            self.assertEqual(result["handoff"]["status"], "queued_for_review")
            self.assertEqual(len(list_curation_reviews(root)), 1)
            self.assertEqual(list_curation_candidates(root), [])
            review = next(iter((root / "curation-reviews").rglob("*.md")))
            self.assertIn("`curated-manual`", review.read_text(encoding="utf-8"))

    def test_configured_adapter_automatically_closes_a_valid_no_bundle_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: curated\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "no_bundle", "evidence_ids": [evidence_id],
                "rationale": "The Evidence duplicates existing knowledge.",
                "recheck_condition": "New non-duplicate Evidence arrives.",
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()

            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "no_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "no_bundle")
            self.assertEqual(result["decision"]["status"], "no_bundle")
            self.assertEqual(list_curation_reviews(root), [])
            self.assertEqual(list_curation_queue(root), [])

    def test_configured_curation_batch_counts_report_as_auto_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: report\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "report", "domain": "marketing", "bundle_type": "report",
                "title": "Batch report", "summary": "Summary.", "body": "# Report",
                "evidence_ids": [evidence_id], "tags": ["batch", "report"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "create_draft_bundle", "blocking_conditions": [], "candidate_bundles": []}
            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    batch = run_configured_curation_batch(root, limit=1)

            self.assertEqual(batch["counts"]["auto_promoted"], 1)
            self.assertEqual(batch["counts"]["draft_created"], 0)
            self.assertEqual(batch["items"][0]["result"]["promotion"]["promotion_mode"], "automatic")
            self.assertEqual(list_curation_candidates(root), [])

    def test_reused_review_consumes_a_repaired_queue_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence = find_document_by_id(root, evidence_id)
            output = self._output(evidence_id, "manual")
            first = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
            )
            enqueue_curation_work(root, evidence_id, evidence.path)

            reused = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
            )

            self.assertEqual(first["review_id"], reused["review_id"])
            self.assertEqual(reused["action"], "reused_review")
            self.assertEqual(list_curation_queue(root), [])

    def test_failed_review_approval_preserves_review_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = self._output(evidence_id, kind="guide")
            created = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/guide",
            )
            review_path = root.parent / created["path"]

            with patch(
                "circled_wiki.core.curation.materialize_curation_candidate",
                side_effect=ValueError("fixture failure"),
            ):
                with self.assertRaisesRegex(ValueError, "fixture failure"):
                    decide_curation_review(
                        root, created["review_id"], action="approve", actor="reviewer"
                    )

            self.assertTrue(review_path.is_file())
            self.assertEqual(parse_markdown(review_path).frontmatter["status"], "pending")

    def test_no_bundle_decision_discards_card_and_completes_curation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            review = generate_curation_review(
                root, evidence_id, self._output(evidence_id),
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/guide",
            )
            evidence_path = find_document_by_id(root, evidence_id).path
            evidence_before = evidence_path.read_bytes()

            decided = decide_curation_review(
                root, review["review_id"], action="no_bundle", actor="reviewer",
                note="Not suitable for a Bundle.",
            )

            self.assertTrue(decided["review_deleted"])
            self.assertFalse((root.parent / review["path"]).exists())
            self.assertEqual(evidence_path.read_bytes(), evidence_before)
            self.assertEqual(list_curation_queue(root), [])

    def test_high_confidence_reference_auto_promotes_without_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: reference\n  command: adapter\n",
                encoding="utf-8",
            )
            output = {
                "action": "reference", "domain": "marketing", "bundle_type": "reference",
                "title": "Campaign reference", "summary": "Reference summary.", "body": "# Reference",
                "evidence_ids": [evidence_id], "confidence": "high", "existing_bundle_candidates": [], "tags": ["campaign", "reference"],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "create_draft_bundle", "blocking_conditions": [], "candidate_bundles": []}
            with patch("circled_wiki.core.curation.propose_update", return_value=proposal):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, evidence_id)
            self.assertEqual(result["action"], "created")
            self.assertEqual(result["promotion"]["promotion_mode"], "automatic")
            self.assertEqual(list_curation_reviews(root), [])
            self.assertEqual(list_curation_candidates(root), [])

    def test_rebuildable_workspace_queue_tracks_pending_and_resolved_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            queue = list_curation_queue(root)
            self.assertEqual(queue[0]["evidence_id"], evidence_id)
            self.assertEqual(queue[0]["status"], "pending")
            self.assertTrue(queue[0]["path"].startswith("evidence/"))
            self.assertFalse(queue[0]["path"].startswith("knowledge/"))

            refreshed = refresh_curation_queue(root)
            queue_path = root.parent / refreshed["path"]
            self.assertTrue(queue_path.is_dir())
            queue_item = root.parent / queue[0]["queue_path"]
            task = parse_markdown(queue_item).frontmatter
            self.assertEqual(task["type"], "contract_task")
            self.assertEqual(task["contract"], {"name": "curation_reconciliation", "version": 1})
            self.assertEqual(task["evidence_id"], evidence_id)
            self.assertEqual(task["evidence_path"], queue[0]["path"])
            self.assertEqual(task["current"]["stage"], "queued")
            self.assertEqual(task["current"]["status"], "pending")
            self.assertTrue(task["step_receipts"])

            queue_item.unlink()
            repaired = refresh_curation_queue(root)
            self.assertEqual(repaired["created_count"], 1)
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

            queue_item.write_text("---\nevidence_id: wrong\n---\n", encoding="utf-8")
            malformed = root.parent / "workspace" / "task" / "curation_reconciliation" / "malformed.md"
            malformed.write_text("not frontmatter\n", encoding="utf-8")
            repaired = refresh_curation_queue(root)
            self.assertEqual(repaired["repaired_count"], 1)
            self.assertEqual(repaired["removed_count"], 1)
            self.assertFalse(malformed.exists())
            repaired_task = parse_markdown(queue_item).frontmatter
            self.assertEqual(repaired_task["contract"]["name"], "curation_reconciliation")
            self.assertEqual(repaired_task["current"]["status"], "pending")

            result = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id),
                generated_by="curator", curation_receipt="test://curation",
            )
            self.assertEqual(result["action"], "created")
            self.assertEqual(list_curation_queue(root), [])
            self.assertEqual(list((root.parent / "workspace" / "task" / "curation_reconciliation").glob("*.md")), [])

    def test_queue_repair_keeps_restricted_evidence_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence = find_document_by_id(root, evidence_id)
            restricted = dict(evidence.frontmatter)
            restricted["extensions"] = dict(restricted["extensions"], visibility="restricted")
            evidence.path.write_text(render_markdown(restricted, evidence.body), encoding="utf-8")

            refresh_curation_queue(root)

            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

    def test_concurrent_queue_registration_uses_independent_atomic_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence = find_document_by_id(root, evidence_id)

            with ThreadPoolExecutor(max_workers=8) as executor:
                paths = list(executor.map(
                    lambda _: enqueue_curation_work(root, evidence_id, evidence.path),
                    range(32),
                ))

            self.assertEqual(len(set(paths)), 1)
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)
            temporary_files = list(paths[0].parent.glob("*.tmp"))
            self.assertEqual(temporary_files, [])

    def test_queue_transaction_serializes_separate_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            context = multiprocessing.get_context("spawn")
            started = context.Event()
            acquired = context.Event()

            with curation_queue_transaction(root):
                process = context.Process(
                    target=_acquire_queue_transaction,
                    args=(str(root), started, acquired),
                )
                process.start()
                self.assertTrue(started.wait(5))
                self.assertFalse(acquired.wait(0.2))

            self.assertTrue(acquired.wait(5))
            process.join(5)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)

    def test_refresh_does_not_delete_queue_created_by_concurrent_ingest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            refresh_paused = threading.Event()
            resume_refresh = threading.Event()
            ingest_waiting_for_lock = threading.Event()
            original_queue_root = curation_queue._queue_root
            original_enqueue = curation_queue.enqueue_curation_work
            results = {}
            errors = []

            def gated_queue_root(value):
                if (
                    threading.current_thread().name == "refresh-thread"
                    and not refresh_paused.is_set()
                ):
                    refresh_paused.set()
                    resume_refresh.wait(5)
                return original_queue_root(value)

            def observed_enqueue(*args, **kwargs):
                ingest_waiting_for_lock.set()
                return original_enqueue(*args, **kwargs)

            def run_refresh():
                try:
                    results["refresh"] = refresh_curation_queue(root)
                except Exception as error:
                    errors.append(error)

            def run_ingest():
                try:
                    source = root / "inbox" / "manual" / "source.txt"
                    source.parent.mkdir(parents=True)
                    source.write_text("concurrent source", encoding="utf-8")
                    results["evidence"] = ingest_evidence(
                        root, source, "manual",
                        why_collected="queue race test",
                        intended_use=["queue-race"],
                    )
                except Exception as error:
                    errors.append(error)

            with (
                patch.object(curation_queue, "_queue_root", side_effect=gated_queue_root),
                patch.object(curation_queue, "enqueue_curation_work", side_effect=observed_enqueue),
            ):
                refresh_thread = threading.Thread(
                    name="refresh-thread", target=run_refresh
                )
                ingest_thread = threading.Thread(
                    name="ingest-thread", target=run_ingest
                )
                refresh_thread.start()
                self.assertTrue(refresh_paused.wait(5))
                ingest_thread.start()
                self.assertTrue(ingest_waiting_for_lock.wait(5))
                resume_refresh.set()
                refresh_thread.join(5)
                ingest_thread.join(5)

            self.assertFalse(refresh_thread.is_alive())
            self.assertFalse(ingest_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(results["evidence"].manifest_path.is_file())
            self.assertEqual(
                list_curation_queue(root)[0]["evidence_id"],
                results["evidence"].evidence_id,
            )

    def test_refresh_does_not_restore_queue_removed_by_concurrent_bundle_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            refresh_paused = threading.Event()
            resume_refresh = threading.Event()
            completion_waiting_for_lock = threading.Event()
            original_queue_root = curation_queue._queue_root
            original_complete = curation_queue.complete_curation_work
            errors = []

            def gated_queue_root(value):
                if (
                    threading.current_thread().name == "refresh-thread"
                    and not refresh_paused.is_set()
                ):
                    refresh_paused.set()
                    resume_refresh.wait(5)
                return original_queue_root(value)

            def observed_complete(*args, **kwargs):
                completion_waiting_for_lock.set()
                return original_complete(*args, **kwargs)

            def run_refresh():
                try:
                    refresh_curation_queue(root)
                except Exception as error:
                    errors.append(error)

            def run_bundle_creation():
                try:
                    create_bundle(
                        root,
                        domain="marketing",
                        slug="concurrent-guide",
                        title="Concurrent Guide",
                        bundle_type="guide",
                        summary="Queue race test.",
                        evidence_id=evidence_id,
                        tags=["concurrency", "guide"],
                    )
                except Exception as error:
                    errors.append(error)

            with (
                patch.object(curation_queue, "_queue_root", side_effect=gated_queue_root),
                patch.object(curation_queue, "complete_curation_work", side_effect=observed_complete),
            ):
                refresh_thread = threading.Thread(
                    name="refresh-thread", target=run_refresh
                )
                bundle_thread = threading.Thread(
                    name="bundle-thread", target=run_bundle_creation
                )
                refresh_thread.start()
                self.assertTrue(refresh_paused.wait(5))
                bundle_thread.start()
                self.assertTrue(completion_waiting_for_lock.wait(5))
                resume_refresh.set()
                refresh_thread.join(5)
                bundle_thread.join(5)

            self.assertFalse(refresh_thread.is_alive())
            self.assertFalse(bundle_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(list_curation_queue(root), [])

    def test_queue_scan_excludes_legacy_evidence_already_linked_by_a_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            create_bundle(
                root, domain="marketing", slug="existing-guide", title="Existing Guide",
                bundle_type="guide", summary="Existing.", evidence_id=evidence_id,
            )
            self.assertEqual(list_curation_queue(root), [])
            self.assertEqual(list_curation_queue(root, include_resolved=True), [])

    def test_queue_repair_does_not_trust_an_invalid_bundle_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            bundle = root / "bundles" / "marketing" / "invalid.md"
            bundle.parent.mkdir(parents=True)
            bundle.write_text(
                render_markdown({
                    "type": "guide",
                    "id": "invalid",
                    "evidence": [evidence_id],
                }),
                encoding="utf-8",
            )

            refresh_curation_queue(root)

            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

    def test_validator_rejects_curation_receipt_for_another_evidence_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence = find_document_by_id(root, evidence_id)
            data = dict(evidence.frontmatter)
            extensions = dict(data["extensions"])
            extensions["curation_attempt"] = {
                "receipt": {
                    "evidence_checksum": "sha256:" + "0" * 64,
                    "provider": "test", "model": "test", "profile_version": "v1",
                    "prompt_template_version": "v1", "result_schema_version": "v1",
                    "started_at": "2026-07-22T00:00:00+00:00", "status": "completed",
                },
            }
            data["extensions"] = extensions
            evidence.path.write_text(render_markdown(data, evidence.body), encoding="utf-8")

            validation = validate_document(evidence.path, root)

            self.assertIn(
                "extensions.curation_attempt.receipt.evidence_checksum must match the current Evidence checksum",
                validation.profile_errors,
            )

    def test_configured_adapter_enforces_nonwriting_proposal_blocking_conditions(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n  enabled: true\n  provider: test\n  model: blocked\n  command: noop\n",
                encoding="utf-8",
            )
            with patch(
                "circled_wiki.core.curation.propose_update",
                return_value={"recommended_action": "review_existing_bundle", "blocking_conditions": ["existing_bundle"]},
            ):
                result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["reason"], "proposal_blocked")
            self.assertFalse(result["stored"])
            self.assertEqual(list_curation_candidates(root), [])
            self.assertEqual(list_curation_reviews(root), [])
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

    def test_stale_update_review_is_archived_and_evidence_is_requeued(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root, domain="marketing", slug="existing",
                title="Existing", bundle_type="guide", summary="Existing.",
                evidence_id=evidence_id,
            )
            output = validate_curation_output({
                "action": "guide",
                "domain": "marketing",
                "bundle_type": "guide",
                "title": "Update existing",
                "summary": "Update.",
                "body": "# Update",
                "evidence_ids": [evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "replace_full",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "replace_reason": "Reviewer approved a complete rewrite.",
                "tags": ["marketing", "update"],
            }, [evidence_id])
            review = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/update",
            )
            proposed = dict(target.frontmatter)
            apply_bundle_revision(
                root,
                bundle_id=str(target.frontmatter["id"]),
                expected_revision=1,
                proposed_frontmatter=proposed,
                body=target.body + "\nChanged.\n",
                actor="editor",
            )

            with self.assertRaisesRegex(ValueError, "review is stale"):
                decide_curation_review(
                    root, review["review_id"], action="approve", actor="reviewer",
                )

            self.assertEqual(list_curation_reviews(root), [])
            archived = list((root / "curation-reviews" / ".archive").rglob("*.md"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(parse_markdown(archived[0]).frontmatter["status"], "stale")
            self.assertEqual(list((root.parent / "workspace" / "notifications" / "inbox").glob("notification-*.json")), [])
            self.assertEqual(len(list((root.parent / "workspace" / "notifications" / "archive").glob("notification-*.json"))), 1)
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)
            refreshed = refresh_curation_queue(root)
            self.assertEqual(refreshed["pending_count"], 1)

            current = find_document_by_id(root, target.frontmatter["id"])
            output = replace(
                output,
                base_body_checksum="sha256:" + hashlib.sha256(current.body.encode("utf-8")).hexdigest(),
            )

            replacement = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
                user_review_request="user-request://test/update",
            )
            self.assertNotEqual(replacement["review_id"], review["review_id"])
            self.assertEqual(list_curation_queue(root), [])
            self.assertEqual(refresh_curation_queue(root)["pending_count"], 0)

    def test_stale_review_rolls_back_archive_when_requeue_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            target = create_bundle(
                root,
                domain="marketing",
                slug="rollback-target",
                title="Rollback target",
                bundle_type="guide",
                summary="Existing.",
                evidence_id=evidence_id,
            )
            output = validate_curation_output({
                "action": "guide",
                "domain": "marketing",
                "bundle_type": "guide",
                "title": "Update target",
                "summary": "Update.",
                "body": "# Update",
                "evidence_ids": [evidence_id],
                "existing_bundle_candidates": [target.frontmatter["id"]],
                "update_mode": "replace_full",
                "base_body_checksum": "sha256:" + hashlib.sha256(target.body.encode("utf-8")).hexdigest(),
                "replace_reason": "Reviewer approved a complete rewrite.",
                "tags": ["marketing", "update"],
            }, [evidence_id])
            review = generate_curation_review(
                root,
                evidence_id,
                output,
                generated_by="curator",
                curation_receipt="test://curation",
                user_review_request="user-request://test/update",
            )
            apply_bundle_revision(
                root,
                bundle_id=str(target.frontmatter["id"]),
                expected_revision=1,
                proposed_frontmatter=dict(target.frontmatter),
                body=target.body + "\nChanged.\n",
                actor="editor",
            )

            with (
                patch(
                    "circled_wiki.core.curation_reviews._enqueue_curation_work_unlocked",
                    side_effect=OSError("queue unavailable"),
                ),
                self.assertRaisesRegex(OSError, "queue unavailable"),
            ):
                decide_curation_review(
                    root,
                    review["review_id"],
                    action="approve",
                    actor="reviewer",
                )

            review_path = root.parent / review["path"]
            self.assertTrue(review_path.is_file())
            self.assertEqual(
                parse_markdown(review_path).frontmatter["status"], "pending"
            )
            self.assertEqual(
                list((root / "curation-reviews" / ".archive").rglob("*.md")), []
            )
            self.assertEqual(list_curation_queue(root), [])
