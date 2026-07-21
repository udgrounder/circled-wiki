# OKF 적용 및 확장 규격

## 공식 참고 링크

- Open Definition 2.1: [https://opendefinition.org/od/2.1/en/](https://opendefinition.org/od/2.1/en/)
- Google Cloud OKF 공식 저장소: [https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- Google Cloud OKF 공식 스펙: [https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

## 1. 목적

이 문서는 Example Organization Knowledge Bundle이 따라야 하는 OKF 적용 원칙과 확장 규칙을 정의한다.

이 문서의 역할은 세 가지다.

- 공개적으로 알려진 OKF 철학과 개방성 원칙을 채택한다.
- Google Cloud가 제안한 OKF v0.1의 포맷 관례를 반영한다.
- 구현과 검증에 필요한 저장소 전용 프로파일을 명시한다.

본 문서에서 `Example Organization OKF Profile`은 표준을 대체하는 사양이 아니라, 저장소에서 검증 가능한
구체 규칙 집합을 의미한다.

중요:

- Open Knowledge Foundation의 Open Definition은 무엇이 `open`한지를 정의한다.
- 즉, 라이선스, 접근성, 기계 판독성, 오픈 포맷 같은 원칙을 제공한다.
- 하지만 Bundle Frontmatter 스키마나 Evidence 참조 구조를 직접 규정하지는 않는다.
- 2026년 Google Cloud가 제안한 OKF v0.1은 그 위에 `Markdown 디렉터리 + YAML Frontmatter + 소수의 관례`라는 상호운용 포맷을 얹는다.
- 따라서 본 문서는 `개방성 원칙`, `OKF v0.1 포맷`, `저장소 프로파일`을 분리해서 정의한다.

## 2. 기본 원칙

- OKF v0.1의 최소 포맷 계약을 유지한다.
- 표준 예시 필드의 의미를 조직 내부 사정으로 함부로 재정의하지 않는다.
- 조직 특화 필드는 `extensions` 아래에만 추가한다.
- 공식 Bundle은 Markdown과 YAML Frontmatter 기반으로 저장한다. 여기서 Bundle은 Example Organization Profile의 단일 공식
  지식 문서이며, 디렉터리 단위인 표준 OKF Bundle과 구분한다.
- `knowledge/bundles/`, Evidence Record와 `.knowledge-os/templates/`, `.knowledge-os/schemas/`, `.knowledge-os/policies/`의 관리 문서는 Markdown + YAML Frontmatter를 사용한다.
- `inbox/`, `.raw/`, `evidence/`는 원본 수집/처리/보존 구간이므로 비Markdown 파일을 포함할 수 있다.
- 본 저장소는 `Bundle 본문 + Frontmatter + Evidence 참조`를 하나의 최소 지식 단위로 본다.
- 개념 하나는 파일 하나로 표현한다.
- 파일 경로는 개념의 정체성 일부로 취급한다.
- 관계는 가능한 한 Markdown 링크로 표현한다.

## 3. 규칙 계층

### 3.1 표준 원칙

다음은 표준으로 취급하는 원칙이다.

- 라이선스와 배포 방식은 개방성을 침해하지 않아야 한다.
- 합리적인 비용 또는 무료 접근이 가능해야 한다.
- 지식은 기계가 읽을 수 있어야 한다.
- 지식은 오픈 포맷으로 제공되어야 한다.
- 재사용 가능한 구조를 가져야 한다.
- 메타데이터와 출처가 추적 가능해야 한다.
- 확장이 필요하면 표준 필드 바깥에서 명시적으로 이뤄져야 한다.

### 3.2 OKF v0.1 포맷 원칙

참고 문서 기준으로 정리한 OKF v0.1의 핵심은 다음과 같다.

- OKF 번들은 YAML Frontmatter가 붙은 Markdown 파일들의 디렉터리다.
- 포맷은 `그냥 Markdown`, `그냥 파일`, `그냥 YAML`을 지향한다.
- 최소한의 강제를 지향하며, 강하게 요구되는 핵심 필드는 `type`이다.
- 생산자와 소비자는 서로 독립적이어야 한다.
- 플랫폼이 아니라 포맷이어야 한다.
- Concept ID는 `파일 경로 - .md`로 해석한다.
- `index.md`, `log.md`는 예약 파일명이다.

이 절의 `OKF 번들`은 표준의 디렉터리 단위다. 이 저장소가 API와 파일 모델에서 사용하는 `Bundle`은 그 안의
단일 공식 지식 문서를 뜻하며, 두 의미를 혼용하지 않는다.

### 3.3 OKF v0.1 권장 상호운용 필드

참고 문서에서 예시로 제시된 구조화 필드는 다음과 같다.

- `type`
- `title`
- `description`
- `resource`
- `tags`
- `timestamp`

이 필드들은 상호운용 표면으로 유용하지만, 아래 `Example Organization OKF Profile`의 필수 여부와는 별도로 본다.

### 3.4 Example Organization OKF Profile

다음은 저장소 내부 검증을 위한 프로파일이다.

- 파일 형식은 Markdown + YAML Frontmatter
- Bundle·Evidence와 Control Plane의 template·schema·system policy 관리 문서는 같은 기본 구조를 따르되 소유권 경계를 분리한다.
- `inbox/`, `.raw/`, `evidence/`는 원본 바이너리 또는 원본 파일을 담을 수 있으므로 원본 파일 자체에는 동일 규칙을 강제하지 않는다.
- 식별자는 URI 형태
- 공식 Bundle은 최소 1개의 Evidence 필요
- `bundles/`에 저장되는 정제된 공식 지식은 반드시 OKF 구조를 만족해야 한다.
- 조직 특화 메타데이터는 `extensions` 아래에만 배치
- 상태값과 필수 필드는 검증기로 강제

### 3.5 조직 확장

조직 운영에 필요한 값은 `extensions`에만 둔다.

- `curated_by`
- `confidence`
- `decision_status`
- `review_state`
- `knowledge_revision`
- `visibility`
- `pii_masked`
- `review_requested`
- `review_reason`
- `review_requested_by`
- `review_requested_at`

## 4. 표준 Bundle 예시

```yaml
---
type: policy
title: Refund Policy
description: 예약 환불 정책
resource: https://internal.example/cs/refund-policy
tags: [refund, cancellation]
timestamp: 2026-07-08T10:05:00+09:00
id: knowledge://example-org/cs/refund-policy_7c9e6679-7425-40de-944b-e07fc1f90ae7
bundle_uuid: 7c9e6679-7425-40de-944b-e07fc1f90ae7
status: active
owners:
  - cs-team
summary: 예약 환불 정책
links:
  - knowledge://example-org/product/reservation_3fa85f64-5717-4562-b3fc-2c963f66afa6
updated_at: 2026-07-08T10:05:00+09:00
evidence:
  - evidence://example-org/notion/2026/07/08/550e8400-e29b-41d4-a716-446655440000
extensions:
  curated_by: hermes
  confidence: official
  review_state: approved
  knowledge_revision: 1
  source_uuids:
    - 550e8400-e29b-41d4-a716-446655440000
---
```

공식 v0.1 관점에서는 위 예시 중 `type`만 적합성 판단의 필수값이고, 나머지는 권장 또는 저장소 프로파일 규칙이다.

## 5. 필수 필드

구분해서 보면 다음과 같다.

### 5.1 OKF v0.1 최소 필수

- `type`

또한 적합성 관점에서는 다음도 중요하다.

- 비예약 `.md` 파일은 파싱 가능한 YAML Frontmatter를 가져야 한다.
- `index.md`, `log.md`는 각 용도 규칙을 따라야 한다.

### 5.2 Example Organization OKF Profile 필수

- `id`
- `bundle_uuid`
- `title`
- `type`
- `status`
- `summary`
- `updated_at`
- `evidence`

필수 필드 판단 기준:

- 문서의 의미 식별 가능성
- 상태 추적 가능성
- 소유/설명 가능성
- Evidence 연결 가능성

## 6. 권장 필드

- `description`
- `resource`
- `timestamp`
- `owners`
- `tags`
- `links`
- `extensions`

## 7. 필드 의미 규칙

### id

- URI 형식 사용
- 영속 식별자 역할
- 파일 경로 변경과 분리 가능
- 공식 v0.1의 Concept ID와는 별도 식별자다.
- Evidence `id`는 `source_uuid`(UUIDv4/v7)를 포함하므로 생성 시점에 유일성이 실질적으로 보장된다.
- Bundle `id`도 동일한 원칙을 따른다. `id`는 `knowledge://example-org/{domain}/{slug}_{bundle_uuid}` 형식으로, 끝에 `bundle_uuid`를 붙여 사람이 읽는 slug를 유지하면서도 구조적으로 유일성을 보장한다.
- `bundle_uuid`는 Bundle 최초 생성 시 한 번만 발급하고, 이후 해당 Bundle을 갱신할 때는 새로 만들지 않고 그대로 유지한다. Evidence의 `source_uuid` 발급/유지 원칙과 동일하다.
- 파일명도 같은 원칙으로 `{slug}_{bundle_uuid}.md`를 사용한다.

### bundle_uuid

- Bundle 최초 생성 시 발급하는 UUIDv4 또는 UUIDv7
- `id`의 마지막 세그먼트, 그리고 파일명의 `_{bundle_uuid}` 부분과 항상 같은 값이어야 한다.
- Bundle을 갱신(같은 파일 수정)할 때는 유지하고, 완전히 새로운 개념으로 신규 Bundle을 만들 때만 새로 발급한다.

### type

권장 예시:

- `policy`
- `guide`
- `runbook`
- `decision`
- `spec`
- `reference`

### evidence

- URI 배열
- 빈 배열 금지
- Evidence 객체와 실제로 연결 가능해야 함

### extensions.source_uuids

- Bundle 생성에 사용된 원본 문서 UUID 목록
- `evidence` URI와 중복될 수 있지만, 운영/로그/worker 연계를 쉽게 하기 위한 보조 필드
- 참조 무결성 검증 시 Evidence의 `source_uuid`와 일치해야 함

### resource

- 사람이 원문 시스템이나 대상 자원으로 이동할 수 있는 링크
- 카탈로그, 콘솔, 문서, 대시보드 URL에 사용 가능

### timestamp

- 문서 또는 개념의 기준 시점을 표현
- 내부 `updated_at`과 함께 사용할 경우 의미를 분리해야 함

권장 구분:

- `timestamp`: OKF v0.1 상호운용용 시간 메타데이터
- `updated_at`: 조직 운영용 정제 시각 또는 공식 갱신 시각

### extensions

- 표준 필드가 아닌 조직 전용 메타데이터만 허용
- 중첩 구조는 허용하되 검증 가능해야 함

### extensions.decision_status

- `type: decision` 문서에서만 사용하는 저장소 확장 필드다.
- 표준 OKF 필드가 아니라 Example Organization 저장소 프로파일의 조직 확장이다.
- 결정문의 현재 상태를 표현하며 `review_state`와는 역할이 다르다.
- 권장 값은 `proposed`, `accepted`, `rejected`, `superseded`다.
- 다른 타입 문서에서는 사용하지 않는 것을 권장한다.

## 8. 상태값 규칙

권장 상태값:

- `draft`
- `active`
- `deprecated`
- `archived`

## 9. extensions 규칙

`extensions`에는 아래 범주의 값만 추가한다.

- 내부 검토 상태
- 자동 생성 메타데이터
- 조직 전용 운영 태그
- revision 또는 confidence 정보
- 결정문 상태(`decision_status`)
- 접근 범위(`visibility`) 및 민감정보 처리 상태(`pii_masked`)
- 사후 검토 요청 여부(`review_requested`, `review_reason`, `review_requested_by`, `review_requested_at`)

예시:

```yaml
extensions:
  curated_by: hermes
  confidence: official
  review_state: approved
  knowledge_revision: 3
  visibility: internal
  pii_masked: true
  review_requested: false
```

`visibility`와 `pii_masked`의 세부 규칙은 `.knowledge-os/policies/sensitive-data-masking.md`를 따른다.

`review_requested`는 이미 `active`인 Bundle의 내용에 문제가 있다고 사람 또는 Agent가 판단했을 때 사후적으로 켜는 플래그다. `updated_at` 나이와는 무관하다. 세부 흐름은 `docs/05-hermes-architecture.md` 7절을 따른다.

```yaml
extensions:
  review_requested: true
  review_reason: "환불 정책이 최근 약관 개정과 맞지 않는 것 같음"
  review_requested_by: cs-team
  review_requested_at: 2026-07-09T09:00:00+09:00
```

금지 예시:

- `department: cs-team`
- `review_state: approved`를 최상위에 두는 것
- `confidence`를 최상위에 두는 것

### 9.1 extensions.workflow

`type: runbook` Bundle은 실행 가능한 공식 업무 절차를 표현할 수 있다. `draft` 상태에서는 Workflow
메타데이터가 없어도 되지만 `active` Runbook은 반드시 `extensions.workflow`를 가진다.

필수 필드:

- `workflow_id`: lowercase slug 형태의 안정적인 실행 식별자
- `version`: 1 이상의 정수
- `execution_mode`: `guided`, `agent_assisted`, `automated` 중 하나
- `required_inputs`: `name`, `description`을 가진 입력 목록
- `steps`: 고유한 `id`, `title`, `kind`를 가진 비어 있지 않은 단계 목록
- `completion_criteria`: 비어 있지 않은 완료 기준 목록

Step `kind`는 `action`, `decision`, `approval`, `validation` 중 하나다. `approval_gates`는 실제
`kind: approval` 단계만 참조할 수 있다. 상세 규칙과 실행 상태 분리는
[16-workflow-execution.md](16-workflow-execution.md)를 따른다.

### 9.2 extensions.governance

`active` Bundle은 non-empty `owners`와 아래 필드를 가진다.

- `reviewed_at`: 마지막 승인 검토 시각
- `review_due_at`: 다음 검토 기한
- `freshness_policy`: `on_change`, `monthly`, `quarterly`, `annual` 등의 검토 정책
- `supersedes`, `superseded_by`: 교체 관계

`active` Runbook은 추가로 `freshness_policy: risk_based`, `risk_tier`, `source_volatility`, 양의 정수
`validity_days`, non-empty `change_triggers`를 가진다. Tier별 최대 유효기간은 Critical 7일, High 30일,
Medium 90일, Low 180일이다. `review_due_at`은 `reviewed_at + validity_days`보다 늦을 수 없다.
`source_volatility: volatile`이면 Tier 상한의 50%를 소수점 올림해 최대 기간으로 적용한다.
`change_triggers`는 `user_requested`, `owner_requested`, `source_change`, `outcome_signal`,
`security_or_compliance`를 사용하며 `user_requested`는 필수다.
`active` Runbook은 `extensions.workflow.learning`에 `maturity`, `min_outcomes_for_review`,
`review_on_failure`, `review_on_feedback`을 가진다. 실행 통계는 Frontmatter 카운터가 아니라 Outcome Evidence에서
파생한다. 상세 모델은 [21-runbook-learning.md](21-runbook-learning.md)를 따른다.
검토 기한이 지난 Runbook은 검색 결과에 `freshness.state: expired`로 표시하고 원래 업무 대신 Refresh Task를
생성한다. 상세 기준은 [20-runbook-refresh.md](20-runbook-refresh.md)를 따른다.

`extensions.workflow.artifact_profile`은 선택 필드다. `type`은 `decision_report`, `work_guide`,
`registration_package`, `design_brief`, `review_report`, `comparison_report` 중 하나이며
`required_sections`는 non-empty 문자열 배열이다.

### 9.3 extensions.rulebook

Business Rulebook은 `type: guide`에서만 사용한다. `rulebook_id`는 필수이며 `policies`, `runbooks`,
`guides` 배열로 관련 Bundle을 연결한다. Rulebook은 자체 Workflow나 Task 상태를 갖지 않는다.

### 9.4 extensions.inquiry

Inquiry는 `type: reference`에서만 사용한다. `question_id`, `status`, `owner`를 필수로 가지며 상태는
`open`, `investigating`, `resolved`, `wont_fix` 중 하나다. `resolved` 상태에는 non-empty `resolution`이
필요하다.

### 9.5 extensions.capture_context

Evidence Record는 `why_collected`와 non-empty `intended_use` 배열을 필수로 가진다. 선택 필드는
`business_context`, `key_questions`, `expected_outputs`, `reuse_value`, `retention_class`,
`sensitivity_review`다. Workflow Outcome Evidence는 Task와 Workflow
메타데이터로 필수 값을 자동 생성한다. `extensions.availability`는 `available`, `metadata_only`,
`temporarily_unavailable`, `access_denied`, `missing` 중 하나를 사용한다.

### 9.6 extensions.archive

`status: archived` Bundle은 `archived_at`, `archived_by`, `reason`, `restore_condition`을 가진
`extensions.archive`를 필수로 정의한다. Archive는 경로나 ID를 변경하지 않고 기본 검색·Context에서 제외하는
lifecycle 상태다.

세부 품질 계약은 [22-knowledge-quality-and-artifacts.md](22-knowledge-quality-and-artifacts.md)를 따른다.

## 10. Evidence 연결 규칙

- 모든 Bundle은 최소 1개 이상의 Evidence를 가진다.
- Bundle의 `evidence` 필드는 Evidence URI를 저장한다.
- Evidence가 제거되면 연결 Bundle의 무결성을 다시 검사한다.
- 이는 표준 OKF v0.1 자체가 아니라 Example Organization Profile의 추가 규칙이다.
- 모든 Evidence는 `inbox/`에서 `.raw/`로 이동할 때 발급된 `source_uuid`를 가져야 한다.
- Evidence 파일 경로는 `knowledge/evidence/{source}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.{ext}` 패턴을 권장한다.
- Evidence는 `extensions.capture_context`에 수집 이유와 적용 업무를 기록한다.

주의:

- `evidence/`는 최종적으로 참조 가능한 정식 원본 보존 위치다.
- 실제 원본 바이너리나 업로드 산출물은 `inbox/` 또는 `.raw/`에 먼저 들어오고, 처리 시작 후 `source_uuid`를 받은 뒤 `evidence/`로 보존된다.
- 처리 완료된 외부 Evidence Original은 10MB 이하이면 Git에 추적한다. 10MB를 초과하는 원본은 Git에서 제외하고 별도 원본 저장소에 보존하며, External-file Evidence Manifest의 `extensions.storage`에 복구 위치와 보관 방식을 기록한다.
- Evidence Original이 무결성의 기준이며, 정규화 텍스트나 추출 결과는 원본을 대체하지 않는 Derived Artifact다.
- Bundle은 Evidence URI를 참조하고, Evidence Record를 통해 `source_ref`, checksum, 상태, Derived Artifact 경로를 조회한다.

## 11. Bundle 본문 규칙

- Frontmatter는 메타데이터다.
- 실제 지식 내용은 본문에 존재해야 한다.
- 본문은 최소한 배경, 정책/사실, 예외 또는 참고 링크 중 일부를 가져야 한다.
- 메타데이터만 있는 빈 Bundle은 허용하지 않는다.
- 관련 개념은 Markdown 링크로 연결하는 것을 권장한다.
- 외부 출처 기반 주장에는 `# Citations` 섹션을 두는 것을 권장한다.

권장 본문 섹션:

- 개요
- 핵심 내용
- 적용 범위
- 예외
- 참고 Evidence 또는 관련 Bundle

## 12. 검증 규칙

검증기는 최소 아래 항목을 확인해야 한다.

### 12.1 OKF v0.1 적합성

- 모든 비예약 `.md` 파일에 파싱 가능한 YAML Frontmatter 존재
- 모든 Frontmatter에 non-empty `type` 존재
- `index.md`, `log.md`가 존재할 경우 각 예약 구조를 따름

소비자는 아래 사유만으로 Bundle을 거부하면 안 된다.

- optional frontmatter 필드 누락
- 알 수 없는 `type`
- 알 수 없는 추가 frontmatter key
- 깨진 cross-link
- 누락된 `index.md`

### 12.2 Example Organization OKF Profile 적합성

- 필수 필드 존재 여부
- `id` URI 포맷
- `status` 값 허용 여부
- `evidence` 배열 비어 있지 않음
- `extensions` 외의 조직 전용 필드 사용 금지
- `type: runbook`의 `bundles/<domain>/runbooks/` 배치
- `runbooks/` 하위 비예약 Markdown의 `type: runbook` 확인
- `active` Bundle의 Owner와 `extensions.governance` 확인
- Evidence의 `extensions.capture_context.why_collected`, `intended_use` 확인
- Evidence의 `extensions.availability` 확인
- Rulebook과 Inquiry 확장 타입·상태 계약 확인
- Active Runbook의 Risk Governance와 `workflow.learning` 확인
- 본문 비어 있지 않음
- Evidence URI가 저장소 내 객체와 연결 가능함
- External-file Evidence Manifest가 같은 basename의 원본 파일명을 `original_file`로 기록함
- Evidence 원본 파일이 10MB 이하이면 Git 추적 대상이고, 10MB 초과이면 `original_file_git_tracked: false` 및 `extensions.storage` 정보가 있음
- Bundle Frontmatter는 `.knowledge-os/schemas/bundle.schema.json`을 통과해야 함
- Evidence Record Frontmatter는 호환성 파일명인 `.knowledge-os/schemas/evidence-manifest.schema.json`을 통과해야 함
- `id`의 마지막 UUID 세그먼트와 `bundle_uuid` 필드 값이 일치함
- 파일명의 `_{bundle_uuid}` 부분과 `bundle_uuid` 필드 값이 일치함
- (방어적 점검) `knowledge/bundles/**/*.md` 전체에서 동일한 `id` 또는 동일한 `bundle_uuid`를 가진 문서가 두 개 이상 존재하지 않음
- `.knowledge-os/policies/sensitive-data-masking.md` 기준의 민감정보 마스킹 검토를 거쳤음(`extensions.pii_masked`)

## 13. 적합성 등급

### L1. 구조 적합

- Frontmatter 파싱 가능
- 필수 필드 존재
- 상태값 유효

### L2. 참조 적합

- Evidence 연결 유효
- 링크 필드 형식 유효

### L3. 운영 적합

- 본문 충실도 확보
- owners/summary/updated_at 관리
- Reviewer 또는 Validator 통과

## 14. 파일 배치 규칙

OKF v0.1은 Bundle 내부 하위 디렉터리를 허용하며 도메인별 저장 구조를 강제하지 않는다. 아래 배치 규칙은
공식 OKF 요구가 아니라 Example Organization Profile의 도메인 우선 운영 규칙이다.

- 도메인 기준으로 `bundles/<domain>/` 아래에 저장한다.
- 파일명은 `{slug}_{bundle_uuid}.md` 형식으로 관리한다.
- 파일 경로와 `id`는 직접 동일할 필요는 없지만 의미 충돌이 없어야 하며, 최소한 `bundle_uuid` 세그먼트는 항상 일치해야 한다.
- `index.md`는 디렉터리 안내용 문서로 사용할 수 있다.
- `log.md`는 변경 이력 또는 운영 로그용 보조 문서로 사용할 수 있다.
- `bundles/` 아래 일반 문서는 정제된 공식 지식 문서여야 하며 임시 작업 문서를 두지 않는다.
- `type: runbook` 문서는 내용이 속한 도메인의 `bundles/<domain>/runbooks/` 아래에 저장한다.
- `bundles/<domain>/runbooks/`의 비예약 Markdown은 반드시 `type: runbook`이어야 한다.
- 업무 Rulebook은 여러 Policy·Guide·Runbook을 연결하는 `type: guide`이며 `bundles/<domain>/`에 저장한다.
- `decision` 타입은 내용이 속한 도메인의 `bundles/<domain>/`에 저장한다. 여러 도메인에 걸친 결정은 `bundles/company/`를 기본 위치로 한다.

추가 규칙:

- 일반 concept 문서에는 `index.md`, `log.md` 파일명을 사용하지 않는다.
- 루트 `index.md`는 필요 시 OKF 버전 선언을 포함할 수 있다.

### 14.1 예약 파일 구조

`index.md`와 `log.md`는 예약 파일명이므로 일반 개념 문서와 다른 목적을 가진다.

`index.md`

- 디렉터리의 목적, 하위 문서 목록, 탐색 시작점을 제공한다.
- 최소한 non-empty `type` frontmatter와 해당 디렉터리 설명 본문을 가져야 한다.
- 하위 문서 또는 하위 디렉터리로 이동할 수 있는 링크 목록을 포함하는 것을 권장한다.

`log.md`

- 운영 이력, 변경 기록, 처리 메모를 시간순으로 남기는 보조 문서다.
- 최소한 non-empty `type` frontmatter와 append-friendly 본문 구조를 가져야 한다.
- 개별 concept의 영속 식별자를 대표하는 문서로 사용하지 않는다.

### 14.2 도메인 추가 절차

`bundles/<domain>/`의 도메인 목록은 고정 값이 아니라 아래 절차로 확장 가능하다.

1. `knowledge/bundles/<domain>/index.md`를 `type: domain` Frontmatter로 생성한다.
2. `knowledge/bundles/index.md`에 신규 도메인 링크를 추가한다.
3. 도메인 오너(팀 또는 담당자)를 정한다.
4. 기존 Bundle `type` enum(`policy`, `guide`, `runbook`, `decision`, `spec`, `reference`)으로 표현 가능한지 먼저 검토하고, 표현할 수 없는 경우에만 신규 `type` 추가를 별도로 논의한다.
5. 신규 도메인에서 유입되는 원본이 기존 Evidence `provider`로 표현되지 않으면 `knowledge/evidence/<provider>/`도 함께 추가한다.

## 15. 향후 보완 필요 사항

- 번들 문서의 라이선스 및 배포 메타데이터 채택 여부 결정
- 공식 외부 OKF 스키마 또는 레퍼런스 문서 버전 고정
- JSON Schema 또는 Pydantic 모델로 기계 검증 규칙 명시
- Bundle type taxonomy 확정
