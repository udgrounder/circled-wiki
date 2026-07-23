import tempfile
import unittest
from pathlib import Path

from knowledge_os.core.candidates import promote_curation_candidate, review_curation_candidate
from knowledge_os.core.curation import materialize_curation_candidate
from knowledge_os.core.curation_contract import validate_curation_output
from knowledge_os.core.ingest import ingest_evidence
from knowledge_os.core.pii import record_pii_scan_receipt
from knowledge_os.core.service import KnowledgeService


class KoreanQueryQualityTests(unittest.TestCase):
    def test_sns_marketing_query_finds_active_curated_knowledge_with_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            config = root.parent / ".circled-wiki" / "config.yaml"
            config.parent.mkdir(); config.write_text("schema_version: 1\napproval:\n  knowledge_owner: owner\n", encoding="utf-8")
            source = root / "inbox" / "manual" / "sns.txt"; source.parent.mkdir(parents=True)
            source.write_text("SNS 마케팅 캠페인 목표와 채널을 정한다.", encoding="utf-8")
            evidence = ingest_evidence(root, source, "manual", why_collected="quality test", intended_use=["sns-marketing"])
            record_pii_scan_receipt(root, evidence.evidence_id, scanner="test", scanner_version="1", result="passed", reviewed_by="security", receipt="test://pii")
            output = validate_curation_output({
                "action": "guide", "domain": "marketing", "bundle_type": "guide", "title": "SNS 마케팅 시작 가이드",
                "summary": "캠페인 목표와 채널을 정하는 방법", "body": "# SNS 마케팅\n\n목표와 고객을 먼저 정한다.",
                "evidence_ids": [evidence.evidence_id],
            }, [evidence.evidence_id])
            created = materialize_curation_candidate(root, evidence.evidence_id, output, generated_by="curator", curation_receipt="test://curation")
            review_curation_candidate(root, created["bundle_id"], action="approve", actor="reviewer")
            promote_curation_candidate(root, created["bundle_id"], actor="owner", security_receipt="security://1")
            service = KnowledgeService(root)

            hits = service.search_knowledge("SNS 마케팅")
            bundle = service.read_bundle(created["bundle_id"])

            self.assertEqual([hit["id"] for hit in hits], [created["bundle_id"]])
            self.assertEqual(bundle["sources"][0]["evidence_id"], evidence.evidence_id)
            self.assertEqual(bundle["sources"][0]["kind"], "preserved_evidence")
            self.assertTrue(bundle["sources"][0]["uri"].startswith("evidence/manual/"))
            self.assertNotIn("://", bundle["sources"][0]["uri"])
            self.assertTrue(bundle["sources"][0]["uri"].endswith(".md"))
            self.assertEqual(service.search_knowledge("존재하지 않는 주제"), [])
