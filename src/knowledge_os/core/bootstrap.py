"""Non-destructive installer and upgrader for a Knowledge OS folder."""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from knowledge_os.config.settings import (
    DEFAULT_OPERATOR_AGENT,
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_ORGANIZATION_NAME,
    load_settings,
    render_settings,
)


CONTROL_PLANE = ".circled-wiki"
LEGACY_CONTROL_PLANE = ".knowledge-os"
MANIFEST_PATH = f"{CONTROL_PLANE}/manifest.json"
BACKUP_ROOT = ".circled-wiki-backups"
AGENT_ENTRYPOINT_PATH = "AGENTS.md"
CLAUDE_ENTRYPOINT_PATH = "CLAUDE.md"
HERMES_ENTRYPOINT_PATH = "HERMES.md"
GITIGNORE_PATH = ".gitignore"
GITIGNORE_TEMPLATE_PATH = f"{CONTROL_PLANE}/templates/.gitignore"
OPERATING_RULES_REFERENCE = f"{CONTROL_PLANE}/OPERATING_RULES.md"
MANAGED_DIRECTORIES = (
    f"{CONTROL_PLANE}/agent-rules", f"{CONTROL_PLANE}/templates", f"{CONTROL_PLANE}/policies",
    f"{CONTROL_PLANE}/schemas", f"{CONTROL_PLANE}/bin", f"{CONTROL_PLANE}/runtime",
    f"{CONTROL_PLANE}/issues", f"{CONTROL_PLANE}/proposals", f"{CONTROL_PLANE}/history",
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

Refer to `.circled-wiki/AGENT_BOOTSTRAP.md` and `.circled-wiki/OPERATING_RULES.md`.
"""


def _agent_entrypoint_content() -> str:
    """Return the root shim that makes the OS visible to coding agents."""
    return "# Knowledge OS Agent Entry Point\n\n" + _agent_entrypoint_reference_block()


def _agent_entrypoint_action(path: Path) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if content.startswith("# Knowledge OS Agent Entry Point\n\nThis project uses Knowledge OS."):
        return "replace_legacy_generated_entrypoint"
    if OPERATING_RULES_REFERENCE in content:
        return "preserve_existing"
    return "append_operating_reference"


def _claude_entrypoint_reference_block() -> str:
    """Return an append-only, reference-only block for Claude."""
    return """<!-- circled-wiki:claude-bootstrap -->

Refer to `.circled-wiki/AGENT_BOOTSTRAP.md` and `.circled-wiki/OPERATING_RULES.md`.
"""


def _claude_entrypoint_content() -> str:
    return "# Knowledge OS Claude Entry Point\n\n" + _claude_entrypoint_reference_block()


def _claude_entrypoint_action(path: Path) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if OPERATING_RULES_REFERENCE in content:
        return "preserve_existing"
    return "append_operating_reference"


def _hermes_entrypoint_reference_block() -> str:
    """Return the reference-only block for an autonomous Hermes process."""
    return """<!-- circled-wiki:hermes-bootstrap -->

On startup, read `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`,
`.circled-wiki/AGENT_BOOTSTRAP.md`, and `.circled-wiki/OPERATING_RULES.md`.
"""


def _hermes_entrypoint_content() -> str:
    return "# Knowledge OS Hermes Entry Point\n\n" + _hermes_entrypoint_reference_block()


def _hermes_entrypoint_action(path: Path) -> str:
    if not path.exists():
        return "create"
    content = path.read_text(encoding="utf-8")
    if f"{CONTROL_PLANE}/AUTONOMOUS_AGENT_STARTUP.md" in content:
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
            "Knowledge OS backup failed; upgrade was stopped before modifying the existing OS"
        ) from error
    return destination


def _source_assets(source_root: Path) -> Dict[str, bytes]:
    """Return portable operating assets; never package user Bundle or Evidence data."""
    operating_rules = source_root / "OPERATING_RULES.md"
    if not operating_rules.is_file():
        operating_rules = source_root / CONTROL_PLANE / "OPERATING_RULES.md"
    assets: Dict[str, bytes] = {
        f"{CONTROL_PLANE}/OPERATING_RULES.md": operating_rules.read_bytes(),
    }
    for directory, destination in (
        (
            source_root / "agent-rules"
            if (source_root / "agent-rules").is_dir()
            else source_root / CONTROL_PLANE / "agent-rules",
            f"{CONTROL_PLANE}/agent-rules",
        ),
        (source_root / CONTROL_PLANE / "templates", f"{CONTROL_PLANE}/templates"),
        (source_root / CONTROL_PLANE / "policies", f"{CONTROL_PLANE}/policies"),
        (source_root / CONTROL_PLANE / "schemas", f"{CONTROL_PLANE}/schemas"),
        (source_root / CONTROL_PLANE / "bin", f"{CONTROL_PLANE}/bin"),
        (source_root / CONTROL_PLANE / "issues", f"{CONTROL_PLANE}/issues"),
    ):
        for source in sorted(directory.rglob("*")):
            if source.is_file() and source.name != ".DS_Store":
                assets[f"{destination}/{source.relative_to(directory).as_posix()}"] = source.read_bytes()
    agent_guide = source_root / CONTROL_PLANE / "AGENT_BOOTSTRAP.md"
    if agent_guide.is_file():
        assets[f"{CONTROL_PLANE}/AGENT_BOOTSTRAP.md"] = agent_guide.read_bytes()
    for filename in ("AUTONOMOUS_AGENT_STARTUP.md", "GRAPHIFY.md"):
        source = source_root / CONTROL_PLANE / filename
        if source.is_file():
            assets[f"{CONTROL_PLANE}/{filename}"] = source.read_bytes()
    runtime_source = source_root / "src" / "knowledge_os"
    if not runtime_source.is_dir():
        runtime_source = source_root / CONTROL_PLANE / "runtime" / "knowledge_os"
    for source in sorted(runtime_source.rglob("*.py")):
        assets[
            f"{CONTROL_PLANE}/runtime/knowledge_os/"
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
        raise ValueError("Knowledge OS manifest is invalid; repair it before upgrading") from error
    if payload.get("schema_version") != 1 or not isinstance(payload.get("assets"), dict):
        raise ValueError("Knowledge OS manifest schema is unsupported")
    return payload


def bootstrap_knowledge_root(
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

    Upgrades only write below ``.circled-wiki``. The ``knowledge`` data plane is
    never inventoried, moved, modified, or registered as an OS-managed asset.
    """
    target, source_root = target.expanduser().resolve(), source_root.resolve()
    if target == source_root or target == source_root / "knowledge" or target in source_root.parents:
        raise ValueError("bootstrap target must be a separate project root outside the source project")
    control_root = target / CONTROL_PLANE
    legacy_root = target / LEGACY_CONTROL_PLANE
    if control_root.exists() and legacy_root.exists():
        raise ValueError("both .circled-wiki and legacy .knowledge-os exist; resolve the conflict before upgrading")
    legacy_migration_required = legacy_root.is_dir() and not control_root.exists()
    if apply and legacy_migration_required:
        legacy_manifest = legacy_root / "manifest.json"
        release = "legacy"
        if legacy_manifest.is_file():
            try:
                release = str(json.loads(legacy_manifest.read_text(encoding="utf-8")).get("os_release") or release)
            except ValueError:
                pass
        _backup_operating_system(target, release, legacy_root)
        shutil.move(str(legacy_root), str(control_root))
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
    manifest = _load_manifest(target)
    previous = manifest["assets"]
    if not isinstance(previous, dict):
        raise ValueError("Knowledge OS manifest assets are invalid")
    if legacy_migration_required and apply:
        previous = {
            str(path).replace(f"{LEGACY_CONTROL_PLANE}/", f"{CONTROL_PLANE}/", 1): checksum
            for path, checksum in previous.items()
        }
        manifest = dict(manifest)
        manifest["assets"] = previous
    actions: List[Dict[str, str]] = []
    next_assets: Dict[str, str] = dict(previous)
    assets = _source_assets(source_root)
    writes: List[tuple[Path, bytes]] = []
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
            action = "preserve_existing"
        elif isinstance(recorded, str) and current == recorded:
            action = "upgrade"; next_assets[relative] = desired
        else:
            action = "preserve_and_propose"
        actions.append({"path": relative, "action": action})
        if action in {"create", "upgrade"}:
            writes.append((destination, content))
        elif action == "preserve_and_propose":
            proposal = target / CONTROL_PLANE / "proposals" / f"{relative.replace('/', '__')}.new"
            if not proposal.exists() or _checksum(proposal.read_bytes()) != desired:
                writes.append((proposal, content))
    release = _release_id(next_assets)
    previous_release = manifest.get("os_release")
    manifest_needs_update = (
        not manifest_exists
        or previous_release != release
        or previous != next_assets
    )
    directories_missing = any(not (target / directory).is_dir() for directory in MANAGED_DIRECTORIES)
    os_mutation_required = bool(
        writes
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
        if configuration_action == "create":
            config_path.write_bytes(configuration)
        if manifest_needs_update or backup_path is not None:
            manifest_payload = dict(manifest)
            manifest_payload.update({
                "schema_version": 1,
                "os_release": release,
                "assets": next_assets,
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
    states = ("create", "upgrade", "preserve_existing", "unchanged", "preserve_and_propose")
    return {"target": str(target), "applied": apply, "actions": actions,
            "knowledge_action": knowledge_action,
            "os_release": release,
            "agent_entrypoint_action": agent_entrypoint_action,
            "claude_entrypoint_action": claude_entrypoint_action,
            "hermes_entrypoint_action": hermes_entrypoint_action,
            "gitignore_action": gitignore_action,
            "gitignore_missing_patterns": gitignore_missing_patterns,
            "configuration_action": configuration_action,
            "configuration": configuration_report,
            "legacy_migration_required": legacy_migration_required,
            "backup_required": backup_required,
            "backup_path": str(backup_path) if backup_path is not None else None,
            "summary": {state: sum(item["action"] == state for item in actions) for state in states}}
