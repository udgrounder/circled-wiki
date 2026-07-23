"""Non-destructive installer and upgrader for a Circled Wiki folder."""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from circled_wiki.config.settings import (
    DEFAULT_OPERATOR_AGENT,
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_ORGANIZATION_NAME,
    load_settings,
    render_settings,
)


CONTROL_PLANE = ".circled-wiki"
MANIFEST_PATH = f"{CONTROL_PLANE}/manifest.json"
BACKUP_ROOT = ".circled-wiki-backups"
AGENT_ENTRYPOINT_PATH = "AGENTS.md"
CLAUDE_ENTRYPOINT_PATH = "CLAUDE.md"
HERMES_ENTRYPOINT_PATH = "HERMES.md"
GITIGNORE_PATH = ".gitignore"
GITIGNORE_TEMPLATE_PATH = f"{CONTROL_PLANE}/templates/.gitignore"
RUNTIME_ASSET_PREFIX = f"{CONTROL_PLANE}/runtime/circled_wiki/"
OPERATING_RULES_REFERENCE = f"{CONTROL_PLANE}/OPERATING_RULES.md"
AGENT_ROUTER_REFERENCE = f"{CONTROL_PLANE}/AGENT_ROUTER.md"
RUNTIME_PROFILE_ALLOWLIST = (
    "README.md",
    "evidence-ingest.md",
    "inbox-capture.md",
    "inbox-inspection.md",
    "knowledge-curation.md",
    "knowledge-query.md",
    "publication.md",
    "runtime-upgrade-verification.md",
    "system-observation.md",
    "workflow-execution.md",
)
PRODUCT_PROFILE_NAMES = ("repository-engineering.md", "bootstrap-circled-wiki.md")
LEGACY_PRODUCT_PROFILE_NAMES = (
    "repository-engineering.md",
    "bootstrap-knowledge-os.md",
)
LEGACY_ASSET_PREFIXES = (f"{CONTROL_PLANE}/runtime/knowledge_os/",)
LEGACY_ASSET_PATHS = (
    f"{CONTROL_PLANE}/bin/knowledge-os.py",
    *(f"{CONTROL_PLANE}/agent-rules/{name}" for name in LEGACY_PRODUCT_PROFILE_NAMES),
)
MANAGED_DIRECTORIES = (
    f"{CONTROL_PLANE}/agent-rules", f"{CONTROL_PLANE}/templates", f"{CONTROL_PLANE}/policies",
    f"{CONTROL_PLANE}/schemas", f"{CONTROL_PLANE}/bin", f"{CONTROL_PLANE}/runtime",
    f"{CONTROL_PLANE}/proposals", f"{CONTROL_PLANE}/history",
)
GITIGNORE_BEGIN = "# BEGIN circled-wiki:generated-artifacts"
GITIGNORE_END = "# END circled-wiki:generated-artifacts"
LEGACY_GITIGNORE_MARKER = "# circled-wiki:generated-artifacts"


