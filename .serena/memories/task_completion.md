# Task completion gates
- Run targeted tests covering changed business logic, failures, edge cases, and data-integrity/security boundaries.
- Run full suite: `python3 -m pytest`.
- Run Runtime validator: `PYTHONPATH=src python3 -m circled_wiki.cli validate`; require `invalid=0`.
- For release/upgrade work additionally canary-install/upgrade and verify `knowledge/` and `workspace/` preservation plus reproducible checksums/receipts.
- Confirm scope with `git status --short` and preserve unrelated dirty-worktree changes.
- Do not claim deployed/verified in an installed Wiki from source tests alone; deployment and independent Runtime verification are separate receipts.