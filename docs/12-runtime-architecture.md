# 런타임 아키텍처 설계

## 공식 참고 링크

- Google Cloud OKF 공식 저장소: [https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- Google Cloud OKF 공식 스펙: [https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

## 1. 목적

이 문서는 Campingtalk AI Knowledge Operating System의 실행 구조를 정의한다.

핵심 질문은 다음과 같다.

- 핵심 비즈니스 로직은 어디에 둘 것인가
- CLI와 MCP는 어떤 관계를 가져야 하는가
- 파일 변경, 웹훅, 스케줄 같은 이벤트는 누가 처리하는가
- 장기적으로 어떤 구조가 테스트와 운영에 유리한가

## 2. 결론

권장 구조는 `core service 중심`이다.

- `core`: 순수 도메인 및 비즈니스 로직
- `cli`: 운영자와 배치 작업용 진입점
- `mcp`: Agent용 인터페이스
- `worker`: 이벤트 감지와 작업 실행

즉, `MCP 서버가 CLI를 subprocess로 감싼다`보다 `CLI와 MCP가 같은 core를 호출한다`가 정식 구조다.

## 3. 권장 아키텍처

```text
                ┌──────────────┐
                │   Events     │
                │ cron/schedule│
                │ (기본)       │
                │ 수동 트리거   │
                └──────┬───────┘
                       │
                       ▼
                ┌──────────────┐
                │    Worker    │
                │ detect/route │
                └──────┬───────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │   CLI    │  │   MCP    │  │  Admin   │
   │ operator │  │  tools   │  │ scripts  │
   └────┬─────┘  └────┬─────┘  └────┬─────┘
        │             │             │
        └─────────────┴─────────────┘
                      │
                      ▼
              ┌──────────────┐
              │ Core Service │
              │ domain logic │
              └──────┬───────┘
                     │
      ┌──────────────┼──────────────┐
      │              │              │
      ▼              ▼              ▼
 Repository      Validators     Search/Index
 Git/Files       OKF/Profile    OS Files/Links
```

## 4. 구성 요소

### 4.1 Core Service

핵심 역할:

- Bundle/Evidence 읽기와 쓰기
- OKF Validator와 Profile Validator 실행
- Context 생성
- Curator 실행
- 기본 검색 통합
- 인덱스 갱신 트리거

원칙:

- 프레임워크에 독립적이어야 한다.
- CLI, MCP, Worker 모두 같은 코드를 사용해야 한다.
- 가능한 한 순수 함수와 명확한 서비스 계층으로 분리한다.

### 4.2 CLI

목적:

- 운영자 수동 실행
- 배치 실행
- 디버깅
- 로컬 개발

예상 명령:

- `validate`
- `ingest-evidence`
- `curate`
- `build-index`
- `prepare-context`
- `reindex`

CLI는 사람과 스크립트가 쓰기 위한 얇은 shell이어야 한다.

### 4.3 MCP Server

목적:

- Codex, Claude Code, Gemini 같은 Agent에 Tool 제공

예상 Tool:

- `search_knowledge`
- `read_bundle`
- `prepare_context`
- `propose_update`
- `ingest_evidence`
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

원칙:

- MCP는 core service를 호출한다.
- CLI의 stdout을 파싱하는 구조는 MVP 외에는 피한다.
- Agent 권한과 자동 Commit 정책을 MCP 계층에서 통제한다.

### 4.4 Worker

목적:

- 이벤트 수신
- 작업 생성
- 재시도
- 비동기 처리

입력 이벤트 예시:

- 지정 Batch가 inbox에 적재한 신규/변경 원본
- 수동 트리거(CLI/MCP를 통한 즉시 실행 요청)
- Hermes가 업무 중 수집한 원본

보류된 이벤트 예시(`docs/13-future-work.md` 참고):

- 실시간 파일 watcher
- Git hook
- webhook

작업 예시:

- `ingest`
- `curate`
- `validate`
- `reindex`
- `rebuild_context`

## 5. CLI를 중심에 두지 않는 이유

`MCP -> CLI subprocess -> core` 구조는 초기 MVP에서는 빠르지만, 정식 구조로는 단점이 크다.

### 장점

- 빠르게 시작 가능
- 이미 CLI가 있으면 재사용 쉬움
- 운영자가 보는 출력과 일치

### 단점

- stdout/stderr 파싱 필요
- 에러 타입 구조화가 어렵다
- 성능 손실이 있다
- 테스트가 불편하다
- 동시성 제어가 어렵다
- 장기 실행 워커에 불리하다

## 6. 권장 구현 단계

### 단계 1. Core library 작성

- 파일 모델
- Validator
- Service API

### 단계 2. CLI 작성

- 운영용 명령 노출
- 로컬 반복 작업 지원

### 단계 3. MCP 작성

- 읽기 Tool부터 시작
- 검증 통과 후 자동 Commit 흐름 추가

### 단계 4. Worker 작성

- 지정 Batch·수동 트리거 결과 처리
- 유지보수 검증·Audit
- 실시간 파일 이벤트/webhook은 보류(`docs/13-future-work.md`)

## 7. 이벤트 처리 모델

### 7.1 지정 Batch 수집

예:

- Notion, GitHub 등 외부 소스의 신규/변경 문서 수집
- `inbox/` 신규 파일 스캔

처리 흐름:

1. 지정 Batch가 자체 스케줄과 watermark로 변경분을 조회한다.
2. 원본을 `knowledge/inbox/`에 적재한다.
3. 외부 객체와 revision을 식별하는 `idempotency_key`로 `ingest_evidence`를 호출한다.
4. Hermes Curator가 `propose_update` 결과를 검토한다.
5. 신규 지식은 `create_draft_bundle`, 기존 지식은 `apply_bundle_revision`으로 반영한다.
6. 검증 후 발행한다.

Hermes 운영 서버는 대상 Repository를 인식하고 작업한다. 수집·정제 결과는 Repository의 `knowledge/`에 반영한 뒤 Validator를 통과한 변경만 Git commit/push 대상으로 만든다. Git은 지식 라이브러리의 복원, 공유, 변경 이력 및 백업 계층으로 사용한다.

### 7.2 수동 트리거 (예외 처리)

예:

- 긴급 정책 반영처럼 스케줄을 기다릴 수 없는 경우
- 사람 또는 Agent가 CLI/MCP로 즉시 처리를 요청하는 경우

처리 흐름:

1. 사용자 또는 Hermes가 원본을 inbox에 적재한다.
2. CLI `ingest-evidence` 또는 MCP `ingest_evidence`를 호출한다.
3. 이후 과정은 지정 Batch 경로와 같은 Core API를 사용한다.

### 7.3 유지보수 스케줄

예:

- nightly reindex
- `review_requested` 처리(`docs/05-hermes-architecture.md` 7절)
- broken link scan

처리 흐름:

1. scheduler 실행
2. worker에 maintenance job 등록
3. core service 실행

### 7.4 보류된 이벤트 경로

실시간 파일 watcher와 webhook 수신(Notion 변경, Slack 이벤트, GitHub PR/Issue 등)은 기본 경로로 채택하지 않는다. 지식 갱신은 실시간성이 필요하지 않다고 판단했고, 스케줄 폴링과 수동 트리거로 충분히 커버된다. 보류 상세는 `docs/13-future-work.md`를 따른다.

## 8. 권장 디렉터리 구조

```text
cpt-knowledge/
├── AGENTS.md
├── README.md
├── docs/
├── .knowledge-os/
│   ├── templates/
│   ├── schemas/
│   └── policies/
├── knowledge/
│   ├── bundles/
│   │   └── <domain>/
│   │       └── runbooks/
│   ├── evidence/
│   ├── inbox/
│   └── .raw/
├── src/
│   └── knowledge_os/
│       ├── core/
│       ├── cli/
│       ├── mcp/
│       ├── worker/
│       ├── integrations/
│       └── config/
├── tests/
└── pyproject.toml
```

이 구조에서:

- `knowledge/`는 실제 Obsidian Vault
- `.knowledge-os/`는 업그레이드 가능한 운영 Control Plane
- `.knowledge-os-backups/`는 업그레이드 직전 Control Plane의 버전별 복구 스냅샷
- `.knowledge-os/runtime/`은 대상 폴더에서 독립 실행하는 CLI 구현
- `.knowledge-os/bin/knowledge-os.py`는 대상 프로젝트 root를 선택하는 portable launcher
- `.knowledge-os/AGENT_BOOTSTRAP.md`는 AI Agent의 규칙·Profile·CLI 시작 계약
- root `AGENTS.md`는 Agent 자동 발견용 비관리 진입점이며, 기존 조직 파일을 보존한다.
- `.knowledge-os/issues/`는 사용자·Agent·운영자·자동화의 시스템 개선 이슈를 저장하는 로컬 피드백 영역
- 루트 저장소 전체는 Git 복원 단위
- `docs/`는 설계 기준 문서
- `src/`는 운영 시스템 구현체
- `knowledge/.raw/`는 처리 중 원본 작업의 staging area
- OS 업그레이드는 `knowledge/` 아래를 변경하지 않는다.
- 기존 OS를 변경하는 업그레이드는 백업 성공을 선행 Gate로 사용한다.

경로 원칙:

- 런타임 설정은 프로젝트 루트 기준 상대 경로를 우선한다.
- 기본 지식 저장소 경로는 `knowledge/`다.
- 특정 개발자 PC의 절대 경로는 코드, 문서, 설정에 저장하지 않는다.

## 9. 인터페이스 원칙

### 9.1 Core API는 구조화된 결과를 반환한다

예:

- success/failure
- validation errors
- changed bundles
- warnings

CLI와 MCP는 이 구조화된 결과를 각각 사람용/Agent용으로 렌더링한다.

### 9.2 검색 실행은 Core가 담당한다

- MCP는 `search_knowledge` Tool 요청을 Core Service로 위임한다.
- CLI의 `search` 명령도 같은 Core 검색 API를 호출한다.
- Core는 OS와 사용 가능한 명령을 감지한다.
- 기본 우선순위는 `rg`다.
- `rg`가 없으면 macOS/Linux는 `grep`, Windows는 PowerShell `Select-String`으로 fallback한다.
- MCP와 CLI는 검색 결과를 렌더링만 하고, OS별 검색 분기를 직접 갖지 않는다.

### 9.3 CLI는 렌더러이지 진실의 원천이 아니다

- CLI 출력 포맷은 사용자 친화적일 수 있다.
- 하지만 다른 런타임이 CLI 문자열을 파싱하게 만들지 않는다.

### 9.4 MCP는 정책 계층을 가진다

- Validator 통과 후 자동 Commit
- 민감 문서 필터링
- Tool별 권한 제한

### 9.5 Worker는 idempotent 해야 한다

- 같은 이벤트가 두 번 와도 안전해야 한다.
- 상태 기반 재시도를 지원해야 한다.

## 10. MVP와 정식 구조

### MVP 허용 구조

```text
MCP -> CLI -> core
```

조건:

- 짧은 수명
- 단일 사용자
- 낮은 동시성
- 빠른 검증 목적
- Validator 통과 후 자동 Commit

### 정식 권장 구조

```text
CLI -> core
MCP -> core
worker -> core
```

이 구조를 기본으로 해야 테스트, 운영, 확장이 쉬워진다.

## 11. 추천 명령 및 Tool 대응표

| 목적 | CLI | MCP | Worker |
|---|---|---|---|
| Bundle 조회 | `read-bundle` | `read_bundle` | - |
| 검색 | `search` | `search_knowledge` | - |
| 문맥 생성 | `prepare-context` | `prepare_context` | - |
| 검증 | `validate` | `validate_result` | `validate_on_schedule` |
| 큐레이션 | `curate` | `propose_update` | `curate_on_schedule` |
| Workflow 탐색 | `find-workflow` | `find_workflow` | - |
| Task 준비 | `prepare-task` | `prepare_task` | - |
| Runbook 최신화 준비 | `prepare-runbook-refresh` | `prepare_runbook_refresh` | - |
| 사용자 레퍼런스 제출 | `submit-runbook-reference` | `submit_runbook_reference` | - |
| 사용자 레퍼런스 평가 | `record-reference-assessment` | `record_reference_assessment` | - |
| Evidence 수집 | `ingest-evidence` | `ingest_evidence` | 지정 Batch·사용자·Hermes |
| Draft Bundle 생성 | `create-bundle` | `create_draft_bundle` | - |
| Bundle revision 적용 | - | `apply_bundle_revision` | - |
| Runbook revision 확인 | `confirm-runbook-revision` | `confirm_runbook_revision` | - |
| 지식 품질 감사 | `audit-knowledge` | `audit_knowledge` | `run_maintenance` 포함 |
| 지식 Inventory | `list-knowledge-inventory` | `list_knowledge_inventory` | Audit 내부 파생 |
| 주장 근거 검사 | `validate-claim-support` | `validate_claim_support` | - |
| Runbook revision 효과 측정 | `measure-runbook-effectiveness` | `measure_runbook_effectiveness` | 예약 실행 가능 |
| Task 입력 보완 | `update-task-inputs` | `update_task_inputs` | - |
| 단계·승인 기록 | `record-task-step` | `record_task_step` | - |
| Refresh 변화 판정 | `record-refresh-decision` | `record_refresh_decision` | - |
| 결과 Evidence 환류 | `record-outcome` | `record_outcome` | - |
| 인덱스 갱신 | `reindex` | - | `scheduled_reindex` |

## 12. 현재 프로젝트에 대한 권장안

현재 단계에서는 아래 순서를 추천한다.

1. `core` 모델과 validator 설계
2. `CLI` 먼저 구현
3. ingest, evidence manifest, bundle 생성 흐름 구현
4. 기본 검색 구현
5. 읽기·Workflow 실행 준비용 `MCP` 구현
6. 공식 Runbook과 `.runtime/tasks/` Task 상태 분리
7. Outcome Evidence 환류 구현
8. 지정 Batch 연동과 유지보수 `worker` 구현(파일 watcher/webhook은 보류)
9. 쓰기와 자동 Commit 흐름 확장

즉, 시작은 CLI로 해도 되지만 중심은 core여야 한다.

## 13. 결론

이 프로젝트는 단순 커맨드 모음이 아니라, 장기적으로는 이벤트와 Agent 호출을 함께 처리해야 하는
지식 운영 시스템이다.

따라서 런타임 설계는 다음 원칙으로 고정하는 것이 적절하다.

- core 중심
- CLI는 얇게
- MCP와 CLI는 Hermes가 하위·외부 Agent에게 지식 라이브러리를 이용하게 하는 인터페이스
- worker는 이벤트 처리
- 모두 같은 도메인 로직 공유
