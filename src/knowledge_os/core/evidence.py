"""Shared helpers for external-file and embedded-text Evidence originals."""

from pathlib import Path
from typing import Optional

from .models import MarkdownDocument


ORIGINAL_CONTENT_START = "<!-- ORIGINAL_CONTENT_START -->"
ORIGINAL_CONTENT_END = "<!-- ORIGINAL_CONTENT_END -->"


def evidence_content_mode(document: MarkdownDocument) -> str:
    extensions = document.frontmatter.get("extensions")
    if isinstance(extensions, dict) and extensions.get("content_mode") == "embedded":
        return "embedded"
    return "external_file"


def embedded_original_text(document: MarkdownDocument) -> Optional[str]:
    """Return the immutable embedded original, excluding its marker comments."""
    start = document.body.find(ORIGINAL_CONTENT_START)
    end = document.body.find(ORIGINAL_CONTENT_END)
    if start < 0 or end < 0 or end < start:
        return None
    start += len(ORIGINAL_CONTENT_START)
    return document.body[start:end]


def evidence_original_bytes(document: MarkdownDocument) -> Optional[bytes]:
    """Read the canonical Evidence original for integrity and curation."""
    if evidence_content_mode(document) == "embedded":
        content = embedded_original_text(document)
        return content.encode("utf-8") if content is not None else None
    original_file = document.frontmatter.get("original_file")
    if not isinstance(original_file, str) or not original_file:
        return None
    original_path = document.path.parent / original_file
    if not original_path.is_file():
        return None
    return original_path.read_bytes()


def evidence_original_path(document: MarkdownDocument) -> Path:
    """Return the file carrying the original; embedded Evidence is self-contained."""
    if evidence_content_mode(document) == "embedded":
        return document.path
    return document.path.parent / str(document.frontmatter.get("original_file", ""))


def render_embedded_body(content: str) -> str:
    """Wrap verbatim UTF-8 source content in stable integrity markers."""
    return (
        "# Conversation Evidence\n\n"
        "## Original Conversation\n\n"
        f"{ORIGINAL_CONTENT_START}{content}{ORIGINAL_CONTENT_END}\n\n"
        "## Derived Summary\n\n"
        "Pending curation.\n"
    )
