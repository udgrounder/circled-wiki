"""Detect installation-specific values accidentally embedded in source assets."""

from pathlib import Path
from typing import Dict, Iterable, List

from circled_wiki.config.settings import load_settings


DEFAULT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".sh"}
DEFAULT_EXCLUDED_PARTS = {".git", ".venv", "knowledge", ".runtime", ".circled-wiki-backups"}


def audit_hardcoded_install_values(project_root: Path, paths: Iterable[Path] = ()) -> List[Dict[str, object]]:
    """Report configured organization/owner/path values found outside local config.

    This is intentionally a report, not a blocker: matches in deployment
    templates require reviewer judgement, while a CI wrapper can fail on any
    unexpected result.
    """
    settings = load_settings(project_root)
    values = {
        "organization_id": settings.organization_id,
        "organization_name": settings.organization_name,
        "knowledge_owner": settings.approval.knowledge_owner,
        "project_path": str(project_root.resolve()),
    }
    targets = list(paths) or [project_root / "src", project_root / "agent-rules", project_root / "HERMES.md"]
    findings: List[Dict[str, object]] = []
    for target in targets:
        for path in _iter_text_files(target):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                for kind, value in values.items():
                    if value and value in line:
                        findings.append({
                            "path": path.relative_to(project_root).as_posix(), "line": line_number,
                            "kind": kind, "value": value,
                        })
    return findings


def _iter_text_files(target: Path):
    if target.is_file():
        if target.suffix.lower() in DEFAULT_SUFFIXES or not target.suffix:
            yield target
        return
    if not target.is_dir():
        return
    for path in target.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in DEFAULT_SUFFIXES:
            continue
        if set(path.parts) & DEFAULT_EXCLUDED_PARTS:
            continue
        yield path
