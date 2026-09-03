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
- 자동 Curation 또는 자동 처리 목적의 수동 Curation은 Bundle 생성·갱신 전에 반드시 `propose-update`를 실행한다. Runtime의 `reconcile-curation`은 이를 내부 선행 단계로 수행하며, 직접 `create-bundle`·revision 명령으로 이 단계를 대체하지 않는다. 명시적 수동 복구·관리 작업은 예외로 하되, 실행 사유와 적용한 기존 Gate를 기록한다.
- 설치본 `.circled-wiki/curation-taxonomy.yaml`의 `routing_rules`를 분류 기준으로 먼저 읽는다. 기존 Bundle 후보 탐색·의미 관련성·Review·Security Gate는 계속 적용하며, 적합한 기존 Bundle이 없고 단일 일치 rule의 `auto_create: true`일 때만 해당 rule의 domain/type으로 신규 Draft를 자동 생성하고 RB-NOTIFY-001 형식의 사용자 알림을 Bundle Curation 이력과 결과에 남긴다.
- proposal의 `routing_hints`는 설치별 taxonomy 정책 힌트이고, `suggested_bundle_type`은 Evidence 기반의 비구속적 휴리스틱이다. `candidate_bundles`는 키워드·Frontmatter 기반 탐색 후보이므로 빈 목록도 기존 Bundle 부재의 증거가 아니다. 자동 신규 Draft 검토 권한은 `creation_authorized`만 표현하며, 이것도 의미 검증·Security·Review·Publication Gate를 대체하지 않는다.
- `curation-taxonomy.yaml`이 없으면 관련 기존 Bundle의 domain·type·제목·태그·경로를 읽기 전용으로 조사해 taxonomy 초안을 사용자에게 제시한다. Agent는 Bundle 구조만으로 분류 관례를 확정하거나 파일을 자동 생성하지 않으며, 사용자 승인 뒤에만 설치별 파일을 만든다.
- Bundle 태그는 구조 태그(`bundles`, Bundle type, domain)만으로 끝내지 않는다. Evidence·제목·요약·본문에서 확인한 (1) 핵심 주제·개념, (2) 적용 대상 또는 업무 영역, (3) 주요 행위·산출물·결정 특성 중 해당하는 것을 태그로 함께 사용해, 태그만으로도 문서의 성격을 빠르게 파악할 수 있게 한다. 서로 중복하거나 근거가 약한 태그를 채우기 위해 만들지 않으며, 원문에 없는 사실·민감정보·자격증명을 태그로 만들지 않는다. 태그의 표기 언어는 원문 표현을 따르며, 한글 개념·용어를 별도로 영어로 번역한 태그를 추가로 만들지 않는다.
- 신규 `manual`과 `runbook` CurationOutput은 Evidence 본문의 주제·업무를 확인해 생성한, 안전한 ASCII `slug`를 반드시 명시한다. 기존 Bundle 갱신에는 새 slug를 요구하지 않는다. 한글 제목을 기계적으로 변환하거나 checksum을 식별자로 쓰지 않는다. 생성된 slug는 Review 카드의 Proposed identifier에서 검토한다. 신규 manual은 `bundles/<domain>/manuals/`, runbook은 `bundles/<domain>/runbooks/`에 둔다.
- Evidence 본문·excerpt·생성할 Bundle 내용을 읽을 때 활성 하드 PII와 `agent_mask_categories`에 따라 마스킹된 값을 복사하지 않고, 확정된 Data Protection Receipt와 Evidence checksum의 결합만 확인한다. 계약·법률 자문·분쟁·소송·규제 대응과 그 결정은 이 마스킹 규칙만으로 제한하지 않는다. `agent_mask_categories`에 선언되지 않은 업무 연락처는 승인된 내부 운영 기록에 필요한 경우 보존할 수 있으며 외부 발행에는 Publication Gate를 적용한다.

## Gates

- 원본 접근 가능성
- Evidence 참조와 source UUID
- 기존 Bundle 갱신 시 expected revision 일치
- taxonomy 개선의 영향 Bundle 목록은 자동으로 생성·사용자에게 알릴 수 있다. 그러나 기존 Bundle의 domain·type·경로 재분류는 사용자가 해당 알림을 확인한 뒤 명시적으로 요청할 때만 `propose-bundle-reclassification`으로 이전·새 경로와 revision을 확인한다. 실제 이동은 사용자 요청을 actor·rationale으로 기록한 `apply-bundle-reclassification`만 사용하며, 자동 Curation은 수행하지 않는다.
- Bundle 생성·갱신의 파일명과 Frontmatter `id`가 RB-KNW-026 canonical 형식에 맞을 것. legacy 형식의 일괄 정규화는 Publication Profile의 검토·발행 Gate로 넘길 것
- `runbook`·`manual` Review 또는 직접 생성 가능 유형의 자동 Promotion Gate를 수행할 실행 주체 존재
- RB-SEC-001·005와 RB-PUB-002의 보안 Gate. Draft와 active 전환의 차이는 RB-CUR-006을 적용
- `runbook`과 `manual`은 `knowledge/curation-reviews/`의 checksum 결합 Review 카드 존재. `policy`, `guide`, `decision`, `spec`, `reference`, `report`는 확정된 Evidence를 입력으로 Draft 직접 생성 가능
- Curation Review·자동 갱신의 유형별 경로와 Gate는 RB-CUR-001~006을 따른다. Curator는 현재 대화에서 승인 선택지를 묻지 않고 Review handoff 또는 재시도 차단 결과를 반환한다
- active Runbook은 사람이 읽는 비어 있지 않은 `## Workflow Summary` 본문 section과 `extensions.workflow` 실행 정의를 함께 가질 것
- Curation Queue 완료 후 상태를 공유할 때는 원본 Queue 파일 삭제만 포함한다. Bundle 또는 Curation
  Review 카드가 결과와 결정을 보존하며, 새 reconciliation task Archive 파일을 만들지 않는다.
  `verify-curation-commit` Gate를 통과시킨다.

