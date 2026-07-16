# Runbook Evidence-driven Learning Loop

## 1. 목적

Runbook이 실제 사용자 업무에서 얻은 성공, 실패, 피드백과 예외를 Evidence로 축적하고 검증된 revision으로
점진적으로 성장하는 모델을 정의한다. 실행 결과는 Runbook을 직접 수정하지 않으며 개선 검토 Trigger로만 사용한다.

## 2. Growth Loop

```text
Runbook 실행
  -> 단계·승인·결과 기록
  -> Outcome Evidence
  -> reviewed_at 이후 Outcome 집계
  -> Learning Policy 평가
  -> 임계치 미달: Evidence 누적
  -> 임계치 도달/실패/피드백: 개선 Refresh Task
  -> 최신 원본 Evidence 보강
  -> 변화 판정
  -> 독립 Agent 검증
  -> Owner 승인
  -> 새 knowledge_revision
```

## 3. Learning Policy

```yaml
extensions:
  workflow:
    learning:
      maturity: pilot
      min_outcomes_for_review: 3
      review_on_failure: true
      review_on_feedback: true
```

- `maturity`: `pilot`, `operational`, `optimized`
- `min_outcomes_for_review`: 마지막 `reviewed_at` 이후 정기 개선 검토를 시작할 최소 Outcome 수
- `review_on_failure`: 실패 Outcome 1건을 즉시 개선 신호로 사용할지 여부
- `review_on_feedback`: 사용자 피드백이 있는 Outcome을 즉시 개선 신호로 사용할지 여부

실행 횟수와 성공률은 파생 데이터이므로 Runbook Frontmatter에 누적 카운터로 저장하지 않는다. Outcome Evidence를
기준으로 계산한다.
`measure_runbook_effectiveness`는 `knowledge_revision`별 완료·실패·검토 필요·피드백과 완료율을 계산한다.
최소 두 revision에 실제 Outcome이 있을 때만 비교 가능하며, 결과 차이를 변경의 인과 효과로 자동 확정하지 않는다.

## 4. Maturity

| 단계 | 의미 | 승격 기준 |
| --- | --- | --- |
| `pilot` | 초기 절차, 실제 사용 검증 중 | 서로 다른 실제 사용 Outcome과 Owner 검토 확보 |
| `operational` | 반복 사용되고 예외·승인 기준이 안정화 | 정기 검토에서 목표 성공률과 실패 처리 확인 |
| `optimized` | 측정과 개선이 반복되는 안정 절차 | 다수 revision에서 개선 효과와 재현성 확인 |

Maturity 승격은 자동화하지 않는다. Outcome 지표, 최신 Evidence, 독립 Agent 검증과 Owner 승인을 근거로
새 revision에서 변경한다.

## 5. 개선 Trigger

- `min_outcomes_for_review` 도달
- 실패 Outcome과 `review_on_failure: true`
- non-empty 사용자 피드백과 `review_on_feedback: true`
- 승인 반려·`needs_review` 결과
- 반복되는 누락 입력 또는 예외
- 사용자가 절차 개선·최신화를 명시적으로 요청
- 사용자가 더 낫거나 최신이라고 판단한 레퍼런스를 제공

Trigger가 발생하면 `reason: outcome_signal`인 Refresh Task를 생성한다. 동일 Runbook의 미완료 Refresh Task가
있으면 새 Task를 중복 생성하지 않고 기존 Task를 반환한다.

사용자 레퍼런스는 `reason: user_reference`로 분류한다. 먼저 원본을 Evidence로 보존하고 대상 Runbook의
`candidate_evidence_ids`에 연결한다. “더 좋은 자료”라는 사용자 평가는 중요한 개선 신호지만 검증 결과는
아니므로, 권위·최신성·적용 범위·상충 여부를 비교한 뒤 채택·부분 채택·비채택을 결정한다.

## 6. 안전 규칙

- Outcome만으로 정책·법률·외부 플랫폼 사실을 최신이라고 판단하지 않는다.
- 개선 검토 시 관련 최신 원본 Evidence를 별도로 확보한다.
- 한 사용자의 선호를 조직 표준으로 즉시 일반화하지 않는다.
- 작성 Agent는 자신의 변경안을 독립 검증할 수 없다.
- `no_change`도 유효한 검토 결과이며 억지로 본문을 변경하지 않는다.
- 근거가 부족하면 `insufficient_evidence`로 중단한다.
