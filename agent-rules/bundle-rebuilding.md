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
