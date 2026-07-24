# Evidence 모델 설계

## 1. 목적

Evidence는 Evidence Original을 보존하고, 공식 지식이 어떤 근거로 생성되었는지 추적하게 해주는 참조 앵커다.
Evidence Record는 ID·출처·checksum·상태·역참조를 관리한다.

## 2. 설계 원칙

- 원본은 정제 전에 보존한다.
- 원본 문서는 실제 처리 작업이 시작될 때 UUID를 발급받는다.
- Evidence는 Bundle과 분리 저장한다.
- Evidence 무결성의 기준은 정규화문이 아니라 Evidence Original이다.
- 정규화 텍스트, OCR 결과, 파싱 결과는 원본을 대체하지 않는 파생 산출물이다.
- 상태 전이를 가진다.
- Bundle과 양방향 연결된다.
- Bundle의 `evidence` 필드와 기계적으로 매칭 가능해야 한다.
- 원본 시스템 참조와 내부 UUID 참조를 함께 유지한다.

## 3. 저장 형식과 경로

Evidence는 두 형식 중 하나로 저장한다.

- External-file Evidence: 외부 Evidence Original과 동일 basename의 External-file Evidence Manifest
- Embedded Evidence: Evidence Record와 불변 Evidence Original을 합친 Embedded Evidence Document

외부 파일 형식의 경로는 다음과 같다.

```text
evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.{ext}
```

예:

```text
evidence/notion/2026/07/08/refund-policy_550e8400-e29b-41d4-a716-446655440000.pdf
```

## 4. ID 규칙

```text
evidence/{organization_id}/{name}_{source_uuid}.md
```

## 5. UUID 발급 규칙

원본 입력은 `inbox/`에서 `.raw/`로 이동하며 실제 작업이 시작될 때 UUID를 발급받는다.

의도:

- 외부 시스템의 ID 형식과 무관하게 작업 시작 시 내부 식별자를 고정한다.
- 동일 원본에 대한 후속 처리, 재처리, 검토, 큐레이션 이력을 하나의 기준으로 묶는다.
- Bundle, raw item, 로그, 인덱스가 같은 원본을 안정적으로 참조할 수 있게 한다.

권장 규칙:

- UUIDv4 또는 UUIDv7 사용
- `inbox` 단계에서는 UUID 없이 대기할 수 있다.
- 파일명과 내부 `source_uuid`를 일치시킴
- 파일명은 `{name}_{source_uuid}.{ext}` 규칙을 사용한다.
- `name`은 사람이 읽을 수 있는 slug를 사용한다.
- `ext`는 원본 표현 형식을 유지한다.
- provider별 외부 ID는 별도 필드로 분리 저장

## 6. 저장 객체 구조

External-file Evidence 저장 단위는 Evidence Original과 필수 External-file Evidence Manifest로 구성한다.

```text
evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.{ext}
evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.md
```

- `{name}_{source_uuid}.{ext}`는 보존 대상 원본 파일이다.
- `{name}_{source_uuid}.md`는 원본 파일을 설명하는 External-file Evidence Manifest다.
- External-file Evidence Manifest는 원본 파일을 대체하지 않으며, 참조·검증·상태 추적을 위한 Evidence Record다.
- 바이너리 원본은 같은 위치에 같은 basename의 `.md` 파일을 함께 둔다.
- 처리 완료된 원본 파일은 `evidence/`에 보존한다.
- 크기가 10MB 이하인 원본은 `.md` manifest와 함께 Git에 추적해 저장소 복원성과 공유성을 확보한다.
- 크기가 10MB를 초과하는 원본은 Git에서 제외하고 별도 원본 저장소에 보존한다. Git에는 `.md` manifest만 추적한다.
- Git은 파일 크기만으로 ignore할 수 없으므로, ingest와 commit 전 Validator가 10MB 초과 Evidence 원본의 Git 추적을 차단해야 한다.

Embedded Evidence Document는 별도 원본 파일 없이 하나의 Markdown에 Evidence Record와 불변 원문 구역을 둔다.
`extensions.content_mode: embedded`, `checksum_scope: original_content`를 사용하며 `original_file`은 두지 않는다.

## 7. External-file Evidence Manifest 기본 구조

```yaml
---
type: evidence
id: evidence/example-org/refund-policy_550e8400-e29b-41d4-a716-446655440000.md
title: Refund Policy Source Snapshot
source_uuid: 550e8400-e29b-41d4-a716-446655440000
provider: notion
source_ref:
  provider: notion
  provider_url: https://example.com/page
  external_id: notion-page-12345
  captured_from: api
captured_at: 2026-07-08T10:00:00+09:00
status: processed
processed_at: 2026-07-08T10:03:00+09:00
checksum: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
language: ko
original_file: refund-policy_550e8400-e29b-41d4-a716-446655440000.pdf
original_file_git_tracked: true
derived_files:
  - refund-policy_550e8400-e29b-41d4-a716-446655440000.txt
extensions:
  availability: available
  capture_context:
    why_collected: 환불 정책을 공식 CS 지식으로 갱신하기 위한 근거
    intended_use:
      - refund-policy
    business_context: 고객 환불 문의 처리
    key_questions: []
    expected_outputs:
      - cs policy
  review_state: approved
  visibility: internal
  pii_scanned: true
  pii_masked: false
  storage:
    class: git
---
```
본문에는 원본 요약, 추출 텍스트 위치, 처리 메모를 저장할 수 있다. 원본 내용 자체는 `original_file`이 가리키는 파일을 기준으로 한다.

