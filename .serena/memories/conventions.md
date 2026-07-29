# Repository conventions
- Treat product source and installed Runtime as separate scopes and apply separate gates.
- File content changes must use an editing tool (`apply_patch`/Edit/Write), never shell text-rewrite commands; `mv` is allowed for rename.
- Preserve dirty-worktree/user changes and avoid unrelated edits.
- Use project-root-relative paths in repository docs/config/examples; never hardcode machine paths, credentials, organization values, or PII.
- OKF managed documents use YAML frontmatter; normative terminology comes from `OPERATING_RULES.md`.
- Core, CLI, MCP, and worker responsibilities remain separated.
- Commit, push, release, and deployment each require explicit user authorization.