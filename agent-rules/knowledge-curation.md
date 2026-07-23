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
- Evidence 본문·excerpt·생성할 Bundle 내용을 읽을 때 자격증명·PII 평문과 문맥상 재식별 가능성을 다시 확인
- Evidence PII Scan 증빙과 마스킹 상태가 실제 원문 checksum에 대응하는지 확인

## Gates

- 원본 접근 가능성
- Evidence 참조와 source UUID
- 기존 Bundle 갱신 시 expected revision 일치
- Review가 필요한 유형 또는 active 전환 후보를 정식 검토 대상으로 넘길 Owner 존재
- 마스킹 재확인과 Evidence PII Scan 증빙 통과; 증빙이 없거나 의심 값이 남으면 Draft 생성·revision 적용 차단
- `runbook`과 Manual 성격의 `guide`는 `knowledge/curation-reviews/`의 checksum 결합 Review 카드 존재. `policy`, `decision`, `spec`, `reference`는 Evidence·PII Gate 통과 후 Draft 직접 생성 가능
- Review가 필요한 유형은 생성 actor와 다른 Owner 또는 명시 위임 승인자의 승인 기록. 직접 생성 가능한 유형도 active 전환 전에는 동일한 Review를 추가로 생성·승인

## Output

정제 제안 또는 Evidence 역참조가 연결된 Draft Bundle. 제안은 `suggested_bundle_type`을 힌트로 제공하되 Curator가
원문을 검토해 `no_bundle`, `guide`, `decision`, `runbook` 중 적절한 결과를 선택한다. Business Rulebook은
`guide`와 `extensions.rulebook`으로 표현한다. Owner가 없는 Draft 후보는
`assign_owner_and_review_draft`와 차단 조건을 반환한다.

## Failure State

Evidence를 `needs_review`로 유지하고 상충·근거 부족·Owner 부재를 기록한다. 민감정보 문제는 실제 값을 복사하지 않고
범주·영향 경로·필요한 보안 검토만 기록한다.

## Prohibited

- 검토 없이 active 승격
- `create-bundle`, 일반 revision API 또는 Frontmatter 직접 변경으로 `draft -> active` 전환
- 테스트·가상 데이터라는 이유로 Review가 필요한 유형 또는 active 전환의 Review 카드, 독립 승인, Security Receipt 또는 Validator 생략
- 한 번의 Outcome 자동 일반화
- Evidence 원문 변경
- Evidence의 평문 자격증명·PII를 Bundle·요약·제안·로그에 복사
- Scan Receipt 없이 마스킹 확인만으로 Evidence가 발행 가능하다고 판단
