# Runbook 유효성 및 Refresh 절차

## 1. 목적

Runbook의 시간 기반 유효기간과 이벤트 기반 재검토 조건을 정의하고, 만료되었거나 사용자가 최신화를
요청한 Runbook을 최신 Evidence로 검토해 새 revision으로 발행하는 절차를 정의한다.

만료는 지식이 거짓이라는 뜻이 아니라 마지막 검증 보증이 종료됐다는 뜻이다. 만료 Runbook은 삭제하지 않고
업무 실행을 보류한 뒤 Refresh Task를 먼저 수행한다.

## 2. 유효기간 판단 기준

### 2.1 Risk Tier

| Tier | 판단 기준 | 최대 유효기간 | 예시 |
| --- | --- | ---: | --- |
| `critical` | 법률·보안·결제·개인정보 또는 오류가 즉각 중대한 손실을 유발 | 7일 | 개인정보 처리, 결제 승인 |
| `high` | 고객·매출·외부 플랫폼 등록에 직접 영향 | 30일 | 캠핑장 등록, 가격·환불 운영 |
| `medium` | 내부 운영 품질에 영향하며 복구 가능 | 90일 | 포스터 제작, 콘텐츠 검수 |
| `low` | 안정적인 내부 보조 절차이며 오류 영향이 제한적 | 180일 | 정기 파일 정리, 내부 참고 절차 |

### 2.2 Source Volatility

| 값 | 기준 | 적용 |
| --- | --- | --- |
| `volatile` | 외부 정책·API·가격·법규가 수시 변경 | Risk Tier 상한의 50%, 소수점 올림 |
| `periodic` | 월·분기 단위 변경 가능 | Risk Tier 기본 상한 적용 |
| `stable` | 조직이 직접 통제하며 변경이 드묾 | Risk Tier 기본 상한 적용 |

실제 `validity_days`는 Risk Tier 최대값을 초과할 수 없다. 더 짧게 설정할 수 있으며, `review_due_at`은
`reviewed_at + validity_days`보다 늦을 수 없다.

### 2.3 즉시 Refresh Trigger

아래 이벤트는 유효기간이 남아 있어도 즉시 Refresh Task를 만든다.

- 사용자가 최신화 확인을 명시적으로 요청
- 사용자가 기존 근거보다 낫거나 최신이라고 판단한 레퍼런스를 제공
- Runbook Owner 또는 Reviewer가 재검토 요청
- 참조 Evidence의 원본 정책·API·법규·가격·도구 계약 변경 감지
- 실행 실패, 반려, 부정 피드백이 반복되거나 Critical 실패 1회 발생
- 보안 사고, 감사 지적 또는 권한 모델 변경
- 관련 상위 Policy 또는 Business Rulebook revision 변경

## 3. Frontmatter 계약

```yaml
extensions:
  governance:
    reviewed_at: 2026-07-14T00:00:00+09:00
    review_due_at: 2026-08-13T00:00:00+09:00
    freshness_policy: risk_based
    risk_tier: high
    source_volatility: periodic
    validity_days: 30
    change_triggers:
      - user_requested
      - user_reference
      - source_change
      - outcome_signal
```

유효성 상태는 저장하지 않고 현재 시각과 `review_due_at`으로 계산한다.

- `valid`: 검토 기한 전
- `due_soon`: 남은 기간이 전체 유효기간의 20% 이하
- `expired`: 현재 시각이 검토 기한 이상

## 4. Process Flow

```text
Workflow 사용 요청
  -> Runbook 유효성 계산
  -> valid/due_soon: 기존 Workflow Task 생성
  -> expired: 업무 실행 보류 + Runbook Refresh Task 생성

사용자 최신화 요청
  -> 유효성 상태와 관계없이 Runbook Refresh Task 생성

사용자 레퍼런스 제출
  -> 원본과 manifest를 Evidence로 보존
  -> submit_runbook_reference로 후보 등록
  -> 열린 동일 Runbook Refresh Task가 있으면 candidate_evidence_ids에 병합

Refresh Task
  -> 최신 Evidence 수집
  -> Evidence 최신성·접근성·출처 검증
  -> 기존 Runbook과 차이 비교
  -> update_required / no_change / insufficient_evidence 판정
  -> 변경 draft 또는 무변경 갱신안 작성
  -> 작성 Agent와 다른 Agent의 독립 검증
  -> Validator 실행
  -> Owner 승인
  -> 새 revision 발행
  -> Refresh Outcome Evidence 기록
  -> 원래 업무 요청 재시도
```

## 5. Refresh Task 표준 단계

