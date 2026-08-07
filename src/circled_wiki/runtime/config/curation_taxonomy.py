"""Installation-local Curation taxonomy, separate from Runtime settings."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Optional

import yaml

from .settings import SAFE_IDENTIFIER
from .schema_validation import validate_yaml_payload


SAFE_SLUG_PREFIX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class CurationRoutingRule:
    match_terms: tuple[str, ...]
    description: str
    domain: str
    bundle_type: str
    auto_create: bool
    slug_prefix: str = ""


@dataclass(frozen=True)
class CurationDomain:
    """An installation-approved domain and its classification boundary."""

    identifier: str
    description: str


TAXONOMY_PATH = ".circled-wiki/curation-taxonomy.yaml"
TAXONOMY_TEMPLATE_PATH = ".circled-wiki/templates/curation-taxonomy.yaml"


@dataclass(frozen=True)
class CurationTaxonomy:
    domains: tuple[CurationDomain, ...] = ()
    routing_rules: tuple[CurationRoutingRule, ...] = ()
    configured: bool = False


def render_curation_taxonomy(template_root: Optional[Path] = None) -> str:
    return _template_file(template_root).read_text(encoding="utf-8")


def load_curation_taxonomy(project_root: Path) -> CurationTaxonomy:
    path = project_root / TAXONOMY_PATH
    if not path.is_file():
        return CurationTaxonomy()
    try:
        payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{TAXONOMY_PATH} is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"{TAXONOMY_PATH} schema_version must be 1")
    validate_yaml_payload(
        payload,
        project_root=project_root,
        schema_name="curation-taxonomy",
        instance_name=TAXONOMY_PATH,
    )
    domains = payload.get("domains", [])
    rules = payload.get("routing_rules", [])
    if not isinstance(domains, list):
        raise ValueError(f"{TAXONOMY_PATH} domains must be a list")
    if not isinstance(rules, list):
        raise ValueError(f"{TAXONOMY_PATH} routing_rules must be a list")
    parsed_domains = tuple(_validate_curation_domain(domain) for domain in domains)
    domain_ids = tuple(domain.identifier for domain in parsed_domains)
    if len(domain_ids) != len(set(domain_ids)):
        raise ValueError(f"{TAXONOMY_PATH} domains must not contain duplicate identifiers")
    parsed_rules = tuple(_validate_curation_routing_rule(rule) for rule in rules)
    unknown_domains = sorted({rule.domain for rule in parsed_rules} - set(domain_ids))
    if unknown_domains:
        raise ValueError(f"{TAXONOMY_PATH} routing rule refers to unknown domain: {unknown_domains[0]}")
    return CurationTaxonomy(
        domains=parsed_domains,
        routing_rules=parsed_rules,
        configured=True,
    )


def _template_file(project_root: Optional[Path]) -> Path:
    if project_root is not None:
        candidate = project_root / TAXONOMY_TEMPLATE_PATH
        if candidate.is_file():
            return candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / TAXONOMY_TEMPLATE_PATH
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(TAXONOMY_TEMPLATE_PATH)


def _validate_curation_routing_rule(value: object) -> CurationRoutingRule:
    if not isinstance(value, dict):
        raise ValueError(f"{TAXONOMY_PATH} routing rule is invalid")
    terms, description = value.get("match_terms"), value.get("description", "")
    domain, bundle_type = value.get("domain"), value.get("bundle_type")
    auto_create = value.get("auto_create")
    slug_prefix = value.get("slug_prefix", "")
    if not isinstance(terms, list) or not terms or any(not isinstance(term, str) or not term.strip() for term in terms):
        raise ValueError(f"{TAXONOMY_PATH} match_terms must be a non-empty string list")
    normalized = tuple(term.strip().casefold() for term in terms)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{TAXONOMY_PATH} match_terms must not contain duplicates")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{TAXONOMY_PATH} description must be a non-empty string")
    if not isinstance(domain, str) or not SAFE_IDENTIFIER.fullmatch(domain):
        raise ValueError(f"{TAXONOMY_PATH} domain must be a safe lowercase identifier")
    if not isinstance(bundle_type, str) or not SAFE_IDENTIFIER.fullmatch(bundle_type):
        raise ValueError(f"{TAXONOMY_PATH} bundle_type must be a safe lowercase identifier")
    if not isinstance(auto_create, bool):
        raise ValueError(f"{TAXONOMY_PATH} auto_create must be boolean")
    if not isinstance(slug_prefix, str) or (slug_prefix and not SAFE_SLUG_PREFIX.fullmatch(slug_prefix)):
        raise ValueError(f"{TAXONOMY_PATH} slug_prefix must be a lowercase ASCII slug")
    return CurationRoutingRule(normalized, description.strip(), domain, bundle_type, auto_create, slug_prefix)


def _validate_curation_domain(value: object) -> CurationDomain:
    if not isinstance(value, dict):
        raise ValueError(f"{TAXONOMY_PATH} domain is invalid")
    identifier, description = value.get("id"), value.get("description")
    if not isinstance(identifier, str) or not SAFE_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"{TAXONOMY_PATH} domain id must be a safe lowercase identifier")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{TAXONOMY_PATH} domain description must be a non-empty string")
    return CurationDomain(identifier, description.strip())
