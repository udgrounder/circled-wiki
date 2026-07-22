---
type: catalog
title: Circled Wiki Knowledge Vault
description: Obsidian과 Agent가 함께 사용하는 지식 저장소 루트
tags: [knowledge, vault, root, circled-wiki, readme]
updated_at: 2026-07-22T00:00:00+09:00
---

# Circled Wiki Knowledge Vault

이 디렉터리는 실제 지식 저장소이자 Obsidian Vault 기준 경로다. 사람은 Obsidian으로 읽고 검토하며,
운영 Agent는 검증된 CLI·MCP 경로로 수집·정제·발행을 수행한다.

이 문서는 Vault의 빠른 안내다. Agent의 실제 권한·보안·발행 규칙은 이 문서가 아니라
`.circled-wiki/OPERATING_RULES.md`와 선택한 `agent-rules/` Profile을 따른다.

## 하위 구조

- [Bundles](./bundles/README.md)
- [Evidence](./evidence/README.md)
- `inbox/` — provider별 처리 대기 입력 영역; 자동 index 관리 대상이 아님
- [Raw Processing](./.raw/index.md)

## 역할과 경계

| 대상 | 목적 | 변경 주체 |
| --- | --- | --- |
| `bundles/` | 검토·발행 가능한 공식 지식 | Validator와 Review Gate를 통과한 Agent/Owner |
| `evidence/` | 원본과 provenance를 가진 근거 | 승인된 Inbox 변환 작업 |
| `inbox/<provider>/` | 수집 직후·검토 전 입력 | Capture API 또는 승인된 수집 Agent |
| `.raw/` | 처리 중·실패·격리 원본의 임시 영역 | Ingest 작업만 |
| `.circled-wiki/` | 운영 규칙, 설정, 템플릿, Runtime | 설치·upgrade 작업 |

## 운영 원칙

| 항목 | 규칙 |
| --- | --- |
| 공식 지식 | `bundles/`의 `active` Bundle만 기본 검색·질의·Workflow 실행에 사용한다. |
| Bundle ID | `bundle/{organization_id}/{filename}.md`; 실제 폴더 경로와 분리된 불변 식별자다. |
| Evidence ID | `evidence/{organization_id}/{filename}.md`; provider·날짜 폴더 이동으로 바꾸지 않는다. |
| 파일 링크 | `evidence_links`에는 `[표시명](evidence/.../file.md)` 형식의 실제 Markdown 링크만 기록한다. |
| 태그 | Bundle에는 `bundles`, type, domain을; Evidence에는 `evidence`, provider, `source`를 포함한다. |
| Inbox | `inbox/<provider>/`에만 수집하며, Inbox Item은 Evidence나 공식 지식이 아니다. |
| 원본 | 성공한 원본은 `evidence/`에 보존한다. `.raw/`는 처리·실패·격리 중인 임시 영역이다. |
| 직접 수정 | 사람의 Obsidian 수정은 참고·검토용이다. 공식 변경은 Agent가 검증된 경로로 처리한다. |

## 빠른 경로

1. 새 자료는 `inbox/<provider>/`에 수집한다.
2. Inbox 민감성 검토와 승인을 마친 항목만 [Evidence](./evidence/index.md)로 변환한다.
3. Evidence PII Scan과 Validator를 통과한 자료만 Agent가 `draft` Bundle 후보로 정제한다.
4. Reviewer가 후보를 검토하고, Owner와 Security Gate를 통과한 후보만 `active` 공식 지식으로 사용한다.

## Agent 시작 전 확인

1. `.circled-wiki/AGENT_BOOTSTRAP.md`와 `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`를 읽는다.
2. 현재 요청에 맞는 Profile을 선택하고 해당 `agent-rules/`만 추가로 읽는다.
3. 변경 작업 전 `operational-preflight`를 실행한다.
4. 실패·검토 필요·예상과 다른 결과는 민감정보를 제외하고 `.circled-wiki/issues/`에 기록한다.

## Obsidian 사용 원칙

- Vault는 `knowledge/`를 루트로 연다.
- 루트 안내는 이 `README.md`이고, 자동 index 관리는 바로 아래 1-depth 폴더에만 적용한다.
- `inbox/`와 그 하위 폴더에는 index를 자동 생성·갱신·삭제하지 않는다.
- 링크가 깨졌다면 ID를 바꾸지 말고 실제 파일 링크를 검사하고, 필요하면 `backfill-evidence-links`를 먼저 dry-run으로 실행한다.
