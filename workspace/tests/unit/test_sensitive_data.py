import unittest

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

    def test_does_not_automatically_mask_general_contact_information(self):
        content = "홍길동 / gildong@example.com / 010-1234-5678 / https://intranet.example.test"
        result = redact_sensitive_data(content)

        self.assertEqual(result.content, content)
        self.assertEqual(result.categories, ())

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

    def test_evidence_ingest_recheck_masks_a_legacy_unmasked_text_item(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from circled_wiki.core.frontmatter import parse_markdown, render_markdown
        from circled_wiki.core.ingest import accept_conversation_intake, capture_conversation
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
            unsafe_text = "password=do-not-store"
            unsafe_content = "<!-- INBOX_CONTENT_START -->" + unsafe_text + "<!-- INBOX_CONTENT_END -->"
            document.frontmatter["checksum"] = (
                "sha256:" + __import__("hashlib").sha256(unsafe_text.encode("utf-8")).hexdigest()
            )
            captured.inbox_path.write_text(
                render_markdown(document.frontmatter, "# Inbox Conversation\n\n" + unsafe_content + "\n"),
                encoding="utf-8",
            )

            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)
            self.assertEqual(result["ingested_count"], 1)
            self.assertEqual(
                result["items"][0]["sensitive_data_recheck"]["categories"], ["credential"]
            )
            evidence = Path(knowledge_root.parent / result["items"][0]["evidence_path"])
            self.assertNotIn("do-not-store", evidence.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
