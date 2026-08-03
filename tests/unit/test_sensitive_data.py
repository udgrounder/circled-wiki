import unittest
from unittest.mock import patch

from circled_wiki.core.sensitive_data import REDACTED_VALUE, redact_sensitive_data


class SensitiveDataPrecheckTests(unittest.TestCase):
    def test_redacts_only_high_risk_identifiers_and_credentials(self):
        result = redact_sensitive_data(
            "주민번호 900101-1234567, 계좌번호: 123-4567-890123, "
            "카드 4111-1111-1111-1111, api_key=sk-abcdefghijklmnopqrstuvwxyz123456, "
            "password: correct-horse-battery-staple"
        )

        self.assertNotIn("900101-1234567", result.content)
        self.assertNotIn("123-4567-890123", result.content)
        self.assertNotIn("4111-1111-1111-1111", result.content)
        self.assertNotIn("correct-horse-battery-staple", result.content)
        self.assertEqual(
            set(result.categories),
            {"resident_registration_number", "account_number", "card_number", "credential"},
        )

    def test_masks_only_mobile_contact_information(self):
        content = "홍길동 / gildong@example.com / 010-1234-5678 / https://intranet.example.test"
        result = redact_sensitive_data(content)

        self.assertNotIn("010-1234-5678", result.content)
        self.assertIn("gildong@example.com", result.content)
        self.assertEqual(result.categories, ("mobile_phone_number",))

    def test_does_not_mask_uuid_that_contains_a_phone_like_digit_sequence(self):
        task_id = "c2f29370-e7d6-0100-1234-56789abcdef0"
        result = redact_sensitive_data(f"task_id={task_id}")

        self.assertEqual(result.content, f"task_id={task_id}")
        self.assertEqual(result.categories, ())

    def test_reuses_a_valid_pii_receipt_without_rescanning_the_same_candidate(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from circled_wiki.core.ingest import capture_conversation, run_automatic_pii_scan

        with TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            (knowledge_root / "organization.yaml").parent.mkdir(parents=True)
            (knowledge_root / "organization.yaml").write_text(
                "organization_id: test-org\n", encoding="utf-8"
            )
            captured = capture_conversation(
                knowledge_root, "safe candidate", "test", title="receipt reuse",
                why_collected="unit test", intended_use=["test"],
                idempotency_key="receipt-reuse",
            )
            run_automatic_pii_scan(knowledge_root, captured.intake_id)
            with patch(
                "circled_wiki.core.ingest.redact_sensitive_data",
                side_effect=AssertionError("same candidate must not be rescanned"),
            ):
                reused = run_automatic_pii_scan(knowledge_root, captured.intake_id)

        self.assertTrue(reused["reused"])

    def test_masks_credential_before_text_capture_is_written(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from circled_wiki.core.ingest import capture_conversation, read_conversation_intake

        with TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            (knowledge_root / "organization.yaml").parent.mkdir(parents=True)
            (knowledge_root / "organization.yaml").write_text(
                "organization_id: test-org\n", encoding="utf-8"
            )
            captured = capture_conversation(
                knowledge_root, "token=ghp_abcdefghijklmnopqrstuvwxyz123456", "test",
                title="credential test", why_collected="unit test", intended_use=["test"],
                idempotency_key="sensitive-data-test",
            )
            data, content = read_conversation_intake(captured.inbox_path)

        self.assertNotIn("ghp_", content)
        self.assertIn(REDACTED_VALUE, content)
        self.assertEqual(
            data["capture_details"]["sensitive_data_precheck"]["categories"], ["credential"]
        )

    def test_masks_presigned_url_credential_parameters(self):
        result = redact_sensitive_data(
            "https://example.test/file?X-Amz-Security-Token=synthetic-token&"
            "X-Amz-Credential=synthetic-credential&X-Amz-Signature=synthetic-signature"
        )

        self.assertNotIn("synthetic-token", result.content)
        self.assertNotIn("synthetic-credential", result.content)
        self.assertNotIn("synthetic-signature", result.content)
        self.assertEqual(result.categories, ("credential",))

    def test_canonical_pii_scan_masks_a_legacy_unmasked_text_item_before_evidence(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from circled_wiki.core.frontmatter import parse_markdown, render_markdown
        from circled_wiki.core.ingest import (
            accept_conversation_intake,
            capture_conversation,
            run_automatic_pii_scan,
        )
        from circled_wiki.worker.jobs import ingest_accepted_inbox

        with TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            (knowledge_root / "organization.yaml").parent.mkdir(parents=True)
            (knowledge_root / "organization.yaml").write_text(
                "organization_id: test-org\n", encoding="utf-8"
            )
            captured = capture_conversation(
                knowledge_root, "safe content", "test", title="legacy item",
                why_collected="unit test", intended_use=["test"],
                idempotency_key="legacy-sensitive-data-test", sensitivity_review="completed",
            )
            document = parse_markdown(captured.inbox_path)
            unsafe_text = "010-1234-5678"
            unsafe_content = "<!-- INBOX_CONTENT_START -->" + unsafe_text + "<!-- INBOX_CONTENT_END -->"
            document.frontmatter["checksum"] = (
                "sha256:" + __import__("hashlib").sha256(unsafe_text.encode("utf-8")).hexdigest()
            )
            captured.inbox_path.write_text(
                render_markdown(document.frontmatter, "# Inbox Conversation\n\n" + unsafe_content + "\n"),
                encoding="utf-8",
            )

            run_automatic_pii_scan(knowledge_root, captured.intake_id)
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)
            self.assertEqual(result["ingested_count"], 1)
            item = result["items"][0]
            self.assertEqual(item["pii_scan_result"], "masked")
            evidence = Path(knowledge_root.parent / item["evidence_path"])
            self.assertNotIn("010-1234-5678", evidence.read_text(encoding="utf-8"))
            evidence_data = parse_markdown(evidence).frontmatter
            self.assertEqual(evidence_data["extensions"]["pii_scan"]["result"], "masked")
            self.assertEqual(evidence_data["extensions"]["pii_scan"]["source_checksum"], evidence_data["checksum"])


if __name__ == "__main__":
    unittest.main()
