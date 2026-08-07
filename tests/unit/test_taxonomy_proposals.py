import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.notification_store import acknowledge_user_notification, list_user_notifications
from circled_wiki.core.taxonomy_proposals import (
    record_taxonomy_change_proposal,
    require_reclassification_approval,
)


class TaxonomyProposalTests(unittest.TestCase):
    def test_records_approval_gated_proposal_and_impact_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge = Path(directory) / "knowledge"
            proposal = record_taxonomy_change_proposal(
                knowledge, evidence_id="evidence/example", domain="marketing", bundle_type="guide",
                rationale="The validated Curator found a route not covered by the approved taxonomy.",
                impacted_bundle_ids=["bundle/example-a", "bundle/example-b"],
            )
            duplicate = record_taxonomy_change_proposal(
                knowledge, evidence_id="evidence/example", domain="marketing", bundle_type="guide",
                rationale="The validated Curator found a route not covered by the approved taxonomy.",
            )
            notifications = list_user_notifications(knowledge.parent / "workspace")
        self.assertFalse(proposal["reused"])
        self.assertTrue(duplicate["reused"])
        self.assertEqual(proposal["status"], "awaiting_user")
        self.assertEqual(proposal["impacted_bundle_ids"], ["bundle/example-a", "bundle/example-b"])
        self.assertEqual({item["event"] for item in notifications}, {
            "taxonomy_change_proposed", "reclassification_ready",
        })

    def test_reclassification_requires_acknowledged_matching_impact_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge = Path(directory) / "knowledge"
            proposal = record_taxonomy_change_proposal(
                knowledge, evidence_id="evidence/example", domain="marketing", bundle_type="guide",
                rationale="A classification proposal is ready for review.",
                impacted_bundle_ids=["bundle/example-a"],
            )
            notification_id = str(proposal["reclassification_notification"]["notification_id"])
            with self.assertRaisesRegex(ValueError, "acknowledged"):
                require_reclassification_approval(
                    knowledge, notification_id=notification_id, bundle_id="bundle/example-a",
                    domain="marketing", bundle_type="guide",
                )
            acknowledge_user_notification(knowledge.parent / "workspace", notification_id=notification_id, actor="owner")
            receipt = require_reclassification_approval(
                knowledge, notification_id=notification_id, bundle_id="bundle/example-a",
                domain="marketing", bundle_type="guide",
            )
            with self.assertRaisesRegex(ValueError, "impact list"):
                require_reclassification_approval(
                    knowledge, notification_id=notification_id, bundle_id="bundle/not-listed",
                    domain="marketing", bundle_type="guide",
                )
        self.assertEqual(receipt["proposal_id"], proposal["proposal_id"])


if __name__ == "__main__":
    unittest.main()
