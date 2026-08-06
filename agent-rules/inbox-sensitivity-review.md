# Data Protection Review Rule

## Trigger

현재 `sensitivity_review: required`인 Inbox Item을 검사할 때 이 규칙을 `inbox-inspection.md`와 함께 적용한다.
Capture 직후에는 모든 Inbox Item이 이 상태로 시작한다. 이 단계는 PII Scan과 민감도 판단을 분리하지 않는
Inbox→Evidence 전환의 단일 Data Protection 단계이며, 이미 해소된 동일 checksum에는 다시 적용하지 않는다.

## Input

- `pending` Inbox Item과 원문 또는 Envelope
- Capture Receipt와 기존 `sensitivity_review` 상태
- 검사 actor
- Agent가 적용할 설치 정책의 구체적인 `agent_mask_categories` ID와 업무 맥락 근거.
- Agent가 식별한 민감 텍스트 조각과 그 분류. 이 값은 마스킹 실행에만 사용하고 Receipt에는 저장하지 않는다.

## Allowed Actions

- `inbox-sensitivity/v1` 기준에 따른 검사
- 근거가 충분한 경우 통합 `data_protection_receipt`와 `completed` 또는 `not_applicable` 기록
- 사용자만 결정할 수 있는 경우 계약 requirement와 안전한 다음 행동 기록

## Integrated Procedure

`review-data-protection`은 PII Scan과 민감도 판단을 같은 후보에 적용하고 하나의
`data_protection_receipt`를 기록한다. 기존 `pii_scan_receipt`와 `sensitivity_inspection`은 이 Receipt에서
파생된 호환용 projection이며 Evidence·acceptance Gate의 정본이 아니다.

1. Data Protection Review는 대상 Inbox 후보를 한 번 읽어 PII 탐지 결과와 민감도 판단 후보를 함께 만든다.
   `hard_mask_categories`가 `true`인 범주는 기계적으로 마스킹하고, `false`인 범주는 하드 마스킹하지 않은
   민감도 판단 입력으로 유지한다.
2. Data Protection Review는 같은 처리 결과에서 하드 스캔 누락을 보완하고,
   `agent_mask_categories`의 `include` 경계에 해당하는 텍스트도 선택적으로 마스킹한다. 계약·법률 자문·분쟁·소송·
   규제 대응과 그 업무상 결정은 그 자체로 마스킹하지 않으며, 명시적인 불법 행위 실행·조장·은폐 또는 타인의
   권리·안전을 침해하는 구체적 지시만 `unlawful_content`로 다룬다.
3. Agent 마스킹은 후보에서 정확한 텍스트를 제거하는 변환이므로, 최초 기계 PII Scan 결과를 최종 후보 checksum에
   다시 결합한다. 같은 결정적 PII 규칙을 후보 전체에 다시 실행하지 않는다.
4. `agent_mask_categories`에 선언된 대상만 Agent가 정확한 범위를 판단해 마스킹한다. 선언되지 않은
   잔여 후보는 보존 allowlist를 요구하지 않고 계속 처리한다.
5. 위 결과를 하나의 `data_protection_receipt`로 기록한다. `passed` 또는 `masked`만 acceptance Gate를
   통과한다. Evidence는 이 Receipt와 후보 checksum·생성 스키마·전환 산출물만 검증한다.

하드 처리된 값은 복원·재판단하지 않는다. Agent 마스킹 범주가 판단 가능하면 해당 부분만 마스킹하고 나머지 업무 정보 처리를 계속한다. 법적 처리·결정은 법무 업무라는 이유만으로 제한하지 않는다. 명시적인 불법성이 확인되지 않은 법률·계약 내용은 `unlawful_content`로 추정하지 않으며, 그 불확실성만으로 `awaiting_user`로 전환하지 않는다. 실제 마스킹 대상의 범위·처리 방식 또는 다른 정책 판단을 안전하게 정할 수 없을 때만 원문을 Git 추적 영역으로 보내지 않고 `awaiting_user`로 둔다.

`agent_mask_categories`의 `include`·`exclude`는 Agent 판단의 범위와 예시를 정의하는 정책 근거이지,
단어 하나를 발견하면 기계적으로 전체 문장을 마스킹하는 패턴 목록이 아니다. `include`는 최소 하나 이상의
판단 경계를 가져야 하며, `exclude`에 해당하거나 범위가 불명확하면 마스킹을 확대하지 않고 `awaiting_user`로 보류한다.

