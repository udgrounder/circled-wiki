import tempfile
import unittest
from pathlib import Path

from knowledge_os.core.frontmatter import parse_markdown
from knowledge_os.core.service import KnowledgeService
from knowledge_os.integrations.collector import CollectedItem, collect_items


class CollectorAdapterTests(unittest.TestCase):
    def test_scheduled_collector_lands_text_and_file_snapshots_without_ingesting(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            service = KnowledgeService(knowledge_root)
            report = collect_items(
                service,
                "notion",
                [
                    CollectedItem(
                        external_id="page-1", revision="2026-07-15T01:00:00Z",
                        title="변경된 고객 응대 절차", content="# 고객 응대\n\n변경 내용",
                        source_url="https://www.notion.so/page-1",
                    ),
                    CollectedItem(
                        external_id="file-2", revision="rev-2", title="절차 PDF",
                        content=b"%PDF-1.7\\nsource", original_filename="procedure.pdf",
                    ),
                ],
                why_collected="전일 변경된 업무 원천을 수집",
            )

            self.assertEqual(report["captured_count"], 2)
            self.assertEqual(list((knowledge_root / "evidence").rglob("*.md")), [])
            first_path = knowledge_root.parent / report["receipts"][0]["inbox_path"]
            first = parse_markdown(first_path)
            self.assertEqual(first.frontmatter["provider"], "notion")
            self.assertEqual(first.frontmatter["capture_details"]["external_id"], "page-1")
            repeated = collect_items(
                service,
                "notion",
                [CollectedItem(
                    external_id="page-1", revision="2026-07-15T01:00:00Z",
                    title="변경된 고객 응대 절차", content="# 고객 응대\n\n변경 내용",
                )],
                why_collected="전일 변경된 업무 원천을 수집",
            )
            self.assertTrue(repeated["receipts"][0]["reused"])

