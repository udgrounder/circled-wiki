"""Project-local Knowledge OS settings with backwards-compatible defaults."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Dict, Tuple

import yaml


SAFE_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DEFAULT_ORGANIZATION_ID = "example-org"
DEFAULT_ORGANIZATION_NAME = "Example Organization"
DEFAULT_OPERATOR_AGENT = "hermes"
DEFAULT_WORKFLOW_OWNERS: Tuple[str, ...] = ()
DEFAULT_PUBLICATION_PATHS: Tuple[str, ...] = ("knowledge",)


@dataclass(frozen=True)
class GraphifySettings:
    enabled: bool = False
    installation: str = "external"
    command: str = "graphify-mcp"
    graph_path: str = "graphify-out/graph.json"
    source_paths: Tuple[str, ...] = ("knowledge/bundles",)


@dataclass(frozen=True)
class WorkflowSettings:
    default_owners: Tuple[str, ...] = DEFAULT_WORKFLOW_OWNERS


@dataclass(frozen=True)
class PublicationSettings:
    allowed_paths: Tuple[str, ...] = DEFAULT_PUBLICATION_PATHS


@dataclass(frozen=True)
class KnowledgeOSSettings:
    organization_id: str = DEFAULT_ORGANIZATION_ID
    organization_name: str = DEFAULT_ORGANIZATION_NAME
    operator_agent: str = DEFAULT_OPERATOR_AGENT
    graphify: GraphifySettings = GraphifySettings()
    workflow: WorkflowSettings = WorkflowSettings()
    publication: PublicationSettings = PublicationSettings()


def render_settings(
    *,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    organization_name: str = DEFAULT_ORGANIZATION_NAME,
    operator_agent: str = DEFAULT_OPERATOR_AGENT,
    graphify_enabled: bool = False,
    workflow_default_owners: Tuple[str, ...] = DEFAULT_WORKFLOW_OWNERS,
    publication_allowed_paths: Tuple[str, ...] = DEFAULT_PUBLICATION_PATHS,
) -> str:
    """Render the initial installation-local configuration."""
    settings = _validate_settings({
        "organization": {"id": organization_id, "name": organization_name},
        "agent": {"operator": operator_agent},
        "graphify": {
            "enabled": graphify_enabled,
            "installation": "external",
            "command": "graphify-mcp",
            "graph_path": "graphify-out/graph.json",
            "source_paths": ["knowledge/bundles"],
        },
        "workflow": {"default_owners": list(workflow_default_owners)},
        "publication": {"allowed_paths": list(publication_allowed_paths)},
    })
    payload = {
        "schema_version": 1,
        "organization": {
            "id": settings.organization_id,
            "name": settings.organization_name,
        },
        "agent": {"operator": settings.operator_agent},
        "graphify": {
            "enabled": settings.graphify.enabled,
            "installation": settings.graphify.installation,
            "command": settings.graphify.command,
            "graph_path": settings.graphify.graph_path,
            "source_paths": list(settings.graphify.source_paths),
        },
        "workflow": {
            "default_owners": list(settings.workflow.default_owners),
        },
        "publication": {
            "allowed_paths": list(settings.publication.allowed_paths),
        },
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def load_settings(project_root: Path) -> KnowledgeOSSettings:
    """Load `.circled-wiki/config.yaml`, or preserve legacy defaults when absent."""
    path = project_root / ".circled-wiki" / "config.yaml"
    if not path.is_file():
        return KnowledgeOSSettings()
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(".circled-wiki/config.yaml is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(".circled-wiki/config.yaml schema_version must be 1")
    return _validate_settings(payload)


def organization_id_for(knowledge_root: Path) -> str:
    return load_settings(knowledge_root.resolve().parent).organization_id


def _validate_settings(payload: Dict[str, Any]) -> KnowledgeOSSettings:
    organization = payload.get("organization", {})
    agent = payload.get("agent", {})
    graphify = payload.get("graphify", {})
    workflow = payload.get("workflow", {})
    publication = payload.get("publication", {})
    if any(
        not isinstance(section, dict)
        for section in (organization, agent, graphify, workflow, publication)
    ):
        raise ValueError(
            "organization, agent, graphify, workflow, and publication settings must be objects"
        )
    organization_id = organization.get("id", DEFAULT_ORGANIZATION_ID)
    organization_name = organization.get("name", DEFAULT_ORGANIZATION_NAME)
    operator_agent = agent.get("operator", DEFAULT_OPERATOR_AGENT)
    if not isinstance(organization_id, str) or not SAFE_IDENTIFIER.fullmatch(organization_id):
        raise ValueError("organization.id must be a safe lowercase identifier")
    if not isinstance(organization_name, str) or not organization_name.strip():
        raise ValueError("organization.name must be non-empty")
    if not isinstance(operator_agent, str) or not SAFE_IDENTIFIER.fullmatch(operator_agent):
        raise ValueError("agent.operator must be a safe lowercase identifier")
    graphify_enabled = graphify.get("enabled", False)
    if not isinstance(graphify_enabled, bool):
        raise ValueError("graphify.enabled must be boolean")
    installation = graphify.get("installation", "external")
    command = graphify.get("command", "graphify-mcp")
    graph_path = graphify.get("graph_path", "graphify-out/graph.json")
    source_paths = graphify.get("source_paths", ["knowledge/bundles"])
    if installation != "external":
        raise ValueError("graphify.installation must be external")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("graphify.command must be non-empty")
    if not isinstance(graph_path, str) or not graph_path.strip() or Path(graph_path).is_absolute():
        raise ValueError("graphify.graph_path must be a non-empty project-relative path")
    if ".." in Path(graph_path).parts:
        raise ValueError("graphify.graph_path must stay inside the project root")
    if not isinstance(source_paths, list) or not source_paths or any(
        not isinstance(path, str)
        or not path.strip()
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        for path in source_paths
    ):
        raise ValueError("graphify.source_paths must be project-relative paths")
    default_owners = workflow.get("default_owners", list(DEFAULT_WORKFLOW_OWNERS))
    if not isinstance(default_owners, list) or any(
        not isinstance(owner, str) or not SAFE_IDENTIFIER.fullmatch(owner)
        for owner in default_owners
    ):
        raise ValueError("workflow.default_owners must be safe lowercase identifiers")
    if len(default_owners) != len(set(default_owners)):
        raise ValueError("workflow.default_owners must not contain duplicates")
    allowed_paths = publication.get("allowed_paths", list(DEFAULT_PUBLICATION_PATHS))
    if allowed_paths != list(DEFAULT_PUBLICATION_PATHS):
        raise ValueError(
            "publication.allowed_paths must remain ['knowledge'] to preserve the publication boundary"
        )
    return KnowledgeOSSettings(
        organization_id=organization_id,
        organization_name=organization_name.strip(),
        operator_agent=operator_agent,
        graphify=GraphifySettings(
            enabled=graphify_enabled,
            installation=installation,
            command=command.strip(),
            graph_path=graph_path,
            source_paths=tuple(path.strip() for path in source_paths),
        ),
        workflow=WorkflowSettings(default_owners=tuple(default_owners)),
        publication=PublicationSettings(allowed_paths=tuple(allowed_paths)),
    )
