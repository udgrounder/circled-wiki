"""Shared structural validation for installation-local YAML configuration."""

import json
from pathlib import Path
from typing import Any, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


def validate_yaml_payload(
    payload: object,
    *,
    project_root: Optional[Path],
    schema_name: str,
    instance_name: str,
) -> None:
    """Validate a parsed YAML value against its registered versioned Schema.

    Installed schemas take precedence.  Source-tree fallback keeps the loader
    usable while bootstrapping a new installation and in product tests.
    """
    schema_path, schema_file = _schema_for_payload(payload, project_root, schema_name)
    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        raise ValueError(f"{schema_path} is invalid") from error
    try:
        validator.validate(payload)
    except ValidationError as error:
        location = "/".join(str(part) for part in error.absolute_path)
        suffix = f" at {location}" if location else ""
        raise ValueError(f"{instance_name} does not match {schema_path}{suffix}: {error.message}") from error


def _schema_for_payload(
    payload: object, project_root: Optional[Path], schema_name: str,
) -> tuple[str, Path]:
    if not isinstance(payload, dict) or not isinstance(payload.get("schema_version"), int):
        raise ValueError(f"{schema_name} YAML must declare an integer schema_version")
    registry_path = ".circled-wiki/schemas/schema-registry.json"
    registry_file = _find_control_file(project_root, registry_path)
    try:
        registry = json.loads(registry_file.read_text(encoding="utf-8"))
        entry = registry["schemas"][schema_name]
        filename = entry["versions"][str(payload["schema_version"])]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{registry_path} has no supported {schema_name} schema_version") from error
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError(f"{registry_path} has an invalid schema file for {schema_name}")
    schema_file = registry_file.parent / filename
    if not schema_file.is_file():
        raise FileNotFoundError(schema_file)
    return f".circled-wiki/schemas/{filename}", schema_file


def _find_control_file(project_root: Optional[Path], relative_path: str) -> Path:
    if project_root is not None:
        installed = project_root / relative_path
        if installed.is_file():
            return installed
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative_path
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(relative_path)
