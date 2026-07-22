# Operational PII Re-scan and Remediation Runbook

## When to use

Use this runbook on the installed operational Circled Wiki when existing Evidence has a boolean-only PII claim,
missing receipt, stale checksum, or suspected personal-data exposure. The operational Agent performs writes; the
source repository only supplies this procedure.

## Prerequisites

- Operator MCP/CLI access on the installed project.
- A scanner adapter or accountable manual security reviewer.
- Authority to quarantine restricted Evidence and open a system issue.
- A clean Git working tree or a recorded pre-existing change boundary.

## Procedure

1. Run `operational-preflight` and `validate`; stop on runtime or namespace drift.
2. Produce a read-only Evidence inventory: status, `pii_scanned`, `extensions.pii_scan`, checksum, visibility and Git-tracked-original flag.
3. For each missing/stale receipt, run the configured scanner adapter or `record-evidence-pii-scan` with a scanner/version/reviewer/receipt.
4. Record only `passed`, `masked`, or `needs_review`; never set `pii_scanned: true` without the checksum-bound receipt.
5. If `needs_review` or exposure is found, set restricted visibility/quarantine according to the security policy, stop automatic publication, and record a system issue without copying the sensitive original into the issue.
6. Re-run Validator. Confirm every Git-tracked Evidence original has a current successful receipt before publication.
7. Have a security reviewer independent from the implementing Agent verify the scanner receipt and affected Bundle references.
8. Commit the scoped remediation only after the normal Publication Gate. Push only through the configured Commit/Push boundary.

## Rollback and escalation

- Do not revert a confirmed exposure merely to restore publication. Preserve the receipt, affected IDs and issue linkage.
- If a sensitive original was already pushed, assess Git history, clones and caches; ordinary revert is not sufficient closure.
- Restore only Control Plane changes from `.circled-wiki-backups/`; do not overwrite Evidence during an upgrade rollback.

## Completion evidence

- Scanner receipt with Evidence checksum for every remediated item.
- Validator output and publication decision.
- Independent reviewer identity and verification note.
- System issue fixed release and verification artifact before `resolved`.
