"""Conservative pre-Inbox redaction for high-risk identifiers and credentials.

This is intentionally not a general PII classifier.  It only handles the
small, high-confidence set that must never be copied into a Wiki capture:
Korean resident registration numbers, financial account/card numbers, and
credentials.  Names, email addresses, telephone numbers, and ordinary internal
URLs are outside this automatic rule and remain subject to the normal reviewer
judgment.
"""

from dataclasses import dataclass
import re


REDACTED_VALUE = "********"


@dataclass(frozen=True)
class SensitiveDataPrecheckResult:
    """Safe text plus the non-sensitive categories that were redacted."""

    content: str
    categories: tuple[str, ...]


_RESIDENT_REGISTRATION_NUMBER = re.compile(
    r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)"
)
_ACCOUNT_NUMBER = re.compile(
    r"(?i)(?P<label>계좌(?:\s*번호)?|account(?:\s*number)?)"
    r"(?P<separator>\s*[:=]?\s*)"
    r"(?P<value>\d(?:[\d -]{8,22}\d))"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?im)(?P<label>\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"token|password|passwd|secret|client[_ -]?secret|private[_ -]?key)\b"
    r"\s*[:=]\s*)(?P<value>[^\s'\"`]+)"
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    re.DOTALL,
)
_KNOWN_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,})(?![A-Za-z0-9_-])"
)
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_valid(number: str) -> bool:
    digits = [int(value) for value in number]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def redact_sensitive_data(content: str) -> SensitiveDataPrecheckResult:
    """Mask only high-confidence identifiers and credentials in ``content``.

    The function does not claim that a text is free of all personal information;
    it records only categories actually redacted.  This makes it safe to run
    before every text Inbox capture without broad automatic PII processing.
    """
    if not isinstance(content, str):
        raise TypeError("content must be a string")

    categories: set[str] = set()

    def redact_resident_registration(match: re.Match[str]) -> str:
        categories.add("resident_registration_number")
        return REDACTED_VALUE

    def redact_account(match: re.Match[str]) -> str:
        categories.add("account_number")
        return f"{match.group('label')}{match.group('separator')}{REDACTED_VALUE}"

    def redact_credential(match: re.Match[str]) -> str:
        categories.add("credential")
        return f"{match.group('label')}{REDACTED_VALUE}"

    def redact_card(match: re.Match[str]) -> str:
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            categories.add("card_number")
            return REDACTED_VALUE
        return match.group(0)

    redacted = _PRIVATE_KEY_BLOCK.sub(REDACTED_VALUE, content)
    if redacted != content:
        categories.add("credential")
    redacted = _CREDENTIAL_ASSIGNMENT.sub(redact_credential, redacted)
    redacted = _KNOWN_TOKEN.sub(lambda _match: _redact_token(categories), redacted)
    redacted = _RESIDENT_REGISTRATION_NUMBER.sub(redact_resident_registration, redacted)
    redacted = _ACCOUNT_NUMBER.sub(redact_account, redacted)
    redacted = _CARD_CANDIDATE.sub(redact_card, redacted)
    return SensitiveDataPrecheckResult(redacted, tuple(sorted(categories)))


def detect_sensitive_data_categories(content: str) -> tuple[str, ...]:
    """Return high-risk categories still present in text, without exposing them."""
    return redact_sensitive_data(content).categories


def _redact_token(categories: set[str]) -> str:
    categories.add("credential")
    return REDACTED_VALUE
