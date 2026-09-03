import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.git_hygiene import (
    tracked_generated_artifacts,
    verify_curation_completion_staging,
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

    def test_accepts_staged_completed_queue_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self._git_repo(directory)
            queue = self._seed_queue_item(project)
            queue.unlink()
            subprocess.run(["git", "-C", str(project), "add", "--", queue.relative_to(project).as_posix()], check=True)

            result = verify_curation_completion_staging(project)

            self.assertTrue(result["passed"])
            self.assertEqual(result["completed_task_deletions"], [
                "workspace/task/curation_reconciliation/11111111-1111-1111-1111-111111111111.md",
            ])
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(project), "diff", "--cached", "--name-only"],
                    capture_output=True, text=True, check=True,
                ).stdout.splitlines(),
                ["workspace/task/curation_reconciliation/11111111-1111-1111-1111-111111111111.md"],
            )
