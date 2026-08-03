import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.publisher import PublishError, push_committed_changes, resume_pending_push


class PushPublicationTests(unittest.TestCase):
    def test_resume_pending_push_retries_the_single_pending_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            receipt = project / ".runtime" / "publication" / "push" / "abc.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({"commit": "abc", "status": "commit_pending_push"}), encoding="utf-8")
            with (
                patch("circled_wiki.core.publisher._git", return_value=subprocess.CompletedProcess([], 0, stdout="def\n", stderr="")),
                patch("circled_wiki.core.publisher.push_committed_changes", return_value={"pushed": True, "commit": "def"}) as push,
            ):
                result = resume_pending_push(project)
            stored = json.loads(receipt.read_text(encoding="utf-8"))

            push.assert_called_once_with(project, "def")
            self.assertTrue(result["resumed"])
            self.assertEqual(result["pending_count"], 1)
            self.assertEqual(stored["status"], "pushed")
            self.assertEqual(stored["delivered_by"], "def")

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
                subprocess.CompletedProcess([], 0, stdout="def\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
            ]
            with (
                patch("circled_wiki.core.publisher._git", side_effect=responses) as git,
                patch(
                    "circled_wiki.core.publisher._git_result",
                    return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                ) as git_result,
            ):
                result = push_committed_changes(project, "abc")

            self.assertTrue(result["pushed"])
            self.assertEqual(
                git.call_args_list[3].args[1:],
                ("fetch", "--quiet", "origin", "refs/heads/main:refs/remotes/origin/main"),
            )
            self.assertEqual(git_result.call_args.args[1:], ("merge-base", "--is-ancestor", "def", "abc"))
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
                subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                subprocess.CompletedProcess([], 0, stdout="def\n", stderr=""),
                subprocess.CalledProcessError(1, ["git", "push"]),
            ]
            with (
                patch("circled_wiki.core.publisher._git", side_effect=responses),
                patch(
                    "circled_wiki.core.publisher._git_result",
                    return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                ),
            ):
                with self.assertRaisesRegex(PublishError, "commit_pending_push receipt recorded"):
                    push_committed_changes(project, "abc")

            receipt = json.loads((project / ".runtime" / "publication" / "push" / "abc.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "commit_pending_push")
            self.assertEqual(receipt["attempts"], 1)

    def test_push_stops_when_remote_branch_is_ahead(self):
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
                subprocess.CompletedProcess([], 0, stdout="def\n", stderr=""),
            ]
            with (
                patch("circled_wiki.core.publisher._git", side_effect=responses) as git,
                patch(
                    "circled_wiki.core.publisher._git_result",
                    return_value=subprocess.CompletedProcess([], 1, stdout="", stderr=""),
                ),
            ):
                with self.assertRaisesRegex(PublishError, "remote_advanced receipt recorded"):
                    push_committed_changes(project, "abc")

            self.assertNotIn("push", [call.args[1] for call in git.call_args_list])
            receipt = json.loads((project / ".runtime" / "publication" / "push" / "abc.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "remote_advanced")

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
