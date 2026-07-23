# Publication Profile

## Trigger

검토된 Draft 또는 Bundle revision을 공식 지식으로 발행하거나 Commit한다.

## Input

- 검토 완료 변경
- Evidence 참조
- 승인 actor와 발행 권한

## Allowed Actions

- 전체 Validator와 보안 Gate 실행
- 승인된 `knowledge/` 변경 Commit

## Checks

- 품질 경고와 신선도
- 변경 영향과 롤백 조건

## Gates

- OKF·Profile Validator
- Evidence 양방향 참조
- Publication Security Review
- 승인 상태와 발행 권한
- 기존 staged 변경 없음
- 현재 Evidence checksum, 생성 actor와 다른 승인 Owner 기록. `runbook`·Manual 성격 `guide`와 직접 생성 Draft의 active 전환에는 `curation_review` Review ID 필수
- active 전환이면 전용 Promotion Gate의 Security Receipt와 PII Scan Receipt

## Output

발행 revision 또는 Commit 결과

## Failure State

Draft를 유지하고 발행 차단 원인과 수정 조건을 기록한다.

## Prohibited

- Gate 우회
- 일반 Bundle 생성·revision API로 `draft -> active`를 전환
- Review가 필요한 유형 또는 직접 생성 Draft의 active 전환에 Review 카드·독립 Owner 승인 없이 active 상태를 주장
- 미검토·`needs_review` 자료 발행
- 승인 없는 외부 게시·Commit
