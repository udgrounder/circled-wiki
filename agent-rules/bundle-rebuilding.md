# Bundle Rebuilding Profile

## Trigger

사용자가 특정 Bundle 또는 Bundle 시리즈의 리빌딩을 명시적으로 요청한다.

## Input

- 사용자가 지정한 Bundle 또는 Bundle 목록
- 관련 Bundle·Evidence의 현재 revision·상태·경로
- 사용자가 대화에서 합의한 리빌딩 범위와 원하는 결과 구조

## Allowed Actions

- 관련 Bundle·Evidence·링크를 읽기 전용으로 조사하고 리빌딩 계획을 제시
- 사용자와 통합·갱신·분리·archive 대상 및 결과 Bundle 구조를 조율
- 합의된 계획에 한해 Bundle 생성·revision·archive를 적용하고 검증
- 적용 결과·archive 목록·복구 조건을 `workspace/bundle-rebuilds/`에 간단한 receipt로 자동 기록

## Rules

- 일반 Evidence Curation, Bundle 생성·갱신, 날짜별 supplement 생성 흐름은 이 Profile로 바꾸지 않는다.
- 자동 주기 실행, 날짜·개수 기반 후보 탐지, 자동 통합·archive, 사전 알림은 수행하지 않는다.
- 사용자의 리빌딩 요청은 조사와 리빌딩 수행 권한이다. Agent는 관련 Bundle·Evidence를 최신 Evidence 우선으로 검토하고, 요청 범위에서 통합·갱신·archive를 한 번에 수행한다. 파일명 날짜가 아니라 Evidence `source_ref.snapshot_at`, 없으면 `captured_at`을 최신성 기준으로 사용한다.
- 서로 다른 Bundle을 통합하는 경우 새 또는 갱신되는 Bundle이 원본 Evidence 관계를 보존해야 한다. 원본 Bundle은 성공적으로 검증된 결과가 생긴 뒤에만 `knowledge/bundles/.archive/<domain>/`으로 이동한다.
- 기존 Bundle의 domain·type·경로를 바꾸는 작업은 `curation-taxonomy.md`의 acknowledged reclassification Gate를 함께 적용한다.
- 결과는 전체 Validator를 통과해야 하며, 실패하면 새·변경 Bundle과 archive 이동을 원복하고 receipt에 실패·복구 상태를 남긴다.

## Checks

- 요청 대상과 같은 시리즈라는 근거, 현재 revision, status, ID·UUID·Evidence·링크 관계
- 통합 결과의 제목·요약·본문이 원본 Bundle의 확정 Evidence로 뒷받침되는지
- archive 대상이 결과 Bundle으로 대체되는지와 각 원본의 복구 조건
- domain·type·경로 변경이 있으면 acknowledged reclassification approval의 유효성

## Gates

- 사용자 명시 요청과 사용자와 확정한 리빌딩 계획
- 새·갱신 Bundle의 Evidence·revision·Review·Security Gate
- archive 전 결과 Bundle 검증 및 전체 Validator 통과
- reclassification이 있으면 RB-KNW-027의 notification acknowledgement·영향 목록·taxonomy domain 대조

## Procedure

1. `inspect`: 요청 대상과 관련 Bundle·Evidence를 읽고 최신 Evidence를 우선해 현재 구조·관계를 확인한다.
2. `rebuild`: 요청 범위에서 통합·갱신·분리·archive를 수행한다. 새 결과 Bundle을 먼저 검증하고, 그 뒤에 원본을 archive한다.
3. `verify`: 전체 Validator와 Evidence 참조·ID·UUID·링크·archive 복구 조건을 확인한다.
4. `record`: 적용 결과와 복구 조건을 `workspace/bundle-rebuilds/`에 자동 기록하고 결과를 사용자에게 알린다.

## Existing Duplicate Recovery

중복 방지 제품 수정은 기존 Bundle을 병합하거나 정리하지 않는다. 이 절차는 사용자가 명시적으로
지정한 기존 중복에 적용하며, 제품 수정·배포 요청이나 이슈 처리만으로 운영 지식 변경을 시작하지 않는다.
`draft`뿐 아니라 이미 자동 승격된 `active` 중복도 조사 대상이다. 제목이 비슷하다는 사실만으로
내용과 적용 범위가 같다고 판단하지 않는다.

