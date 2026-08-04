# Knowledge Curation Profile

## Trigger

Evidence를 기존 Bundle과 비교하거나 신규 Draft를 작성한다.

## Input

- 검증 가능한 Evidence
- 관련 active·draft Bundle 후보
- 새 Bundle domain 또는 Evidence provider를 처음 사용하는 경우 `knowledge/README.md`

## Applicable Global Rules

- Evidence 참조·가용성·불변성·Curation Queue: RB-EVD-003·014~016·023
- 민감정보·발행: RB-SEC-001·005·009, RB-PUB-001~010, RB-CUR-001~008

## Allowed Actions

- 중복·충돌·관련성 분석
- 비변경 정제 제안
- 신규 Draft 생성 또는 revision 조건부 갱신

## Checks

- 출처 권위·최신성·적용 범위
- 의미 중복과 상충
- Outcome 일반화 가능성
- 후보 Bundle의 `status`, Owner, review 요청 상태
- 새 domain·provider를 사용하거나 그 의미를 판단할 때 `knowledge/README.md`의 운영 목록
- Bundle을 만들거나 기존 Bundle의 `id`·파일명 관계를 판단할 때 `OPERATING_RULES.md`의 RB-KNW-026 Bundle Identity Contract
- 여러 단계 정제 작업에서 독립·제한된 조사 또는 검증 작업을 위임할 수 있는지와, 위임해도 Owner 승인·Security Gate·최종 책임이 유지되는지
- 후보의 제목·요약과 Evidence 제목·intended use 간 의미 관련성, 그리고 적합한 Bundle type
- Bundle 태그는 구조 태그(`bundles`, Bundle type, domain)만으로 끝내지 않는다. Evidence·제목·요약·본문에서 확인한 (1) 핵심 주제·개념, (2) 적용 대상 또는 업무 영역, (3) 주요 행위·산출물·결정 특성 중 해당하는 것을 태그로 함께 사용해, 태그만으로도 문서의 성격을 빠르게 파악할 수 있게 한다. 서로 중복하거나 근거가 약한 태그를 채우기 위해 만들지 않으며, 원문에 없는 사실·민감정보·자격증명을 태그로 만들지 않는다. 태그의 표기 언어는 원문 표현을 따르며, 한글 개념·용어를 별도로 영어로 번역한 태그를 추가로 만들지 않는다.
- Evidence 본문·excerpt·생성할 Bundle 내용을 읽을 때 RB-SEC-001·005의 민감정보와 PII Receipt를 다시 확인

## Gates

- 원본 접근 가능성
- Evidence 참조와 source UUID
- 기존 Bundle 갱신 시 expected revision 일치
- Bundle 생성·갱신의 파일명과 Frontmatter `id`가 RB-KNW-026 canonical 형식에 맞을 것. legacy 형식의 일괄 정규화는 Publication Profile의 검토·발행 Gate로 넘길 것
- `runbook`·`manual` Review 또는 직접 생성 가능 유형의 자동 Promotion Gate를 수행할 실행 주체 존재
- RB-SEC-001·005와 RB-PUB-002의 보안 Gate. Draft와 active 전환의 차이는 RB-CUR-006을 적용
- `runbook`과 `manual`은 `knowledge/curation-reviews/`의 checksum 결합 Review 카드 존재. `policy`, `guide`, `decision`, `spec`, `reference`, `report`는 확정된 Evidence를 입력으로 Draft 직접 생성 가능
- `runbook`과 `manual`의 Review는 사용자 또는 검증 Agent의 별도 검증 시도·주체·시각·Evidence checksum·결과 기록. 운영 Agent는 이 두 유형 외에는 Review 카드를 만들지 않으며, 직접 생성 가능한 유형의 Review는 Runtime이 기록한 사용자의 명시 요청 식별자가 있을 때만 예외적으로 가능. Review 카드 생성 뒤 Curator는 현재 대화에서 승인 선택지를 묻지 않고 `knowledge/curation-reviews/` Queue에 handoff. 직접 생성 가능한 유형은 RB-CUR-006의 확정된 Evidence·참조 무결성·전체 Validator Gate를 통과하면 별도 사람 Review 없이 자동 active 전환 가능하며, 자동 Gate 실패는 Review가 아니라 재시도 차단 상태로 남긴다. Curation은 Evidence 생성 시 끝난 PII Scan이나 민감도 판단을 재실행하지 않음
- active Runbook은 사람이 읽는 비어 있지 않은 `## Workflow Summary` 본문 section과 `extensions.workflow` 실행 정의를 함께 가질 것

## Output

