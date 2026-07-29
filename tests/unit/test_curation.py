import tempfile
import unittest
import sys
import json
import hashlib
from unittest.mock import patch
from pathlib import Path

from circled_wiki.core.curation import materialize_curation_candidate
from circled_wiki.core.curation import run_configured_curation, run_configured_curation_batch
from circled_wiki.core.curation_contract import validate_curation_output
from circled_wiki.core.ingest import ingest_evidence
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.pii import build_pii_scan_receipt
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.candidates import list_curation_candidates
from circled_wiki.core.repository import apply_bundle_revision, create_bundle, find_document_by_id
from circled_wiki.core.validator import validate_document
from circled_wiki.core.candidates import promote_curation_candidate, review_curation_candidate
from circled_wiki.core.curation_reviews import (
    decide_curation_review,
    generate_curation_review,
    list_curation_reviews,
)
from circled_wiki.core.curation_queue import list_curation_queue, refresh_curation_queue


class CurationMaterializationTests(unittest.TestCase):
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
        return validate_curation_output({"action": kind, "domain": "marketing", "bundle_type": kind, "title": "SNS campaign launch", "summary": "Launch a campaign.", "body": "# Steps\n\n1. Define audience.", "evidence_ids": [evidence_id], "rationale": "repeatable process", "limitations": "budget omitted", "existing_bundle_candidates": [], "confidence": "medium", "tags": ["sns", "campaign"]}, [evidence_id])

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
            review = generate_curation_review(
                root, evidence_id, self._output(evidence_id, "manual"),
                generated_by="curator", curation_receipt="test://curation",
            )

            applied = decide_curation_review(
                root, review["review_id"], action="approve", actor="manual-owner",
            )

            bundle = find_document_by_id(root, applied["result"]["bundle_id"])
            self.assertEqual(bundle.frontmatter["type"], "manual")
            self.assertEqual(
                bundle.frontmatter["extensions"]["curation"]["review_decision"]["review_id"],
                review["review_id"],
            )
            self.assertTrue(applied["review_deleted"])
            review_path = root.parent / review["path"]
            self.assertFalse(review_path.exists())

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

            self.assertEqual(result["action"], "needs_review")
            self.assertEqual(result["evidence_id"], evidence_id)
            self.assertTrue(result["stored"])
            self.assertEqual(result["reason"], "invalid_json")
            self.assertEqual(list_curation_candidates(root), [])
            evidence = find_document_by_id(root, evidence_id)
            self.assertNotIn("curation_attempt", evidence.frontmatter["extensions"])
            cards = list_curation_reviews(root)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["review_id"], result["review_id"])

    def test_configured_adapter_directly_creates_report_draft(self):
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
            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed) as adapter:
                    result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "created")
            request = json.loads(adapter.call_args.kwargs["input"])
            self.assertEqual(
                {item["type"] for item in request["bundle_taxonomy"]},
                {"policy", "guide", "runbook", "manual", "decision", "spec", "reference", "report"},
            )
            self.assertEqual(request["pre_creation_review_types"], ["manual", "runbook"])
            self.assertEqual(len(list_curation_candidates(root)), 1)
            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    repeated = run_configured_curation(root, evidence_id)
            self.assertEqual(repeated["action"], "reused")
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
            }
            completed = type("Completed", (), {"stdout": json.dumps(output)})()

            with patch("circled_wiki.core.curation.propose_update", return_value={"recommended_action": "create_draft_bundle", "blocking_conditions": []}):
                with patch("circled_wiki.core.curation.subprocess.run", return_value=completed):
                    result = run_configured_curation(root, evidence_id)

            self.assertEqual(result["action"], "created_review")
            self.assertEqual(len(list_curation_reviews(root)), 1)
            self.assertEqual(list_curation_candidates(root), [])

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

    def test_high_confidence_reference_directly_creates_draft(self):
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
            self.assertEqual(list_curation_reviews(root), [])
            self.assertEqual(len(list_curation_candidates(root)), 1)

    def test_rebuildable_workspace_queue_tracks_pending_and_resolved_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            queue = list_curation_queue(root)
            self.assertEqual(queue[0]["evidence_id"], evidence_id)
            self.assertEqual(queue[0]["status"], "pending")

            refreshed = refresh_curation_queue(root)
            queue_path = root.parent / refreshed["path"]
            self.assertTrue(queue_path.is_dir())
            queue_item = root.parent / queue[0]["queue_path"]
            self.assertEqual(
                parse_markdown(queue_item).frontmatter,
                {"evidence_id": evidence_id, "evidence_path": queue[0]["path"]},
            )

            queue_item.unlink()
            repaired = refresh_curation_queue(root)
            self.assertEqual(repaired["created_count"], 1)
            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

            queue_item.write_text("---\nevidence_id: wrong\n---\n", encoding="utf-8")
            malformed = root.parent / "workspace" / "task" / "curation-queue" / "malformed.md"
            malformed.write_text("not frontmatter\n", encoding="utf-8")
            repaired = refresh_curation_queue(root)
            self.assertEqual(repaired["repaired_count"], 1)
            self.assertEqual(repaired["removed_count"], 1)
            self.assertFalse(malformed.exists())
            self.assertEqual(
                parse_markdown(queue_item).frontmatter,
                {"evidence_id": evidence_id, "evidence_path": queue[0]["path"]},
            )

            result = materialize_curation_candidate(
                root, evidence_id, self._output(evidence_id),
                generated_by="curator", curation_receipt="test://curation",
            )
            self.assertEqual(result["action"], "created")
            self.assertEqual(list_curation_queue(root), [])

    def test_queue_repair_keeps_restricted_evidence_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root, evidence_id = self._evidence(directory)
            evidence = find_document_by_id(root, evidence_id)
            restricted = dict(evidence.frontmatter)
            restricted["extensions"] = dict(restricted["extensions"], visibility="restricted")
            evidence.path.write_text(render_markdown(restricted, evidence.body), encoding="utf-8")

            refresh_curation_queue(root)

            self.assertEqual(list_curation_queue(root)[0]["evidence_id"], evidence_id)

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
            self.assertTrue(result["stored"])
            self.assertEqual(list_curation_candidates(root), [])
