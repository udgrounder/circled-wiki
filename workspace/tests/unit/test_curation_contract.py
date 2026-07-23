import unittest

from knowledge_os.core.curation_contract import validate_curation_output


EVIDENCE_ID = "evidence://example-org/manual/2026/07/22/11111111-1111-1111-1111-111111111111"


class CurationContractTests(unittest.TestCase):
    def _payload(self):
        return {
            "action": "runbook", "domain": "marketing", "bundle_type": "runbook",
            "title": "SNS campaign launch", "summary": "Prepare and launch a campaign.",
            "body": "# Steps\n\n1. Define the audience.", "evidence_ids": [EVIDENCE_ID],
            "rationale": "Contains repeatable steps.", "limitations": "Budget is not specified.",
            "existing_bundle_candidates": [], "confidence": "medium",
        }

    def test_accepts_typed_output_with_authorized_evidence(self):
        output = validate_curation_output(self._payload(), [EVIDENCE_ID])

        self.assertEqual(output.bundle_type, "runbook")
        self.assertEqual(output.evidence_ids, (EVIDENCE_ID,))

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
