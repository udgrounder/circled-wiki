"""Core-owned keyword and frontmatter filtering search."""

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Dict, List, Optional
import unicodedata

from .frontmatter import parse_markdown
from .repository import iter_documents


@dataclass(frozen=True)
class SearchHit:
    path: Path
    document_id: str
    title: str
    document_type: str
    summary: str
    status: str
    owners: List[str]
    review_requested: bool


def search_knowledge(knowledge_root: Path, query: str, filters: Optional[Dict[str, str]] = None) -> List[SearchHit]:
    """Search managed Markdown, preferring rg and falling back to Python scanning."""
    filters = filters or {}
    candidates = _rg_candidates(knowledge_root, query) or list(iter_documents(knowledge_root))
    hits = []
    needle = unicodedata.normalize("NFKC", query).casefold().strip()
    tokens = _query_tokens(needle)
    for path in candidates:
        if path.name in {"index.md", "log.md"}:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        if (
            "bundles" in path.parts
            and "status" not in filters
            and data.get("status") != "active"
        ):
            continue
        if not all(str(data.get(key, "")) == value for key, value in filters.items()):
            continue
        haystack = unicodedata.normalize(
            "NFKC", str(data) + "\n" + document.body
        ).casefold()
        if not _matches_query(haystack, needle, tokens):
            continue
        hits.append(SearchHit(
            path,
            str(data.get("id", "")),
            str(data.get("title", "")),
            str(data.get("type", "")),
            str(data.get("summary", "")),
            str(data.get("status", "")),
            [str(owner) for owner in data.get("owners", []) if isinstance(owner, str)],
            bool(data.get("extensions", {}).get("review_requested"))
            if isinstance(data.get("extensions"), dict) else False,
        ))
    return hits


def _rg_candidates(knowledge_root: Path, query: str) -> List[Path]:
    rg = shutil.which("rg")
    if not rg:
        return []
    completed = subprocess.run([rg, "-l", "-i", "--glob", "*.md", query, str(knowledge_root / "bundles"), str(knowledge_root / "evidence")], capture_output=True, text=True, check=False)
    return [Path(line) for line in completed.stdout.splitlines() if line]


_QUERY_STOPWORDS = {
    "어떤", "것을", "무엇을", "해야", "하나요", "인가요", "주세요", "알려줘",
    "그리고", "또는", "the", "and", "what", "how", "should", "please",
}
_KOREAN_PARTICLE_SUFFIXES = ("에서", "으로", "에게", "부터", "까지", "의", "을", "를", "은", "는", "이", "가", "에", "로")


def _query_tokens(query: str) -> List[str]:
    tokens: List[str] = []
    for raw in re.findall(r"[0-9a-zA-Z가-힣]+", query):
        token = raw.casefold()
        for suffix in _KOREAN_PARTICLE_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                token = token[:-len(suffix)]
                break
        if len(token) < 2 or token in _QUERY_STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens


def _matches_query(haystack: str, needle: str, tokens: List[str]) -> bool:
    if needle and needle in haystack:
        return True
    if not tokens:
        return False
    required = 1 if len(tokens) == 1 else 2
    return sum(token in haystack for token in tokens) >= required
