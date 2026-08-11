"""Installation-local authorization for external collection handoffs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from .schema_validation import validate_yaml_payload
from .settings import SAFE_IDENTIFIER


HANDOFF_PATH = ".circled-wiki/collection-handoff.yaml"
HANDOFF_TEMPLATE_PATH = ".circled-wiki/templates/collection-handoff.yaml"


@dataclass(frozen=True)
class CollectionCollector:
    providers: tuple[str, ...]
    guidance: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionHandoffSettings:
    collectors: dict[str, CollectionCollector]

    def allows(self, collector_id: str) -> tuple[str, ...]:
        collector = self.collectors.get(collector_id)
        return collector.providers if collector else ()

    def guidance_for(self, collector_id: str) -> tuple[str, ...]:
        collector = self.collectors.get(collector_id)
        return collector.guidance if collector else ()


def render_collection_handoff(template_root: Optional[Path] = None) -> str:
    return _template_file(template_root).read_text(encoding="utf-8")


def load_collection_handoff(project_root: Path) -> CollectionHandoffSettings:
    path = project_root / HANDOFF_PATH
    if not path.is_file():
        return CollectionHandoffSettings({})
    try:
        payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{HANDOFF_PATH} is invalid") from error
    validate_yaml_payload(payload, project_root=project_root, schema_name="collection-handoff", instance_name=HANDOFF_PATH)
    collectors = payload.get("collectors", []) if isinstance(payload, dict) else []
    parsed: dict[str, CollectionCollector] = {}
    for entry in collectors:
        if not isinstance(entry, dict):
            raise ValueError(f"{HANDOFF_PATH} collectors must contain objects")
        collector_id, providers, inbox_write, guidance = entry.get("collector_id"), entry.get("providers"), entry.get("inbox_write"), entry.get("guidance", [])
        if not isinstance(collector_id, str) or not SAFE_IDENTIFIER.fullmatch(collector_id):
            raise ValueError(f"{HANDOFF_PATH} collector_id must be a safe lowercase identifier")
        if collector_id in parsed:
            raise ValueError(f"{HANDOFF_PATH} collectors must not contain duplicate collector_id")
        if not isinstance(providers, list) or not providers or any(not isinstance(value, str) or not SAFE_IDENTIFIER.fullmatch(value) for value in providers):
            raise ValueError(f"{HANDOFF_PATH} providers must be a non-empty safe identifier list")
        if len(providers) != len(set(providers)) or not isinstance(inbox_write, bool):
            raise ValueError(f"{HANDOFF_PATH} collector entry is invalid")
        if not isinstance(guidance, list) or any(not isinstance(value, str) or not value.strip() for value in guidance):
            raise ValueError(f"{HANDOFF_PATH} guidance must be a string list")
        parsed[collector_id] = CollectionCollector(
            tuple(providers) if inbox_write else (), tuple(value.strip() for value in guidance),
        )
    return CollectionHandoffSettings(parsed)


def _template_file(project_root: Optional[Path]) -> Path:
    if project_root is not None:
        candidate = project_root / HANDOFF_TEMPLATE_PATH
        if candidate.is_file():
            return candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / HANDOFF_TEMPLATE_PATH
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(HANDOFF_TEMPLATE_PATH)
