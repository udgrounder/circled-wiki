import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.ingest import accept_conversation_intake, capture_conversation, iter_active_inbox_items
from circled_wiki.core.inbox_disposals import (
    decide_inbox_disposal, list_inbox_disposals, quarantine_inbox_item,
)
from circled_wiki.core.inbox_review_queue import list_inbox_review_queue


class InboxDisposalTests(unittest.TestCase):
    def _capture(self, root: Path, key: str):
        return capture_conversation(
            root, "non-business conversation", "slack", title="Casual chat",
            why_collected="collector test", intended_use=["test"], idempotency_key=key,
        )

    def test_quarantine_is_reversible_and_suspends_downstream_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            captured = self._capture(root, "quarantine-1")
            self.assertEqual(len(list_inbox_review_queue(root)), 1)

            quarantined = quarantine_inbox_item(
                root, captured.intake_id, classifier="slack-business-filter",
                rule_version="v1", reason="non-business-confirmed",
            )

            self.assertEqual(quarantined["status"], "pending_disposal_review")
            self.assertEqual(len(list_inbox_review_queue(root)), 0)
            pending = list_inbox_disposals(root)
            self.assertEqual(pending[0]["classification"], "non_business_confirmed")
            self.assertFalse(captured.inbox_path.exists())

            recovered = decide_inbox_disposal(root, captured.intake_id, decision="recover", actor="reviewer")
            self.assertEqual(recovered["status"], "recovered")
            self.assertTrue(captured.inbox_path.exists())
            self.assertEqual(len(list_inbox_review_queue(root)), 1)
            self.assertEqual(list_inbox_disposals(root), [])

    def test_dispose_removes_original_but_keeps_minimal_archive_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            captured = self._capture(root, "dispose-1")
            quarantine_inbox_item(
                root, captured.intake_id, classifier="slack-business-filter",
                rule_version="v1", reason="non-business-confirmed",
            )

            disposed = decide_inbox_disposal(root, captured.intake_id, decision="dispose", actor="reviewer")

            self.assertEqual(disposed["status"], "disposed")
            self.assertFalse(captured.inbox_path.exists())
            receipt = root.parent / disposed["record_path"]
            self.assertTrue(receipt.is_file())
            self.assertNotIn("non-business conversation", receipt.read_text(encoding="utf-8"))

    def test_quarantine_is_excluded_even_with_a_date_hierarchy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            captured = self._capture(root, "active-1")
            held = root / "inbox" / ".quarantine" / "slack" / "2026" / "07" / "held.md"
            held.parent.mkdir(parents=True)
            held.write_text("not an active Inbox item", encoding="utf-8")

            active = list(iter_active_inbox_items(root))

            self.assertEqual(active, [captured.inbox_path])

    def test_unclassified_item_uses_the_normal_inspection_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            captured = capture_conversation(
                root, "classification test", "slack", title="Ambiguous chat",
                why_collected="collector test", intended_use=["test"],
                idempotency_key="classification-1", sensitivity_review="completed",
            )
            document = parse_markdown(captured.inbox_path)
            data = dict(document.frontmatter)
            data["business_relevance"] = {"classification": "unclassified"}
            captured.inbox_path.write_text(
                render_markdown(data, document.body), encoding="utf-8"
            )

            self.assertEqual(
                accept_conversation_intake(root, captured.intake_id, "inspector")["status"],
                "accepted",
            )
