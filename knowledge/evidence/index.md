---
type: catalog
title: Evidence Store
description: 원본 근거 저장소 루트
tags: [evidence, catalog, provenance, source]
timestamp: 2026-07-08T00:00:00+09:00
---

# Evidence Store

Evidence 보존·보안·provider 배치 규칙은 [README](./README.md)를 따른다. 이 문서는 Obsidian 탐색용 목록이다.

원본 입력은 provider별로 저장한다. `evidence/`는 정제본이 아니라 원본 파일 자체를 보존하는 위치이며, 각 공식 Evidence는 참조와 검증을 위한 manifest를 함께 가진다. 영구 ID는 `evidence/{organization_id}/{filename}.md`이고, 날짜·provider 폴더는 저장·탐색용이다.

처리 완료된 원본 파일은 이 위치에 보존한다. 10MB 이하 원본은 같은 basename의 `.md` manifest와 함께 Git에 추적한다. 10MB 초과 원본은 별도 원본 저장소에 보존하고, Git에는 checksum과 보관 위치를 담은 manifest만 추적한다.

## 처리 기준

- Inbox Sensitive Data Review와 Evidence PII Scan은 서로 다른 Gate다.
- Bundle에는 Evidence ID를 `evidence`에 기록하고, 사람이 여는 실제 파일 링크는 `evidence_links`에 Markdown 링크로 기록한다.
- `restricted` Evidence는 자동 정제·일반 검색·일반 Inventory에 노출하지 않는다.
- Evidence의 `tags`에는 최소 `evidence`, provider, `source`를 기록한다.

Evidence는 `notion/`, `slack/`, `github/`, `meetings/` 등 provider별 폴더에 저장한다. provider 하위 폴더에는 별도 index를 두지 않는다.