## Checks

`inbox-sensitivity/v1`은 PII Scan과 다르다. PII Scan은 하드 마스킹 값과 정책 판단 후보를 구분해 탐지하는 보안 검사이고,
이 규칙은 Inbox를 Evidence로 보존·변환할 수 있는지를 판단한다.

PII Scan이 하드 마스킹하지 않고 남긴 실제 후보는 별도 보존 allowlist 없이 통합 민감도 판단에 전달한다.
정책에 선언된 `agent_mask_categories`에 해당하는 값만 Agent가 정확한 범위를 지정해 마스킹하며, 그 밖의
연락처·이메일 등은 변경하지 않고 계속 처리한다.

설치별 분류 기준은 `.circled-wiki/data-protection.yaml`에서 읽는다. 파일이 없으면 동일한
`.circled-wiki/templates/data-protection.yaml`을 기본 정책으로 사용하며, Bootstrap은 그 템플릿으로 누락된
파일만 생성한다. 기존 파일은 업그레이드에서 덮어쓰지 않는다. `hard_mask_categories`는
지원되는 범주별 boolean 토글이다. 매핑에서 빠진 범주는 `true`로 간주하고, 기본 템플릿은 휴대전화와 이메일을
`false`로 명시한다. 정책 파일이 없거나 판단 근거가 부족한 경우의 안전한 기본 동작은 `awaiting_user`다. 다른
동작으로 바꾸려면 Queue 상태·재시도 계약을 함께 정의해야 한다.

### 우선순위

1. PII Scan은 `hard_mask_categories: true`인 범주를 즉시 마스킹하고, `false`인 범주는 하드 마스킹하지 않은
   실제 탐지 후보로 통합 민감도 판단에 전달한다.
2. Data Protection Review는 활성 하드 범주를 다시 확인해 누락을 보완하고, Agent가 판단 가능한
   `agent_mask_categories`의 `include` 경계에 해당하는 부분만 마스킹한다. 각 범주의 `exclude` 경계와
   업무 맥락을 함께 확인하며, 값이 아닌 범주·횟수·근거만 Receipt에 기록한다.
3. `agent_mask_categories`에 선언된 대상은 Agent가 업무 맥락과 `include`·`exclude` 경계를 근거로
   정확한 텍스트만 선택해 마스킹한다. 선언되지 않은 잔여 후보는 보존 allowlist를 요구하지 않는다.
4. 민감 범위·마스킹 방식·업무 맥락을 안전하게 판단할 수 없으면 `missing_policy_action`에 따라 `awaiting_user`로 둔다.

| 분류 | 판정 기준 | Agent 결정 |
| --- | --- | --- |
| `automatic_protection` | 주민번호·금융정보·자격증명처럼 하드 PII Scan 정책이 보호하는 값 | 통합 단계가 마스킹 후 최종 후보 checksum에 결합된 `masked` Receipt를 확정한다. 이 범주만으로 별도 민감도 사용자 검토를 요구하지 않는다. |
| `scanner_candidate` | 하드 마스킹 후에도 PII Scan이 탐지한 값으로 업무 맥락에 따라 보존 여부가 달라지는 후보 | 승인된 구성원·협력업체 업무 맥락 근거가 있으면 내부 보존하며, 근거가 없을 때만 `awaiting_user`로 둔다. |
| `agent_mask_context` | `agent_mask_categories`의 `include` 경계에 해당하는 고객 휴대전화·급여·평가·징계·미공개 사업정보·보안 구성 또는 명시적인 불법 콘텐츠 | 해당 텍스트만 마스킹하고 범주·횟수·근거를 Receipt에 기록한 뒤 `completed` |
| `user_decision_required` | 현재 Wiki 정책의 판단 근거로 안전한 범위·마스킹 경계를 정할 수 없는 내용, 접근 제한 원문, 정책에 없는 새 범주, 안전하게 검사할 수 없는 파일 원본 | `required`를 유지하고 `awaiting_user`로 문의 |

