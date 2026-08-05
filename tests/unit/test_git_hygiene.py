import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.git_hygiene import (
    tracked_generated_artifacts,
    verify_curation_archive_transitions,
)


class GitHygieneTests(unittest.TestCase):
    def test_lists_tracked_generated_artifacts_without_mutating_git(self):
        completed = subprocess.CompletedProcess([], 0, stdout="knowledge/.raw/source.bin\nsrc/app.py\n.runtime/tasks/a.json\n", stderr="")
        with patch("circled_wiki.core.git_hygiene.subprocess.run", return_value=completed):
            result = tracked_generated_artifacts(Path("/project"))
        self.assertEqual([item["path"] for item in result], ["knowledge/.raw/source.bin", ".runtime/tasks/a.json"])

    def _git_repo(self, directory: str) -> Path:
        project = Path(directory)
        subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.name", "Test"], check=True)
        return project

    def _seed_queue_item(self, project: Path, evidence_id: str = "11111111-1111-1111-1111-111111111111") -> Path:
        queue = project / "workspace" / "task" / "curation_reconciliation" / f"{evidence_id}.md"
        queue.parent.mkdir(parents=True)
        queue.write_text("---\ntype: contract_task\n---\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(project), "add", "--", queue.relative_to(project).as_posix()], check=True)
        subprocess.run(["git", "-C", str(project), "commit", "-qm", "seed"], check=True)
        return queue

    def test_blocks_staged_queue_deletion_without_archive_addition(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._git_repo(directory)
            queue = self._seed_queue_item(project)
            archive = project / "workspace" / "task" / ".archive" / "curation_reconciliation" / queue.name
            queue.unlink()
            archive.parent.mkdir(parents=True)
            archive.write_text("---\ntype: contract_task\n---\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(project), "add", "--", queue.relative_to(project).as_posix()], check=True)

            result = verify_curation_archive_transitions(project)

            self.assertFalse(result["passed"])
            self.assertEqual(result["missing_archive"], [
                "workspace/task/.archive/curation_reconciliation/11111111-1111-1111-1111-111111111111.md",
            ])
            self.assertTrue(archive.is_file())
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(project), "diff", "--cached", "--name-only"],
                    capture_output=True, text=True, check=True,
                ).stdout.splitlines(),
                ["workspace/task/curation_reconciliation/11111111-1111-1111-1111-111111111111.md"],
            )

    def test_accepts_staged_queue_deletion_and_archive_addition_as_one_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._git_repo(directory)
            queue = self._seed_queue_item(project)
            archive = project / "workspace" / "task" / ".archive" / "curation_reconciliation" / queue.name
            queue.unlink()
            archive.parent.mkdir(parents=True)
            archive.write_text("---\ntype: contract_task\n---\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(project), "add", "--", queue.relative_to(project).as_posix(), archive.relative_to(project).as_posix()],
                check=True,
            )

            result = verify_curation_archive_transitions(project)

            self.assertTrue(result["passed"])
            self.assertEqual(result["checked_count"], 1)
            self.assertEqual(result["transitions"][0]["archive_status"], "A")

    def test_blocks_orphaned_archive_addition(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._git_repo(directory)
            archive = project / "workspace" / "task" / ".archive" / "curation_reconciliation" / "22222222-2222-2222-2222-222222222222.md"
            archive.parent.mkdir(parents=True)
            archive.write_text("---\ntype: contract_task\n---\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(project), "add", "--", archive.relative_to(project).as_posix()], check=True)

            result = verify_curation_archive_transitions(project)

            self.assertFalse(result["passed"])
            self.assertEqual(result["orphaned_archive_additions"], [
                "workspace/task/.archive/curation_reconciliation/22222222-2222-2222-2222-222222222222.md",
            ])
