# Bundle–Evidence Reference Contract

> Document authority: this is a source-only design reference, not a Runtime contract shipped to installed Wikis.
> Canonical Runtime rules are `OPERATING_RULES.md` RB-EVD-003·015·016·023 and RB-PUB-002·010; schema and
> Validator determine accepted structure.

## Canonical fields

| Field | Owner | Canonical value | Purpose |
| --- | --- | --- | --- |
| `Bundle.evidence` | Bundle | `evidence/{organization_id}/{name}_{source_uuid}.md` | Stable machine reference to an Evidence Record. |
| `Bundle.evidence_links` | Bundle | `[{display_name}](evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.md)` | Obsidian and human navigation only. It is derived from `evidence` and is never an identity. |

`display_name` is the Evidence `title` when it is available; a filename is only the fallback. All paths in
`evidence_links` are relative to the `knowledge/` root.

## Invariants

- Every `Bundle.evidence` value must resolve to exactly one Evidence Record.
- The two fields are immutable in meaning: moving an Evidence file changes only its derived `evidence_links`
  path, never its ID.
- Reference updates validate the Bundle's Evidence IDs before publishing and restore the Bundle on failure.

## ID generation

- `organization_id` is a stable lowercase ASCII namespace and cannot change after managed knowledge exists.
- `source_uuid` is generated once when an Inbox item enters processing, then reused on retry and idempotent ingest.
- Evidence IDs use the manifest filename. The filename includes the globally unique `source_uuid`; provider/date
  directories are storage locations, not identity.
- `bundle_uuid` is generated once at Bundle creation. Bundle IDs use `{slug}--{bundle_uuid}`, while the Bundle
  filename remains the human-readable `{slug}.md`.
- `id`, `source_uuid`, and `bundle_uuid` are machine identifiers. A Bundle ID's slug is a stable human-readable
  label, not a file-path dependency; titles, display labels, and paths must not be used as lookup identity.

## Legacy migration boundary

Direct Markdown links in `Bundle.evidence`, URI identifiers (`evidence://` and `knowledge://`), and extensionless
Bundle paths are legacy input formats only. Explicit migration may normalize Bundle IDs, Bundle filenames, and
Bundle references after a dry-run and reference-integrity check. It never rewrites an existing Evidence ID or
Evidence bytes: legacy Evidence IDs remain read-only compatibility identifiers, and canonical replacement requires
creating a new Evidence record. Legacy forms are not valid for newly created documents or normal Runtime automation.

## Archive location

An archived Bundle is moved to `knowledge/bundles/.archive/<domain>/` after its Archive metadata is complete. The
Bundle ID and Evidence IDs do not change when it moves. Archive is therefore an
explicit lifecycle operation, not deletion; restoration moves the same Bundle back to its domain only after review.
