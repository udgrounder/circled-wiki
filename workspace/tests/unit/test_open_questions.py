import tempfile
import unittest
import json
from pathlib import Path

from circled_wiki.core.open_questions import (
    claim_slack_decision_delivery, list_open_questions, queue_slack_decision,
    reconcile_open_question_deliveries, record_open_question, resolve_open_question,
)


class OpenQuestionTests(unittest.TestCase):
    def test_records_lists_and_resolves_administrator_question(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".runtime"
            created = record_open_question(
                runtime, question="Who receives the form?", asked_of="admin",
                context="Security pledge workflow needs a handoff owner.",
            )
            self.assertEqual([item["question_id"] for item in list_open_questions(runtime, asked_of="admin")], [created["question_id"]])
            resolved = resolve_open_question(
                runtime, question_id=created["question_id"], answer="Security owner", actor="admin-user",
            )
            self.assertEqual(resolved["status"], "resolved")
            self.assertEqual(list_open_questions(runtime), [])

    def test_queues_slack_dm_and_waits_for_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".runtime"
            created = record_open_question(
                runtime, question="Approve the change?", asked_of="admin", context="A decision is required."
            )
            delivery = queue_slack_decision(runtime, question_id=created["question_id"], recipient="U123")
            self.assertEqual(delivery["status"], "pending_connector_delivery")
            waiting = list_open_questions(runtime)[0]
            self.assertEqual(waiting["status"], "waiting_for_reply")
            outbox_path = runtime / "outbox" / "slack" / f"{delivery['delivery_id']}.json"
            self.assertTrue(outbox_path.is_file())

            resolve_open_question(
                runtime, question_id=created["question_id"], answer="Approved", actor="admin-user",
            )
            outbox = json.loads(outbox_path.read_text(encoding="utf-8"))
            self.assertEqual(outbox["status"], "cancelled")
            self.assertEqual(outbox["cancellation_reason"], "question_resolved_before_delivery")

    def test_connector_claim_rechecks_question_and_reconciliation_cancels_stale_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".runtime"
            created = record_open_question(
                runtime, question="Send this?", asked_of="admin", context="Test only."
            )
            delivery = queue_slack_decision(
                runtime, question_id=created["question_id"], recipient="U123"
            )
            claimed = claim_slack_decision_delivery(
                runtime, delivery_id=delivery["delivery_id"]
            )
            self.assertEqual(claimed["status"], "ready_for_connector_delivery")

            question_path = runtime / "awaiting-input" / f"{created['question_id']}.json"
            question = json.loads(question_path.read_text(encoding="utf-8"))
            question["status"] = "resolved"
            question["resolution"] = {"answer": "Already answered", "actor": "admin"}
            question_path.write_text(
                json.dumps(question, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            report = reconcile_open_question_deliveries(runtime)
            self.assertEqual(report["cancelled"], [delivery["delivery_id"]])
            outbox_path = runtime / "outbox" / "slack" / f"{delivery['delivery_id']}.json"
            outbox = json.loads(outbox_path.read_text(encoding="utf-8"))
            self.assertEqual(outbox["status"], "cancelled")
            self.assertEqual(
                outbox["cancellation_reason"], "question_not_waiting_at_delivery_time"
            )
