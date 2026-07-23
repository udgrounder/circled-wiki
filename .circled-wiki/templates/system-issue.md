---
type: template
title: System Issue Template
description: Circled Wiki 운영 문제와 사용자 피드백 기록 형식
tags: [template, system-issue, operations]
timestamp: 2026-07-15T00:00:00+09:00
---

# <issue title>

- Issue ID: `issue-<timestamp>-<id>`
- Recorded at: <ISO-8601 UTC timestamp>
- Reported by: <operator or agent identity>
- Reported from: <user|agent|operator|automation>
- Area: <runtime|cli|agent_rules|workflow|integration|bootstrap|other>
- Severity: <low|medium|high|critical>
- Status: open

## Summary

<what happened and the impact>

## Expected result

<expected behavior>

## Actual result

<observed behavior; separate facts from hypotheses>

## Reproduction or context

<safe reproduction steps, version, relevant conditions>

## Related paths or artifacts

- <relative path or artifact reference; do not include secrets or raw personal data>

## Improvement hint

<optional improvement hypothesis; not an approved change>

## Review outcome

Pending system-maintainer review.

## Status history

- <ISO-8601 UTC timestamp>: `open` -> `<triaged|wont_fix>` by `<system-maintainer>` — <safe triage note>
- <ISO-8601 UTC timestamp>: `triaged` -> `<mitigated|wont_fix>` by `<system-maintainer>` — <safe implementation note; optional fixed release>
- <ISO-8601 UTC timestamp>: `mitigated` -> `<verified|triaged>` by `<independent-reviewer>` — <verification evidence or reopen reason>
- <ISO-8601 UTC timestamp>: `verified` -> `<resolved|triaged>` by `<system-maintainer>` — <closure or reopen note>
