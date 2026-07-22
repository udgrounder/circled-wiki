"""Project-local Knowledge OS settings with backwards-compatible defaults."""

from dataclasses import dataclass
import hashlib
import json
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
DEFAULT_CURATION_TIMEOUT_SECONDS = 60
DEFAULT_CURATION_MAX_RETRIES = 0
DEFAULT_CURATION_MAX_INPUT_BYTES = 120000


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
    push_enabled: bool = False
    push_remote: str = ""
    push_branch: str = ""


@dataclass(frozen=True)
class CurationSettings:
    """Optional LLM adapter settings; disabled unless an installation opts in."""
    enabled: bool = False
    provider: str = ""
    model: str = ""
    command: str = ""
    timeout_seconds: int = DEFAULT_CURATION_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_CURATION_MAX_RETRIES
    max_input_bytes: int = DEFAULT_CURATION_MAX_INPUT_BYTES
    profile_version: str = "v1"


@dataclass(frozen=True)
class ApprovalSettings:
    """Installation-local Active-publication authority; empty means disabled."""
    knowledge_owner: str = ""


@dataclass(frozen=True)
class KnowledgeOSSettings:
    organization_id: str = DEFAULT_ORGANIZATION_ID
    organization_name: str = DEFAULT_ORGANIZATION_NAME
    operator_agent: str = DEFAULT_OPERATOR_AGENT
    graphify: GraphifySettings = GraphifySettings()
    workflow: WorkflowSettings = WorkflowSettings()
    publication: PublicationSettings = PublicationSettings()
    curation: CurationSettings = CurationSettings()
    approval: ApprovalSettings = ApprovalSettings()


def render_settings(
    *,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    organization_name: str = DEFAULT_ORGANIZATION_NAME,
    operator_agent: str = DEFAULT_OPERATOR_AGENT,
    graphify_enabled: bool = False,
    workflow_default_owners: Tuple[str, ...] = DEFAULT_WORKFLOW_OWNERS,
    publication_allowed_paths: Tuple[str, ...] = DEFAULT_PUBLICATION_PATHS,
    curation_enabled: bool = False,
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
        "publication": {"allowed_paths": list(publication_allowed_paths), "push_enabled": False, "push_remote": "", "push_branch": ""},
        "curation": {"enabled": curation_enabled},
        "approval": {"knowledge_owner": ""},
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
            "push_enabled": settings.publication.push_enabled,
            "push_remote": settings.publication.push_remote,
            "push_branch": settings.publication.push_branch,
        },
        "curation": {
            "enabled": settings.curation.enabled,
            "provider": settings.curation.provider,
            "model": settings.curation.model,
            "command": settings.curation.command,
            "timeout_seconds": settings.curation.timeout_seconds,
            "max_retries": settings.curation.max_retries,
            "max_input_bytes": settings.curation.max_input_bytes,
            "profile_version": settings.curation.profile_version,
        },
        "approval": {"knowledge_owner": settings.approval.knowledge_owner},
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
    return _validate_settings(_migrate_settings_payload(payload))


def _migrate_settings_payload(payload: object) -> Dict[str, Any]:
    """Read legacy unversioned settings as v1 without rewriting local config."""
    if not isinstance(payload, dict):
        raise ValueError(".circled-wiki/config.yaml must be an object")
    version = payload.get("schema_version", 0)
    if version == 1:
        return payload
    if version == 0:
        migrated = dict(payload)
        migrated["schema_version"] = 1
        return migrated
    raise ValueError(".circled-wiki/config.yaml schema_version is unsupported")


def organization_id_for(knowledge_root: Path) -> str:
    return load_settings(knowledge_root.resolve().parent).organization_id


