# Knowledge MCP 설계

## 1. 목적

Knowledge MCP는 여러 AI Agent가 공통으로 사용하는 외부 인터페이스다. Hermes는 지식 라이브러리 운영 중과 사용자 요청 처리 중 Knowledge Service를 직접 이용할 수 있으며, 하위·외부 AI Agent에는 MCP 또는 CLI를 통해 라이브러리를 이용하게 하는 대표 오케스트레이터다.

## 2. 설계 원칙

- 내부 저장소 구조를 숨긴다.
- Bundle 중심으로 지식을 제공한다.
- Evidence는 필요 시 참조 정보로만 노출한다.
- Tool 이름은 명확하고 안정적으로 유지한다.
- 쓰기 전 검증은 `표준 규칙`과 `프로파일 규칙`을 함께 통과해야 한다.
- 기본 `read_only` 모드는 조회·검증 Tool만 노출하고, 명시적 `operator` 모드만 Task·Outcome·발행 Tool을 노출한다.
- MVP `operator`는 Hermes 또는 Hermes가 작업 범위·기간을 한정해 위임한 내부 Agent 실행 컨텍스트에만 사용하며 정식 사용자 인증을 대체하지 않는다.

## 3. 권장 Tool 목록

- `search_knowledge`
- `prepare_context`
- `read_bundle`
- `propose_update`
- `propose_pending`
- `ingest_evidence`
- `capture_conversation`
- `capture_document`
- `capture_file`
- `inspect_inbox`
- `review_inbox_sensitivity`
- `accept_inbox`
- `ingest_accepted`
- `create_draft_bundle`
- `apply_bundle_revision`
- `validate_result`
- `publish_changes`
- `find_workflow`
- `prepare_task`
- `prepare_runbook_refresh`
- `submit_runbook_reference`
- `record_reference_assessment`
- `confirm_runbook_revision`
- `audit_knowledge`
- `list_knowledge_inventory`
- `validate_claim_support`
- `measure_runbook_effectiveness`
- `get_task`
- `update_task_inputs`
- `record_task_step`
- `record_refresh_decision`
- `record_outcome`

## 4. Tool 개요

### search_knowledge

- 목적: 질의 기반 지식 탐색
- 입력: query, filters, domain
- 출력: Bundle 중심 결과 목록
- 구현: MCP 서버는 OS별 검색 명령을 직접 실행하지 않고 Knowledge Service의 `search_knowledge`를 호출한다.
- 검색 fallback: OS별 명령 선택은 Knowledge Service/Core가 담당한다.

### prepare_context

- 목적: 특정 작업에 필요한 문맥 패키지 생성
- 입력: task_description, bundle_ids, constraints
- 출력: 정리된 Context Package

### read_bundle

- 목적: 특정 Bundle 전문 조회
- 입력: bundle_id
- 출력: Frontmatter + 본문

### propose_update

- 목적: Evidence 또는 변경 요청 기반 수정안 생성
- 입력: evidence_id 또는 change_request
- 출력: 수정안과 근거

### propose_pending

- 목적: 아직 정제 제안을 만들지 않은 non-restricted Evidence를 읽기 전용 Batch로 평가
- 변경: 없음. 공식 Bundle을 자동 생성하거나 수정하지 않는다.

### capture_conversation / capture_document / capture_file

- 목적: Agent 대화, 외부 문서, 바이너리 원본을 provider별 pending Inbox Item으로 적재
- 변경: `knowledge/inbox/<provider>/`만 변경하며 Evidence 변환이나 정제를 함께 수행하지 않는다.
- `capture_file` payload는 base64로 전달하고 파일명·경로·idempotency를 검증한다.

### inspect_inbox / review_inbox_sensitivity / accept_inbox / ingest_accepted

- `inspect_inbox`: pending 항목의 checksum·경로·필수 메타데이터·민감정보 Gate를 읽기 전용 검사
- `review_inbox_sensitivity`: 식별된 사람의 민감정보 검토 결정을 기록
- `accept_inbox`: inspector actor와 함께 검사 통과 항목을 accepted로 전환
- `ingest_accepted`: accepted 항목만 Evidence로 변환하며 정제는 수행하지 않음

