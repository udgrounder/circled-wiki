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

    def test_detects_mobile_contact_information_for_policy_review(self):
        content = "홍길동 / gildong@example.com / 010-1234-5678 / https://intranet.example.test"
        result = redact_sensitive_data(content)

        self.assertIn("010-1234-5678", result.content)
        self.assertIn("gildong@example.com", result.content)
        self.assertEqual(result.categories, ())
        self.assertEqual(result.policy_categories, ("mobile_phone_number",))

    def test_supported_email_feature_is_off_by_default_and_masks_when_enabled(self):
        content = "담당자 gildong@example.com"
        default_result = redact_sensitive_data(content)
        enabled_result = redact_sensitive_data(
            content, hard_mask_categories={"email_address"},
        )

        self.assertEqual(default_result.content, content)
        self.assertEqual(default_result.categories, ())
        self.assertNotIn("gildong@example.com", enabled_result.content)
        self.assertEqual(enabled_result.categories, ("email_address",))

    def test_disabling_credential_hard_mask_leaves_candidate_untouched(self):
        result = redact_sensitive_data(
            "password: visible-secret",
            hard_mask_categories=set(),
        )

        self.assertEqual(result.content, "password: visible-secret")
        self.assertEqual(result.categories, ())

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

    def test_data_protection_review_preserves_partner_contact_with_explicit_context(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from circled_wiki.core.frontmatter import parse_markdown
        from circled_wiki.core.ingest import capture_conversation, review_data_protection

        with TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            (knowledge_root / "organization.yaml").parent.mkdir(parents=True)
            (knowledge_root / "organization.yaml").write_text(
                "organization_id: test-org\n", encoding="utf-8"
            )
            captured = capture_conversation(
                knowledge_root, "협력업체 담당자 010-1234-5678", "test", title="partner",
                why_collected="unit test", intended_use=["test"], idempotency_key="partner-contact",
            )
            review = review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="partner_business_contact",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="승인된 협력업체 업무용 연락처다.",
            )
            data, content = __import__("circled_wiki.core.ingest", fromlist=["read_conversation_intake"]).read_conversation_intake(captured.inbox_path)

        self.assertIn("010-1234-5678", content)
        self.assertEqual(
            data["capture_details"]["sensitive_data_precheck"]["policy_categories"],
            ["mobile_phone_number"],
        )
        self.assertEqual(review["data_protection"]["resolution"], "preserve_internal")
        self.assertEqual(data["sensitivity_inspection"]["data_protection"]["context"], "partner_business_contact")

    def test_data_protection_review_transitions_unknown_context_to_user_contract(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from circled_wiki.core.ingest import capture_conversation, review_data_protection
        from circled_wiki.core.inbox_review_queue import get_inbox_review

        with TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            (knowledge_root / "organization.yaml").parent.mkdir(parents=True)
            (knowledge_root / "organization.yaml").write_text(
                "organization_id: test-org\n", encoding="utf-8"
            )
            captured = capture_conversation(
                knowledge_root, "담당자 연락처 010-2222-3333", "test", title="unknown",
                why_collected="unit test", intended_use=["test"], idempotency_key="unknown-context",
            )
            result = review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="unknown_context",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="승인된 업무 맥락을 확인할 수 없다.",
            )
            review = get_inbox_review(knowledge_root, captured.intake_id)

        self.assertEqual(result["status"], "awaiting_user")
        self.assertEqual(review["current"]["status"], "awaiting_user")
        requirement = next(
            item for item in review["requirements"]
            if item["reason_code"] == "sensitivity_review_required"
        )
        self.assertEqual(requirement["requested_action"], "review_data_protection")

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
            complete_inbox_sensitivity_review,
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
                idempotency_key="legacy-sensitive-data-test",
            )
            document = parse_markdown(captured.inbox_path)
            unsafe_text = "password=unsafe-test-value"
            unsafe_content = "<!-- INBOX_CONTENT_START -->" + unsafe_text + "<!-- INBOX_CONTENT_END -->"
            document.frontmatter["checksum"] = (
                "sha256:" + __import__("hashlib").sha256(unsafe_text.encode("utf-8")).hexdigest()
            )
            captured.inbox_path.write_text(
                render_markdown(document.frontmatter, "# Inbox Conversation\n\n" + unsafe_content + "\n"),
                encoding="utf-8",
            )

            complete_inbox_sensitivity_review(
                knowledge_root, captured.intake_id, "test-inspection-agent", "completed",
                policy_ref="inbox-sensitivity/v1",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                matched_categories=["test_fixture"],
                rationale="테스트 fixture의 명시적 민감성 검사 결과다.",
            )
            run_automatic_pii_scan(knowledge_root, captured.intake_id)
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)
            self.assertEqual(result["ingested_count"], 1)
            item = result["items"][0]
            self.assertEqual(item["pii_scan_result"], "masked")
            evidence = Path(knowledge_root.parent / item["evidence_path"])
            self.assertNotIn("unsafe-test-value", evidence.read_text(encoding="utf-8"))
            evidence_data = parse_markdown(evidence).frontmatter
            self.assertEqual(evidence_data["extensions"]["pii_scan"]["result"], "masked")
            self.assertEqual(evidence_data["extensions"]["pii_scan"]["source_checksum"], evidence_data["checksum"])


if __name__ == "__main__":
    unittest.main()
