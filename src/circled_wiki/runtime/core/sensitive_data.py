"""Configurable detection and masking for supported high-confidence categories.

This is intentionally not a general PII classifier.  The scanner supports a
small set of high-confidence identifiers, credentials, mobile phone numbers,
email addresses and OAuth authorization-flow candidates.  The active hard-mask
categories are supplied by the installation policy; the caller decides whether
an omitted or disabled category should be processed elsewhere.
"""

from dataclasses import dataclass
import re
from typing import Iterable, Optional
from urllib.parse import parse_qsl, unquote, unquote_plus, urlsplit


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
    r"\s*[:=]\s*)(?P<value>[^\s'\"`&#]+)"
)
_KOREAN_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?im)(?P<label>(?<![가-힣])(?:계정|비밀번호|패스워드|암호)"
    r"(?:\s*[:=]\s*|[ \t]+|\s*\n[ \t]*))"
    r"(?P<value>[^\s'\"`&#]+)"
)
_URL_CANDIDATE = re.compile(r"(?i)(?P<url>https?://[^\s<>\"'`]+)")
_OAUTH_QUERY_PARAMETER = re.compile(
    r"(?i)(?P<prefix>[?&])"
    r"(?P<key>client_secret|code_verifier|access_token|refresh_token|id_token|code|"
    r"client_id|code_challenge|state)"
    r"(?P<separator>=)(?P<value>[^&#\s<>\"'`]+)"
)
_OAUTH_HARD_QUERY_KEYS = frozenset({
    "client_secret", "code", "code_verifier", "access_token", "refresh_token", "id_token",
})
_OAUTH_FLOW_METADATA_KEYS = frozenset({"client_id", "code_challenge", "state"})
_OAUTH_QUERY_MARKERS = frozenset({
    "client_id", "code", "code_challenge", "code_verifier", "redirect_uri",
    "response_type", "scope", "state",
})
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
_CONTACT_SCAN_CATEGORIES = ("mobile_phone_number", "email_address")


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
    disabled_hard_mask_categories: Optional[Iterable[str]] = None,
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
    # A configuration may explicitly disable any supported hard-mask category.
    # Disabled means excluded, not deferred to the sensitivity review queue.
    disabled_hard_categories = set(
        (_DEFAULT_HARD_MASK_CATEGORIES - active_hard_categories)
        if disabled_hard_mask_categories is None else disabled_hard_mask_categories
    )
    if mask_policy_categories:
        # Review-queue and receipt text must not leak either supported
        # residual scanner category.  This convenience mode is
        # independent of the installation's hard-mask toggles.
        active_hard_categories.update(_CONTACT_SCAN_CATEGORIES)

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
        if not mask_policy_categories:
            categories.add("email_address")
        return REDACTED_VALUE

    def redact_mobile_phone(match: re.Match[str]) -> str:
        if "mobile_phone_number" not in active_hard_categories:
            return match.group(0)
        if not mask_policy_categories:
            categories.add("mobile_phone_number")
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
    redacted, oauth_categories = _redact_oauth_credentials(
        redacted, hard_mask_enabled="credential" in active_hard_categories,
    )
    categories.update(oauth_categories)
    redacted = _PRESIGNED_URL_CREDENTIAL.sub(redact_credential, redacted)
    redacted = _CREDENTIAL_ASSIGNMENT.sub(redact_credential, redacted)
    redacted = _KOREAN_CREDENTIAL_ASSIGNMENT.sub(redact_credential, redacted)
    redacted = _KNOWN_TOKEN.sub(
        lambda _match: _redact_token(categories)
        if "credential" in active_hard_categories else _match.group(0),
        redacted,
    )
    redacted = _RESIDENT_REGISTRATION_NUMBER.sub(redact_resident_registration, redacted)
    redacted = _ACCOUNT_NUMBER.sub(redact_account, redacted)
    redacted = _CARD_CANDIDATE.sub(redact_card, redacted)
    # Preserve residual candidates for safe queue/receipt text, but only after
    # high-risk credential/identifier masking has removed embedded secrets.
    policy_candidates_before_mask = tuple(sorted(
        category for category in _detect_unmasked_categories(redacted)
        if category not in disabled_hard_categories
        and (mask_policy_categories or category not in active_hard_categories)
    ))
    redacted = _EMAIL_ADDRESS.sub(redact_email, redacted)
    redacted = _MOBILE_PHONE_NUMBER.sub(redact_mobile_phone, redacted)
    policy_categories = (
        policy_candidates_before_mask
        if mask_policy_categories else tuple(sorted(
            category for category in _detect_unmasked_categories(redacted)
            if category not in disabled_hard_categories
            and category not in active_hard_categories
        ))
    )
    for index, value in enumerate(protected):
        redacted = redacted.replace(f"__CW_LAYOUT_{index}__", value)
    return SensitiveDataPrecheckResult(redacted, tuple(sorted(categories)), policy_categories)


