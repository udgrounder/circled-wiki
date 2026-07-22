"""Last-mile safety checks for untrusted Curation output before repository writes."""

import re
from typing import List


_CREDENTIAL_PATTERNS = (
    re.compile(r"\b(?:sk|pk)_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_PII_PATTERNS = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore (?:all |any |the )?previous instructions", re.IGNORECASE),
    re.compile(r"reveal (?:the )?(?:system|developer) prompt", re.IGNORECASE),
    re.compile(r"(?:시스템|이전) 지시(?:를)? 무시", re.IGNORECASE),
)


def curation_body_safety_errors(body: str) -> List[str]:
    """Return non-sensitive policy errors; callers must not persist rejected output."""
    if not isinstance(body, str) or not body.strip():
        return ["curation body must be non-empty"]
    errors: List[str] = []
    if any(pattern.search(body) for pattern in _CREDENTIAL_PATTERNS):
        errors.append("curation body appears to contain a credential")
    if any(pattern.search(body) for pattern in _PII_PATTERNS):
        errors.append("curation body appears to contain personal data")
    if any(pattern.search(body) for pattern in _INJECTION_PATTERNS):
        errors.append("curation body appears to contain prompt-injection instructions")
    return errors
