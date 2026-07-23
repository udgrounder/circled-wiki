"""Small, transport-neutral models shared by Core, CLI, MCP, and workers."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class MarkdownDocument:
    """A Markdown document split into YAML frontmatter and body."""

    path: Path
    frontmatter: Dict[str, Any]
    body: str


@dataclass
class ValidationResult:
    """Validation errors are deliberately split by their governing rule set."""

    path: Path
    okf_errors: List[str] = field(default_factory=list)
    profile_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.okf_errors and not self.profile_errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "valid": self.is_valid,
            "okf_errors": self.okf_errors,
            "profile_errors": self.profile_errors,
            "warnings": self.warnings,
        }

