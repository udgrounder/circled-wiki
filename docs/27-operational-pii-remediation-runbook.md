# Operational PII Re-scan and Remediation Runbook

> Document authority: this is a source-only remediation design reference and is not shipped to installed Wikis.
> Before execution, use the installed Runtime rules and tools. Evidence immutability and PII receipt requirements
> are defined only by `OPERATING_RULES.md` RB-EVD-020·023 and RB-SEC-005.

## When to use

Use this runbook when an installed Circled Wiki contains immutable Evidence with a missing or invalid PII receipt,
a stale checksum binding, or suspected personal-data exposure. Remediation never repairs the existing Evidence in
place. It blocks unsafe use, creates a corrected replacement when appropriate, and revises affected Bundles.

## Prerequisites

- Operator MCP/CLI access on the installed project.
- A scanner adapter or accountable manual security reviewer.
- Authority to stop publication, open a system issue, and handle a security or legal disposal request.
- Access to an approved source from which a replacement Evidence candidate can be created.
- A clean Git working tree or a recorded pre-existing change boundary.

## Procedure

1. Run `validate`; stop on namespace or knowledge validation errors.
2. Produce a read-only inventory of affected Evidence IDs, paths, checksums, PII receipts, visibility, source
   references, and referring Bundles. Do not add, remove, or modify Evidence fields.
3. Stop automatic publication of affected Bundles and record a system issue without copying sensitive content into
   the issue.
4. Re-acquire an approved source or safe masked derivative. Run the configured scanner against the final Evidence
   candidate before Ingest.
5. Bind scanner, version, scan time, result, reviewer, receipt, and candidate checksum into the Ingest input.
   `passed` or `masked` creates a new Evidence with `pii_scanned: true`; `needs_review` creates it with
   `pii_scanned: false`.
6. Allow Ingest to create the new immutable Evidence and its Curation Queue item atomically. Do not copy the old
   Evidence ID or edit the old Evidence receipt.
7. Process the queue into a validated Bundle revision or Review card. Replace affected Bundle references only
   through the normal review and revision flow.
8. Re-run Validator and have an independent security reviewer verify the new receipt, candidate checksum, and
   affected Bundle references.
9. Commit the scoped remediation only after the normal Publication Gate. Push only through the configured
   Commit/Push boundary.

## Exposure and controlled disposal

- A confirmed exposure is a security incident, not an ordinary Evidence correction. Preserve IDs, checksums, and
  issue linkage without repeating the sensitive value.
- If sensitive content was pushed, assess Git history, clones, caches, backups, and downstream exports. An ordinary
  revert does not remove the exposure.
- Legal or security deletion uses a separately authorized controlled-disposal procedure. Evidence immutability does
  not override mandatory erasure, but normal curation, upgrades, and rollback must not delete or rewrite Evidence.
- Restore only Control Plane changes from `.circled-wiki-backups/`; do not overwrite Evidence during an upgrade
  rollback.

## Completion evidence

- Read-only inventory of affected Evidence and referring Bundles.
- New Evidence ID and checksum-bound Data Protection Receipt, when a replacement is appropriate.
- Validator output, Bundle revision or Review decision, and publication decision.
- Independent reviewer identity and verification note.
- System issue fixed release and verification artifact before `resolved`.
