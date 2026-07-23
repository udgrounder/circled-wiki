import unittest

from knowledge_os.integrations.channel import answer_knowledge_query, prepare_channel_workflow


class _Service:
    def search_knowledge(self, request):
        return [{"id": "knowledge://bundle/1", "title": "Customer Support", "summary": "Support procedure"}]

    def read_bundle(self, bundle_id):
        return {
            "id": bundle_id,
            "frontmatter": {"status": "active", "extensions": {"confidence": "verified"}},
            "sources": [{"kind": "original_source", "uri": "https://notion.example/support", "locator": "page=1"}],
        }

    def prepare_task(self, workflow_id, request, inputs):
        return {
            "mode": "workflow_execution",
            "task": {
                "task_id": "task-1", "workflow_id": workflow_id, "status": "awaiting_input",
                "missing_inputs": ["customer_id"],
                "required_inputs": [{"name": "customer_id", "description": "고객 식별자"}],
            },
            "context": {"bundles": []},
        }


class ChannelIntegrationTests(unittest.TestCase):
    def test_query_returns_bundle_support_and_source_links(self):
        response = answer_knowledge_query(_Service(), "고객 응대 절차")
        self.assertEqual(response["mode"], "knowledge_query")
        self.assertEqual(response["answers"][0]["support_status"], "verified")
        self.assertEqual(response["answers"][0]["sources"][0]["uri"], "https://notion.example/support")

    def test_workflow_preparation_returns_missing_input_questions(self):
        response = prepare_channel_workflow(_Service(), "고객 처리", workflow_id="customer-support")
        self.assertEqual(response["status"], "awaiting_input")
        self.assertEqual(response["questions"], [{"input": "customer_id", "question": "고객 식별자"}])
