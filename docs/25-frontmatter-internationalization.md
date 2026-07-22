# Frontmatter Internationalization Rules

## Principle

Machine-readable keys, identifiers, enum values, URI segments and filesystem slugs use stable ASCII values.
Human-facing titles, summaries, body text, Evidence excerpts and UI messages may use any UTF-8 language.

| Field class | Examples | Rule |
| --- | --- | --- |
| Stable identifiers | `id`, `bundle_uuid`, `source_uuid`, Evidence URI | Never translate, truncate, or derive lookup identity from display text. |
| Machine enums | `type`, `status`, `review_state`, `provider`, `support_status` | Use documented lowercase ASCII vocabulary. |
| Path values | domain directory, CLI slug, runtime task id | Use safe ASCII path segments; derive from normalized text plus checksum/full UUID where needed. |
| Display text | `title`, `summary`, Markdown body, `rationale`, `limitations` | Preserve UTF-8; Korean and other languages are valid. |
| Actor/config identifiers | `organization.id`, `agent.operator`, `approval.knowledge_owner` | Safe lowercase ASCII identifiers; display names belong in separate fields. |

## Migration guidance

1. Preserve legacy identifiers and URIs exactly; do not translate them in place.
2. Add display fields or revise human text through a normal Bundle revision when wording changes.
3. Do not create a slug from UUID prefixes. Use a safe title normalization and a checksum suffix, while the full UUID remains the identity.
4. Treat unknown language text in external Evidence as untrusted input until Curation and PII gates complete.
5. API and MCP transports return display strings as UTF-8 JSON and machine fields unchanged.

## Existing mixed fields

- `title`, `summary`, `body`, `rationale`, `limitations`: display text.
- `domain`, `type`, `status`, `review_state`, `source_ref.provider`: machine fields.
- `owners`/actor values: machine identifiers, not display names.
- `extensions.*`: extension namespace; new fields must state whether they are display or machine fields in their schema/validator contract.
