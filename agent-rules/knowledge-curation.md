# Knowledge Curation Profile

## Trigger

Evidence를 기존 Bundle과 비교하거나 신규 Draft를 작성한다.

## Input

- 검증 가능한 Evidence
- 관련 active·draft Bundle 후보

## Allowed Actions

- 중복·충돌·관련성 분석
- 비변경 정제 제안
- 신규 Draft 생성 또는 revision 조건부 갱신

## Checks

- 출처 권위·최신성·적용 범위
- 의미 중복과 상충
- Outcome 일반화 가능성
- 후보 Bundle의 `status`, Owner, review 요청 상태
- 후보의 제목·요약과 Evidence 제목·intended use 간 의미 관련성, 그리고 적합한 Bundle type

## Gates

- 원본 접근 가능성
- Evidence 참조와 source UUID
- 기존 Bundle 갱신 시 expected revision 일치
- Draft 후보를 정식 검토 대상으로 넘길 Owner 존재

## Output

정제 제안 또는 Evidence 역참조가 연결된 Draft Bundle. 제안은 `suggested_bundle_type`을 힌트로 제공하되 Curator가
원문을 검토해 `no_bundle`, `guide`, `decision`, `runbook` 중 적절한 결과를 선택한다. Business Rulebook은
`guide`와 `extensions.rulebook`으로 표현한다. Owner가 없는 Draft 후보는
`assign_owner_and_review_draft`와 차단 조건을 반환한다.

## Failure State

Evidence를 `needs_review`로 유지하고 상충·근거 부족·Owner 부재를 기록한다.

## Prohibited

- 검토 없이 active 승격
- 한 번의 Outcome 자동 일반화
- Evidence 원문 변경
