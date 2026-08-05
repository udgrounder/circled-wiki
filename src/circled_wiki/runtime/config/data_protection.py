"""Installation-local data-protection policy and scanner feature switches."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


POLICY_PATH = ".circled-wiki/data-protection.yaml"
POLICY_REF = "inbox-sensitivity/v1"
DEFAULT_HARD_MASK_CATEGORIES = (
    "resident_registration_number",
    "account_number",
    "card_number",
    "credential",
)
SUPPORTED_HARD_MASK_CATEGORIES = DEFAULT_HARD_MASK_CATEGORIES + (
    "mobile_phone_number",
    "email_address",
)
HARD_MASK_CATEGORIES = DEFAULT_HARD_MASK_CATEGORIES  # compatibility alias
POLICY_EVALUATED_CATEGORIES = ("mobile_phone_number",)
DEFAULT_NON_SENSITIVE_CATEGORIES = (
    "employee_business_contact",
    "partner_business_contact",
)
DEFAULT_AGENT_MASK_CATEGORIES = (
    "compensation",
    "performance_review",
    "disciplinary_action",
    "unlawful_content",
)
DEFAULT_AGENT_MASK_GUIDANCE = {
    "compensation": {
        "description": "개인별 급여·보너스·퇴직금·보상액 또는 산정 결과",
        "include": ["개인별 급여액", "보너스·인센티브", "퇴직금·보상액", "보상 산정 결과"],
        "exclude": ["일반 보상 정책", "공개 급여 범위", "비식별 총액 예산"],
    },
    "performance_review": {
        "description": "개인의 평가 점수·등급·피드백 또는 승진 결정",
        "include": ["개인 평가 점수·등급", "개인 피드백", "승진 결정"],
        "exclude": ["일반 평가 기준", "평가 양식", "비식별 집계 지표"],
    },
    "disciplinary_action": {
        "description": "개인에 대한 징계 사유·절차·결정·조치 기록",
        "include": ["징계 사유", "징계 절차·결정", "개인 조치 기록"],
        "exclude": ["일반 행동강령", "징계 절차 안내", "비식별 교육 자료"],
    },
    "unlawful_content": {
        "description": "명시적인 불법 행위의 실행·조장·은폐 또는 타인의 권리·안전을 침해하는 구체적 지시",
        "include": [
            "불법 행위 실행·조장 지시",
            "사기·뇌물·절도·불법 거래 실행 방법",
            "증거 삭제·감사 방해·규제 회피 지시",
            "타인의 권리·안전을 침해하는 구체적 실행 방법",
        ],
        "exclude": [
            "계약·법률 자문·소송·분쟁·규제 대응 및 결정",
            "법 위반 여부 검토·컴플라이언스 점검",
            "불법 행위의 신고·예방·교육·수사 협조",
            "공개 법령·판례·사건 보도 또는 사실 기록",
        ],
    },
}
KNOWN_SCAN_CATEGORIES = frozenset(SUPPORTED_HARD_MASK_CATEGORIES) | frozenset(POLICY_EVALUATED_CATEGORIES)


@dataclass(frozen=True)
class DataProtectionPolicy:
    schema_version: int
    policy_ref: str
    hard_mask_categories: tuple[str, ...]
    policy_evaluated_categories: tuple[str, ...]
    non_sensitive_categories: tuple[str, ...]
    agent_mask_categories: tuple[str, ...]
    agent_mask_guidance: dict[str, dict[str, object]]
    missing_policy_action: str


def default_data_protection_policy() -> DataProtectionPolicy:
    return DataProtectionPolicy(
        schema_version=1,
        policy_ref=POLICY_REF,
        # Phone and email are supported scanner features, but are explicitly
        # disabled in the product default.  An omitted category in an existing
        # local map is handled separately as ``true`` by the loader.
        hard_mask_categories=DEFAULT_HARD_MASK_CATEGORIES,
        policy_evaluated_categories=POLICY_EVALUATED_CATEGORIES,
        non_sensitive_categories=DEFAULT_NON_SENSITIVE_CATEGORIES,
        agent_mask_categories=DEFAULT_AGENT_MASK_CATEGORIES,
        agent_mask_guidance=DEFAULT_AGENT_MASK_GUIDANCE,
        missing_policy_action="awaiting_user",
    )


def render_data_protection_policy() -> str:
    policy = default_data_protection_policy()
    return yaml.safe_dump({
        "schema_version": policy.schema_version,
        "pii_scan": {
            "policy_version": "v1",
            "hard_mask_categories": {
                category: category in policy.hard_mask_categories
                for category in SUPPORTED_HARD_MASK_CATEGORIES
            },
            "policy_evaluated_categories": list(policy.policy_evaluated_categories),
        },
        "sensitivity_review": {
            "policy_ref": policy.policy_ref,
            "non_sensitive_categories": list(policy.non_sensitive_categories),
            "agent_mask_categories": {
                category: policy.agent_mask_guidance[category]
                for category in policy.agent_mask_categories
            },
            "missing_policy_action": policy.missing_policy_action,
        },
    }, allow_unicode=True, sort_keys=False)


def load_data_protection_policy(project_root: Path) -> DataProtectionPolicy:
    """Load a local policy, falling back to the safe default without rewriting it."""
    path = project_root / POLICY_PATH
    if not path.is_file():
        return default_data_protection_policy()
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{POLICY_PATH} is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"{POLICY_PATH} schema_version must be 1")
    pii_scan = payload.get("pii_scan")
    review = payload.get("sensitivity_review")
    if not isinstance(pii_scan, dict) or not isinstance(review, dict):
        raise ValueError(f"{POLICY_PATH} pii_scan and sensitivity_review must be objects")
    allowed_review_fields = {
        "policy_ref", "non_sensitive_categories", "agent_mask_categories", "missing_policy_action",
    }
    unknown_review_fields = set(review) - allowed_review_fields
    if unknown_review_fields:
        raise ValueError(
            f"{POLICY_PATH} sensitivity_review contains unsupported fields: "
            f"{sorted(unknown_review_fields)}"
        )
    hard_mask = _hard_mask_categories(pii_scan.get("hard_mask_categories"))
    policy_evaluated = _categories(pii_scan.get("policy_evaluated_categories"), "pii_scan.policy_evaluated_categories")
    non_sensitive = _categories(review.get("non_sensitive_categories", []), "sensitivity_review.non_sensitive_categories")
    agent_mask_categories, agent_mask_guidance = _agent_mask_definitions(
        review.get("agent_mask_categories", DEFAULT_AGENT_MASK_GUIDANCE),
        "sensitivity_review.agent_mask_categories",
    )
    if not set(hard_mask) <= KNOWN_SCAN_CATEGORIES:
        raise ValueError(f"{POLICY_PATH} contains a hard-mask category without a scanner")
    if not set(policy_evaluated) <= KNOWN_SCAN_CATEGORIES:
        raise ValueError(f"{POLICY_PATH} contains a policy category without a scanner")
    if set(hard_mask) & set(policy_evaluated):
        raise ValueError(f"{POLICY_PATH} cannot classify a category as both hard-mask and policy-evaluated")
    if set(non_sensitive) & set(agent_mask_categories):
        raise ValueError(f"{POLICY_PATH} cannot classify a category as both non-sensitive and agent-mask")
    if review.get("policy_ref") != POLICY_REF:
        raise ValueError(f"{POLICY_PATH} sensitivity_review.policy_ref must be {POLICY_REF}")
    if review.get("missing_policy_action") != "awaiting_user":
        raise ValueError(f"{POLICY_PATH} missing_policy_action must be awaiting_user")
    return DataProtectionPolicy(
        1, POLICY_REF, tuple(hard_mask), tuple(policy_evaluated), tuple(non_sensitive),
        tuple(agent_mask_categories), agent_mask_guidance, "awaiting_user",
    )


def resolve_policy_context(policy: DataProtectionPolicy, detected_categories: tuple[str, ...], context: str) -> str:
    """Resolve policy-evaluated detections without permitting context inference."""
    if not detected_categories:
        return "no_policy_candidates"
    if not isinstance(context, str) or not context.strip():
        return policy.missing_policy_action
    if context in policy.agent_mask_categories:
        return policy.missing_policy_action
    if context in policy.non_sensitive_categories:
        return "preserve_internal"
    return policy.missing_policy_action


def _categories(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{POLICY_PATH} {field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{POLICY_PATH} {field} must not contain duplicates")
    return [item.strip() for item in value]


def _agent_mask_definitions(value: Any, field: str) -> tuple[list[str], dict[str, dict[str, object]]]:
    if not isinstance(value, dict):
        raise ValueError(f"{POLICY_PATH} {field} must be a mapping")
    guidance: dict[str, dict[str, object]] = {}
    for category, definition in value.items():
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"{POLICY_PATH} {field} category names must be non-empty strings")
        if not isinstance(definition, dict):
            raise ValueError(f"{POLICY_PATH} {field}.{category} must be an object")
        if set(definition) - {"description", "include", "exclude"}:
            raise ValueError(f"{POLICY_PATH} {field}.{category} contains unsupported fields")
        description = definition.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{POLICY_PATH} {field}.{category}.description must be non-empty")
        include = _categories(definition.get("include", []), f"{field}.{category}.include")
        exclude = _categories(definition.get("exclude", []), f"{field}.{category}.exclude")
        if not include:
            raise ValueError(f"{POLICY_PATH} {field}.{category}.include must contain at least one item")
        if set(include) & set(exclude):
            raise ValueError(f"{POLICY_PATH} {field}.{category} include/exclude must not overlap")
        guidance[category.strip()] = {
            "description": description.strip(),
            "include": include,
            "exclude": exclude,
        }
    return list(guidance), guidance


def _hard_mask_categories(value: Any) -> list[str]:
    """Resolve the active hard-mask set from explicit per-category switches.

    A mapping is the canonical schema: an omitted supported category defaults
    to ``true``.  The rendered default policy explicitly writes
    ``mobile_phone_number: false`` and ``email_address: false`` so those
    supported features remain off by default.  The old list form is accepted
    for compatibility and represents the categories explicitly listed there.
    """
    field = "pii_scan.hard_mask_categories"
    if value is None:
        return list(SUPPORTED_HARD_MASK_CATEGORIES)
    if isinstance(value, list):
        return _categories(value, field)
    if not isinstance(value, dict):
        raise ValueError(f"{POLICY_PATH} {field} must be an object of booleans")
    unknown = set(value) - set(SUPPORTED_HARD_MASK_CATEGORIES)
    if unknown:
        raise ValueError(f"{POLICY_PATH} {field} contains unsupported categories: {sorted(unknown)}")
    if any(not isinstance(enabled, bool) for enabled in value.values()):
        raise ValueError(f"{POLICY_PATH} {field} values must be booleans")
    return [
        category for category in SUPPORTED_HARD_MASK_CATEGORIES
        if value.get(category, True)
    ]
