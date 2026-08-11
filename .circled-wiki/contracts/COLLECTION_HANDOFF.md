---
guidance_version: v1
---

# Collection Handoff Guide

외부 수집 Agent는 이 안내를 수집 전에 읽고, 원문과 함께 필요한 맥락을 보존한다. 이 안내는 수집 성공 Gate가 아니다.

## 위치와 변경 경계

- 새 원문은 `knowledge/inbox/<provider>/`에만 만든다.
- 기존 Inbox 파일, `knowledge/evidence/`, `knowledge/bundles/`, `workspace/`, `.circled-wiki/`는 변경하지 않는다.
- 표준 Inbox envelope를 만들 수 없으면 같은 provider 폴더에 raw 원문을 새 파일로 보존한다.

## 권장 Frontmatter

가능하면 `provider`, `title`, `captured_at`, `why_collected`, `intended_use`, `idempotency_key`, `source_url`, `source_locator`, `captured_from`을 함께 남긴다.

- `source_url`: Notion 등 원문의 안정적 URL
- `source_locator`: `page_id=...`, 상위 경로, 문서·대화 내 위치 등 URL로 충분하지 않은 위치 정보
- `captured_from`: `api`, `webhook`, `manual`, `upload`, `sync` 중 수집 경로

값이 없으면 추정하지 않고 원문을 보존한다. Runtime 또는 `jsonschema` 오류도 raw 원문 보존을 중단시키지 않는다. 복구 뒤 Wiki Agent가 `capture-file --inbox-file <provider/원본파일명>`로 정규화하고 Inbox Inspection을 진행한다.