def detect_sensitive_data_categories(content: str) -> tuple[str, ...]:
    """Return high-risk categories still present in text, without exposing them."""
    return redact_sensitive_data(content).categories


def _detect_unmasked_categories(content: str) -> tuple[str, ...]:
    """Detect supported categories still present after active redaction."""
    detected: set[str] = set()
    if _RESIDENT_REGISTRATION_NUMBER.search(content):
        detected.add("resident_registration_number")
    if any(
        match.group("value") != REDACTED_VALUE
        for match in _ACCOUNT_NUMBER.finditer(content)
    ):
        detected.add("account_number")
    if (
        _PRIVATE_KEY_BLOCK.search(content)
        or _PRESIGNED_URL_CREDENTIAL.search(content)
        or _KNOWN_TOKEN.search(content)
        or any(
            match.group("value") != REDACTED_VALUE
            for match in _CREDENTIAL_ASSIGNMENT.finditer(content)
        )
        or any(
            match.group("value") != REDACTED_VALUE
            for match in _KOREAN_CREDENTIAL_ASSIGNMENT.finditer(content)
        )
    ):
        detected.add("credential")
    oauth_credential, oauth_metadata = _detect_oauth_query_categories(content)
    if oauth_credential:
        detected.add("credential")
    if oauth_metadata:
        detected.add("oauth_flow_metadata")
    if any(
        13 <= len(re.sub(r"[ -]", "", match.group(0))) <= 19
        and _luhn_valid(re.sub(r"[ -]", "", match.group(0)))
        for match in _CARD_CANDIDATE.finditer(content)
    ):
        detected.add("card_number")
    if _MOBILE_PHONE_NUMBER.search(content):
        detected.add("mobile_phone_number")
    if _EMAIL_ADDRESS.search(content):
        detected.add("email_address")
    return tuple(sorted(detected))


def _redact_oauth_credentials(content: str, *, hard_mask_enabled: bool) -> tuple[str, set[str]]:
    """Mask only credential values in high-confidence OAuth authorize URLs.

    ``client_id``, ``code_challenge`` and ``state`` are OAuth flow metadata, not
    credentials.  They remain available as policy candidates for the integrated
    sensitivity review and are never hard-masked by the credential switch.
    """
    categories: set[str] = set()

    def replace_url(url_match: re.Match[str]) -> str:
        original = url_match.group("url")
        trailing = ""
        while original and original[-1] in ".,;:!?)]}":
            trailing = original[-1] + trailing
            original = original[:-1]
        if not original or not _is_oauth_authorize_url(original):
            return url_match.group("url")

        def replace_parameter(parameter_match: re.Match[str]) -> str:
            key = parameter_match.group("key").lower()
            value = parameter_match.group("value")
            if hard_mask_enabled and key in _OAUTH_HARD_QUERY_KEYS and value != REDACTED_VALUE:
                categories.add("credential")
                return (
                    f"{parameter_match.group('prefix')}{parameter_match.group('key')}"
                    f"{parameter_match.group('separator')}{REDACTED_VALUE}"
                )
            return parameter_match.group(0)

        return _OAUTH_QUERY_PARAMETER.sub(replace_parameter, original) + trailing

    return _URL_CANDIDATE.sub(replace_url, content), categories


def _detect_oauth_query_categories(content: str) -> tuple[bool, bool]:
    """Return whether an OAuth URL contains credential or metadata values."""
    credential_found = False
    metadata_found = False
    for url_match in _URL_CANDIDATE.finditer(content):
        url = url_match.group("url").rstrip(".,;:!?)]}")
        if not _is_oauth_authorize_url(url):
            continue
        for parameter_match in _OAUTH_QUERY_PARAMETER.finditer(url):
            if parameter_match.group("value") == REDACTED_VALUE:
                continue
            key = parameter_match.group("key").lower()
            credential_found |= key in _OAUTH_HARD_QUERY_KEYS
            metadata_found |= key in _OAUTH_FLOW_METADATA_KEYS
    return credential_found, metadata_found


def _is_oauth_authorize_url(url: str) -> bool:
    """Recognize OAuth authorization endpoints without treating arbitrary URLs as OAuth."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return False
        path = unquote(parsed.path).lower()
        query_keys = {
            unquote_plus(key).lower()
            for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
        }
    except ValueError:
        return False
    path_signal = (
        "/oauth" in path
        and ("authorize" in path or path.endswith("/auth") or "/auth/" in path)
    )
    query_signal = "client_id" in query_keys and len(query_keys & _OAUTH_QUERY_MARKERS) >= 2
    return path_signal or query_signal


def _redact_token(categories: set[str]) -> str:
    categories.add("credential")
    return REDACTED_VALUE
