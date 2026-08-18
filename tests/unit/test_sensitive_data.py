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

    def test_masks_accounts_with_limited_bank_or_holder_context(self):
        result = redact_sensitive_data(
            "환불계좌 : 신한은행 예금주 110-451-983540 / 농협 204017-56-024375"
        )

        self.assertNotIn("110-451-983540", result.content)
        self.assertNotIn("204017-56-024375", result.content)
        self.assertEqual(result.categories, ("account_number",))

    def test_does_not_mask_unlabelled_number_without_a_known_bank(self):
        content = "참조번호 204017-56-024375"
        result = redact_sensitive_data(content)

        self.assertEqual(result.content, content)
        self.assertEqual(result.categories, ())

    def test_detects_mobile_contact_information_for_policy_review(self):
        content = "홍길동 / gildong@example.com / 010-1234-5678 / https://intranet.example.test"
        result = redact_sensitive_data(content)

        self.assertIn("010-1234-5678", result.content)
        self.assertIn("gildong@example.com", result.content)
        self.assertEqual(result.categories, ())
        self.assertEqual(result.policy_categories, ("email_address", "mobile_phone_number"))

    def test_supported_email_feature_is_off_by_default_and_masks_when_enabled(self):
        content = "담당자 gildong@example.com"
        default_result = redact_sensitive_data(content)
        enabled_result = redact_sensitive_data(
            content, hard_mask_categories={"email_address"},
        )

        self.assertEqual(default_result.content, content)
        self.assertEqual(default_result.categories, ())
        self.assertEqual(default_result.policy_categories, ("email_address",))
        self.assertNotIn("gildong@example.com", enabled_result.content)
        self.assertEqual(enabled_result.categories, ("email_address",))
        self.assertEqual(enabled_result.policy_categories, ())

    def test_enabled_mobile_phone_hard_mask_masks_and_reports_the_category(self):
        result = redact_sensitive_data(
            "담당자 010-1234-5678",
            hard_mask_categories={"mobile_phone_number"},
        )

        self.assertNotIn("010-1234-5678", result.content)
        self.assertEqual(result.categories, ("mobile_phone_number",))
        self.assertEqual(result.policy_categories, ())

    def test_policy_masking_mode_masks_phone_and_email_for_safe_metadata(self):
        result = redact_sensitive_data(
            "담당자 010-1234-5678 / gildong@example.com",
            mask_policy_categories=True,
        )

        self.assertNotIn("010-1234-5678", result.content)
        self.assertNotIn("gildong@example.com", result.content)
        self.assertEqual(result.categories, ())
        self.assertEqual(
            set(result.policy_categories), {"mobile_phone_number", "email_address"},
        )

    def test_disabling_credential_hard_mask_excludes_it_from_review(self):
        result = redact_sensitive_data(
            "password: visible-secret",
            hard_mask_categories=set(),
        )

        self.assertEqual(result.content, "password: visible-secret")
        self.assertEqual(result.categories, ())
        self.assertEqual(result.policy_categories, ())

    def test_masks_korean_credential_labels_with_whitespace_or_newline_separator(self):
        content = "계정 synthetic-user\n비밀번호 synthetic-password"

        result = redact_sensitive_data(content)

        self.assertNotIn("synthetic-user", result.content)
        self.assertNotIn("synthetic-password", result.content)
        self.assertEqual(result.content, "계정 ********\n비밀번호 ********")
        self.assertEqual(result.categories, ("credential",))

    def test_masks_korean_credential_labels_with_assignment_separator(self):
        content = "계정: synthetic-user\n패스워드=synthetic-password\n암호 : synthetic-passcode"

        result = redact_sensitive_data(content)

        self.assertNotIn("synthetic-user", result.content)
        self.assertNotIn("synthetic-password", result.content)
        self.assertNotIn("synthetic-passcode", result.content)
        self.assertEqual(result.categories, ("credential",))

    def test_masks_oauth_credentials_but_preserves_flow_metadata(self):
        content = (
            "https://login.example.test/oauth/authorize?client_id=public-client"
            "&code=authorization-code&code_challenge=challenge-value"
            "&code_verifier=verifier-value&state=csrf-state"
            "&access_token=access-value&id_token=id-value"
        )

        result = redact_sensitive_data(content)

        self.assertNotIn("authorization-code", result.content)
        self.assertNotIn("verifier-value", result.content)
        self.assertNotIn("access-value", result.content)
        self.assertNotIn("id-value", result.content)
        self.assertIn("client_id=public-client", result.content)
        self.assertIn("code_challenge=challenge-value", result.content)
        self.assertIn("state=csrf-state", result.content)
        self.assertEqual(result.categories, ("credential",))
        self.assertEqual(result.policy_categories, ("oauth_flow_metadata",))

    def test_oauth_flow_metadata_is_sent_to_policy_review_without_hard_masking(self):
        content = (
            "https://login.example.test/oauth/authorize?client_id=public-client"
            "&code_challenge=challenge-value&state=csrf-state"
        )

        result = redact_sensitive_data(content)

        self.assertEqual(result.content, content)
        self.assertEqual(result.categories, ())
        self.assertEqual(result.policy_categories, ("oauth_flow_metadata",))

    def test_disabling_credential_hard_mask_keeps_only_oauth_metadata_for_review(self):
        content = (
            "https://login.example.test/oauth/authorize?client_id=public-client"
            "&code=authorization-code&state=csrf-state"
        )

        result = redact_sensitive_data(content, hard_mask_categories=set())

        self.assertEqual(result.content, content)
        self.assertEqual(result.categories, ())
        self.assertEqual(result.policy_categories, ("oauth_flow_metadata",))

    def test_does_not_classify_state_or_code_as_oauth_outside_authorize_context(self):
        content = "https://example.test/status?code=200&state=ready"

        result = redact_sensitive_data(content)

        self.assertEqual(result.content, content)
        self.assertEqual(result.categories, ())
        self.assertEqual(result.policy_categories, ())

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

    def test_capture_masks_korean_whitespace_separated_credentials_before_write(self):
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
                knowledge_root, "계정 synthetic-user\n비밀번호 synthetic-password", "test",
                title="korean credential test", why_collected="unit test", intended_use=["test"],
                idempotency_key="korean-sensitive-data-test",
            )
            data, content = read_conversation_intake(captured.inbox_path)

        self.assertNotIn("synthetic-user", content)
        self.assertNotIn("synthetic-password", content)
        self.assertEqual(
            data["capture_details"]["sensitive_data_precheck"]["categories"], ["credential"]
        )

    def test_capture_masks_oauth_credentials_and_records_flow_metadata_candidate(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from circled_wiki.core.ingest import capture_conversation, read_conversation_intake

        content = (
            "https://login.example.test/oauth/authorize?client_id=public-client"
            "&code=authorization-code&code_challenge=challenge-value&state=csrf-state"
        )
        with TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            (knowledge_root / "organization.yaml").parent.mkdir(parents=True)
            (knowledge_root / "organization.yaml").write_text(
                "organization_id: test-org\n", encoding="utf-8"
            )
            captured = capture_conversation(
                knowledge_root, content, "test", title="oauth test",
                why_collected="unit test", intended_use=["test"],
                idempotency_key="oauth-sensitive-data-test",
            )
            data, stored_content = read_conversation_intake(captured.inbox_path)

        self.assertNotIn("authorization-code", stored_content)
        self.assertIn("client_id=public-client", stored_content)
        self.assertIn("code_challenge=challenge-value", stored_content)
        self.assertIn("state=csrf-state", stored_content)
        self.assertEqual(
            data["capture_details"]["sensitive_data_precheck"]["categories"], ["credential"]
        )
        self.assertEqual(
            data["capture_details"]["sensitive_data_precheck"]["policy_categories"],
            ["oauth_flow_metadata"],
        )

    def test_explicitly_disabled_mobile_phone_skips_data_protection_review(self):
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
                knowledge_root, "협력업체 담당자 010-1234-5678", "test", title="partner",
                why_collected="unit test", intended_use=["test"], idempotency_key="partner-contact",
            )
            data, content = read_conversation_intake(captured.inbox_path)

        self.assertIn("010-1234-5678", content)
        self.assertNotIn("sensitive_data_precheck", data.get("capture_details", {}))

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
