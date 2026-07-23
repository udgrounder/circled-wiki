import tempfile
import unittest
import hashlib
from pathlib import Path
from uuid import uuid4

from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.governance import audit_knowledge, list_knowledge_inventory, validate_claim_support
from circled_wiki.core.search import search_knowledge


class GovernanceTests(unittest.TestCase):
    def _repository(self, directory: str) -> tuple[Path, str, str]:
        root = Path(directory) / "knowledge"
        evidence_uuid = str(uuid4())
        bundle_uuid = str(uuid4())
        evidence_id = f"evidence://example-org/manual/2026/07/14/{evidence_uuid}"
        bundle_id = f"knowledge://example-org/ops/audit-policy_{bundle_uuid}"
        evidence_path = root / "evidence" / "manual" / "2026" / "07" / "14" / f"source_{evidence_uuid}.md"
        bundle_path = root / "bundles" / "ops" / f"audit-policy_{bundle_uuid}.md"
        evidence_path.parent.mkdir(parents=True)
        bundle_path.parent.mkdir(parents=True)
        evidence_path.write_text(render_markdown({
            "type": "evidence", "id": evidence_id, "title": "Audit source",
            "source_uuid": evidence_uuid, "provider": "manual",
            "source_ref": {"provider": "manual", "captured_from": "manual"},
            "captured_at": "2026-07-14T00:00:00+00:00", "status": "processed",
            "checksum": "sha256:" + hashlib.sha256(b"source").hexdigest(), "original_file": "source.txt",
            "original_file_git_tracked": True, "curated_into": [bundle_id],
            "extensions": {"availability": "available", "capture_context": {
                "why_collected": "governance test", "intended_use": ["audit-policy"]
            }},
        }), encoding="utf-8")
        (evidence_path.parent / "source.txt").write_text("source", encoding="utf-8")
        bundle_path.write_text(render_markdown({
            "type": "policy", "id": bundle_id, "bundle_uuid": bundle_uuid,
            "title": "Audit Policy", "status": "active", "summary": "governance audit policy",
            "updated_at": "2026-07-14T00:00:00+00:00", "owners": ["ops-owner"],
            "evidence": [evidence_id], "links": [], "extensions": {
                "knowledge_revision": 1, "governance": {
                    "reviewed_at": "2025-01-01T00:00:00+00:00",
                    "review_due_at": "2025-12-31T00:00:00+00:00",
                    "freshness_policy": "annual",
                }
            },
        }), encoding="utf-8")
        return root, bundle_id, evidence_id

    def test_inventory_audit_and_claim_support_are_derived(self):
        with tempfile.TemporaryDirectory() as directory:
            root, bundle_id, evidence_id = self._repository(directory)
            runtime_root = Path(directory) / ".runtime"

            inventory = list_knowledge_inventory(root, runtime_root)
            audit = audit_knowledge(root, runtime_root)
            claims = validate_claim_support(root, [{
                "claim": "Audit Policy is active", "support_status": "verified",
                "evidence_ids": [evidence_id], "limitations": [],
            }])

            self.assertEqual(inventory[0]["id"], bundle_id)
            self.assertEqual(inventory[0]["freshness_state"], "expired")
            self.assertIn("review_overdue", [issue["code"] for issue in audit["issues"]])
            self.assertTrue(claims["valid"])
            self.assertFalse(claims["semantic_entailment_validated"])

    def test_default_search_excludes_non_active_bundles(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self._repository(directory)
            bundle_path = next((root / "bundles").rglob("*.md"))
            text = bundle_path.read_text(encoding="utf-8").replace("status: active", "status: archived")
            bundle_path.write_text(text, encoding="utf-8")

            self.assertEqual(search_knowledge(root, "governance", {"type": "policy"}), [])
            self.assertEqual(len(search_knowledge(
                root, "governance", {"type": "policy", "status": "archived"}
            )), 1)

    def test_search_matches_natural_korean_question_by_meaningful_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root, bundle_id, _ = self._repository(directory)
            bundle_path = next((root / "bundles").rglob("*.md"))
            document = parse_markdown(bundle_path)
            data = dict(document.frontmatter)
            data["title"] = "신규 입사자 장비 지급 절차"
            data["summary"] = "신규 입사자의 장비와 계정을 준비한다."
            bundle_path.write_text(render_markdown(data, document.body), encoding="utf-8")

            hits = search_knowledge(root, "신규 입사자 입사 시 어떤 것을 해야 하나요?")

            self.assertEqual([hit.document_id for hit in hits], [bundle_id])

    def test_inventory_excludes_restricted_bundle_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self._repository(directory)
            bundle_path = next((root / "bundles").rglob("*.md"))
            document = parse_markdown(bundle_path)
            data = dict(document.frontmatter)
            data["extensions"] = dict(data["extensions"], visibility="restricted")
            bundle_path.write_text(render_markdown(data, document.body), encoding="utf-8")

            self.assertEqual(list_knowledge_inventory(root, Path(directory) / ".runtime"), [])
