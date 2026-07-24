# Circled Wiki Naming Completion Audit

**Generated review date:** 2026-07-22  
**Official user-facing name:** Circled Wiki  
**Canonical identifiers:** `circled-wiki` CLI, `circled_wiki` Python package, `.circled-wiki/bin/circled-wiki.py`

## Classification

| Class | Current locations | Migration rule |
| --- | --- | --- |
| User-facing product text | `README.md`, `docs/17-human-guide.md`, `docs/18-agent-guide.md`, bootstrap prompts | Use **Circled Wiki** only. |
| Runtime/agent contracts | `AGENTS.md`, `OPERATING_RULES.md`, `agent-rules/` | Use canonical Circled Wiki command and path names. |
| Python implementation | `src/circled_wiki/`, `pyproject.toml`, CLI parser and bootstrap runtime | Use `circled_wiki` and `circled-wiki` only. |
| Historical/reference material | `docs/source/`, `docs/AI_Circled_Wiki_Build_Plan.md`, older architecture documents | Normalize product naming when the document remains part of this repository. |
| Tests | `tests/` | Cover canonical names only. |

## Current inventory

The following tracked files contain `Circled Wiki` or `circled-wiki` outside the operational improvement plan:

- `AGENTS.md`, `OPERATING_RULES.md`, `README.md`
- `agent-rules/README.md`, `agent-rules/bootstrap-circled-wiki.md`, `agent-rules/repository-engineering.md`, `agent-rules/system-observation.md`
- `docs/02-architecture.md`, `docs/03-okf-spec.md`, `docs/04-evidence-model.md`, `docs/06-knowledge-service.md`, `docs/08-sync-pipeline.md`, `docs/11-implementation-guidelines.md`, `docs/12-runtime-architecture.md`, `docs/13-future-work.md`, `docs/16-workflow-execution.md`, `docs/17-human-guide.md`, `docs/18-agent-guide.md`, `docs/22-knowledge-quality-and-artifacts.md`, `docs/AI_Circled_Wiki_Build_Plan.md`, `docs/README.md`, `docs/source/chatgpt-llm-wiki-conversation-2026-07-08.md`
- `pyproject.toml`, `src/circled_wiki/__init__.py`, `src/circled_wiki/cli/__main__.py`, `src/circled_wiki/config/paths.py`, `src/circled_wiki/config/settings.py`, `src/circled_wiki/core/bootstrap.py`
- `tests/unit/test_bootstrap.py`, `tests/unit/test_cli.py`

## Migration acceptance criteria

1. New installation prompts, README headings, MCP descriptions and Agent startup text show **Circled Wiki**.
2. `circled-wiki` and `circled_wiki` are the only supported CLI and Python package identifiers.
3. Portable Runtime is installed as `.circled-wiki/bin/circled-wiki.py` and `.circled-wiki/runtime/circled_wiki/`.
4. Repository-wide name inventory has no obsolete product identifiers.
5. Tests cover canonical identifiers and installed Runtime execution.

## Naming decision

The product name, CLI, Python package, Runtime path, Agent contracts, documentation, tests and installed launcher use
**Circled Wiki** exclusively. No alternate product identifier is retained.