def settings_semantic_checksum(project_root: Path) -> str:
    """Stable digest of effective settings, independent of YAML layout or omitted defaults."""
    settings = load_settings(project_root)
    payload = {
        "organization_id": settings.organization_id, "organization_name": settings.organization_name,
        "operator_agent": settings.operator_agent, "graphify": settings.graphify.__dict__,
        "workflow": settings.workflow.__dict__, "publication": settings.publication.__dict__,
        "curation": settings.curation.__dict__, "approval": settings.approval.__dict__,
    }
    encoded = json.dumps(payload, sort_keys=True, default=list, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_settings(payload: Dict[str, Any]) -> KnowledgeOSSettings:
    organization = payload.get("organization", {})
    agent = payload.get("agent", {})
    graphify = payload.get("graphify", {})
    workflow = payload.get("workflow", {})
    publication = payload.get("publication", {})
    curation = payload.get("curation", {})
    approval = payload.get("approval", {})
    if any(
        not isinstance(section, dict)
        for section in (organization, agent, graphify, workflow, publication, curation, approval)
    ):
        raise ValueError(
            "organization, agent, graphify, workflow, publication, curation, and approval settings must be objects"
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
    graphify_command = graphify.get("command", "graphify-mcp")
    graph_path = graphify.get("graph_path", "graphify-out/graph.json")
    source_paths = graphify.get("source_paths", ["knowledge/bundles"])
    if installation != "external":
        raise ValueError("graphify.installation must be external")
    if not isinstance(graphify_command, str) or not graphify_command.strip():
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
    push_enabled = publication.get("push_enabled", False)
    push_remote = publication.get("push_remote", "")
    push_branch = publication.get("push_branch", "")
    if not isinstance(push_enabled, bool):
        raise ValueError("publication.push_enabled must be boolean")
    if any(not isinstance(value, str) for value in (push_remote, push_branch)):
        raise ValueError("publication.push_remote and push_branch must be strings")
    if push_enabled and (not push_remote.strip() or not push_branch.strip()):
        raise ValueError("enabled publication push requires push_remote and push_branch")
    if any("/" in value or value.startswith(".") for value in (push_remote.strip(), push_branch.strip()) if value):
        raise ValueError("publication push remote and branch must be simple names")
    curation_enabled = curation.get("enabled", False)
    provider = curation.get("provider", "")
    model = curation.get("model", "")
    curation_command = curation.get("command", "")
    timeout_seconds = curation.get("timeout_seconds", DEFAULT_CURATION_TIMEOUT_SECONDS)
    max_retries = curation.get("max_retries", DEFAULT_CURATION_MAX_RETRIES)
    max_input_bytes = curation.get("max_input_bytes", DEFAULT_CURATION_MAX_INPUT_BYTES)
    profile_version = curation.get("profile_version", "v1")
    if not isinstance(curation_enabled, bool):
        raise ValueError("curation.enabled must be boolean")
    if any(not isinstance(value, str) for value in (provider, model, curation_command, profile_version)):
        raise ValueError("curation provider, model, command, and profile_version must be strings")
    if curation_enabled and any(not value.strip() for value in (provider, model, curation_command)):
        raise ValueError("enabled curation requires provider, model, and command")
    if not profile_version.strip():
        raise ValueError("curation.profile_version must be non-empty")
    if (not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or timeout_seconds < 1):
        raise ValueError("curation.timeout_seconds must be a positive integer")
    if (not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0):
        raise ValueError("curation.max_retries must be a non-negative integer")
    if (not isinstance(max_input_bytes, int) or isinstance(max_input_bytes, bool) or max_input_bytes < 1):
        raise ValueError("curation.max_input_bytes must be a positive integer")
    knowledge_owner = approval.get("knowledge_owner", "")
    if not isinstance(knowledge_owner, str) or (knowledge_owner and not SAFE_IDENTIFIER.fullmatch(knowledge_owner)):
        raise ValueError("approval.knowledge_owner must be empty or a safe lowercase identifier")
    return KnowledgeOSSettings(
        organization_id=organization_id,
        organization_name=organization_name.strip(),
        operator_agent=operator_agent,
        graphify=GraphifySettings(
            enabled=graphify_enabled,
            installation=installation,
            command=graphify_command.strip(),
            graph_path=graph_path,
            source_paths=tuple(path.strip() for path in source_paths),
        ),
        workflow=WorkflowSettings(default_owners=tuple(default_owners)),
        publication=PublicationSettings(
            allowed_paths=tuple(allowed_paths), push_enabled=push_enabled,
            push_remote=push_remote.strip(), push_branch=push_branch.strip(),
        ),
        curation=CurationSettings(
            enabled=curation_enabled,
            provider=provider.strip(),
            model=model.strip(),
            command=curation_command.strip(),
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_input_bytes=max_input_bytes,
            profile_version=profile_version.strip(),
        ),
        approval=ApprovalSettings(knowledge_owner=knowledge_owner.strip()),
    )