1. **대상 고정과 복구 준비.** 요청된 각 Bundle의 ID·UUID·경로·상태·`knowledge_revision`·본문
   checksum과 Evidence 목록을 읽는다. 같은 대상의 Curation·발행 쓰기와 충돌하지 않도록 조율하고,
   변경 전 파일과 경로를 보존한 복구 snapshot을 준비한다. 사용자 작업 트리 변경은 포함 여부를
   구분해 보존하며, 적용 직전 revision·checksum이 달라졌으면 다시 조사한다.
2. **정본과 통합 내용 결정.** 각 원본의 고유 내용·상충·적용 범위와 Evidence의
   `source_ref.snapshot_at` 또는 `captured_at`을 비교한다. 더 오래됐거나 더 긴 Bundle이라는 이유만으로
   정본을 고르지 않는다. 정본 ID·UUID를 유지할지 새 결과를 만들지 정하고, 원본별로 유지할 내용과
   제외할 중복·오래된 주장의 사유를 계획에 남긴다. 사실이 상충하거나 보존 범위를 판단할 수 없으면
   해당 부분의 변경을 보류한다. 원본 Evidence를 삭제·재작성하지 않는다.
3. **참조·검증 계획 확정.** 결과 Bundle은 통합 대상의 모든 유효 Evidence 참조를 중복 없이 보존한다.
   제외가 필요하면 사유와 원본 archive의 추적 경로를 명시한다. 다른 Bundle, Review, 실행 중인 task,
   Markdown·위키 링크와 외부 소비자가 원본 ID·경로를 사용하는지 조사하고, 갱신·유지·수동 확인
   대상으로 구분한다. ID만 비교하는 Validator가 경로 링크와 외부 참조까지 보장한다고 간주하지 않는다.
   domain·type·경로를 재분류하면 기존 acknowledged reclassification Gate도 적용한다.
4. **결과를 먼저 적용·검증.** 확정된 통합 본문과 Evidence를 결과 Bundle에 반영한다. 변경 시점의
   revision과 본문 checksum을 대조하고 기존 Review·Owner·Security Gate를 통과시킨다. active 결과의
   현재 Evidence checksum과 Data Protection Receipt 결합, Security provenance를 다시 확인하며,
   `runbook`·`manual`은 필요한 Review·별도 검증·보완 이력을 보존한다. `draft -> active`는 전용
   Promotion Gate만 수행한다. 결과 Bundle과 전체 Validator가 통과하기 전에는 원본을 archive하지 않는다.
5. **중복 archive와 참조 정리.** 결과의 검증 후 각 중복에 대체 정본 ID와 병합 사유를 기록한다.
   `extensions.archive`에 시각·담당자·사유·복구 조건을 남기고, 상태와 Review 상태가 모순되지 않게
   처리한 뒤 원래 도메인·파일명을 유지해 `knowledge/bundles/.archive/<domain>/`으로 이동한다.
   계획에 포함된 참조만 정본으로 갱신하고, 보존한 원본 ID·UUID와 실제 archive 경로를 receipt에 남긴다.
   원본이나 원본 Evidence를 삭제하거나 ID를 정본 ID로 덮어쓰지 않는다.
   active 원본에 Curation provenance가 있으면 `extensions.review_state: merged`와
   `extensions.curation.merged_into: <정본 ID>`를 함께 기록하고 기존 Review·Promotion 이력은 보존한다.
   `status`만 `archived`로 바꿔 이전 `approved` Review 상태와 모순되게 만들지 않는다. 적용 직전
   원본 revision·본문 checksum을 다시 대조하고, 수동 archive의 `knowledge_revision`은 1 증가시키며
   `updated_at`·`extensions.updated_by`와 merge actor·시각·사유를 기록한다.
6. **완료 검증과 기록.** 전체 Validator를 다시 실행하고, 정본에서 모든 보존 Evidence를 찾을 수 있는지,
   고유 내용이 빠지지 않았는지, 기본 검색·후속 proposal이 중복 archive 대신 정본을 선택하는지 확인한다.
   기존 참조의 갱신·잔여 수동 확인 결과도 별도로 검증한다. 실패하면 변경 전 snapshot으로 이번 작업의
   Bundle·링크 변경과 archive 이동을 원복한다. 그사이 새 변경이 생겼다면 덮어쓰지 말고 부분 복구 상태와
   남은 조치를 기록한다. 발행·Commit·Push는 Publication Profile의 별도 권한을 따른다.