기본 민감도 판단 근거는 고객 연락처의 휴대전화, 개인 이름·이메일이 개인 식별 맥락과 결합된 경우, 고객 문의·불만, 개인별 급여·평가·징계,
미공개 매출·정산·가격·사업 전략, 내부 보안 솔루션 구성·접근통제·탐지 규칙·사고 대응 기술 상세다. 일반
정책에 선언되지 않은 구성원 프로필·입사·퇴사·업무 연락처는 변경하지 않고 내부 운영 목적에 필요한 경우 보존할 수 있다. 계약의 법적 조건·의무·해지·책임·보증·면책, 계약 협상,
분쟁·소송·합의 대응, 법률 자문·법적 보존·법적 절차·규제기관 대응과 그 결정은 법무 업무 내용이라는 이유만으로
자동 제한하지 않는다. 다만 명시적인 불법 행위 실행·조장·은폐 또는 타인의 권리·안전을 침해하는 구체적 지시는
`unlawful_content`로 마스킹한다. Wiki는 `agent_mask_categories`의 범주별 `description`·`include`·`exclude`
경계와 근거를 추가·조정할 수 있으며, 단순 이름·이메일·일반 계정 ID만으로는 자동 제한 대상으로 추정하지 않는다.

`agent_mask_categories`에 명시된 `include` 범위의 고객 휴대전화·급여·평가·징계·미공개 사업정보·보안 구성과 명시적인 불법 콘텐츠만 민감도 마스킹 대상이다.
업무용 구성원·협력업체 연락처와 결합돼도 해당 민감한 부분만 마스킹하고, 연락처와 나머지 안전한 업무 정보는 계속 처리한다.

## Gates

`completed` 또는 `not_applicable` 결정은 다음 정보를 가진 `data_protection_receipt`로만 기록한다.

```yaml
schema_version: 1
source_checksum: sha256:{current_inbox_checksum}
candidate_checksum: sha256:{body_and_metadata_candidate}
policy_ref: inbox-sensitivity/v1
policy_config: .circled-wiki/data-protection.yaml
policy_config_version: 1
status: passed | masked
pii_scan: {checksum-bound PII result}
sensitivity:
  decision: completed | not_applicable
  context: "customer_mobile_phone | compensation | performance_review | "
  matched_categories: []
  agent_masked_findings: []
receipt: runtime://data-protection/{checksum}
```

`source_checksum`은 Inbox 본문 또는 payload 무결성을, `candidate_checksum`은 Evidence로 복사되는 본문과
제목·수집 이유·source URL/locator·intended use 메타데이터를 함께 묶는다. 둘 중 하나라도 현재 후보와
다르면 이전 Receipt는 재사용하지 않고 통합 Data Protection 단계를 다시 시작한다.

- `not_applicable`은 `sensitivity.decision: not_applicable`이고 실제 정책 처리 대상이 없을 때만 쓴다.
- Agent 마스킹 범주를 마스킹했으면 남은 정책 후보가 없어도 `sensitivity.decision: completed`, `status: masked`로 기록한다.
- Agent 민감정보 마스킹은 `sensitivity.agent_masked_findings`에 범주와 횟수만 기록한다. 원래 값·문장·식별자는 기록하지 않는다.
- Agent의 “문제가 없음”이라는 결론만으로는 근거가 아니다. `policy_ref`, 검사 항목, 관찰 사실과 결론의 연결이 있어야 한다.
- 해당 Receipt를 만들 수 없으면 `required`를 해소하지 않는다.

## Output

`data_protection_receipt`와 해소된 `sensitivity_review`, 또는 사용자 문의를 위한 계약 requirement.

## Failure State

적용할 정책이 없거나 Receipt를 만들 근거가 부족하면 Inbox를 변경하지 않는다. 계약 작업의 requirement에
문의 내용·막힌 단계(`sensitivity_review`)·부재하거나 모호한 절차·안전한 다음 행동·관찰 사실·가설만 기록하고
`awaiting_user`로 둔다. 이 기록의 모든 문자열은 저장 전에 기존 PII Scan 정책으로 검사·마스킹하고,
그 checksum-bound Receipt를 requirement에 기록한다. 원문이나 PII는 이 기록에 복사하지 않는다.

## Prohibited

- PII Scan 결과만으로 정책 판단 대상의 보존을 승인하거나 `data_protection_receipt`를 완료
- 정책·검사 근거 없이 `completed` 또는 `not_applicable` 기록
- 원문을 계약 작업 기록 또는 사용자 문의에 복사
