# Circled Wiki core
- Product source repository; installed Wiki Runtime is a separate boundary.
- Product-agent routing and invariants: `AGENTS.md`, `PRODUCT_ENGINEERING_RULES.md`, then one selected `product-agent-rules/*.md` profile.
- Runtime canonical rules: `OPERATING_RULES.md`, `.circled-wiki/AGENT_ROUTER.md`, `agent-rules/`; Product Profiles and `docs/` are not Runtime release assets.
- Preserve user-managed installed assets: upgrades must not overwrite/register `knowledge/`, `workspace/`, or install-local config.
- Core Python implementation is under `src/circled_wiki/`; tests under `tests/`.
- For stack/build details read `mem:tech_stack`; for repository conventions read `mem:conventions`; for verification read `mem:task_completion`; for executable commands read `mem:suggested_commands`.