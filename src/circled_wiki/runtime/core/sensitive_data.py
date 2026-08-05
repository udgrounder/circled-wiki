"""Configurable detection and masking for supported high-confidence categories.

This is intentionally not a general PII classifier.  The scanner supports a
small set of high-confidence identifiers, credentials, mobile phone numbers,
and email addresses.  The active hard-mask categories are supplied by the
installation policy; the caller decides whether an omitted or disabled
category should be processed elsewhere.
"""

from dataclasses import dataclass
import re
from typing import Iterable, Optional


REDACTED_VALUE = "********"


@dataclass(frozen=True)
class SensitiveDataPrecheckResult:
    """Safe text plus the non-sensitive categories that were redacted."""

    content: str
    categories: tuple[str, ...]
    policy_categories: tuple[str, ...] = ()


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
_PRESIGNED_URL_CREDENTIAL = re.compile(
    r"(?i)(?P<label>[?&]X-Amz-(?:Security-Token|Credential|Signature)=)"
    r"(?P<value>[^&#\s'\"`\\)]+)"
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
_EMAIL_ADDRESS = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
)
_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
# Hyphenated UUIDs and identifiers can contain a digit sequence that looks
# like a phone number.  Do not match when either edge remains part of such an
# identifier.
_MOBILE_PHONE_NUMBER = re.compile(r"(?<![\d-])(?:010|\+82[ -]?10)[ -]?\d{3,4}[ -]?\d{4}(?![\d-])")
_HTML_LAYOUT_NUMBER = re.compile(r'(?P<attribute>\b(?:width|height)\s*=\s*["\'])(?P<value>\d+(?:\.\d+)?)(?P<end>["\'])', re.I)

_DEFAULT_HARD_MASK_CATEGORIES = frozenset({
    "resident_registration_number",
    "account_number",
    "card_number",
    "credential",
})


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


def redact_sensitive_data(
    content: str, *, mask_policy_categories: bool = False,
    hard_mask_categories: Optional[Iterable[str]] = None,
) -> SensitiveDataPrecheckResult:
    """Mask only high-confidence identifiers and credentials in ``content``.

    The function does not claim that a text is free of all personal information;
    it records only categories actually redacted.  This makes it safe to run
    before every text Inbox capture without broad automatic PII processing.
    """
    if not isinstance(content, str):
        raise TypeError("content must be a string")

    active_hard_categories = set(
        _DEFAULT_HARD_MASK_CATEGORIES if hard_mask_categories is None else hard_mask_categories
    )
    if mask_policy_categories:
        active_hard_categories.add("mobile_phone_number")

    categories: set[str] = set()
    protected: list[str] = []

    def protect_layout(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__CW_LAYOUT_{len(protected) - 1}__"

    content = _HTML_LAYOUT_NUMBER.sub(protect_layout, content)

    def redact_resident_registration(match: re.Match[str]) -> str:
        if "resident_registration_number" not in active_hard_categories:
            return match.group(0)
        categories.add("resident_registration_number")
        return REDACTED_VALUE

    def redact_account(match: re.Match[str]) -> str:
        if "account_number" not in active_hard_categories:
            return match.group(0)
        categories.add("account_number")
        return f"{match.group('label')}{match.group('separator')}{REDACTED_VALUE}"

    def redact_credential(match: re.Match[str]) -> str:
        if "credential" not in active_hard_categories:
            return match.group(0)
        categories.add("credential")
        return f"{match.group('label')}{REDACTED_VALUE}"

    def redact_email(match: re.Match[str]) -> str:
        if "email_address" not in active_hard_categories:
            return match.group(0)
        categories.add("email_address")
        return REDACTED_VALUE

    def redact_card(match: re.Match[str]) -> str:
        if "card_number" not in active_hard_categories:
            return match.group(0)
        digits = re.sub(r"[ -]", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            categories.add("card_number")
            return REDACTED_VALUE
        return match.group(0)

    redacted = (
        _PRIVATE_KEY_BLOCK.sub(REDACTED_VALUE, content)
        if "credential" in active_hard_categories else content
    )
    if redacted != content:
        categories.add("credential")
    redacted = _PRESIGNED_URL_CREDENTIAL.sub(redact_credential, redacted)
    redacted = _CREDENTIAL_ASSIGNMENT.sub(redact_credential, redacted)
    redacted = _KNOWN_TOKEN.sub(
        lambda _match: _redact_token(categories)
        if "credential" in active_hard_categories else _match.group(0),
        redacted,
    )
    redacted = _RESIDENT_REGISTRATION_NUMBER.sub(redact_resident_registration, redacted)
    redacted = _ACCOUNT_NUMBER.sub(redact_account, redacted)
    redacted = _CARD_CANDIDATE.sub(redact_card, redacted)
    redacted = _EMAIL_ADDRESS.sub(redact_email, redacted)
    policy_categories = (
        ("mobile_phone_number",) if _MOBILE_PHONE_NUMBER.search(redacted) else ()
    )
    if mask_policy_categories and policy_categories:
        redacted = _MOBILE_PHONE_NUMBER.sub(REDACTED_VALUE, redacted)
    for index, value in enumerate(protected):
        redacted = redacted.replace(f"__CW_LAYOUT_{index}__", value)
    return SensitiveDataPrecheckResult(redacted, tuple(sorted(categories)), policy_categories)


def detect_sensitive_data_categories(content: str) -> tuple[str, ...]:
    """Return high-risk categories still present in text, without exposing them."""
    return redact_sensitive_data(content).categories


def _redact_token(categories: set[str]) -> str:
    categories.add("credential")
    return REDACTED_VALUE
