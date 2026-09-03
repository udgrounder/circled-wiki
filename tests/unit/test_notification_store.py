import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.notification_store import (
    acknowledge_user_notification,
    dismiss_notifications_for_resource,
    dismiss_user_notification,
    list_user_notifications,
    record_user_notification,
)


class NotificationStoreTests(unittest.TestCase):
    def test_records_deduplicates_and_acknowledges_a_user_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            created = record_user_notification(
                workspace, event="bundle_created", priority="attention",
                title="새 Bundle이 생성되었습니다", summary="분류 규칙에 따라 생성했습니다.",
                next_action="필요하면 Bundle을 검토하세요.", resource_ref="knowledge/bundles/operations/example.md",
                approval_required=False, dedupe_key="bundle_created:bundle/example",
                related_bundle_id="bundle/example",
            )
            duplicate = record_user_notification(
                workspace, event="bundle_created", priority="attention",
                title="새 Bundle이 생성되었습니다", summary="분류 규칙에 따라 생성했습니다.",
                next_action="필요하면 Bundle을 검토하세요.", resource_ref="knowledge/bundles/operations/example.md",
                approval_required=False, dedupe_key="bundle_created:bundle/example",
                related_bundle_id="bundle/example",
            )
            self.assertTrue(duplicate["reused"])
            self.assertEqual(len(list_user_notifications(workspace)), 1)
            acknowledgement = acknowledge_user_notification(
                workspace, notification_id=str(created["notification_id"]), actor="owner",
            )
            self.assertFalse(acknowledgement["reused"])
            self.assertEqual(list_user_notifications(workspace), [])
            records = list_user_notifications(workspace, include_acknowledged=True)
        self.assertEqual(records[0]["acknowledgement"]["actor"], "owner")

    def test_dismisses_open_notifications_and_their_acknowledgements(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            first = record_user_notification(
                workspace, event="review_requested", priority="action_required",
                title="검토가 필요합니다", summary="검토할 Curation Review가 있습니다.",
                next_action="Review를 검토하세요.", resource_ref="knowledge/curation-reviews/review-a.md",
                approval_required=True, dedupe_key="review_requested:a",
            )
            second = record_user_notification(
                workspace, event="taxonomy_change_proposed", priority="action_required",
                title="taxonomy 변경 제안", summary="분류 규칙 검토가 필요합니다.",
                next_action="제안을 검토하세요.", resource_ref="workspace/taxonomy-proposals/proposal-a.json",
                approval_required=True, dedupe_key="taxonomy_change_proposed:a",
            )
            acknowledge_user_notification(
                workspace, notification_id=str(first["notification_id"]), actor="owner",
            )
            dismissed = dismiss_notifications_for_resource(
                workspace, resource_ref="knowledge/curation-reviews/review-a.md", reason="Review resolved",
            )
            manual = dismiss_user_notification(
                workspace, notification_id=str(second["notification_id"]), reason="Withdrawn",
            )
            self.assertFalse((workspace / "notifications" / "inbox" / f"{first['notification_id']}.json").exists())
            self.assertFalse((workspace / "notifications" / "acknowledgements" / f"{first['notification_id']}.json").exists())
            self.assertFalse((workspace / "notifications" / "archive").exists())
        self.assertEqual(dismissed[0]["notification_id"], first["notification_id"])
        self.assertTrue(dismissed[0]["deleted"])
        self.assertEqual(manual["reason"], "Withdrawn")


if __name__ == "__main__":
    unittest.main()