### ingest_evidence

- 목적: 사용자·지정 Batch·Hermes가 `knowledge/inbox/`에 적재한 원본을 Evidence로 보존
- 입력: inbox_path, provider, why_collected, intended_use, 선택적 idempotency_key
- `inbox_path`는 inbox 상대경로만 허용한다.
- 동일 provider·idempotency_key·checksum 재실행은 기존 Evidence를 반환하고, checksum이 다르면 충돌로 중단한다.

### create_draft_bundle

- 목적: 기존 Evidence 한 건을 근거로 `policy`, `decision`, `spec`, `reference` 신규 Draft Bundle 생성
- `guide`(Manual 성격 문서 포함)와 `runbook`은 이 API로 생성하지 않고 checksum 결합 Curation Review·독립 Owner 승인 경로를 사용한다.
- 이 API와 일반 revision API는 `active` 상태 전환 권한을 갖지 않는다.
- 경로 segment를 제한하고 Evidence 역참조를 함께 기록한다.

### apply_bundle_revision

- 목적: 기존 Bundle의 검증된 revision 적용
- 입력: bundle_id, expected_revision, 전체 frontmatter, body, actor
- id, bundle_uuid, type은 변경할 수 없다.
- revision 불일치, Restricted 참조, Validator 실패를 거부하며 Bundle과 Evidence 역참조를 원복한다.

### validate_result

- 목적: Agent 생성 결과를 Knowledge 기준으로 검증
- 입력: draft_content, related_bundle_ids
- 출력: 적합성, 누락, 충돌, 표준 위반, 프로파일 위반

### publish_changes

- 목적: 검증을 통과한 변경 반영
- 입력: patch_set 또는 bundle_update
- 출력: 반영 결과와 Commit 정보

### find_workflow

- 목적: 사용자 요청에 맞는 활성 실행 Runbook 탐색
- 입력: request, limit
- 출력: Workflow ID, Bundle ID, 실행 모드, 매칭 점수, `freshness`, `stale` 상태

### prepare_task

- 목적: Runbook 정의를 런타임 Task로 스냅샷하고 필수 입력을 확인
- Runbook이 만료됐으면 원래 업무 Task 대신 `runbook_refresh` Task를 생성한다.
- 입력: workflow_id, request, inputs
- 출력: Task 상태, missing_inputs, Workflow Context
- 저장: Git 지식 저장소 밖의 `.runtime/tasks/`

### prepare_runbook_refresh

- 목적: 사용자의 최신화 확인 요청 또는 변경 이벤트로 Runbook Refresh Task를 즉시 생성
- 입력: workflow_id, request, requested_by, reason
- reason: `expired`, `user_requested`, `user_reference`, `owner_requested`, `source_change`, `outcome_signal`, `security_or_compliance`
- 출력: 표준 Refresh 단계, Owner 승인 지점, 대상 Runbook Context
- 유효기간이 남아 있어도 호출할 수 있다.

### submit_runbook_reference

- 목적: 사용자가 제공한 Evidence를 Runbook 개선 후보로 제출
- 입력: workflow_id, evidence_id, submitted_by, note
- 출력: 중복 제거된 Refresh Task, Candidate Evidence, 적용 범위 정렬 상태
- 열린 동일 Runbook Refresh Task가 있으면 새 Task를 만들지 않고 후보와 제출 이력을 병합한다.
- 제출은 채택을 의미하지 않으며 `record_refresh_decision`, 독립 검증, Owner 승인이 뒤따라야 한다.

### record_reference_assessment

- 목적: Candidate Evidence의 권위·최신성·적용 범위·교차 검증·충돌·채택 판정 기록
- 입력: task_id, evidence_id, assessment fields, assessed_by, verified_by
- 평가자와 검증자는 달라야 하며 결과는 Runtime Task에 저장한다.
- Candidate Evidence가 있는 Refresh는 모든 후보 평가 전 `record_refresh_decision`을 완료할 수 없다.

