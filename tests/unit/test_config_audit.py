import tempfile
import unittest
from pathlib import Path

from knowledge_os.config.settings import render_settings
from knowledge_os.core.config_audit import audit_hardcoded_install_values


class HardcodedInstallValueAuditTests(unittest.TestCase):
    def test_reports_only_install_specific_values_in_selected_source(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text(render_settings(organization_id="acme", organization_name="Acme"), encoding="utf-8")
            config.write_text(config.read_text(encoding="utf-8") + "approval:\n  knowledge_owner: alice\n", encoding="utf-8")
            source = project / "src" / "worker.py"
            source.parent.mkdir()
            source.write_text("ORG = 'acme'\nOWNER = 'alice'\nROOT = '" + str(project.resolve()) + "'\n", encoding="utf-8")

            findings = audit_hardcoded_install_values(project)

            self.assertEqual({item["kind"] for item in findings}, {"organization_id", "knowledge_owner", "project_path"})