| 순서 | Step | Kind | 완료 조건 |
| ---: | --- | --- | --- |
| 1 | `collect-current-evidence` | action | 필수 원본의 최신 스냅샷 확보 |
| 2 | `validate-current-evidence` | validation | 최신성·접근성·출처와 검증 범위 확인 |
| 3 | `compare-runbook` | validation | 기존 단계·Policy·Tool 계약과 Evidence 차이 기록 |
| 4 | `prepare-refresh-proposal` | decision | `update_required`, `no_change`, `insufficient_evidence` 판정 |
| 5 | `independent-agent-review` | validation | 제안 작성자와 다른 Agent가 근거·누락·충돌 검증 |
| 6 | `validate-proposal` | validation | OKF/Profile/보안 검증 통과 |
| 7 | `owner-approval` | approval | 실제 Owner 승인 기록 |
| 8 | `publish-revision` | action | 승인 revision 발행 및 index/link 갱신 |

Refresh 완료 전 원래 업무 Workflow를 실행하지 않는다. `no_change`는 본문을 억지로 수정하지 않고 새
`reviewed_at`, `review_due_at`, 검토 Evidence와 `knowledge_revision`만 반영한다. `insufficient_evidence`는
`needs_review`로 중단한다. 독립 검증 Agent의 `actor`는 제안 작성 Agent와 달라야 한다.
운영 환경에서는 actor 문자열을 Prompt가 아니라 인증된 Agent·사용자 identity에서 주입한다.

`update_required`와 `no_change`가 참조하는 Evidence는 저장소 manifest로 해석 가능하고
`extensions.availability: available`이어야 한다. 최소 하나는 기존 `reviewed_at` 이후에 캡처된 최신
스냅샷이어야 한다. `metadata_only`, `access_denied`, `missing` 근거는 `insufficient_evidence` 사유로
참조할 수 있지만 변경·무변경 확정에는 사용할 수 없다.

사용자 레퍼런스는 제출 시점에 우수성이 확정되지 않은 Candidate Evidence다. 제출자, 제출 시각, 메모를
`reference_submissions`에 보존하고 출처 권위, 캡처 시각, 원본 접근성, 적용 범위, 기존 Evidence와의 충돌을
검사한다. 비교 결과만으로 변경안을 만들며 이후 독립 Agent 검증과 Owner 승인을 생략할 수 없다.
구조화된 비교는 `record_reference_assessment`로 기록하며 평가자와 검증자를 분리한다. 채택 결과는
`accept`, `partial_accept`, `reject`, `needs_more_evidence` 중 하나다.
Candidate Evidence가 있으면 모든 후보의 Assessment가 있어야 변화 판정을 확정할 수 있다. 갱신안 승인 후
`confirm_runbook_revision`이 실제 Runbook의 증가한 `knowledge_revision`, 새 검토 시각과 Validator 통과를
확인해야 `publish-revision` 단계를 완료할 수 있다.

## 6. RACI

| 단계 | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| 최신 Evidence 수집 | Hermes/Curator | Runbook Owner | 원본 시스템 담당자 | 요청자 |
| 변경 판정·갱신안 | Curator | Runbook Owner | 도메인 담당자 | 요청자 |
| 독립 Agent 검증 | Sub Agent/다른 Agent | Reviewer | 도메인·Security Owner | Runbook Owner |
| Validator·보안 검토 | Validator/Reviewer | Reviewer | Security Owner | Runbook Owner |
| 승인·발행 | Repository Agent | Runbook Owner | Reviewer | 요청자 |

## 7. 예외 처리

| 상황 | 처리 |
| --- | --- |
| 최신 원본 접근 불가 | `needs_review`, 기존 Runbook 자동 실행 금지 |
| Owner 부재 | 대체 승인자 지정 전 발행 금지 |
| 변경 내용이 상위 Policy와 충돌 | 상위 Policy 검토를 먼저 수행 |
| 긴급 업무이나 Runbook 만료 | 승인권자가 일회성 예외를 명시적으로 승인하고 Outcome에 기록 |
| 최신화 요청이 중복됨 | 진행 중 Refresh Task를 반환하고 중복 Task를 생성하지 않음 |
| 진행 중 새 사용자 레퍼런스 제출 | 기존 Task에 Candidate Evidence와 제출 이력을 병합 |

## 8. 운영 지표

| 지표 | 목표 |
| --- | --- |
| 만료 Runbook 실행 건수 | 0 |
| Refresh 기한 내 완료율 | 95% 이상 |
| Owner 없는 Active Runbook | 0 |
| 사용자 최신화 요청 후 Refresh Task 생성 | 즉시 |
| 변경 없는 Refresh 비율 | 유효기간 조정 근거로 분기별 검토 |
