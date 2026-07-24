# Bundle–Evidence Reference Contract

## Canonical fields

| Field | Owner | Canonical value | Purpose |
| --- | --- | --- | --- |
| `Bundle.evidence` | Bundle | `evidence/{organization_id}/{name}_{source_uuid}.md` | Stable machine reference to an Evidence Record. |
| `Bundle.evidence_links` | Bundle | `[{display_name}](evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.md)` | Obsidian and human navigation only. It is derived from `evidence` and is never an identity. |
| `Evidence.curated_into` | Evidence | `bundle/{organization_id}/{slug}_{bundle_uuid}.md` | Inverse index of Bundles that reference this Evidence. |

`display_name` is the Evidence `title` when it is available; a filename is only the fallback. All paths in
`evidence_links` are relative to the `knowledge/` root.

## Invariants

- Every `Bundle.evidence` value must resolve to exactly one Evidence Record.
- Every resolved Bundle Evidence ID must have the Bundle ID in that Evidence Record's `curated_into` array.
- `curated_into` is maintained by Bundle create/revision operations; it is not a display link and must not be
  cleared by ingest, curation, or scheduled reprocessing.
- The three fields are immutable in meaning: moving an Evidence file changes only its derived `evidence_links`
  path, never its ID.
- Reference updates are one atomic change: validate both directions before publishing and restore both on failure.

## ID generation

- `organization_id` is a stable lowercase ASCII namespace and cannot change after managed knowledge exists.
- `source_uuid` is generated once when an Inbox item enters processing, then reused on retry and idempotent ingest.
- Evidence IDs use the manifest filename. The filename includes the globally unique `source_uuid`; provider/date
  directories are storage locations, not identity.
- `bundle_uuid` is generated once at Bundle creation. Bundle IDs use the Bundle filename, which includes that UUID.
- `id`, `source_uuid`, and `bundle_uuid` are machine identifiers. Human titles, display labels, and paths must not
  be used as lookup identity.

## Legacy migration boundary

Direct Markdown links in `Bundle.evidence`, URI identifiers (`evidence://` and `knowledge://`), and extensionless
Bundle paths are legacy input formats only. They are accepted solely by the explicit upgrade migration, which must
produce a dry-run plan and pass the reference-integrity check before apply. They are not valid for new documents,
new revisions, or normal runtime automation.

## Archive location

An archived Bundle is moved to `knowledge/bundles/archive/<domain>/` after its Archive metadata is complete. The
Bundle ID, Evidence IDs, and `Evidence.curated_into` values do not change when it moves. Archive is therefore an
explicit lifecycle operation, not deletion; restoration moves the same Bundle back to its domain only after review.
