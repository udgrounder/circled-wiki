import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from circled_wiki.core.candidates import curation_backlog_metrics, curation_candidate_digest, curation_daily_transitions, list_curation_candidates, review_curation_candidate
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.ingest import ingest_evidence
from circled_wiki.core.repository import create_bundle, find_document_by_id
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.validator import validate_document, validate_repository


class CurationCandidateTests(unittest.TestCase):
    def _candidate(self, directory: str, slug: str = "candidate"):
        knowledge_root = Path(directory) / "knowledge"
        source = knowledge_root / "inbox" / "manual" / f"{slug}.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("source", encoding="utf-8")
        evidence = ingest_evidence(
            knowledge_root, source, "manual",
            why_collected="candidate test", intended_use=["candidate-test"],
        )
        bundle = create_bundle(
            knowledge_root, domain="operations", slug=slug, title=f"{slug} candidate",
            bundle_type="guide", summary="candidate summary", evidence_id=evidence.evidence_id,
            curated_by="test-curator",
        )
        return knowledge_root, bundle

    def test_lists_draft_candidates_without_exposing_active_bundles(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle = self._candidate(directory)

            candidates = list_curation_candidates(knowledge_root)

            self.assertEqual([item["id"] for item in candidates], [bundle.frontmatter["id"]])
            self.assertEqual(candidates[0]["review_state"], "pending")
            hits = KnowledgeService(knowledge_root).search_knowledge("candidate")
            self.assertNotIn(bundle.frontmatter["id"], [item["id"] for item in hits])

    def test_approval_records_review_but_does_not_activate_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle = self._candidate(directory)

            result = review_curation_candidate(
                knowledge_root, bundle.frontmatter["id"], action="approve", actor="reviewer"
            )

            self.assertEqual(result["status"], "draft")
            self.assertEqual(result["review_state"], "approved")
            self.assertTrue(all(item.is_valid for item in validate_repository(knowledge_root)))

    def test_rejection_archives_candidate_with_audit_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle = self._candidate(directory)

            result = review_curation_candidate(
                knowledge_root, bundle.frontmatter["id"], action="reject", actor="reviewer",
                note="not useful enough",
            )

            self.assertEqual(result["status"], "archived")
            self.assertEqual(result["review_state"], "rejected")
            self.assertTrue(result["path"].startswith("bundles/archive/"))
            self.assertTrue(all(item.is_valid for item in validate_repository(knowledge_root)))

    def test_rejects_invalid_curation_review_history(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle = self._candidate(directory)
            document = parse_markdown(bundle.path)
            data = dict(document.frontmatter)
            data["extensions"] = dict(data["extensions"], curation={
                "review_history": [{"action": "approve", "actor": "", "at": "not-a-time", "note": 1}]
            })
            bundle.path.write_text(render_markdown(data, document.body), encoding="utf-8")

            errors = validate_document(bundle.path, knowledge_root).profile_errors

            self.assertIn("extensions.curation.review_history.actor must be non-empty", errors)
            self.assertIn("extensions.curation.review_history.at must be ISO 8601", errors)
            self.assertIn("extensions.curation.review_history.note must be a string", errors)

    def test_digest_counts_pending_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, _ = self._candidate(directory)
            digest = curation_candidate_digest(knowledge_root)
            self.assertEqual(digest["candidate_count"], 1)
            self.assertEqual(digest["by_review_state"]["pending"], 1)

    def test_backlog_metrics_counts_new_evidence_and_candidate_domain(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, _ = self._candidate(directory)
            metrics = curation_backlog_metrics(knowledge_root)
            self.assertEqual(metrics["evidence_total"], 1)
            self.assertEqual(metrics["evidence_new"], 0)
            self.assertEqual(metrics["candidate_domains"], {"operations": 1})

    def test_daily_transition_metrics_include_creation_and_review_action(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle = self._candidate(directory)
            document = parse_markdown(bundle.path)
            data = dict(document.frontmatter)
            extensions = dict(data["extensions"])
            evidence = find_document_by_id(knowledge_root, document.frontmatter["evidence"][0])
            extensions["curation"] = {
                "generated_by": "test-curator",
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "generation_reason": "test",
                "evidence_checksum": evidence.frontmatter["checksum"],
                "curation_receipt": "test://curation",
                "recommendation": "guide",
                "profile_version": "v1",
            }
            # The metric only needs an ISO timestamp; validation is not the subject of this test.
            data["extensions"] = extensions
            bundle.path.write_text(render_markdown(data, document.body), encoding="utf-8")
            review_curation_candidate(
                knowledge_root, bundle.frontmatter["id"], action="needs_changes", actor="reviewer"
            )

            transitions = curation_daily_transitions(knowledge_root)

            self.assertEqual(transitions["created"], 1)
            self.assertEqual(transitions["needs_changes"], 1)
            self.assertEqual(curation_backlog_metrics(knowledge_root)["candidate_daily_transitions"], transitions)

    def test_validator_rejects_incomplete_generated_curation_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle = self._candidate(directory)
            document = parse_markdown(bundle.path)
            data = dict(document.frontmatter)
            data["extensions"] = dict(data["extensions"], curation={"generated_by": "agent"})
            bundle.path.write_text(render_markdown(data, document.body), encoding="utf-8")
            errors = validate_document(bundle.path, knowledge_root).profile_errors
            self.assertIn("extensions.curation.curation_receipt must be non-empty", errors)


if __name__ == "__main__":
    unittest.main()