일반 Evidence의 `extensions.capture_context.why_collected`와 `intended_use`는 필수다. 수집 이유와 적용할
업무가 없는 원본은 지식의 무덤이 되기 쉬우므로 처리 전에 사람 또는 수집기가 채운다. Workflow Outcome은
Task와 Workflow ID를 사용해 두 필드를 자동 생성한다. 세부 규칙은 [19-knowledge-governance.md](19-knowledge-governance.md)를 따른다.

## 8. 원본 참조 구조

원본 참조는 `source_ref` 객체로 관리한다.

권장 필드:

- `provider`: 원본 시스템 이름
- `provider_url`: 사람이 원문으로 이동할 수 있는 링크
- `locator`: 원문 내 정확한 위치. `page=12;section=Refund`, `sheet=Orders;range=A1:F20`처럼 기록한다.
- `external_id`: 원본 시스템 내부 ID
- `captured_from`: `api`, `webhook`, `manual`, `upload`, `sync` 등
- `snapshot_at`: 원문 스냅샷 시각

예시:

```yaml
source_ref:
  provider: slack
  provider_url: https://workspace.slack.com/archives/C123/p123456789
  locator: timestamp=2026-07-08T10:00:00+09:00
  external_id: C123:p123456789
  captured_from: webhook
  snapshot_at: 2026-07-08T10:00:00+09:00
```

운영 원칙:

- 내부 시스템은 `source_uuid`를 1차 참조키로 사용한다.
- 외부 시스템 재조회가 필요할 때만 `source_ref`를 사용한다.
- 사람과 Agent 응답에서는 `provider_url`과 `locator`가 있으면 이를 1차 근거로 먼저 제시한다.
- 로컬 Evidence URI와 보존 원본은 검증·복구를 위한 보조 근거로 함께 제시한다.

## 9. 상태 모델

- `new`: 신규 입력
- `processing`: 처리 중
- `processed`: Bundle 반영 완료
- `ignored`: 의미 없는 입력
- `failed`: 처리 실패
- `needs_review`: 사람 검토 필요

상태 전이 원칙:

- `new -> processing -> processed`
- `new -> ignored`
- `processing -> failed`
- `processing -> needs_review`
- `needs_review -> processing`

## 10. Bundle -> Evidence 연결

`evidence` 배열을 사용한다. 사람·Obsidian 탐색 링크는 별도 `evidence_links` 배열에만 둔다.

정확한 ID·링크·역참조 형식과 갱신 주체는 [26-reference-contract.md](26-reference-contract.md)를 따른다.

추가 권장:

- Bundle 본문이나 메타데이터에 `source_uuid`를 설명용으로 기록할 수 있다.
- 운영 로그와 worker 작업 파일도 같은 `source_uuid`를 공유한다.

## 11. 운영 규칙

- Evidence는 삭제보다 상태 변경을 우선한다.
- 원본 파일은 수정하지 않고 새 스냅샷이 필요하면 같은 `source_uuid`의 revision 또는 새 Evidence 정책으로 처리한다.
- Git으로 추적되는 Evidence 원본은 저장소 복원 시 함께 복원된다. Git에서 제외된 대용량 원본은 manifest의 `source_ref`, `checksum`, `original_file`, `extensions.storage` 정보를 통해 재확보할 수 있어야 한다.
- 민감정보 포함 가능성이 있으면 `.circled-wiki/policies/sensitive-data-masking.md` 기준으로 Git 추적 가능 여부를 판단한다. 원본의 증거성은 유지하되, 민감 원본을 Git에 올려서는 안 된다.
- 동일 입력 중복 수집 여부를 checksum으로 판단할 수 있다.
- `capture_context.reuse_value`, `retention_class`, `sensitivity_review`는 수집 가치와 보존·민감정보 검토 상태를 분류한다.
- 이 분류는 Evidence 진실성 점수가 아니며 출처 권위와 최신성 평가는 Refresh Task의 Reference Assessment에서 수행한다.
- Bundle이 참조하는 Evidence는 Evidence Record를 통해 최소 메타데이터 수준에서 항상 읽을 수 있어야 한다.
- `availability: available`이면 Evidence Original의 존재와 Evidence Record의 실제 SHA-256 checksum 일치를 검사한다.
- Active Bundle의 Evidence 누락은 발행 차단 오류로 취급한다.
- 같은 원본을 재처리할 때는 새 UUID를 만들지 말고 기존 `source_uuid`를 유지한다.

## 12. 구현 고려사항

- provider별 파서 분리
- 원본 파일, manifest, 파생 산출물의 경로 관계 고정
- 10MB 초과 첨부파일의 별도 저장소, 백업 및 복구 전략
- Evidence와 Bundle 참조 무결성 검사 배치 필요
- UUID 발급기와 source_ref 정규화기 분리
