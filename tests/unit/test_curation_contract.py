import unittest

from circled_wiki.core.curation_contract import validate_curation_output


EVIDENCE_ID = "evidence://example-org/manual/2026/07/22/11111111-1111-1111-1111-111111111111"


class CurationContractTests(unittest.TestCase):
    def _payload(self):
        return {
            "action": "runbook", "domain": "marketing", "bundle_type": "runbook",
            "title": "SNS campaign launch", "summary": "Prepare and launch a campaign.",
            "body": "# Steps\n\n1. Define the audience.", "evidence_ids": [EVIDENCE_ID],
            "rationale": "Contains repeatable steps.", "limitations": "Budget is not specified.",
            "existing_bundle_candidates": [], "confidence": "medium", "tags": ["sns", "campaign"],
            "slug": "campaign-launch",
        }

    def test_accepts_typed_output_with_authorized_evidence(self):
        output = validate_curation_output(self._payload(), [EVIDENCE_ID])

        self.assertEqual(output.bundle_type, "runbook")
        self.assertEqual(output.evidence_ids, (EVIDENCE_ID,))
        self.assertEqual(output.tags, ("sns", "campaign"))

    def test_accepts_safe_slug(self):
        payload = self._payload()
        payload["slug"] = "campaign-launch-manual"

        output = validate_curation_output(payload, [EVIDENCE_ID])

        self.assertEqual(output.slug, "campaign-launch-manual")

    def test_rejects_manual_or_runbook_without_content_derived_slug(self):
        payload = self._payload()
        payload.pop("slug")

        with self.assertRaisesRegex(ValueError, "requires a slug derived from the content"):
            validate_curation_output(payload, [EVIDENCE_ID])

    def test_allows_existing_manual_update_without_a_new_slug(self):
        payload = self._payload()
        payload.pop("slug")
        payload.update({
            "existing_bundle_candidates": ["bundle/example/manual--11111111-1111-1111-1111-111111111111"],
            "update_mode": "append",
            "base_body_checksum": "sha256:" + "a" * 64,
        })

        output = validate_curation_output(payload, [EVIDENCE_ID])

        self.assertEqual(output.slug, "")

    def test_rejects_empty_or_missing_topical_tags(self):
        payload = self._payload()
        payload["tags"] = []
        with self.assertRaisesRegex(ValueError, "tags"):
            validate_curation_output(payload, [EVIDENCE_ID])

    def test_rejects_invented_or_partial_evidence_references(self):
        payload = self._payload()
        payload["evidence_ids"] = ["evidence://example-org/manual/2026/07/22/invented"]

        with self.assertRaisesRegex(ValueError, "exactly match"):
            validate_curation_output(payload, [EVIDENCE_ID])

    def test_no_bundle_requires_reason_and_recheck_condition(self):
        output = validate_curation_output(
            {"action": "no_bundle", "rationale": "Not reusable.", "recheck_condition": "More evidence arrives."},
            [EVIDENCE_ID],
        )

        self.assertEqual(output.action, "no_bundle")
        self.assertEqual(output.evidence_ids, (EVIDENCE_ID,))

    def test_accepts_complete_bundle_taxonomy(self):
        for bundle_type in (
            "policy", "guide", "runbook", "manual",
            "decision", "spec", "reference", "report",
        ):
            payload = self._payload()
            payload["action"] = bundle_type
            payload["bundle_type"] = bundle_type
            if bundle_type not in {"manual", "runbook"}:
                payload.pop("slug")

            output = validate_curation_output(payload, [EVIDENCE_ID])

            self.assertEqual(output.bundle_type, bundle_type)
