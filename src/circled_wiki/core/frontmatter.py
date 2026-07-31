"""Markdown plus YAML frontmatter parsing and rendering."""

from pathlib import Path
from typing import Any, Dict

import yaml

from .models import MarkdownDocument


class FrontmatterError(ValueError):
    """Raised when a managed Markdown file has invalid frontmatter."""


def parse_markdown(path: Path) -> MarkdownDocument:
    """Read a Markdown document with an opening and closing `---` delimiter."""
    with path.open(encoding="utf-8", newline="") as document_file:
        text = document_file.read()
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise FrontmatterError("YAML frontmatter must start at the first line")

    lines = text.splitlines(keepends=True)
    end_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if end_index is None:
        raise FrontmatterError("YAML frontmatter closing delimiter is missing")

    try:
        data = yaml.safe_load("".join(lines[1:end_index]))
    except yaml.YAMLError as error:
        raise FrontmatterError(f"invalid YAML frontmatter: {error}") from error
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise FrontmatterError("YAML frontmatter must be a mapping")
    body = "".join(lines[end_index + 1:])
    extensions = data.get("extensions")
    is_embedded_body_original = (
        isinstance(extensions, dict)
        and extensions.get("content_mode") == "embedded"
        and extensions.get("embedded_format_version") == 2
    )
    if not is_embedded_body_original and (body.startswith("---\n") or body.startswith("---\r\n")):
        raise FrontmatterError("Markdown document must contain exactly one YAML frontmatter block")
    return MarkdownDocument(path=path, frontmatter=data, body=body)


def render_markdown(frontmatter: Dict[str, Any], body: str = "") -> str:
    """Render stable, Unicode-safe YAML frontmatter followed by a Markdown body."""
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{yaml_text}---\n{body.lstrip()}"
