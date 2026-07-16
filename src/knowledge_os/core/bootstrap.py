"""Non-destructive installer and upgrader for a Knowledge OS folder."""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


MANIFEST_PATH = ".knowledge-os/manifest.json"
BACKUP_ROOT = ".knowledge-os-backups"
AGENT_ENTRYPOINT_PATH = "AGENTS.md"
CLAUDE_ENTRYPOINT_PATH = "CLAUDE.md"
OPERATING_RULES_REFERENCE = ".knowledge-os/OPERATING_RULES.md"
MANAGED_DIRECTORIES = (
    ".knowledge-os/agent-rules", ".knowledge-os/templates", ".knowledge-os/policies",
    ".knowledge-os/schemas", ".knowledge-os/bin", ".knowledge-os/runtime",
    ".knowledge-os/issues", ".knowledge-os/proposals", ".knowledge-os/history",
)


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
    return """<!-- knowledge-os:agent-bootstrap -->

Refer to `.knowledge-os/AGENT_BOOTSTRAP.md` and `.knowledge-os/OPERATING_RULES.md`.
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
    return """<!-- knowledge-os:claude-bootstrap -->

Refer to `.knowledge-os/AGENT_BOOTSTRAP.md` and `.knowledge-os/OPERATING_RULES.md`.
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


def _backup_operating_system(target: Path, release: str) -> Path:
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
        shutil.copytree(target / ".knowledge-os", destination, symlinks=True)
    except OSError as error:
        raise RuntimeError(
            "Knowledge OS backup failed; upgrade was stopped before modifying the existing OS"
        ) from error
    return destination


def _source_assets(source_root: Path) -> Dict[str, bytes]:
    """Return portable operating assets; never package user Bundle or Evidence data."""
    operating_rules = source_root / "OPERATING_RULES.md"
    if not operating_rules.is_file():
        operating_rules = source_root / ".knowledge-os" / "OPERATING_RULES.md"
    assets: Dict[str, bytes] = {
        ".knowledge-os/OPERATING_RULES.md": operating_rules.read_bytes(),
    }
    for directory, destination in (
        (
            source_root / "agent-rules"
            if (source_root / "agent-rules").is_dir()
            else source_root / ".knowledge-os" / "agent-rules",
            ".knowledge-os/agent-rules",
        ),
        (source_root / ".knowledge-os" / "templates", ".knowledge-os/templates"),
        (source_root / ".knowledge-os" / "policies", ".knowledge-os/policies"),
        (source_root / ".knowledge-os" / "schemas", ".knowledge-os/schemas"),
        (source_root / ".knowledge-os" / "bin", ".knowledge-os/bin"),
        (source_root / ".knowledge-os" / "issues", ".knowledge-os/issues"),
    ):
        for source in sorted(directory.rglob("*")):
            if source.is_file() and source.name != ".DS_Store":
                assets[f"{destination}/{source.relative_to(directory).as_posix()}"] = source.read_bytes()
    agent_guide = source_root / ".knowledge-os" / "AGENT_BOOTSTRAP.md"
    if agent_guide.is_file():
        assets[".knowledge-os/AGENT_BOOTSTRAP.md"] = agent_guide.read_bytes()
    runtime_source = source_root / "src" / "knowledge_os"
    if not runtime_source.is_dir():
        runtime_source = source_root / ".knowledge-os" / "runtime" / "knowledge_os"
    for source in sorted(runtime_source.rglob("*.py")):
        assets[
            ".knowledge-os/runtime/knowledge_os/"
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


def bootstrap_knowledge_root(target: Path, source_root: Path, *, apply: bool = False) -> Dict[str, object]:
    """Plan or safely apply OS assets at a user-designated project root.

    Upgrades only write below ``.knowledge-os``. The ``knowledge`` data plane is
    never inventoried, moved, modified, or registered as an OS-managed asset.
    """
    target, source_root = target.expanduser().resolve(), source_root.resolve()
    if target == source_root or target == source_root / "knowledge" or target in source_root.parents:
        raise ValueError("bootstrap target must be a separate project root outside the source project")
    manifest_exists = (target / MANIFEST_PATH).exists()
    agent_entrypoint = target / AGENT_ENTRYPOINT_PATH
    agent_entrypoint_action = _agent_entrypoint_action(agent_entrypoint)
    claude_entrypoint = target / CLAUDE_ENTRYPOINT_PATH
    claude_entrypoint_action = _claude_entrypoint_action(claude_entrypoint)
    os_root = target / ".knowledge-os"
    os_exists = os_root.is_dir() and any(os_root.iterdir())
    knowledge_exists = (target / "knowledge").exists()
    knowledge_action = (
        "preserve" if manifest_exists or knowledge_exists else "create_empty_scaffold"
    )
    manifest = _load_manifest(target)
    previous = manifest["assets"]
    if not isinstance(previous, dict):
        raise ValueError("Knowledge OS manifest assets are invalid")
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
            proposal = target / ".knowledge-os" / "proposals" / f"{relative.replace('/', '__')}.new"
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
    os_mutation_required = bool(writes or manifest_needs_update or directories_missing)
    backup_required = os_exists and os_mutation_required
    backup_path = None
    if apply:
        if backup_required:
            prior_release = previous_release if isinstance(previous_release, str) else "unversioned"
            backup_path = _backup_operating_system(target, prior_release)
        for directory in MANAGED_DIRECTORIES:
            (target / directory).mkdir(parents=True, exist_ok=True)
        for destination, content in writes:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
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
    states = ("create", "upgrade", "preserve_existing", "unchanged", "preserve_and_propose")
    return {"target": str(target), "applied": apply, "actions": actions,
            "knowledge_action": knowledge_action,
            "os_release": release,
            "agent_entrypoint_action": agent_entrypoint_action,
            "claude_entrypoint_action": claude_entrypoint_action,
            "backup_required": backup_required,
            "backup_path": str(backup_path) if backup_path is not None else None,
            "summary": {state: sum(item["action"] == state for item in actions) for state in states}}
