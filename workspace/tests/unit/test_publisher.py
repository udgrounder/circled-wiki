import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.publisher import PublishError, push_committed_changes


class PushPublicationTests(unittest.TestCase):
    def test_push_is_disabled_without_install_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".git").mkdir()
            with self.assertRaisesRegex(PublishError, "disabled"):
                push_committed_changes(project, "abc")

    def test_push_uses_only_configured_remote_branch_and_current_head(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".git").mkdir()
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text(
                "schema_version: 1\npublication:\n  push_enabled: true\n  push_remote: origin\n  push_branch: main\n",
                encoding="utf-8",
            )
            responses = [
                subprocess.CompletedProcess([], 0, stdout="abc\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="origin\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ]
            with patch("circled_wiki.core.publisher._git", side_effect=responses) as git:
                result = push_committed_changes(project, "abc")

            self.assertTrue(result["pushed"])
            self.assertEqual(git.call_args_list[-1].args[1:], ("push", "origin", "HEAD:refs/heads/main"))
            self.assertEqual(result["receipt"]["status"], "pushed")

    def test_failed_push_records_retryable_pending_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".git").mkdir()
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text(
                "schema_version: 1\npublication:\n  push_enabled: true\n  push_remote: origin\n  push_branch: main\n",
                encoding="utf-8",
            )
            responses = [
                subprocess.CompletedProcess([], 0, stdout="abc\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="origin\n", stderr=""),
                subprocess.CalledProcessError(1, ["git", "push"]),
            ]
            with patch("circled_wiki.core.publisher._git", side_effect=responses):
                with self.assertRaisesRegex(PublishError, "commit_pending_push receipt recorded"):
                    push_committed_changes(project, "abc")

            receipt = json.loads((project / ".runtime" / "publication" / "push" / "abc.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "commit_pending_push")
            self.assertEqual(receipt["attempts"], 1)

    def test_push_blocks_current_branch_other_than_configured_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".git").mkdir()
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text(
                "schema_version: 1\npublication:\n  push_enabled: true\n  push_remote: origin\n  push_branch: main\n",
                encoding="utf-8",
            )
            responses = [
                subprocess.CompletedProcess([], 0, stdout="abc\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="feature\n", stderr=""),
            ]
            with patch("circled_wiki.core.publisher._git", side_effect=responses):
                with self.assertRaisesRegex(PublishError, "current branch"):
                    push_committed_changes(project, "abc")