정제 제안 또는 Evidence를 참조하는 Draft Bundle. `no_bundle`은 결정 Receipt를 남겨 자동 종결한다. `update_existing`는 대상 Bundle 본문 전체를 교체하는 일반 `body`가 아니라, 대상 본문 checksum과 함께 `update_mode`를 명시한다. `append`의 `body`는 추가분이며 Runtime이 기존 본문을 보존해 병합한다. `replace_full`의 `body`만 전체 신규 본문이며 교체 사유와 사용자·검토 경로가 필수다. 자동 갱신은 `append`만 허용한다. `runbook`·`manual`을 제외한 기존 Bundle의 갱신은 후보의 `type`·도메인·태그·Evidence 참조 Frontmatter가 제안과 맞고 현재 Evidence가 대상의 최신 Evidence보다 같거나 최신일 때 Evidence·Security·Validator·revision Gate 및 자동 갱신 Receipt를 통과하면 자동 적용한다. 일치 후보가 없으면 신규 Bundle로 생성한다. `runbook`·`manual`의 `update_existing`처럼 승인이 필요한 제안은 Review Queue handoff 결과를 반환한다. 그 외 Review handoff는 사용자의 명시 요청 식별자가 있는 경우에만 가능하다. Curator는 대화형 승인 선택지를 만들지 않는다. 제안은 `suggested_bundle_type`을 힌트로 제공하되 Curator가
원문을 검토해 `no_bundle` 또는 전체 Bundle 타입(`policy`, `guide`, `runbook`, `manual`, `decision`,
`spec`, `reference`, `report`) 중 적절한 결과를 선택한다. 시점 기준 현황·평가·주기 보고는 `report`,
제품·시스템 사용 절차는 `manual`, 반복 운영·장애 대응 절차는 `runbook`으로 구분한다. Business Rulebook은
`guide`와 `extensions.rulebook`으로 표현한다. Owner가 없는 Draft 후보는
`assign_owner_and_review_draft`와 차단 조건을 반환한다.

Evidence 정제 결과와 Curation Queue 소비는 RB-EVD-003·023을 적용한다. Queue 재처리 시에는 같은 Evidence의 미완료 Review 카드를 먼저 재사용하고, 카드가 없을 때만 새 UUID 카드를 만든다. Curator가 Review 카드를 만들면 해당 카드가
검토 handoff를 표현한다. Review 카드는 Evidence ID·상대
경로·checksum·제목·수집 목적·intended use의 안전한 snapshot을 보존하며, 실제 Evidence 링크를 기준으로 검토한다. 신규 Draft 승인 또는
`no_bundle` 결정으로 작업을 소비하면 카드를 숨김 archive로 이동해 기본 목록에서는 제거하되 결정 receipt는 보존한다. `runbook`·`manual`의 `update_existing` 승인 카드는
전용 적용 전까지 `approved`로 유지하고, 적용 직전 checksum·대상 revision을 다시 확인한다. 적용되면 최초 생성 Review를 유지한 채
`extensions.curation.review_receipts`에 보완 이력을 누적하고 카드를 archive한다.
Evidence 원문은 카드에 복사하지 않는다. stale 카드는 RB-CUR-004에 따라 archive하고 다시 큐잉한다. Adapter 실패는
RB-CUR-010에 따라 Review 또는 `no_bundle` 결론으로 만들지 않는다. 큐 이상은 `refresh-curation-queue`로 복구한다.

## Failure State

Curation 실행 실패는 Curation Queue 항목과 시도 Receipt를 유지한다. 성공한 분석에서 상충·근거 부족·Owner 부재를
판단한 경우에만 Review 카드를 생성한다.
민감정보 문제는 실제 값을 복사하지 않고 범주·영향 경로·필요한 보안 검토만 기록한다.

## Prohibited

- `runbook`·`manual`을 checksum 결합 Review와 별도 검증 시도 없이 active 승격하거나, 직접 생성 가능 유형을 RB-CUR-006 자동 Gate 없이 active 승격
- `create-bundle`, 일반 revision API 또는 Frontmatter 직접 변경으로 `draft -> active` 전환
- 테스트·가상 데이터라는 이유로 Review가 필요한 유형 또는 active 전환의 Review 카드, 별도 검증 시도 기록, Security Receipt 또는 Validator 생략
- 한 번의 Outcome 자동 일반화
- RB-EVD-023을 위반하는 Evidence 변경
- Evidence의 평문 자격증명·PII를 Bundle·요약·제안·로그에 복사
- Scan Receipt 없이 마스킹 확인만으로 Evidence가 발행 가능하다고 판단