## Output

정제 제안 또는 Evidence를 참조하는 Draft Bundle. `no_bundle`은 추가 기록 없이 자동 종결한다. `update_existing`는 대상 본문 checksum과 `update_mode`를 기록한다. `append`의 `body`는 추가분이며 Runtime이 기존 본문을 보존해 병합한다. `replace_full`의 `body`는 전체 신규 본문이며 교체 사유와 Review 경로가 필수다. 후보 선택·자동 갱신·Review handoff의 조건은 RB-CUR-004를 따른다. 제안은 `suggested_bundle_type`을 힌트로 제공하되 Curator가
원문을 검토해 `no_bundle` 또는 전체 Bundle 타입(`policy`, `guide`, `runbook`, `manual`, `decision`,
`spec`, `reference`, `report`) 중 적절한 결과를 선택한다. 시점 기준 현황·평가·주기 보고는 `report`,
제품·시스템 사용 절차는 `manual`, 반복 운영·장애 대응 절차는 `runbook`으로 구분한다. Business Rulebook은
`guide`와 `extensions.rulebook`으로 표현한다. Owner가 없는 Draft 후보는
`assign_owner_and_review_draft`와 차단 조건을 반환한다.

Evidence 정제 결과와 Curation Queue 소비는 RB-EVD-003·023을 적용한다. Queue 재처리 시에는 같은 Evidence의 미완료 Review 카드를 먼저 재사용하고, 카드가 없을 때만 새 UUID 카드를 만든다. Curator가 Review 카드를 만들면 해당 카드가
검토 handoff를 표현한다. Review 카드는 Evidence ID·상대
경로·checksum·제목·수집 목적·intended use의 안전한 snapshot을 보존하며, 실제 Evidence 링크를 기준으로 검토한다. 신규 Draft 승인 또는
`no_bundle` 결정으로 작업을 소비하면 카드를 삭제한다. `runbook`·`manual`의 `update_existing` 승인 카드는
전용 적용 전까지 `approved`로 유지하고, 적용 직전 checksum·대상 revision을 다시 확인한다. 적용되면 필요한 Bundle provenance를 갱신하고 카드를 삭제한다.
Evidence 원문은 카드에 복사하지 않는다. stale 카드는 RB-CUR-004에 따라 archive하고 다시 큐잉한다. Adapter 실패는
RB-CUR-010에 따라 Review 또는 `no_bundle` 결론으로 만들지 않는다. 큐 이상은 `refresh-curation-queue`로 복구한다.
완료 기록을 Commit할 때 Archive 전환 Gate가 실패하면 Queue 기록을 되돌리지 않고 두 경로를 명시적으로
staging한 뒤 재시도한다.

## Failure State

Curation 실행 실패는 Curation Queue 항목과 시도 Receipt를 유지한다. `runbook`·`manual` 또는 사용자가 명시적으로 요청한 Review만 카드를 생성하며, 그 밖의 미해결 분석은 재시도 차단으로 남긴다.
민감정보 문제는 실제 값을 복사하지 않고 범주·영향 경로·필요한 보안 검토만 기록한다.

## Prohibited

- `runbook`·`manual`을 checksum 결합 Review와 별도 검증 시도 없이 active 승격하거나, 직접 생성 가능 유형을 RB-CUR-006 자동 Gate 없이 active 승격
- `create-bundle`, 일반 revision API 또는 Frontmatter 직접 변경으로 `draft -> active` 전환
- 테스트·가상 데이터라는 이유로 Review가 필요한 유형 또는 active 전환의 Review 카드, 별도 검증 시도 기록, Security Receipt 또는 Validator 생략
- 한 번의 Outcome 자동 일반화
- RB-EVD-023을 위반하는 Evidence 변경
- Evidence의 평문 자격증명·활성 하드 PII·`agent_mask_categories` 마스킹 전 값을 Bundle·요약·제안·로그에 복사
- Scan Receipt 없이 마스킹 확인만으로 Evidence가 발행 가능하다고 판단
