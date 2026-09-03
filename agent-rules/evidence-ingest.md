# Evidence Ingest Profile

## Trigger

`accepted` Inbox 항목을 추적 가능한 Evidence로 변환한다.

## Input

- 승인된 Inbox Item, 검사 기록, 외부 문서의 `source_ref`

## Applicable Global Rules

- Evidence 수명주기·무결성·저장: RB-EVD-002·004~010·013·015·017~021·023
- 통합 Data Protection Receipt: RB-SEC-001·005·010

## Allowed Actions

- source UUID와 Evidence ID 발급
- Embedded Evidence Document 또는 Evidence Original+External-file Evidence Manifest 생성
- 원본 checksum과 출처 보존
- Inbox Data Protection 단계가 확정한 후보와 `data_protection_receipt`를 Evidence 생성 입력에 전달

## Checks

- idempotency key로 기존 Evidence 재사용 여부
- 저장 크기와 보존 방식
- 통합 Receipt의 `source_checksum`과 Evidence 입력 checksum, `candidate_checksum`과 현재 Inbox 본문·복사
  메타데이터 fingerprint가 같은지 확인
- 파일형 입력은 불변 원본과 PII Scan이 확정한 안전한 후보가 분리되어 있는지 확인

## Gates

- Inbox 상태 `accepted`
- 승인된 검사 기록
- Evidence Schema와 원본 checksum 일치
- RB-EVD-020·RB-SEC-005의 통합 Data Protection Receipt Gate 통과. `needs_review` 또는
  `awaiting_user`는 Inbox에 유지하고 `workspace/task/inbox_reconciliation/`에 현재 단계·요청 조치만
  기록하며 Evidence로 변환하지 않음
- Evidence와 Curation Queue가 RB-EVD-023의 동일 처리 단위로 확정될 것

## Output

RB-EVD-023에 따라 함께 확정된 Evidence ID·보존 경로와 Curation Queue 항목.

## Failure State

RB-EVD-007·023에 따라 Inbox 원본을 유지하고 Evidence·Queue의 부분 성공을 남기지 않는다. Evidence 생성·계약
archive·Queue·Inbox 삭제 중 하나라도 실패하면 새 Evidence와 Queue를 되돌리고 Inbox 계약 작업을
`accepted/pending`의 `retry_evidence_ingest`로 되돌려 다음 실행이 같은 절차를 재개하게 한다. 사용자 결정이
필요한 Data Protection 결과는 `awaiting_user`로 유지하며 자동 재시도하지 않는다. 처리 주체 변경 또는 종료
시의 Commit·Push는 Publication Profile이 수행한다.

`ingest_evidence` 생성 시 Manifest Validator와 checksum을 통과한 뒤에는, Evidence 단계의 Check를 Receipt·
checksum·스키마·전환 산출물로 한정한다. Inbox source 삭제·Curation Queue 등록 같은 **전환 산출물**을 확인하고,
Data Protection 판단은 앞 단계의 확정 Receipt를 입력으로 사용한다.

## Prohibited

- Bundle 생성·수정
- 의미 기반 정제 또는 자동 승격
- `pending`, `needs_review` 입력 ingest
- RB-EVD-020·021·023 또는 RB-SEC-001·005·010을 우회한 Evidence 생성
