# Knowledge Service 설계

## 1. 목적

Knowledge Service는 저장소, 검증기, 검색 계층을 감싸는 내부 SDK이자 도메인 서비스다.

## 2. 설계 목표

- MCP와 저장소 구현을 분리한다.
- Git/Markdown/기본 검색 연동을 한 곳에서 관리한다.
- 테스트 가능한 순수 도메인 인터페이스를 제공한다.

## 3. 주요 기능

- Bundle 읽기/쓰기
- Evidence 조회
- 검색 통합
- Context Package 생성
- OKF 검증
- 인덱스 갱신 트리거

## 4. 권장 API

```text
search_knowledge(query, filters)
prepare_context(task, references)
read_bundle(bundle_id)
propose_update(evidence_id)
ingest_evidence(inbox_path, provider, capture_context, idempotency_key)
create_draft_bundle(bundle_fields, evidence_id, actor)
apply_bundle_revision(bundle_id, expected_revision, frontmatter, body, actor)
validate_okf(bundle_document)
rebuild_indexes(scope)
find_workflow(request, limit)
prepare_task(workflow_id, request, inputs)
prepare_runbook_refresh(workflow_id, request, requested_by, reason)
submit_runbook_reference(workflow_id, evidence_id, submitted_by, note)
record_reference_assessment(task_id, evidence_id, assessment)
confirm_runbook_revision(task_id, revision_ref)
audit_knowledge()
list_knowledge_inventory(filters)
validate_claim_support(claims)
measure_runbook_effectiveness(workflow_id)
get_task(task_id)
record_refresh_decision(task_id, decision, rationale, evidence_ids, actor)
record_outcome(task_id, outcome)
```

Workflow API는 공식 Runbook 정의와 실행 중 Task 상태를 분리한다. Runbook은 Git의
`knowledge/bundles/<domain>/runbooks/`에,
Task는 `.runtime/tasks/`에 저장하며 종료 결과만 Evidence로 지식 파이프라인에 다시 넣는다. 상세 계약은
[16-workflow-execution.md](16-workflow-execution.md)를 따른다.

## 5. 내부 모듈

### Repository Adapter

- 파일 시스템/Git 접근
- Bundle/Evidence 로드

### Parser

- Markdown + YAML Frontmatter 파싱
- URI 및 스키마 검증

### Validator

- OKF 규칙 검증
- 조직 정책 검증
- Example Organization OKF Profile 검증

### Search Orchestrator

- 파일 기반 키워드 검색
- Frontmatter 필터 검색
- Markdown 링크와 backlink 확장
- Evidence Record 검색

MVP 범위를 벗어나는 검색 확장은 `docs/13-future-work.md`에서만 관리한다.

MVP 검색 실행 정책:

- MCP와 CLI는 직접 OS별 검색 명령을 선택하지 않고 `search_knowledge`를 호출한다.
- Search Orchestrator가 OS와 사용 가능한 명령을 감지한다.
- 1순위는 모든 OS에서 `rg`다.
- `rg`가 없으면 macOS/Linux는 `grep`, Windows는 PowerShell `Select-String`으로 fallback한다.
- 지식 검색 대상은 `knowledge/bundles/**/*.md`, `knowledge/evidence/**/*.md`다. `.knowledge-os/`의 template·schema·system policy는 실행 규약과 검증 자산이며 조직 지식 검색 결과에 포함하지 않는다.
- `knowledge/evidence/`의 비Markdown 원본 파일은 검색 대상에서 제외하고, 같은 basename의 `.md` manifest만 검색한다.
- OS 명령 결과는 Core에서 공통 결과 형식으로 정규화한다.

### Context Builder

- 작업 목적별 문서 묶음 생성
- 중복 제거
- Evidence 링크 유지

## 6. 응답 원칙

- 검색 결과는 출처(Bundle/Evidence)를 포함한다. `available` Evidence를 검증하거나 확정 근거로 사용할 때는 원본 존재와 SHA-256 일치를 재확인한다.
- `extensions.review_requested`가 `true`인 Bundle을 결과에 포함할 때는 그 사실을 항상 표시한다.
- `validate_claim_support`는 Claim/Evidence 계약과 Evidence 무결성을 검사하며, Claim의 의미가 Evidence에서 실제로 도출되는지는 판정하지 않는다.
- Context Package는 너무 크지 않게 요약 가능해야 한다.
- 검증 실패는 명시적 오류로 반환한다.
- 검증 오류는 `표준 위반`과 `프로파일 위반`을 구분해 반환한다.

## 7. 구현 언어 제안

- Python 우선
- 이유: 파서, MCP 연동, 데이터 처리, 검색 SDK 호환성이 좋음

## 8. 테스트 전략

- 파싱 테스트
- Validator 테스트
- 저장소 경로 규칙 테스트
- 검색 결과 병합 테스트
- Context Builder 결정 규칙 테스트
