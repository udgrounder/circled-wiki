import tempfile
import unittest
import sys
import json
from unittest.mock import patch
from pathlib import Path

from knowledge_os.core.curation import materialize_curation_candidate
from knowledge_os.core.curation import run_configured_curation, run_configured_curation_batch
from knowledge_os.core.curation_contract import validate_curation_output
from knowledge_os.core.ingest import ingest_evidence
from knowledge_os.core.frontmatter import render_markdown
from knowledge_os.core.pii import record_pii_scan_receipt
from knowledge_os.core.service import KnowledgeService
from knowledge_os.core.candidates import list_curation_candidates
from knowledge_os.core.repository import apply_bundle_revision, find_document_by_id
from knowledge_os.core.validator import validate_document
from knowledge_os.core.candidates import promote_curation_candidate, review_curation_candidate
from knowledge_os.core.curation_reviews import (
    decide_curation_review,
    generate_curation_review,
    list_curation_reviews,
)


class CurationMaterializationTests(unittest.TestCase):
    def _evidence(self, directory):
        root = Path(directory) / "knowledge"
        source = root / "inbox" / "manual" / "source.txt"
        source.parent.mkdir(parents=True); source.write_text("campaign procedure", encoding="utf-8")
        evidence = ingest_evidence(root, source, "manual", why_collected="test", intended_use=["marketing"])
        record_pii_scan_receipt(root, evidence.evidence_id, scanner="test", scanner_version="1", result="passed", reviewed_by="security", receipt="test://pii")
        return root, evidence.evidence_id

    def _output(self, evidence_id, kind="runbook"):
        return validate_curation_output({"action": kind, "domain": "marketing", "bundle_type": kind, "title": "SNS campaign launch", "summary": "Launch a campaign.", "body": "# Steps\n\n1. Define audience.", "evidence_ids": [evidence_id], "rationale": "repeatable process", "limitations": "budget omitted", "existing_bundle_candidates": [], "confidence": "medium"}, [evidence_id])

    def test_creates_candidate_and_reuses_same_evidence_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            first = materialize_curation_candidate(root, evidence_id, self._output(evidence_id), generated_by="curator", curation_receipt="test://curation")
            second = materialize_curation_candidate(root, evidence_id, self._output(evidence_id), generated_by="curator", curation_receipt="test://curation")
            self.assertEqual(first["action"], "created")
            self.assertEqual(second["action"], "reused")

    def test_blocks_evidence_without_pii_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            source = root / "inbox" / "manual" / "source.txt"; source.parent.mkdir(parents=True); source.write_text("source", encoding="utf-8")
            evidence = ingest_evidence(root, source, "manual", why_collected="test", intended_use=["marketing"])
            with self.assertRaisesRegex(ValueError, "PII Scan Receipt"):
                materialize_curation_candidate(root, evidence.evidence_id, self._output(evidence.evidence_id), generated_by="curator", curation_receipt="test://curation")

    def test_service_is_the_external_adapter_write_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            result = KnowledgeService(root).materialize_curation_candidate(
                evidence_id, output={"action": "runbook", "domain": "marketing", "bundle_type": "runbook", "title": "SNS campaign launch", "summary": "Launch a campaign.", "body": "# Steps", "evidence_ids": [evidence_id]},
                generated_by="curator", curation_receipt="test://curation",
            )
            self.assertEqual(result["action"], "created")
            candidate = list_curation_candidates(root)[0]
            self.assertEqual(candidate["recommendation"], "runbook")
            self.assertEqual(candidate["confidence"], "")

    def test_general_revision_api_cannot_promote_curation_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            result = materialize_curation_candidate(root, evidence_id, self._output(evidence_id), generated_by="curator", curation_receipt="test://curation")
            bundle = find_document_by_id(root, result["bundle_id"])
            proposed = dict(bundle.frontmatter)
            proposed["status"] = "active"
            with self.assertRaisesRegex(ValueError, "Owner and Security"):
                apply_bundle_revision(root, bundle_id=result["bundle_id"], expected_revision=1, proposed_frontmatter=proposed, body=bundle.body, actor="reviewer")

    def test_configured_owner_with_security_receipt_promotes_approved_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text("schema_version: 1\napproval:\n  knowledge_owner: alice\n", encoding="utf-8")
            created = materialize_curation_candidate(root, evidence_id, self._output(evidence_id, "guide"), generated_by="curator", curation_receipt="test://curation")
            review_curation_candidate(root, created["bundle_id"], action="approve", actor="reviewer")
            with self.assertRaisesRegex(ValueError, "configured knowledge-owner"):
                promote_curation_candidate(root, created["bundle_id"], actor="mallory", security_receipt="security://1")
            result = promote_curation_candidate(root, created["bundle_id"], actor="alice", security_receipt="security://1")
            self.assertEqual(result["status"], "active")

    def test_candidate_review_rejects_generating_actor_self_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            created = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id, "guide"),
                generated_by="curator", curation_receipt="test://curation",
            )

            with self.assertRaisesRegex(ValueError, "reviewer must differ"):
                review_curation_candidate(root, created["bundle_id"], action="approve", actor="curator")

            candidate = list_curation_candidates(root)[0]
            self.assertEqual(candidate["review_state"], "pending")

    def test_active_promotion_requires_configured_owner_and_security_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            created = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id, "guide"),
                generated_by="curator", curation_receipt="test://curation",
            )
            review_curation_candidate(root, created["bundle_id"], action="approve", actor="reviewer")

            with self.assertRaisesRegex(ValueError, "knowledge_owner is configured"):
                promote_curation_candidate(root, created["bundle_id"], actor="reviewer", security_receipt="security://1")

            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text("schema_version: 1\napproval:\n  knowledge_owner: reviewer\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "security_receipt is required"):
                promote_curation_candidate(root, created["bundle_id"], actor="reviewer", security_receipt="")

    def test_no_bundle_decision_is_persisted_without_processing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = validate_curation_output(
                {"action": "no_bundle", "rationale": "Not reusable.", "recheck_condition": "More sources arrive."},
                [evidence_id],
            )
            result = materialize_curation_candidate(root, evidence_id, output, generated_by="curator", curation_receipt="test://curation")
            evidence = find_document_by_id(root, evidence_id)
            self.assertTrue(result["stored"])
            self.assertEqual(evidence.frontmatter["status"], "new")
            self.assertEqual(evidence.frontmatter["extensions"]["curation_no_bundle"]["rationale"], "Not reusable.")

    def test_korean_title_uses_checksum_slug_without_uuid_prefix_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide", "title": "한국어 SNS 가이드",
                "summary": "요약", "body": "# 본문", "evidence_ids": [evidence_id],
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
            self.assertFalse(result["stored"])

    def test_configured_curation_batch_reports_bounded_needs_review_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            report = run_configured_curation_batch(root, limit=1)

            self.assertEqual(report["attempted"], 1)
            self.assertEqual(report["counts"]["needs_review"], 1)
            self.assertEqual(report["items"][0]["evidence_id"], evidence_id)
            self.assertEqual(report["usage"]["tokens"], "unknown")

    def test_invalid_adapter_output_records_safe_needs_review_receipt_without_bundle(self):
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

            self.assertEqual(result, {"action": "needs_review", "evidence_id": evidence_id, "stored": True, "reason": "invalid_json"})
            self.assertEqual(list_curation_candidates(root), [])
            evidence = find_document_by_id(root, evidence_id)
            attempt = evidence.frontmatter["extensions"]["curation_attempt"]
            self.assertEqual(attempt["status"], "needs_review")
            self.assertEqual(attempt["failure_kind"], "invalid_json")
            self.assertEqual(attempt["receipt"]["evidence_checksum"], evidence.frontmatter["checksum"])
            self.assertEqual(attempt["receipt"]["prompt_template_version"], "v1")
            self.assertEqual(attempt["receipt"]["result_schema_version"], "v1")
            self.assertEqual(attempt["receipt"]["status"], "invalid_json")
            self.assertNotIn("not-json", str(attempt))

    def test_configured_adapter_creates_review_then_approval_creates_candidate(self):
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
                "action": "guide", "domain": "marketing", "bundle_type": "guide",
                "title": "Curated guide", "summary": "Summary.", "body": "# Guide",
                "evidence_ids": [evidence_id],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            with patch("knowledge_os.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("knowledge_os.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "created_review")
            self.assertEqual(list_curation_candidates(root), [])
            review = list_curation_reviews(root)[0]
            self.assertEqual(review["recommendation"], "create_draft_bundle")
            self.assertEqual(review["evidence_refs"][0]["evidence_id"], evidence_id)
            with patch("knowledge_os.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("knowledge_os.core.curation.subprocess.run", return_value=completed):
                    repeated = run_configured_curation(root, evidence_id)
            self.assertEqual(repeated["action"], "reused_review")
            self.assertEqual(len(list_curation_reviews(root)), 1)
            review_path = root.parent / review["path"]
            self.assertTrue(review_path.is_file())
            applied = decide_curation_review(root, review["review_id"], action="approve", actor="reviewer")
            self.assertEqual(applied["status"], "applied")
            self.assertTrue(applied["review_deleted"])
            self.assertEqual(applied["result"]["action"], "created")
            self.assertFalse(review_path.exists())
            self.assertEqual(list_curation_reviews(root, include_resolved=True), [])
            candidate = find_document_by_id(root, applied["result"]["bundle_id"])
            receipt = candidate.frontmatter["extensions"]["curation"]["receipt"]
            self.assertEqual(receipt["provider"], "test")
            self.assertEqual(receipt["model"], "curated")
            self.assertEqual(receipt["status"], "completed")
            self.assertIn("completed_at", receipt)
            decision = candidate.frontmatter["extensions"]["curation"]["review_decision"]
            self.assertEqual(decision["review_id"], review["review_id"])
            self.assertEqual(decision["decided_by"], "reviewer")
            evidence = find_document_by_id(root, evidence_id)
            self.assertIn(candidate.frontmatter["id"], evidence.frontmatter["curated_into"])
            self.assertNotIn("curation_review", evidence.frontmatter["extensions"])

    def test_failed_review_approval_preserves_review_card(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            output = self._output(evidence_id, kind="guide")
            created = generate_curation_review(
                root, evidence_id, output,
                generated_by="curator", curation_receipt="test://curation",
            )
            review_path = root.parent / created["path"]

            with patch(
                "knowledge_os.core.curation.materialize_curation_candidate",
                side_effect=ValueError("fixture failure"),
            ):
                with self.assertRaisesRegex(ValueError, "fixture failure"):
                    decide_curation_review(
                        root, created["review_id"], action="approve", actor="reviewer"
                    )

            self.assertTrue(review_path.is_file())
            evidence = find_document_by_id(root, evidence_id)
            self.assertEqual(
                evidence.frontmatter["extensions"]["curation_review"]["status"],
                "pending",
            )

    def test_opted_in_high_confidence_reference_can_create_draft_without_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(exist_ok=True)
            config.write_text(
                "schema_version: 1\ncuration:\n"
                "  enabled: true\n  provider: test\n  model: reference\n  command: adapter\n"
                "  auto_materialize_reference: true\n",
                encoding="utf-8",
            )
            output = {
                "action": "reference", "domain": "marketing", "bundle_type": "reference",
                "title": "Campaign reference", "summary": "Reference summary.", "body": "# Reference",
                "evidence_ids": [evidence_id], "confidence": "high", "existing_bundle_candidates": [],
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()
            proposal = {"recommended_action": "create_draft_bundle", "blocking_conditions": [], "candidate_bundles": []}
            with patch("knowledge_os.core.curation.propose_update", return_value=proposal):
                with patch("knowledge_os.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, evidence_id)
            self.assertEqual(result["action"], "created")
            self.assertEqual(list_curation_reviews(root), [])
            candidate = find_document_by_id(root, result["bundle_id"])
            self.assertEqual(candidate.frontmatter["type"], "reference")

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
                "knowledge_os.core.curation.propose_update",
                return_value={"recommended_action": "review_existing_bundle", "blocking_conditions": ["existing_bundle"]},
            ):
                result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["reason"], "proposal_blocked")
            self.assertTrue(result["stored"])
            self.assertEqual(list_curation_candidates(root), [])
