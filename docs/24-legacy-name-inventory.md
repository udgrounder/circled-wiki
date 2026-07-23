# Circled Wiki Legacy Name Inventory

**Generated review date:** 2026-07-22  
**Official user-facing name:** Circled Wiki  
**Compatibility identifiers retained:** `knowledge-os` CLI, `knowledge_os` Python package, `.circled-wiki/bin/knowledge-os.py`

## Classification

| Class | Current locations | Migration rule |
| --- | --- | --- |
| User-facing product text | `README.md`, `docs/17-human-guide.md`, `docs/18-agent-guide.md`, bootstrap prompts | Replace with **Circled Wiki** unless explaining a legacy command/package. |
| Runtime/agent contracts | `AGENTS.md`, `OPERATING_RULES.md`, `agent-rules/` | Replace product wording, but keep file paths and compatibility command names until deprecation. |
| Compatibility code | `src/knowledge_os/`, `pyproject.toml`, `knowledge-os` CLI parser and bootstrap runtime | Do not rename without a versioned CLI/package alias and migration test. |
| Historical/reference material | `docs/source/`, `docs/AI_Knowledge_OS_Build_Plan.md`, older architecture documents | Preserve original quotations; add a Circled Wiki context note only when actively maintained. |
| Tests | `workspace/tests/unit/test_bootstrap.py`, `workspace/tests/unit/test_cli.py` | Update display assertions after compatibility alias behavior is specified; retain compatibility-command coverage. |

## Current inventory

The following tracked files contain `Knowledge OS` or `knowledge-os` outside the operational improvement plan:

- `AGENTS.md`, `OPERATING_RULES.md`, `README.md`
- `agent-rules/README.md`, `agent-rules/bootstrap-knowledge-os.md`, `agent-rules/repository-engineering.md`, `agent-rules/system-observation.md`
- `docs/02-architecture.md`, `docs/03-okf-spec.md`, `docs/04-evidence-model.md`, `docs/06-knowledge-service.md`, `docs/08-sync-pipeline.md`, `docs/11-implementation-guidelines.md`, `docs/12-runtime-architecture.md`, `docs/13-future-work.md`, `docs/16-workflow-execution.md`, `docs/17-human-guide.md`, `docs/18-agent-guide.md`, `docs/22-knowledge-quality-and-artifacts.md`, `docs/AI_Knowledge_OS_Build_Plan.md`, `docs/README.md`, `docs/source/chatgpt-llm-wiki-conversation-2026-07-08.md`
- `pyproject.toml`, `src/knowledge_os/__init__.py`, `src/knowledge_os/cli/__main__.py`, `src/knowledge_os/config/paths.py`, `src/knowledge_os/config/settings.py`, `src/knowledge_os/core/bootstrap.py`
- `workspace/tests/unit/test_bootstrap.py`, `workspace/tests/unit/test_cli.py`

## Migration acceptance criteria

1. New installation prompts, README headings, MCP descriptions and Agent startup text show **Circled Wiki**.
2. `knowledge-os` and `knowledge_os` remain functional throughout the published compatibility period.
3. A new `circled-wiki` CLI alias must be tested before user-facing references switch to it.
4. Historical source documents are not mechanically rewritten.
5. The next release notes the compatibility period and removal decision.

## Compatibility decision

The product name is **Circled Wiki** and `circled-wiki` is the preferred installed CLI. The legacy `knowledge-os` CLI
and `knowledge_os` Python package remain supported without runtime warnings throughout the 0.x compatibility period.
They cannot be removed until a 1.0 release plan explicitly publishes a replacement or removal notice. New user-facing
installation, upgrade, and Agent documentation must use Circled Wiki; legacy identifiers are limited to compatibility
commands and migration notes.
