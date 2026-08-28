# Publication Profile

## Trigger

검토된 Draft 또는 Bundle revision을 공식 지식으로 발행하거나, 처리 주체 변경·최종 종료 시 검증된 Queue·Review·Draft 상태를 Commit·Push해 다음 실행 주체와 공유한다. 같은 처리 주체의 연속 단계는 하나의 로컬 작업 단위로 묶으며 중간 Commit·Push를 요구하지 않는다.

## Input

- 검토 완료 변경 또는 주체 변경·종료를 나타내는 원문 없는 검증된 처리 주체·작업 상태 전이 Receipt
- Evidence 참조
- 공식 지식 발행에는 승인 actor와 발행 권한, 상태 공유에는 configured publication policy

## Allowed Actions

- 전체 Validator와 보안 Gate 실행
- 승인된 `knowledge/` 변경 또는 허용된 상태 기록 Commit·Push

## Checks

- 품질 경고와 신선도
- 변경 영향과 롤백 조건
- 새 domain·provider를 도입하거나 Vault 운영 흐름을 바꾸면 `knowledge/README.md`의 운영 목록과 설명을 함께 갱신했는지
- Bundle 파일명·Frontmatter ID 변경이면 `OPERATING_RULES.md`의 RB-KNW-026 Bundle Identity Contract, 대상 파일 목록, 참조·링크 영향과 rollback 경로

## Gates

- OKF·Profile Validator
- Bundle `evidence` 참조 무결성
- Bundle 정규화면 파일명 `{slug}.md`, `id` `bundle/{organization_id}/{slug}--{bundle_uuid}`, `bundle_uuid` 불변성과 전체 Validator
- Publication Security Review
- 공식 지식 발행은 승인 상태와 발행 권한, Queue·Review·Draft 상태 공유는 configured publication policy
- 기존 staged 변경 없음
- Curation Queue 완료가 포함되면 `workspace/task/curation_reconciliation/<uuid>.md` 삭제를
  `verify-curation-commit`으로 확인한다. 새 reconciliation task Archive 추가는 허용하지 않는다
- 현재 Evidence checksum과 승격 provenance 기록. `runbook`·`manual`은 생성 전 Review ID와 별도 검증 시도 기록이 필수이며, 최초 생성·보완 Review는 `extensions.curation.review_receipts`에 누적 보존한다. 직접 생성 가능한 유형은 RB-CUR-006 자동 Gate의 provenance를 남긴다
- active 전환이면 전용 Promotion Gate의 Security Receipt와 Evidence에 보존된 통합 `data_protection_receipt`
- 처리 주체 전이 또는 종료면 이전 결과, 대상 checksum, 다음 처리 주체와 `next_action`을 기록. Push Receipt는 Commit·Push 성공 뒤 이 전이를 완료 처리하는 결과물

## Output

발행 revision 또는 처리 주체 전이·종료 Commit 및 Push Receipt. Curation Queue 완료가 포함되면
원본 Queue task 삭제가 검증된 전환 결과를 포함한다. Push가 실패하면
`publication_pending` 상태와 재시도 조건

## Failure State

같은 처리 주체의 아직 미공유 로컬 작업은 다음 작업과 함께 한 번에 Commit·Push할 수 있다. 처리 주체 전이·종료 Commit 뒤 Push가 실패하면 `publication_pending`으로 유지한다. 다음 Push는 `resume-pending-push`로 현재 HEAD와 원격에 없는 모든 선행 Commit을 함께 전송한다. Push 성공 전에는 다음 처리 주체가 전이된 상태를 공유받은 것으로 보지 않는다.
새 reconciliation task Archive가 staged 되었으면 Commit·manifest·Receipt를 진행하지 않고, 해당 Archive
추가를 제거한 뒤 `verify-curation-commit`을 재시도한다.

## Prohibited

- Gate 우회
- 일반 Bundle 생성·revision API로 `draft -> active`를 전환
- `runbook`·`manual`의 active 전환에 Review 카드·별도 검증 시도 기록 없이 active 상태를 주장
- 미검토·`needs_review` 자료 발행
- configured publication policy 또는 명시된 발행 권한 없는 외부 게시·Commit
