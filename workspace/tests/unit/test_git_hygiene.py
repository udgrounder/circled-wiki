import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_os.core.git_hygiene import tracked_generated_artifacts


class GitHygieneTests(unittest.TestCase):
    def test_lists_tracked_generated_artifacts_without_mutating_git(self):
        completed = subprocess.CompletedProcess([], 0, stdout="knowledge/.raw/source.bin\nsrc/app.py\n.runtime/tasks/a.json\n", stderr="")
        with patch("knowledge_os.core.git_hygiene.subprocess.run", return_value=completed):
            result = tracked_generated_artifacts(Path("/project"))
        self.assertEqual([item["path"] for item in result], ["knowledge/.raw/source.bin", ".runtime/tasks/a.json"])