### confirm_runbook_revision

- 목적: Refresh 종료 전 공식 Runbook Markdown의 revision 증가와 검증 통과 확인
- 입력: task_id, revision_ref
- `knowledge_revision`, `reviewed_at`, `review_due_at` 갱신과 Repository Validator 통과를 요구한다.
- 확인 전 `publish-revision` Step 완료를 차단한다.

### audit_knowledge

- 목적: Bundle·Evidence·역참조·최신성·Inquiry·열린 Task의 읽기 전용 품질 감사
- 출력: severity와 code를 가진 이슈, 요약, Archive 후보
- Audit 결과는 파생 데이터이며 공식 지식을 직접 변경하지 않는다.

### list_knowledge_inventory

- 목적: Frontmatter 기반 지식 현황 조회
- 필터: domain, document_type, status, owner, freshness_state
- 수동 Inventory 문서를 생성하지 않는다.

### validate_claim_support

- 목적: 중요한 Agent 주장에 대한 `verified`, `limited`, `inferred`, `needs_review` 계약 검사
- `verified`는 접근 가능한 Evidence Record와 Evidence Original을 요구한다.
- 구조·참조·원본 무결성만 검사하며 Evidence가 Claim을 의미적으로 입증하는지는 판정하지 않는다.

### measure_runbook_effectiveness

- 목적: Workflow Outcome을 `knowledge_revision`별로 집계해 변경 전후 비교 기반 제공
- 출력: 완료·실패·검토 필요·피드백 건수, 완료율과 비교 가능 여부
- 표본이 없는 revision 간 효과를 추정하거나 개선 인과관계로 단정하지 않는다.

### get_task

- 목적: 현재 Task 상태 조회
- 입력: task_id
- 출력: Workflow revision, 입력, 단계, 승인 지점, 완료 기준, 상태

### update_task_inputs

- 목적: 기존 Task를 유지하면서 누락 입력 보완
- 입력: task_id, inputs
- 출력: 갱신된 inputs, missing_inputs, Task 상태

### record_task_step

- 목적: 단계별 실행 결과와 사람 승인 기록
- 입력: task_id, step_id, status, result, actor
- 출력: 단계 상태와 전체 Task 상태
- Workflow 순서와 approval step 종류를 Core가 검증한다.

### record_refresh_decision

- 목적: 최신 Evidence 비교 결과를 강제 변경 없이 구조화해 기록
- 입력: task_id, decision, rationale, evidence_ids, actor
- decision: `update_required`, `no_change`, `insufficient_evidence`
- `insufficient_evidence`는 Task를 `needs_review`로 중단한다.
- `independent-agent-review` actor는 decision actor와 달라야 한다.

### record_outcome

- 목적: 완료·실패·검토 필요 결과를 Outcome Inbox Item으로 수집해 검사·승인 흐름으로 환류
- 입력: task_id, status, summary, feedback, learnings, artifacts, decisions, action_items, open_questions
- 출력: Intake ID, Inbox Item 경로, Runbook Bundle ID, 다음 검사 작업
- 동일 Runtime Task 재호출은 기존 Outcome Inbox Item을 재사용하고, 이미 변환된 경우 연결된 Outcome Evidence를 반환한다.

Workflow Tool의 전체 계약은 [16-workflow-execution.md](16-workflow-execution.md)를 따른다.

## 5. 보안 및 통제

- MVP 쓰기 작업은 승인 없이 `표준 규칙`과 `프로파일 규칙` 검증을 통과하면 자동 Commit한다.
- 민감 문서는 MCP 단계에서 필터링할 수 있어야 한다.
- Agent별 권한 범위를 분리할 수 있어야 한다.

## 6. 출력 원칙

- 항상 출처를 유지하고 중요 주장은 Claim Support 계약으로 가용성과 지원 상태를 검사한다.
- confidence 또는 검증 상태를 포함할 수 있다.
- `extensions.review_requested`가 `true`인 Bundle을 사용할 때는 그 사실을 함께 표시한다.
- 추정과 사실을 구분할 수 있게 설계한다.
