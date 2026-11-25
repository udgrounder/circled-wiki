"""Markdown plus YAML frontmatter parsing and rendering."""

from pathlib import Path
from typing import Any, Dict
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from collections import OrderedDict

import yaml

from .models import MarkdownDocument


class FrontmatterError(ValueError):
    """Raised when a managed Markdown file has invalid frontmatter."""


_read_cache = ContextVar("markdown_read_cache", default=None)
_CACHE_SOURCE_BYTES = 16 * 1024 * 1024
_CACHE_DOCUMENT_BYTES = 256 * 1024
_CACHE_ENTRIES = 4096


class _ReadCache:
    def __init__(self):
        self.documents = OrderedDict()
        self.source_bytes = 0


def markdown_read_session(function):
    """Reuse unchanged parses within one operation, including nested operations.

    File identity, size and nanosecond timestamps invalidate writes/replacements.
    Copies prevent callers mutating a cached document. Nothing survives the call.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _read_cache.get() is not None:
            return function(*args, **kwargs)
        token = _read_cache.set(_ReadCache())
        try:
            return function(*args, **kwargs)
        finally:
            _read_cache.reset(token)
    return wrapped


def parse_markdown(path: Path) -> MarkdownDocument:
    """Read a Markdown document with an opening and closing `---` delimiter."""
    cache = _read_cache.get()
    key = None
    if cache is not None:
        stat = path.stat()
        key = (path, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        cached = cache.documents.get(path)
        if cached is not None and cached[0] == key:
            cache.documents.move_to_end(path)
            return deepcopy(cached[1])
        if cached is not None:
            cache.source_bytes -= cache.documents.pop(path)[2]
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
    document = MarkdownDocument(path=path, frontmatter=data, body=body)
    if cache is not None and stat.st_size <= min(_CACHE_DOCUMENT_BYTES, _CACHE_SOURCE_BYTES):
        # Bound both retained source bytes and object count. Large originals
        # are parsed normally rather than held for the lifetime of a batch.
        while cache.documents and (
            cache.source_bytes + stat.st_size > _CACHE_SOURCE_BYTES
            or len(cache.documents) >= _CACHE_ENTRIES
        ):
            _, evicted = cache.documents.popitem(last=False)
            cache.source_bytes -= evicted[2]
        cache.documents[path] = (key, deepcopy(document), stat.st_size)
        cache.source_bytes += stat.st_size
    return document


def render_markdown(frontmatter: Dict[str, Any], body: str = "") -> str:
    """Render stable, Unicode-safe YAML frontmatter followed by a Markdown body."""
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{yaml_text}---\n{body.lstrip()}"
