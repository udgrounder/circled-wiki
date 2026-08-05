# Inbox Inspection Profile

## Trigger

업무성 분류에서 격리되지 않은 `pending` Inbox 대화·문서·파일 항목을 다음 단계로 넘길 수 있는지 검사하거나 검사 결과를 승인한다. 업무성 판단이 애매하면 이 Profile 이전에 폐기하지 않고 여기로 전달한다.

## Input

- 자기완결형 Inbox Item Markdown 또는 Inbox Envelope와 원본 Payload
- 검사자 actor

## Allowed Actions

- 원문 checksum, 필수 메타데이터, provider 폴더, Inbox Sensitive Data Review 상태 검사
- Inbox 내용을 직접 다시 읽어 Capture 단계의 지정된 고위험 식별자·자격증명 마스킹 누락 가능성을 확인하고,
  `review-data-protection`의 통합 Scan·민감도 판단으로 연결한다. 이 확인은 통합 Receipt를 만들기 전의
  읽기 전용 점검이며 자체적으로 PII Scan 완료를 주장하지 않는다.
- 하드 마스킹 누락과 의미 기반 민감정보의 선택적 마스킹·최종 Scan은 `inbox-sensitivity-review.md`의
  `review-data-protection`이 하나의 `data_protection_receipt`로 수행한다. 외부 파일 원본과 payload는 직접
  변경하지 않는다.
- 외부 문서의 source URL·locator 존재 여부 검사
- `required` 민감성 상태는 `inbox-sensitivity-review.md`의 `inbox-sensitivity/v1`을 적용한다. Agent는
  `review-data-protection`에서 하드 PII Scan, 선택적 민감정보 마스킹, 최종 후보 재검사와 업무 맥락 판단을
  수행하고 하나의 `data_protection_receipt`로 `completed` 또는 `not_applicable`을 기록해 해소한다.
  적용할 정책이나 근거가 부족하거나 PII Scan이 `needs_review`이면 같은 통합 절차가
  `workspace/task/inbox_reconciliation/` 계약 작업을 `awaiting_user`로 전환하며 원문은 작업 기록에 복사하지 않는다.
- 통과 항목을 검사자 actor와 함께 `accepted`로 기록
- `inspect-inbox` 검사 보고에서 통과했고 통합 Data Protection Receipt가 해소된 여러 `pending` 항목은
  `accept-ready-inbox`로 한 번에 `accepted`로 전환. 이 일괄 처리는 Scan·민감성 결정·PII 판단을 대신하거나 우회하지 않는다.

## Checks

- 내용 유형과 intended use의 타당성
- 재사용 가치와 보존 분류
- 현재 `hard_mask_categories: true`인 범주의 평문 잔존 여부
- 자동 점검 범위 밖 개인정보는 자동 마스킹하지 않으며, 별도 조직 정책 또는 사람 검토가 필요한지

## Gates

- checksum 일치
- provider와 폴더 일치
- 필수 메타데이터 완전성
- `sensitivity_review`가 해소되고 현재 Inbox checksum에 결합된 `data_protection_receipt`가 `passed` 또는 `masked`
- 통합 Receipt 확정은 acceptance 전에 수행한다. Evidence Ingest Profile은 그 Receipt·checksum과 생성
  Receipt·checksum·생성 스키마를 검증한다. 파일 원본과 판단 불가 입력은 `awaiting_user`로 유지한다.

## Output

읽기 전용 검사 보고서, Inbox Sensitive Data Review 기록 또는 `accepted` Inbox Item 상태

## Failure State

원본을 `pending` Inbox에 유지하고 문제 목록과 재검사 조건을 반환한다.

## Prohibited

- Evidence 또는 Bundle 생성
- Capture·Inspection이 임의로 원문을 자동 수정
- Data Protection Review의 Receipt·새 checksum 없이 Inbox 본문을 수정해 검사를 통과시키기
- 검사자 정보 없는 승인
- 수집 Agent가 Inbox Sensitive Data Review를 완료했다고 자동 기록
- 1차·2차 마스킹 확인만으로 `pii_scanned: true`를 기록
