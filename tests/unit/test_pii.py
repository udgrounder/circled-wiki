import hashlib
import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.evidence import evidence_original_bytes
from circled_wiki.core.ingest import ingest_evidence
from circled_wiki.core.pii import build_pii_scan_receipt
from circled_wiki.core.validator import validate_document


class PiiScanReceiptTests(unittest.TestCase):
    def _ingest(self, directory: str, *, with_receipt: bool = False):
        knowledge_root = Path(directory) / "knowledge"
        source = knowledge_root / "inbox" / "manual" / "sample.txt"
        source.parent.mkdir(parents=True)
        source.write_text("masked sample", encoding="utf-8")
        checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        scan = build_pii_scan_receipt(
            checksum, scanner="manual-review", scanner_version="policy-1",
            result="passed", reviewed_by="security-agent",
            receipt="review://local/pii-001",
            scanned_at="2026-07-22T10:00:00+09:00",
        ) if with_receipt else None
        result = ingest_evidence(
            knowledge_root, source, "manual",
            why_collected="PII gate test", intended_use=["security-test"],
            pii_scan_receipt=scan,
        )
        return knowledge_root, result

    def test_receipt_is_bound_to_current_evidence_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, ingested = self._ingest(directory, with_receipt=True)
            document = parse_markdown(ingested.manifest_path)
            self.assertTrue(document.frontmatter["extensions"]["pii_scanned"])
            self.assertEqual(
                document.frontmatter["extensions"]["pii_scan"]["source_checksum"],
                document.frontmatter["checksum"],
            )
            self.assertTrue(validate_document(ingested.manifest_path, knowledge_root).is_valid)

    def test_boolean_without_receipt_is_rejected_by_validation(self):
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

    def test_stale_checksum_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            source = knowledge_root / "inbox" / "manual" / "sample.txt"
            source.parent.mkdir(parents=True)
            source.write_text("masked sample", encoding="utf-8")
            stale = build_pii_scan_receipt(
                "sha256:" + "0" * 64,
                scanner="manual-review", scanner_version="policy-1",
                result="masked", reviewed_by="security-agent",
                receipt="review://local/pii-002",
            )
            with self.assertRaisesRegex(ValueError, "source_checksum must equal"):
                ingest_evidence(
                    knowledge_root, source, "manual",
                    why_collected="PII gate test", intended_use=["security-test"],
                    pii_scan_receipt=stale,
                )

    def test_direct_pii_scanned_flag_cannot_bypass_pre_creation_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            source = knowledge_root / "inbox" / "manual" / "sample.txt"
            source.parent.mkdir(parents=True)
            source.write_text("masked sample", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot be set directly"):
                ingest_evidence(
                    knowledge_root, source, "manual",
                    why_collected="PII gate test", intended_use=["security-test"],
                    pii_scanned=True,
                )

    def test_embedded_evidence_preserves_marker_text_and_pii_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            source = knowledge_root / "inbox" / "manual" / "conversation.md"
            source.parent.mkdir(parents=True)
            content = (
                "---\n"
                "quoted start: <!-- ORIGINAL_CONTENT_START -->\n"
                "quoted end: <!-- ORIGINAL_CONTENT_END -->\n"
            )
            source.write_text(content, encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            receipt = build_pii_scan_receipt(
                checksum, scanner="manual-review", scanner_version="policy-1",
                result="masked", reviewed_by="security-agent",
                receipt="review://local/pii-embedded",
            )

            ingested = ingest_evidence(
                knowledge_root, source, "manual",
                why_collected="Embedded PII gate test", intended_use=["security-test"],
                content_mode="embedded", pii_scan_receipt=receipt,
            )
            document = parse_markdown(ingested.manifest_path)

            self.assertEqual(document.body, content)
            self.assertEqual(evidence_original_bytes(document), content.encode("utf-8"))
            self.assertEqual(document.frontmatter["extensions"]["checksum_scope"], "document_body")
            self.assertTrue(document.frontmatter["extensions"]["pii_scanned"])
            self.assertEqual(document.frontmatter["extensions"]["pii_scan"]["result"], "masked")
            self.assertTrue(validate_document(ingested.manifest_path, knowledge_root).is_valid)

    def test_unsupported_embedded_format_version_is_rejected_without_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            source = knowledge_root / "inbox" / "manual" / "conversation.md"
            source.parent.mkdir(parents=True)
            source.write_text("safe conversation\n", encoding="utf-8")

            ingested = ingest_evidence(
                knowledge_root, source, "manual",
                why_collected="format version test", intended_use=["test"],
                content_mode="embedded",
            )
            document = parse_markdown(ingested.manifest_path)
            document.frontmatter["extensions"]["embedded_format_version"] = 99
            ingested.manifest_path.write_text(
                render_markdown(document.frontmatter, document.body), encoding="utf-8"
            )

            validation = validate_document(ingested.manifest_path, knowledge_root)
            self.assertIn(
                "unsupported embedded Evidence format version: 99",
                validation.profile_errors,
            )

    def test_needs_review_receipt_keeps_source_in_inbox(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            source = knowledge_root / "inbox" / "manual" / "sample.txt"
            source.parent.mkdir(parents=True)
            source.write_text("requires a human decision", encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            receipt = build_pii_scan_receipt(
                checksum,
                scanner="manual-review",
                scanner_version="policy-1",
                result="needs_review",
                reviewed_by="security-agent",
                receipt="review://local/pii-pending",
            )

            with self.assertRaisesRegex(ValueError, "keep the source in Inbox"):
                ingest_evidence(
                    knowledge_root, source, "manual",
                    why_collected="PII gate test",
                    intended_use=["security-test"],
                    pii_scan_receipt=receipt,
                )

            self.assertTrue(source.is_file())
            self.assertFalse((knowledge_root / ".raw").exists())
            self.assertFalse((knowledge_root / "evidence").exists())


if __name__ == "__main__":
    unittest.main()