### Supported Operations and Limits

- 이미 처리된 Evidence도 `create-curation-review`로 정본 갱신을 검토할 수 있다. 정본에 없는 Evidence를
  하나씩 입력하고, 출력의 `action`·`bundle_type`·`domain`은 정본과 일치시키며
  `existing_bundle_candidates: [<정본 ID>]`, `evidence_ids: [<해당 Evidence ID>]`, 현재
  `base_body_checksum`을 명시한다. 추가분은 `update_mode: append`, 검토된 전체 본문 통합은
  `update_mode: replace_full`과 `replace_reason`을 사용한다. 각 적용 뒤 revision·본문 checksum을
  다시 읽어 다음 Review의 기준으로 삼는다.
- `guide` 등 사용자 요청이 필요한 유형에는 실제 요청을 식별하는 `--user-review-request`를 전달해
  Review 카드를 만들고, 생성자와 다른 검증자가 `decide-curation-review --action approve`로 확인한 뒤
  `apply-approved-curation-update`로 정본을 갱신한다. 활성 정본은 ID·UUID·active 상태를 유지한다.
  이 경로는 이미 완료된 Evidence에 pending Queue를 요구하지 않는다. 복구를 위해 Queue를 임의 생성하거나
  pending Queue를 요구하는 `apply-automatic-curation-update`로 이 검토 경로를 대체하지 않는다.
- `review-curation-candidate --action merge --merged-into <result-id>`는 reviewable **Draft**의 병합
  결정을 기록하고 원본을 archive하는 명령이다. 내용·Evidence·기존 링크를 정본에 자동 통합하지 않는다.
  위 절차로 결과를 먼저 통합·검증한 뒤에만 이 명령을 사용한다.
- active·draft 중복의 명시적 복구에는 아래 전용 명령을 사용한다. 일반 `apply_bundle_revision`의
  상태 전환 제한이나 Draft 전용 merge 명령을 우회 수단으로 사용하지 않는다.

### Dedicated Recovery Commands

1. 검토할 **최종 정본 본문만** UTF-8 Markdown 파일로 준비한다. 의미적 중복 제거·상충 해소·고유 내용
   보존은 Curator와 Reviewer가 판단한다. 명령은 본문을 자동 요약하거나 어느 원본이 맞는지 추정하지 않는다.
2. `plan-duplicate-bundle-recovery --source <중복 ID> --target <정본 ID> --merged-body-file <파일>`로
   변경 없는 계획을 확인한다. source/target의 revision·전체 파일 checksum·권한·ID·UUID·상태·경로,
   Evidence 합집합의 checksum·manifest checksum과 최종 본문 checksum이 `plan_checksum`에 결합된다.
   계획에는 본문 원문을 복사하지 않고, snapshot·receipt·잠금 파일도 생성하지 않는다.
3. 사용자 요청 범위에서 본문·보존 Evidence·보관 경로·내외부 참조 영향을 검토한다. 적용자는 검토자와
   달라야 한다. 발견한 다른 문서·task의 원본 경로 참조는 별도의 명시적 변경으로 먼저 정리하고 계획을
   다시 만든다. 정본에 남는 Frontmatter의 경로 참조도 차단 대상이며, 외부 소비자는 별도로 확인한다.
4. `recover-duplicate-bundle`에 같은 `--source`, `--target`, `--merged-body-file`과 계획의
   `--expected-source-revision`, `--expected-target-revision`, `--approved-plan-checksum`,
   `--actor`, `--reviewed-by`, `--request-ref`, `--security-receipt`를 전달한다. revision이 같아도
   파일·Evidence·본문·권한이 바뀌면 승인 계획과 불일치하므로 거부한다. 참조를 몰래 수정하지 않는다.
   일반 모드는 같은 타입의 `policy`, `guide`, `decision`, `spec`, `reference`, `report`만 통합하며,
   정본 ID·UUID·type·상태·도메인·기존 provenance를 유지하고 모든 원본 Evidence를 보존한다.
   정본 revision을 증가시키고 검증한 뒤 중복에 `merged`·정본 ID·archive 메타데이터를 기록하고
   revision을 증가시켜 원래 상대 경로를 보존한 `.archive/`로 이동한다. 전체 Validator와 검색 제외를
   확인한 후 receipt를 완료한다. 이 명령은 승격·재분류·발행·Commit·Push를 수행하지 않는다.