def _checksum(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _release_id(assets: Dict[str, str]) -> str:
    """Return a stable version identifier for the installed managed assets."""
    digest = hashlib.sha256()
    for path, checksum in sorted(assets.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(checksum.encode("utf-8"))
        digest.update(b"\0")
    return f"v1-{digest.hexdigest()[:12]}"


def _agent_entrypoint_reference_block() -> str:
    """Return an append-only, reference-only block for an existing agent file."""
    return """<!-- circled-wiki:agent-bootstrap -->

Refer to `.circled-wiki/AGENT_BOOTSTRAP.md`, `.circled-wiki/AGENT_ROUTER.md`,
and `.circled-wiki/OPERATING_RULES.md`.
"""


def _agent_entrypoint_content() -> str:
    """Return the root shim that makes the OS visible to coding agents."""
    return "# Circled Wiki Agent Entry Point\n\n" + _agent_entrypoint_reference_block()


def _agent_entrypoint_action(path: Path) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if content.startswith("# Circled Wiki Agent Entry Point\n\nThis project uses Circled Wiki."):
        return "replace_legacy_generated_entrypoint"
    if AGENT_ROUTER_REFERENCE in content:
        return "preserve_existing"
    return "append_operating_reference"


def _claude_entrypoint_reference_block() -> str:
    """Return an append-only, reference-only block for Claude."""
    return """<!-- circled-wiki:claude-bootstrap -->

Refer to `.circled-wiki/AGENT_BOOTSTRAP.md`, `.circled-wiki/AGENT_ROUTER.md`,
and `.circled-wiki/OPERATING_RULES.md`.
"""


def _claude_entrypoint_content() -> str:
    return "# Circled Wiki Claude Entry Point\n\n" + _claude_entrypoint_reference_block()


def _claude_entrypoint_action(path: Path) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if AGENT_ROUTER_REFERENCE in content:
        return "preserve_existing"
    return "append_operating_reference"


def _hermes_entrypoint_reference_block() -> str:
    """Return the reference-only block for an autonomous Hermes process."""
    return """<!-- circled-wiki:hermes-bootstrap -->

On startup, read `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`,
`.circled-wiki/AGENT_BOOTSTRAP.md`, `.circled-wiki/AGENT_ROUTER.md`,
and `.circled-wiki/OPERATING_RULES.md`.
"""


def _hermes_entrypoint_content() -> str:
    return "# Circled Wiki Hermes Entry Point\n\n" + _hermes_entrypoint_reference_block()


def _hermes_entrypoint_action(path: Path) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if (
        f"{CONTROL_PLANE}/AUTONOMOUS_AGENT_STARTUP.md" in content
        and AGENT_ROUTER_REFERENCE in content
    ):
        return "preserve_existing"
    return "append_operating_reference"


def _load_gitignore_template(source_root: Path) -> tuple[str, List[str]]:
    template = source_root / GITIGNORE_TEMPLATE_PATH
    if not template.is_file():
        raise ValueError(f"Circled Wiki Git ignore template is missing: {GITIGNORE_TEMPLATE_PATH}")
    content = template.read_text(encoding="utf-8")
    region = _gitignore_region(content)
    if content.strip() != region:
        raise ValueError("Circled Wiki Git ignore template must contain only the managed region")
    block = region + "\n"
    patterns = [
        line
        for line in region.splitlines()
        if line and not line.startswith("#")
    ]
    if not patterns:
        raise ValueError("Circled Wiki Git ignore template must contain at least one pattern")
    return block, patterns


def _gitignore_action(path: Path, desired_block: str) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if GITIGNORE_BEGIN in content or GITIGNORE_END in content:
        current = _gitignore_region(content)
        return "preserve_existing" if current == desired_block.rstrip("\n") else "replace_generated_artifacts"
    if LEGACY_GITIGNORE_MARKER in content:
        return "migrate_legacy_generated_artifacts"
    return "append_generated_artifacts"


def _gitignore_region(content: str) -> str:
    if content.count(GITIGNORE_BEGIN) != 1 or content.count(GITIGNORE_END) != 1:
        raise ValueError(".gitignore Circled Wiki managed region markers are incomplete or duplicated")
    start = content.index(GITIGNORE_BEGIN)
    end = content.index(GITIGNORE_END, start) + len(GITIGNORE_END)
    return content[start:end]


def _gitignore_missing_patterns(path: Path, desired_patterns: List[str]) -> List[str]:
    if not path.is_file():
        return list(desired_patterns)
    content = path.read_text(encoding="utf-8")
    if GITIGNORE_BEGIN in content or GITIGNORE_END in content:
        current_lines = set(_gitignore_region(content).splitlines())
    elif LEGACY_GITIGNORE_MARKER in content:
        current_lines = set(_legacy_gitignore_region(content).splitlines())
    else:
        current_lines = set()
    return [pattern for pattern in desired_patterns if pattern not in current_lines]


def _legacy_gitignore_region(content: str) -> str:
    start = content.index(LEGACY_GITIGNORE_MARKER)
    remainder = content[start:]
    end = remainder.find("\n\n")
    return remainder if end == -1 else remainder[:end]


def _render_gitignore(content: str, desired_block: str) -> str:
    if GITIGNORE_BEGIN in content or GITIGNORE_END in content:
        current = _gitignore_region(content)
        return content.replace(current, desired_block.rstrip("\n"), 1)
    if LEGACY_GITIGNORE_MARKER in content:
        current = _legacy_gitignore_region(content)
        return content.replace(current, desired_block.rstrip("\n"), 1)
    prefix = content
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + desired_block


def _backup_operating_system(target: Path, release: str, control_plane: Path) -> Path:
    """Copy the complete control plane before any upgrade mutation."""
    backup_root = target / BACKUP_ROOT
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{release}-{timestamp}"
    destination = backup_root / stem
    suffix = 2
    while destination.exists():
        destination = backup_root / f"{stem}-{suffix}"
        suffix += 1
    backup_root.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(control_plane, destination, symlinks=True)
    except OSError as error:
        raise RuntimeError(
            "Circled Wiki backup failed; upgrade was stopped before modifying the existing OS"
        ) from error
    return destination


def rollback_control_plane(target: Path, backup_ref: str) -> Dict[str, object]:
    """Restore one reviewed Control Plane backup without touching user-owned planes."""
    target = target.expanduser().resolve()
    backup_root = (target / BACKUP_ROOT).resolve()
    backup = (target / backup_ref).resolve()
    if backup_root not in backup.parents or not backup.is_dir():
        raise ValueError("backup_ref must identify a Control Plane backup below .circled-wiki-backups")
    control_root = target / CONTROL_PLANE
    if not control_root.is_dir():
        raise ValueError("current .circled-wiki Control Plane is missing")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    displaced = backup_root / f"rollback-displaced-{timestamp}"
    suffix = 2
    while displaced.exists():
        displaced = backup_root / f"rollback-displaced-{timestamp}-{suffix}"
        suffix += 1
    control_root.rename(displaced)
    try:
        shutil.copytree(backup, control_root, symlinks=True)
    except OSError as error:
        if control_root.exists():
            shutil.rmtree(control_root)
        displaced.rename(control_root)
        raise RuntimeError(
            "Control Plane rollback failed; the pre-rollback Control Plane was restored"
        ) from error
    restored_manifest = _load_manifest(target)
    return {
        "target": str(target),
        "restored_backup": backup.as_posix(),
        "displaced_control_plane": displaced.as_posix(),
        "os_release": restored_manifest.get("os_release"),
        "knowledge_action": "preserve",
        "workspace_action": "preserve",
    }


def initialize_operational_workspace(
    target: Path, *, apply: bool = False
) -> Dict[str, object]:
    """Plan or explicitly create only the user-owned Working Plane root."""
    target = target.expanduser().resolve()
    manifest = target / MANIFEST_PATH
    if not manifest.is_file():
        raise ValueError("operational workspace initialization requires a Circled Wiki install")
    workspace = target / "workspace"
    action = "preserve_existing" if workspace.exists() else "create_empty_root"
    if apply and action == "create_empty_root":
        workspace.mkdir(parents=True)
    return {
        "target": str(target),
        "applied": apply,
        "workspace_action": action,
        "path": workspace.as_posix(),
    }


def _source_assets(source_root: Path) -> Dict[str, bytes]:
    """Return portable operating assets; never package user Bundle or Evidence data."""
    operating_rules = source_root / "OPERATING_RULES.md"
    if not operating_rules.is_file():
        operating_rules = source_root / CONTROL_PLANE / "OPERATING_RULES.md"
    assets: Dict[str, bytes] = {
        f"{CONTROL_PLANE}/OPERATING_RULES.md": operating_rules.read_bytes(),
    }
    runtime_profiles = (
        source_root / "agent-rules"
        if (source_root / "agent-rules").is_dir()
        else source_root / CONTROL_PLANE / "agent-rules"
    )
    for filename in RUNTIME_PROFILE_ALLOWLIST:
        source = runtime_profiles / filename
        if source.is_file():
            assets[f"{CONTROL_PLANE}/agent-rules/{filename}"] = source.read_bytes()
    for directory, destination in (
        (source_root / CONTROL_PLANE / "templates", f"{CONTROL_PLANE}/templates"),
        (source_root / CONTROL_PLANE / "policies", f"{CONTROL_PLANE}/policies"),
        (source_root / CONTROL_PLANE / "schemas", f"{CONTROL_PLANE}/schemas"),
        (source_root / CONTROL_PLANE / "bin", f"{CONTROL_PLANE}/bin"),
    ):
        for source in sorted(directory.rglob("*")):
            if source.is_file() and source.name != ".DS_Store":
                assets[f"{destination}/{source.relative_to(directory).as_posix()}"] = source.read_bytes()
    agent_guide = source_root / CONTROL_PLANE / "AGENT_BOOTSTRAP.md"
    if agent_guide.is_file():
        assets[f"{CONTROL_PLANE}/AGENT_BOOTSTRAP.md"] = agent_guide.read_bytes()
    for filename in ("AGENT_ROUTER.md", "AUTONOMOUS_AGENT_STARTUP.md", "GRAPHIFY.md"):
        source = source_root / CONTROL_PLANE / filename
        if source.is_file():
            assets[f"{CONTROL_PLANE}/{filename}"] = source.read_bytes()
    runtime_source = source_root / "src" / "circled_wiki"
    if not runtime_source.is_dir():
        runtime_source = source_root / CONTROL_PLANE / "runtime" / "circled_wiki"
    for source in sorted(runtime_source.rglob("*.py")):
        if source.relative_to(runtime_source).as_posix() in {
            "core/issue_workspace.py",
            "product_cli.py",
        }:
            # Operational Issue intake is Product Agent authority and is never
            # shipped inside an installed Wiki runtime.
            continue
        assets[
            f"{CONTROL_PLANE}/runtime/circled_wiki/"
            + source.relative_to(runtime_source).as_posix()
        ] = source.read_bytes()
    return assets


def _load_manifest(target: Path) -> Dict[str, object]:
    path = target / MANIFEST_PATH
    if not path.exists():
        return {"schema_version": 1, "assets": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("Circled Wiki manifest is invalid; repair it before upgrading") from error
    if payload.get("schema_version") != 1 or not isinstance(payload.get("assets"), dict):
        raise ValueError("Circled Wiki manifest schema is unsupported")
    return payload


def bootstrap_circled_wiki(
    target: Path,
    source_root: Path,
    *,
    apply: bool = False,
    organization_id: str = DEFAULT_ORGANIZATION_ID,
    organization_name: str = DEFAULT_ORGANIZATION_NAME,
    operator_agent: str = DEFAULT_OPERATOR_AGENT,
    graphify_enabled: bool = False,
) -> Dict[str, object]:
    """Plan or safely apply OS assets at a user-designated project root.

    Upgrades only write below ``.circled-wiki``. The ``knowledge`` data plane and
    user-owned ``workspace`` working plane are never inventoried, moved, modified,
    backed up, or registered as OS-managed assets.
    """
    target, source_root = target.expanduser().resolve(), source_root.resolve()
    if target == source_root or target == source_root / "knowledge" or target in source_root.parents:
        raise ValueError("bootstrap target must be a separate project root outside the source project")
    control_root = target / CONTROL_PLANE
    manifest_exists = (target / MANIFEST_PATH).exists()
    agent_entrypoint = target / AGENT_ENTRYPOINT_PATH
    agent_entrypoint_action = _agent_entrypoint_action(agent_entrypoint)
    claude_entrypoint = target / CLAUDE_ENTRYPOINT_PATH
    claude_entrypoint_action = _claude_entrypoint_action(claude_entrypoint)
    hermes_entrypoint = target / HERMES_ENTRYPOINT_PATH
    hermes_entrypoint_action = _hermes_entrypoint_action(hermes_entrypoint)
    gitignore = target / GITIGNORE_PATH
    gitignore_block, gitignore_patterns = _load_gitignore_template(source_root)
    gitignore_action = _gitignore_action(gitignore, gitignore_block)
    gitignore_missing_patterns = _gitignore_missing_patterns(gitignore, gitignore_patterns)
    config_path = target / CONTROL_PLANE / "config.yaml"
    configuration_action = "preserve_existing" if config_path.exists() else "create"
    configuration = render_settings(
        organization_id=organization_id,
        organization_name=organization_name,
        operator_agent=operator_agent,
        graphify_enabled=graphify_enabled,
    ).encode("utf-8")
    configured = load_settings(target) if configuration_action == "preserve_existing" else None
    configuration_report = {
        "organization_id": configured.organization_id if configured else organization_id,
        "organization_name": configured.organization_name if configured else organization_name,
        "operator_agent": configured.operator_agent if configured else operator_agent,
        "graphify_enabled": configured.graphify.enabled if configured else graphify_enabled,
    }
    os_root = target / CONTROL_PLANE
    os_exists = os_root.is_dir() and any(os_root.iterdir())
    knowledge_exists = (target / "knowledge").exists()
    knowledge_action = (
        "preserve" if manifest_exists or knowledge_exists else "create_empty_scaffold"
    )
    workspace_exists = (target / "workspace").exists()
    workspace_action = (
        "preserve"
        if manifest_exists or workspace_exists
        else "create_empty_root"
    )
    manifest = _load_manifest(target)
    previous = manifest["assets"]
    if not isinstance(previous, dict):
        raise ValueError("Circled Wiki manifest assets are invalid")
    actions: List[Dict[str, str]] = []
    pending_proposals: List[Dict[str, str]] = []
    next_assets: Dict[str, str] = dict(previous)
    assets = _source_assets(source_root)
    writes: List[tuple[Path, bytes]] = []
    removals: List[Path] = []
    for relative, content in assets.items():
        destination = target / relative
        desired = _checksum(content)
        current = _checksum(destination.read_bytes()) if destination.is_file() else None
        recorded = previous.get(relative)
        if current is None:
            action = "create"; next_assets[relative] = desired
        elif current == desired and recorded == desired:
            action = "unchanged"; next_assets[relative] = desired
        elif current == desired:
            # The installed content already matches the current release. Adopt
            # its checksum even when an older manifest recorded a prior
            # revision; this is how a reviewed proposal becomes resolved.
            action = "adopt"; next_assets[relative] = desired
        elif relative.startswith(RUNTIME_ASSET_PREFIX):
            # Runtime modules are product code, never installation-local
            # configuration.  Configuration belongs in config.yaml; retaining a
            # locally edited module here can leave a new runtime internally
            # incompatible, even though the rest of the upgrade succeeded.
            action = "upgrade"; next_assets[relative] = desired
        elif isinstance(recorded, str) and current == recorded:
            action = "upgrade"; next_assets[relative] = desired
        else:
            action = "preserve_and_propose"
        actions.append({"path": relative, "action": action})
        if action in {"create", "upgrade"}:
            writes.append((destination, content))
        elif action == "preserve_and_propose":
            proposal = target / CONTROL_PLANE / "proposals" / f"{relative.replace('/', '__')}.new"
            pending_proposals.append({
                "path": relative,
                "proposal": proposal.relative_to(target).as_posix(),
                "checksum": desired,
            })
            if not proposal.exists() or _checksum(proposal.read_bytes()) != desired:
                writes.append((proposal, content))
    legacy_assets = sorted(
        relative
        for relative in previous
        if relative in LEGACY_ASSET_PATHS
        or any(relative.startswith(prefix) for prefix in LEGACY_ASSET_PREFIXES)
    )
    for relative in legacy_assets:
        recorded = previous.get(relative)
        destination = target / relative
        if not isinstance(recorded, str):
            continue
        current = _checksum(destination.read_bytes()) if destination.is_file() else None
        next_assets.pop(relative, None)
        if current is None:
            action = "retire_missing"
        elif current == recorded:
            action = "retire_legacy_asset"
            removals.append(destination)
        else:
            action = "preserve_legacy_modified"
            proposal = (
                target
                / CONTROL_PLANE
                / "proposals"
                / f"legacy-asset__{relative.replace('/', '__')}.review.md"
            )
            proposal_content = (
                "# Legacy Circled Wiki Asset Review\n\n"
                f"`{relative}` contains installation-local modifications and was not deleted.\n"
                "Review the local content, preserve any organization-specific instruction in an "
                "appropriate user-owned file, then remove this retired asset in a separately "
                "approved change.\n"
            ).encode("utf-8")
            if not proposal.exists() or proposal.read_bytes() != proposal_content:
                writes.append((proposal, proposal_content))
        actions.append({"path": relative, "action": action})
    legacy_asset_warnings = [
        relative
        for relative in legacy_assets
        if (target / relative).is_file() and (target / relative) not in removals
    ]
    release = _release_id(next_assets)
    runtime_profiles = sorted(
        Path(path).name
        for path in next_assets
        if path.startswith(f"{CONTROL_PLANE}/agent-rules/")
        and path.endswith(".md")
        and not path.endswith("/README.md")
    )
    router_checksum = next_assets.get(f"{CONTROL_PLANE}/AGENT_ROUTER.md")
    previous_release = manifest.get("os_release")
    manifest_needs_update = (
        not manifest_exists
        or previous_release != release
        or previous != next_assets
        or manifest.get("runtime_profiles") != runtime_profiles
        or manifest.get("router_checksum") != router_checksum
        or manifest.get("pending_proposals", []) != pending_proposals
    )
    directories_missing = any(not (target / directory).is_dir() for directory in MANAGED_DIRECTORIES)
    os_mutation_required = bool(
        writes
        or removals
        or manifest_needs_update
        or directories_missing
        or configuration_action == "create"
    )
    backup_required = os_exists and os_mutation_required
    backup_path = None
    if apply:
        if backup_required:
            prior_release = previous_release if isinstance(previous_release, str) else "unversioned"
            backup_path = _backup_operating_system(target, prior_release, os_root)
        for directory in MANAGED_DIRECTORIES:
            (target / directory).mkdir(parents=True, exist_ok=True)
        for destination, content in writes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        for destination in removals:
            destination.unlink()
        for directory in sorted(
            {parent for path in removals for parent in path.parents if parent != target},
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
        # The portable CLI is a real executable entry point.  Source assets are
        # copied as bytes, so its executable permission must be restored after
        # initial installation and after upgrades.
        portable_cli = target / CONTROL_PLANE / "bin" / "circled-wiki.py"
        if portable_cli.is_file():
            portable_cli.chmod(portable_cli.stat().st_mode | 0o111)
        if configuration_action == "create":
            config_path.write_bytes(configuration)
        if manifest_needs_update or backup_path is not None:
            manifest_payload = dict(manifest)
            manifest_payload.update({
                "schema_version": 1,
                "os_release": release,
                "assets": next_assets,
                "runtime_profiles": runtime_profiles,
                "router_checksum": router_checksum,
                "pending_proposals": pending_proposals,
            })
            if backup_path is not None:
                manifest_payload["last_backup"] = backup_path.relative_to(target).as_posix()
            manifest_path = target / MANIFEST_PATH
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        # Initial setup may create an empty data-plane scaffold. Once present, the
        # bootstrap/upgrade process never writes anywhere below knowledge/.
        knowledge_root = target / "knowledge"
        if not manifest_exists and not knowledge_exists:
            for directory in ("inbox", "evidence", "bundles"):
                (knowledge_root / directory).mkdir(parents=True, exist_ok=True)
        # The working plane is user-owned. Initial installation creates only its
        # root; every later bootstrap or upgrade leaves its entire tree untouched.
        if not manifest_exists and not workspace_exists:
            (target / "workspace").mkdir(parents=True, exist_ok=True)
        # This root file is intentionally outside the managed OS manifest. Existing
        # content is retained; only the missing operating-rules reference is appended.
        if agent_entrypoint_action == "create":
            agent_entrypoint.write_text(_agent_entrypoint_content(), encoding="utf-8")
        elif agent_entrypoint_action == "replace_legacy_generated_entrypoint":
            agent_entrypoint.write_text(_agent_entrypoint_content(), encoding="utf-8")
        elif agent_entrypoint_action == "append_operating_reference":
            with agent_entrypoint.open("a", encoding="utf-8") as output:
                if not agent_entrypoint.read_text(encoding="utf-8").endswith("\n"):
                    output.write("\n")
                output.write("\n" + _agent_entrypoint_reference_block())
        if claude_entrypoint_action == "create":
            claude_entrypoint.write_text(_claude_entrypoint_content(), encoding="utf-8")
        elif claude_entrypoint_action == "append_operating_reference":
            with claude_entrypoint.open("a", encoding="utf-8") as output:
                if not claude_entrypoint.read_text(encoding="utf-8").endswith("\n"):
                    output.write("\n")
                output.write("\n" + _claude_entrypoint_reference_block())
        if hermes_entrypoint_action == "create":
            hermes_entrypoint.write_text(_hermes_entrypoint_content(), encoding="utf-8")
        elif hermes_entrypoint_action == "append_operating_reference":
            with hermes_entrypoint.open("a", encoding="utf-8") as output:
                if not hermes_entrypoint.read_text(encoding="utf-8").endswith("\n"):
                    output.write("\n")
                output.write("\n" + _hermes_entrypoint_reference_block())
        if gitignore_action == "create":
            gitignore.write_text(gitignore_block, encoding="utf-8")
        elif gitignore_action in {
            "append_generated_artifacts",
            "replace_generated_artifacts",
            "migrate_legacy_generated_artifacts",
        }:
            current = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
            gitignore.write_text(_render_gitignore(current, gitignore_block), encoding="utf-8")
    states = (
        "create", "adopt", "upgrade", "preserve_existing", "unchanged",
        "preserve_and_propose", "retire_missing", "retire_legacy_asset",
        "preserve_legacy_modified",
    )
    return {"target": str(target), "applied": apply, "actions": actions,
            "knowledge_action": knowledge_action,
            "workspace_action": workspace_action,
            "os_release": release,
            "runtime_profiles": runtime_profiles,
            "router_checksum": router_checksum,
            "pending_proposals": pending_proposals,
            "agent_entrypoint_action": agent_entrypoint_action,
            "claude_entrypoint_action": claude_entrypoint_action,
            "hermes_entrypoint_action": hermes_entrypoint_action,
            "gitignore_action": gitignore_action,
            "gitignore_missing_patterns": gitignore_missing_patterns,
            "configuration_action": configuration_action,
            "configuration": configuration_report,
        "legacy_asset_warnings": legacy_asset_warnings,
            "backup_required": backup_required,
            "backup_path": str(backup_path) if backup_path is not None else None,
            "summary": {state: sum(item["action"] == state for item in actions) for state in states}}
