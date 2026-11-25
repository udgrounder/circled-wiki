import os
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

from circled_wiki.core.inbox_temporaries import (
    ingest_temporary_lock, ingest_temporary_path, recover_inbox_temporaries,
)
from circled_wiki.core.ingest import iter_active_inbox_items


class InboxTemporaryRecoveryTests(unittest.TestCase):
    def test_interrupted_new_staging_is_not_an_active_inbox_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            path = ingest_temporary_path(root, ".md")
            path.write_text("unfinished source")
            self.assertEqual(list(iter_active_inbox_items(root)), [])
            self.assertEqual(path.read_text(), "unfinished source")

    def test_preview_then_quarantine_preserves_bytes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            path = root / "inbox/notion" / f".ingest-{uuid4()}.md"
            path.parent.mkdir(parents=True)
            payload = b"unfinished\r\nsource\x00"
            path.write_bytes(payload)
            old = time.time() - 90000
            os.utime(path, (old, old))
            preview = recover_inbox_temporaries(root)
            self.assertEqual(preview["item_count"], 1)
            self.assertTrue(path.exists())
            result = recover_inbox_temporaries(root, apply=True)
            destination = root / "inbox" / result["items"][0]["destination"]
            self.assertEqual(destination.read_bytes(), payload)
            self.assertFalse(path.exists())
            self.assertEqual(list(iter_active_inbox_items(root)), [])
            self.assertEqual(recover_inbox_temporaries(root, apply=True)["item_count"], 0)

    def test_recent_files_user_captures_and_symlinks_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            current = ingest_temporary_path(root, ".md")
            current.write_text("active")
            unrelated = current.parent / ".ingest-user-notes.md"
            unrelated.write_text("personal notes")
            symlink = current.parent / f".ingest-{uuid4()}.md"
            symlink.symlink_to(unrelated)
            self.assertEqual(recover_inbox_temporaries(root, apply=True)["item_count"], 0)
            self.assertTrue(current.exists())
            self.assertTrue(symlink.is_symlink())

    def test_recovery_refuses_to_move_files_while_ingest_is_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            with ingest_temporary_lock(root):
                with self.assertRaisesRegex(ValueError, "already running"):
                    recover_inbox_temporaries(root, apply=True)

    def test_old_valid_capture_with_staging_name_is_preserved(self):
        from circled_wiki.core.ingest import capture_document
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            captured = capture_document(root, "safe source", "manual", title="Keep capture",
                                        why_collected="test", intended_use=["test"], idempotency_key="keep")
            renamed = captured.inbox_path.with_name(f".ingest-{uuid4()}.md")
            captured.inbox_path.rename(renamed)
            old = time.time() - 90000
            os.utime(renamed, (old, old))
            self.assertEqual(recover_inbox_temporaries(root, apply=True)["item_count"], 0)
            self.assertTrue(renamed.exists())

    def test_direct_apply_ignores_access_time_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            path = ingest_temporary_path(root, ".md")
            path.write_text("interrupted source")
            old = time.time() - 90000
            os.utime(path, (old, old))
            result = recover_inbox_temporaries(root, apply=True)
            self.assertEqual(result["item_count"], 1, result)
            self.assertEqual(result["failures"], [])