5. 통합을 앞의 Review 경로로 이미 완료했으면 미리보기와 적용 양쪽에 `--archive-only`를 지정한다.
   본문 파일이 현재 정본 본문과 정확히 같고, 중복의 모든 Evidence가 정본에 이미 포함돼야 한다.
   정본 bytes·revision은 그대로 두고 중복만 보관한다. `runbook`·`manual`도 반드시 기존 Review·Owner·
   Security 경로로 정본 통합을 완료한 뒤 이 모드를 사용하며, 일반 모드로 본문 통합을 우회하지 않는다.
   이 두 타입은 `approval.knowledge_owner`가 설정돼야 하며 `--reviewed-by`가 해당 Owner와 일치해야 한다.

적용 전 private snapshot과 journal을 `.runtime/bundle-recoveries/<transaction-id>/`에 보존하고,
원문 없는 처리 receipt는 `workspace/bundle-rebuilds/<transaction-id>.json`에 남긴다. 정상 반환의
`status: applied`만 적용 완료다. 적용·보관·검증·receipt 기록 실패 시 자동 원복하며 `rolled_back`,
다른 작업의 변경과 충돌하면 `partial_rollback`, 복원 자체가 실패하면 `rollback_failed`를 반환한다.
실패 상태를 완료로 표시하지 않는다.

프로세스 중단 또는 후속 명시 복구는
`rollback-duplicate-bundle-recovery --transaction <transaction-id> --actor <복구 담당자>`로 수행한다.
원래 bytes·경로·파일 권한을 복원하고 적용자와 별도로 rollback 담당자·시각·결과를 기록한다. 현재 파일이
이번 작업이 쓴 checksum·권한과 다르거나 다른 작업이 삭제했으면 덮어쓰거나 재생성하지 않는다.
보관 파일의 inode·device도 확인해 같은 내용의 타 작업 보관본을 삭제하지 않는다. snapshot·journal은
명시적 복구를 위해 남으며 제품이 자동 삭제하지 않는다. 백업이 없거나 변경 충돌이 있으면 수동 확인을
위해 snapshot 참조와 충돌 항목을 남긴다.

잠금은 이 전용 명령끼리의 동시 실행만 막는다. 기존 Curation·Publication과 외부 편집자는 같은 잠금을
사용하지 않으므로 적용·rollback 동안 동일 Bundle을 쓰는 다른 작업은 조율·중단해야 한다. checksum
재확인과 충돌 보존은 다른 모든 writer와의 원자적 compare-and-swap을 보장하지 않는다.

### Recovery Receipt

`workspace/bundle-rebuilds/`에는 사용자 요청 범위·담당자, 정본/원본의 ID·UUID·변경 전후 경로·상태·
revision·checksum, 원본별 고유 내용 처리 사유와 보존 Evidence ID, Review·Security 검증 근거,
참조 영향·확인 결과, archive 목록, 검증 명령·결과, 복구 snapshot 참조와 rollback 상태를 남긴다.
원문·PII·credential은 복사하지 않는다. 기존 중복 복구 검증은 제품 소스 회귀 테스트 및 신규 중복
방지 검증과 별개로 기록하며, 운영 설치본에서 실행하지 않았다면 기존 중복 정리 완료로 표시하지 않는다.

## Output

- 적용 결과
- 생성·갱신·archive된 Bundle 목록, 보존된 ID·UUID·Evidence 관계, Validator 결과와 복구 조건
- `workspace/bundle-rebuilds/`의 사용자 요청 기반 receipt

## Failure State

Evidence·revision·Review·Security Gate가 충족되지 않으면 Bundle을 변경하지 않는다. 적용 또는 검증에 실패하면 archive 이동과 새·변경 Bundle을 원복 가능한 범위에서 원복하고, receipt에 실패 원인과 다음 안전한 행동을 기록한다.

## Prohibited

- 사용자 요청 없이 Bundle 시리즈를 탐지·통합·archive
- 날짜 또는 파일명 관례만으로 Bundle을 같은 시리즈로 추정
- 결과 Bundle 검증 전에 원본 Bundle을 archive·삭제
- Evidence 원문·PII·credential을 계획·receipt·알림에 복사
