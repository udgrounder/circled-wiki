# Inbox Sensitivity Review Rule

## Trigger

현재 `sensitivity_review: required`인 Inbox Item을 검사할 때만 이 규칙을 `inbox-inspection.md`와 함께 적용한다.
Capture 직후에는 모든 Inbox Item이 이 상태로 시작하지만, 재처리 시 이미 해소된 항목에는 다시 적용하지 않는다.

## Input

- `pending` Inbox Item과 원문 또는 Envelope
- Capture Receipt와 기존 `sensitivity_review` 상태
- 검사 actor

## Allowed Actions

- `inbox-sensitivity/v1` 기준에 따른 검사
- 근거가 충분한 경우 `sensitivity_inspection` Receipt와 `completed` 또는 `not_applicable` 기록
- 사용자만 결정할 수 있는 경우 계약 requirement와 안전한 다음 행동 기록

## Checks

`inbox-sensitivity/v1`은 PII Scan과 다르다. PII Scan은 정책 대상 값을 탐지·마스킹하는 보안 검사이고,
이 규칙은 Inbox를 Evidence로 보존·변환할 수 있는지를 판단한다.

| 분류 | 판정 기준 | Agent 결정 |
| --- | --- | --- |
| `automatic_protection` | 주민번호·금융정보·휴대전화·자격증명처럼 자동 PII Scan 정책이 보호하는 값 | 이후 Evidence 직전 PII Scan이 `passed` 또는 `masked` Receipt를 확정한다. 이 범주만으로 Sensitivity Review를 요구하지 않는다. |
| `non_sensitive_context` | 공개 자료, 일반 업무 절차, 비식별 운영 정보이며 아래 제한 검토 대상이 없음 | `not_applicable` |
| `policy_handled_sensitive_context` | 개인·고객·직원 맥락, 비공개 업무 정보가 있으나 적용 가능한 조직 정책이 보존 범위·visibility·필요한 보호 조치를 명시함 | 정책과 조치를 Receipt에 기록하고 `completed` |
| `user_decision_required` | 법적 비밀·의료·아동 정보, 접근 제한 원문, 비식별화 가능 여부가 불명확한 내용, 정책에 없는 새 범주, 안전하게 검사할 수 없는 파일 원본 | `required`를 유지하고 `awaiting_user`로 문의 |

제한 검토 대상은 개인 이름·이메일이 개인 식별 맥락과 결합된 경우, 고객 문의·불만, 직원·인사 정보,
계약·분쟁, 미공개 가격·매출·전략, 보안 구성·사고 상세다. 단순 이름·이메일·일반 계정 ID만으로는
자동 제한 대상으로 추정하지 않는다.

## Gates

`completed` 또는 `not_applicable` 결정은 다음 정보를 가진 `sensitivity_inspection` Receipt로만 기록한다.

```yaml
policy_ref: inbox-sensitivity/v1
actor: {authenticated_actor}
checked_at: {ISO-8601 timestamp}
checks:
  - source_access_scope
  - personal_context
  - confidential_business_context
  - publication_scope
matched_categories: []
decision: not_applicable
rationale: "제한 검토 대상이 발견되지 않았고 internal 보존 범위에 해당"
```

- `not_applicable`은 `matched_categories: []`이고 네 검사가 모두 수행됐을 때만 쓴다.
- `completed`는 하나 이상의 정책 처리 대상과 적용한 보존·visibility·보호 조치를 `rationale`에 기록한다.
- Agent의 “문제가 없음”이라는 결론만으로는 근거가 아니다. `policy_ref`, 검사 항목, 관찰 사실과 결론의 연결이 있어야 한다.
- 해당 Receipt를 만들 수 없으면 `required`를 해소하지 않는다.

## Output

`sensitivity_inspection` Receipt와 해소된 `sensitivity_review`, 또는 사용자 문의를 위한 계약 requirement.

## Failure State

적용할 정책이 없거나 Receipt를 만들 근거가 부족하면 Inbox를 변경하지 않는다. 계약 작업의 requirement에
문의 내용·막힌 단계(`sensitivity_review`)·부재하거나 모호한 절차·안전한 다음 행동·관찰 사실·가설만 기록하고
`awaiting_user`로 둔다. 이 기록의 모든 문자열은 저장 전에 기존 PII Scan 정책으로 검사·마스킹하고,
그 checksum-bound Receipt를 requirement에 기록한다. 원문이나 PII는 이 기록에 복사하지 않는다.

## Prohibited

- PII Scan 결과만으로 `sensitivity_review`를 해소
- 정책·검사 근거 없이 `completed` 또는 `not_applicable` 기록
- 원문을 계약 작업 기록 또는 사용자 문의에 복사
