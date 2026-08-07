"""Installation-local data-protection policy and scanner feature switches."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from .schema_validation import validate_yaml_payload


POLICY_PATH = ".circled-wiki/data-protection.yaml"
POLICY_TEMPLATE_PATH = ".circled-wiki/templates/data-protection.yaml"
POLICY_REF = "inbox-sensitivity/v1"
# Scanner capabilities, not the active policy.  The YAML file controls which
# of these supported categories are enabled for an installation.
SUPPORTED_HARD_MASK_CATEGORIES = (
    "resident_registration_number",
    "account_number",
    "card_number",
    "credential",
    "mobile_phone_number",
    "email_address",
)
KNOWN_SCAN_CATEGORIES = frozenset(SUPPORTED_HARD_MASK_CATEGORIES)


@dataclass(frozen=True)
class DataProtectionPolicy:
    schema_version: int
    policy_ref: str
    hard_mask_categories: tuple[str, ...]
    disabled_hard_mask_categories: tuple[str, ...]
    agent_mask_categories: tuple[str, ...]
    agent_mask_guidance: dict[str, dict[str, object]]
    missing_policy_action: str


def default_data_protection_policy(project_root: Optional[Path] = None) -> DataProtectionPolicy:
    """Load the product default from the bundled YAML template."""
    template = _policy_template_file(project_root)
    return _parse_policy_payload(
        _read_policy_yaml(template), template_file=template, project_root=project_root,
    )


def render_data_protection_policy(template_root: Optional[Path] = None) -> str:
    """Return the canonical YAML policy template without re-rendering it in Python."""
    return _policy_template_file(template_root).read_text(encoding="utf-8")


def load_data_protection_policy(project_root: Path) -> DataProtectionPolicy:
    """Load the installation policy, using the YAML template only when absent."""
    path = project_root / POLICY_PATH
    if not path.is_file():
        return default_data_protection_policy(project_root)
    try:
        payload = _read_policy_yaml(path)
    except ValueError as error:
        raise ValueError(f"{POLICY_PATH} is invalid") from error
    return _parse_policy_payload(
        payload, template_file=_policy_template_file(project_root), project_root=project_root,
    )


def _policy_template_file(project_root: Optional[Path] = None) -> Path:
    """Find the control-plane YAML shipped beside source or installed runtime."""
    if project_root is not None:
        local_template = project_root / POLICY_TEMPLATE_PATH
        if local_template.is_file():
            return local_template
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / POLICY_TEMPLATE_PATH
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(POLICY_TEMPLATE_PATH)


def _read_policy_yaml(path: Path) -> dict[str, object]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path} is invalid") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML object")
    return payload


def _parse_policy_payload(
    payload: dict[str, object], *, template_file: Optional[Path] = None, project_root: Optional[Path] = None,
) -> DataProtectionPolicy:
    validate_yaml_payload(
        payload,
        project_root=project_root,
        schema_name="data-protection",
        instance_name=POLICY_PATH,
    )
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"{POLICY_PATH} schema_version must be 1")
    pii_scan = payload.get("pii_scan")
    review = payload.get("sensitivity_review")
    if not isinstance(pii_scan, dict) or not isinstance(review, dict):
        raise ValueError(f"{POLICY_PATH} pii_scan and sensitivity_review must be objects")
    allowed_pii_fields = {"policy_version", "hard_mask_categories"}
    unknown_pii_fields = set(pii_scan) - allowed_pii_fields
    if unknown_pii_fields:
        raise ValueError(
            f"{POLICY_PATH} pii_scan contains unsupported fields: {sorted(unknown_pii_fields)}"
        )
    allowed_review_fields = {"policy_ref", "agent_mask_categories", "missing_policy_action"}
    unknown_review_fields = set(review) - allowed_review_fields
    if unknown_review_fields:
        raise ValueError(
            f"{POLICY_PATH} sensitivity_review contains unsupported fields: "
            f"{sorted(unknown_review_fields)}"
        )
    hard_mask_value = pii_scan.get("hard_mask_categories")
    hard_mask = _hard_mask_categories(hard_mask_value)
    disabled_hard_mask = _disabled_hard_mask_categories(hard_mask_value)
    agent_mask_value = review.get("agent_mask_categories")
    if agent_mask_value is None:
        agent_mask_value = _template_review_defaults(template_file)["agent_mask_categories"]
    agent_mask_categories, agent_mask_guidance = _agent_mask_definitions(
        agent_mask_value, "sensitivity_review.agent_mask_categories",
    )
    if not set(hard_mask) <= KNOWN_SCAN_CATEGORIES:
        raise ValueError(f"{POLICY_PATH} contains a hard-mask category without a scanner")
    if review.get("policy_ref") != POLICY_REF:
        raise ValueError(f"{POLICY_PATH} sensitivity_review.policy_ref must be {POLICY_REF}")
    if review.get("missing_policy_action") != "awaiting_user":
        raise ValueError(f"{POLICY_PATH} missing_policy_action must be awaiting_user")
    return DataProtectionPolicy(
        1, POLICY_REF, tuple(hard_mask), tuple(disabled_hard_mask), tuple(agent_mask_categories),
        agent_mask_guidance, "awaiting_user",
    )


def _template_review_defaults(template_file: Optional[Path] = None) -> dict[str, object]:
    payload = _read_policy_yaml(template_file or _policy_template_file())
    review = payload.get("sensitivity_review")
    if not isinstance(review, dict) or not isinstance(review.get("agent_mask_categories"), dict):
        raise ValueError(f"{POLICY_TEMPLATE_PATH} agent_mask_categories must be a mapping")
    return review


def resolve_policy_context(policy: DataProtectionPolicy, detected_categories: tuple[str, ...], context: str) -> str:
    """Resolve residual scanner detections without a preservation allowlist.

    Residual PII is not automatically a block.  Agent masking categories are
    the only configured targets; an Agent may pass a matching context when it
    is about to submit an exact finding for masking.  Values outside those
    targets continue unchanged.
    """
    if not detected_categories:
        return "no_policy_candidates"
    if not isinstance(context, str):
        return policy.missing_policy_action
    if not context.strip():
        return "no_mask_target"
    if context.strip() in policy.agent_mask_categories:
        return policy.missing_policy_action
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
    to ``true``.  The YAML template explicitly writes
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


def _disabled_hard_mask_categories(value: Any) -> list[str]:
    """Return categories explicitly disabled by the installation policy."""
    if value is None:
        return []
    if isinstance(value, list):
        return [
            category for category in SUPPORTED_HARD_MASK_CATEGORIES
            if category not in value
        ]
    if isinstance(value, dict):
        return [category for category, enabled in value.items() if enabled is False]
    return []
