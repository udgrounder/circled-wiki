import tempfile
import unittest
from pathlib import Path

from knowledge_os.core.frontmatter import parse_markdown, render_markdown
from knowledge_os.core.ingest import ingest_evidence
from knowledge_os.core.pii import record_pii_scan_receipt
from knowledge_os.core.publisher import PublishError, _require_sensitive_data_review
from knowledge_os.core.validator import validate_document


class PiiScanReceiptTests(unittest.TestCase):
    def _ingest(self, directory: str):
        knowledge_root = Path(directory) / "knowledge"
        source = knowledge_root / "inbox" / "manual" / "sample.txt"
        source.parent.mkdir(parents=True)
        source.write_text("masked sample", encoding="utf-8")
        result = ingest_evidence(
            knowledge_root, source, "manual",
            why_collected="PII gate test", intended_use=["security-test"],
        )
        return knowledge_root, result

    def test_receipt_is_bound_to_current_evidence_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, ingested = self._ingest(directory)
            recorded = record_pii_scan_receipt(
                knowledge_root, ingested.evidence_id,
                scanner="manual-review", scanner_version="policy-1",
                result="passed", reviewed_by="security-agent",
                receipt="review://local/pii-001",
                scanned_at="2026-07-22T10:00:00+09:00",
            )
            document = parse_markdown(ingested.manifest_path)
            self.assertTrue(recorded["pii_scanned"])
            self.assertEqual(
                document.frontmatter["extensions"]["pii_scan"]["source_checksum"],
                document.frontmatter["checksum"],
            )
            self.assertTrue(validate_document(ingested.manifest_path, knowledge_root).is_valid)
            _require_sensitive_data_review(knowledge_root)

    def test_boolean_without_receipt_is_rejected_by_validation_and_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, ingested = self._ingest(directory)
            document = parse_markdown(ingested.manifest_path)
            document.frontmatter["extensions"]["pii_scanned"] = True
            ingested.manifest_path.write_text(
                render_markdown(document.frontmatter, document.body), encoding="utf-8"
            )
            validation = validate_document(ingested.manifest_path, knowledge_root)
            self.assertIn(
                "extensions.pii_scan receipt is required when pii_scanned is true",
                validation.profile_errors,
            )
            with self.assertRaisesRegex(PublishError, "pii_scan receipt is required"):
                _require_sensitive_data_review(knowledge_root)

    def test_stale_checksum_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, ingested = self._ingest(directory)
            record_pii_scan_receipt(
                knowledge_root, ingested.evidence_id,
                scanner="manual-review", scanner_version="policy-1",
                result="masked", reviewed_by="security-agent",
                receipt="review://local/pii-002",
            )
            document = parse_markdown(ingested.manifest_path)
            document.frontmatter["extensions"]["pii_scan"]["source_checksum"] = "sha256:" + "0" * 64
            ingested.manifest_path.write_text(
                render_markdown(document.frontmatter, document.body), encoding="utf-8"
            )
            validation = validate_document(ingested.manifest_path, knowledge_root)
            self.assertIn(
                "extensions.pii_scan.source_checksum must equal Evidence checksum",
                validation.profile_errors,
            )


if __name__ == "__main__":
    unittest.main()
