import tempfile
import unittest
from pathlib import Path

import yaml

from circled_wiki.config.data_protection import (
    POLICY_PATH,
    HARD_MASK_CATEGORIES,
    load_data_protection_policy,
    render_data_protection_policy,
)
from circled_wiki.core.frontmatter import parse_markdown, render_markdown


class DataProtectionPolicyTests(unittest.TestCase):
    def test_missing_policy_uses_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            policy = load_data_protection_policy(Path(directory))

        self.assertEqual(set(policy.hard_mask_categories), set(HARD_MASK_CATEGORIES))
        self.assertNotIn("mobile_phone_number", policy.hard_mask_categories)
        self.assertNotIn("email_address", policy.hard_mask_categories)
        self.assertEqual(policy.policy_evaluated_categories, ("mobile_phone_number",))
        self.assertIn("employee_business_contact", policy.non_sensitive_categories)
        self.assertEqual(
            set(policy.agent_mask_categories),
            {"compensation", "performance_review", "disciplinary_action", "unlawful_content"},
        )
        self.assertEqual(policy.missing_policy_action, "awaiting_user")

    def test_local_policy_can_customize_review_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            payload = yaml.safe_load(render_data_protection_policy())
            payload["sensitivity_review"]["agent_mask_categories"]["internal_audit"] = {
                "description": "내부 감사 기록",
                "include": ["개인 감사 결과"],
                "exclude": ["일반 감사 절차"],
            }
            path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

            policy = load_data_protection_policy(root)

        self.assertIn("internal_audit", policy.agent_mask_categories)

    def test_omitted_agent_mask_categories_use_product_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            payload = yaml.safe_load(render_data_protection_policy())
            payload["sensitivity_review"].pop("agent_mask_categories")
            path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

            policy = load_data_protection_policy(root)

        self.assertIn("compensation", policy.agent_mask_categories)

    def test_agent_mask_guidance_requires_non_overlapping_include_and_exclude(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            payload = yaml.safe_load(render_data_protection_policy())
            payload["sensitivity_review"]["agent_mask_categories"]["compensation"]["exclude"].append(
                "개인별 급여액"
            )
            path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "include/exclude must not overlap"):
                load_data_protection_policy(root)

    def test_agent_mask_guidance_requires_an_include_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            payload = yaml.safe_load(render_data_protection_policy())
            payload["sensitivity_review"]["agent_mask_categories"]["compensation"]["include"] = []
            path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "include must contain at least one item"):
                load_data_protection_policy(root)

    def test_empty_agent_mask_categories_explicitly_disables_agent_masking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            payload = yaml.safe_load(render_data_protection_policy())
            payload["sensitivity_review"]["agent_mask_categories"] = {}
            path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

            policy = load_data_protection_policy(root)

        self.assertEqual(policy.agent_mask_categories, ())

    def test_unknown_sensitive_category_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            rendered = render_data_protection_policy().replace(
                "  agent_mask_categories:", "  sensitive_categories:"
            )
            path.write_text(rendered, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported fields"):
                load_data_protection_policy(root)

    def test_policy_can_disable_supported_hard_mask_category(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            path.write_text(render_data_protection_policy().replace(
                "    credential: true", "    credential: false"
            ), encoding="utf-8")

            policy = load_data_protection_policy(root)

        self.assertNotIn("credential", policy.hard_mask_categories)

    def test_omitted_hard_mask_category_defaults_true(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            path.write_text(render_data_protection_policy().replace(
                "    email_address: false\n", ""
            ), encoding="utf-8")

            policy = load_data_protection_policy(root)

        self.assertIn("email_address", policy.hard_mask_categories)

    def test_rejects_unknown_or_non_boolean_hard_mask_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / POLICY_PATH
            path.parent.mkdir()
            unknown = render_data_protection_policy().replace(
                "    email_address: false", "    email_address: false\n    unknown: true"
            )
            path.write_text(unknown, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported categories"):
                load_data_protection_policy(root)

            path.write_text(render_data_protection_policy().replace(
                "    credential: true", "    credential: 'enabled'"
            ), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "values must be booleans"):
                load_data_protection_policy(root)

    def test_metadata_change_reopens_integrated_receipt(self):
        from circled_wiki.core.ingest import capture_conversation, review_data_protection, run_automatic_pii_scan
        from circled_wiki.core.inbox_review_queue import get_inbox_review

        checks = [
            "source_access_scope", "personal_context",
            "confidential_business_context", "publication_scope",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            captured = capture_conversation(
                root, "안전한 본문", "manual", title="안전한 제목",
                why_collected="검증", intended_use=["test"], idempotency_key="metadata-reopen",
            )
            review_data_protection(
                root, captured.intake_id, "agent", context="", checks=checks,
                rationale="민감한 정책 대상이 없는 본문이다.",
            )
            document = parse_markdown(captured.inbox_path)
            document.frontmatter["title"] = "담당자 010-9999-8888"
            captured.inbox_path.write_text(
                render_markdown(document.frontmatter, document.body), encoding="utf-8"
            )

            result = run_automatic_pii_scan(root, captured.intake_id)
            current = parse_markdown(captured.inbox_path).frontmatter
            review = get_inbox_review(root, captured.intake_id)

        self.assertFalse(result.get("reused", False))
        self.assertEqual(current["sensitivity_review"], "required")
        self.assertNotIn("data_protection_receipt", current)
        self.assertEqual(review["current"]["next_action"], "review_data_protection")
