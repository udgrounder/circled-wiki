# 전체 아키텍처

## 공식 참고 링크

- Google Cloud OKF 공식 저장소: [https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- Google Cloud OKF 공식 스펙: [https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

## 1. 시스템 개요

이 시스템은 입력 수집, Evidence 저장, 지식 정제, 기본 검색, AI 인터페이스 제공의 다섯 층으로 구성된다.

```text
외부 입력
  ├─ Notion
  ├─ Slack
  ├─ GitHub
  ├─ Jira
  └─ Meetings
        │
        ▼
Inbox / Evidence Layer
        │
        ▼
Hermes
  ├─ Collector
  ├─ Curator
  ├─ Reviewer
  ├─ Index Manager
  └─ Delegator
        │
        ▼
Knowledge Repository
  ├─ OKF Bundles
  └─ Evidence Objects
        │
        ▼
Knowledge Service
        │
        ▼
Knowledge MCP
        │
        ▼
Codex / Claude Code / Gemini / Internal Apps
```

## 2. 주요 계층

### 입력 계층

- 외부 시스템의 데이터 수집
- 사람 수기 입력 접수
- 임시 버퍼 또는 큐 관리

### 저장 계층

- Evidence 저장
- Bundle 저장
- 템플릿, 정책, 스키마 관리
- `index.md`, `log.md` 같은 보조 파일 관리

### 처리 계층

- 정제
- 중복 검사
- 품질 검토
- 인덱스 갱신
- Candidate Evidence 평가와 독립 검증
- Claim Support 검사
- 파생 Inventory와 읽기 전용 Knowledge Audit

### 접근 계층

- 내부 SDK 제공
- MCP Tool 인터페이스 제공
- 검색/문맥 패키징 제공

## 3. 저장소 구조

```text
project-root/
├── AGENTS.md
├── README.md
├── docs/
├── .knowledge-os/
│   ├── templates/
│   ├── schemas/
│   └── policies/
└── knowledge/
    ├── bundles/
    │   ├── company/
    │   │   └── runbooks/
    │   ├── product/
    │   │   └── runbooks/
    │   ├── engineering/
    │   │   └── runbooks/
    │   ├── cs/
    │   │   └── runbooks/
    │   ├── operations/
    │   │   └── runbooks/
    │   └── marketing/
    │       └── runbooks/
    ├── evidence/
    │   ├── notion/
    │   ├── slack/
    │   ├── github/
    │   └── meetings/
    ├── inbox/
    └── .raw/
```

실제 Obsidian Vault 기준 경로는 아래다.

```text
knowledge/
├── bundles/
│   ├── company/
│   │   └── runbooks/
│   ├── product/
│   │   └── runbooks/
│   ├── engineering/
│   │   └── runbooks/
│   ├── cs/
│   │   └── runbooks/
│   ├── operations/
│   │   └── runbooks/
│   └── marketing/
│       └── runbooks/
├── evidence/
│   ├── notion/
│   ├── slack/
│   ├── github/
│   └── meetings/
├── inbox/
└── .raw/
```

운영 템플릿·스키마·시스템 기본 정책은 Obsidian Vault 밖의 `.knowledge-os/` Control Plane에 둔다.
OS 업그레이드는 이 Control Plane만 변경하며 `knowledge/` Data Plane은 수정하지 않는다. 기존 Control Plane을
변경할 때는 프로젝트 root의 `.knowledge-os-backups/<기존-version>-<UTC timestamp>/`에 전체 스냅샷을 먼저
생성하고, 백업 실패 시 변경을 시작하지 않는다.

`.knowledge-os/runtime/`에는 대상 프로젝트에서 직접 실행하는 CLI Runtime을, `.knowledge-os/bin/knowledge-os.py`에는
프로젝트 root를 자동 선택하는 Launcher를 둔다. Agent는 `.knowledge-os/AGENT_BOOTSTRAP.md`에서 시작해 전역 규칙과
요청별 Profile을 적용한다. root `AGENTS.md`는 이 시작 문서를 Agent가 자동 발견하도록 연결하는 비관리 shim이며,
존재할 때는 조직 소유 파일로 보존한다.

최초 설치는 `.knowledge-os/config.yaml`에 organization ID·표시 이름·operator Agent와 선택적 Graphify 설정을
기록한다. organization ID는 Knowledge·Evidence·Inbox URI namespace이며 설치 후 upgrade가 설정 파일을 덮어쓰지
않는다. 자율형 Agent는 `.knowledge-os/AUTONOMOUS_AGENT_STARTUP.md`에서 시작하고 Graphify는 별도 설치된 파생
인덱스로만 사용한다.

`.knowledge-os/issues/`는 운영 중 발견된 문제와 사용자 피드백을 개선 검토용으로 보관하는 로컬 피드백 영역이다.
이 영역은 OS template와 분리되며 기존 이슈 기록은 업그레이드로 덮어쓰지 않는다.

OKF 관점의 해석은 다음과 같다.

- 파일 하나가 하나의 개념이다.
- 디렉터리 구조는 개념의 지도다.
- 파일 경로는 개념 정체성의 일부다.
- Markdown 링크는 관계를 나타내는 그래프 엣지다.
- `Concept ID`는 파일 경로에서 `.md`를 제거한 값이다.
- 실행 가능한 `type: runbook`은 도메인별 `runbooks/`에 저장한다.
- 업무 Rulebook은 관련 Policy·Guide·Runbook을 연결하는 `type: guide` Bundle이다.

## 4. 데이터 흐름

### 흐름 A: 신규 지식 수집

1. 외부 입력 수집
2. `inbox/`에 입력 적재
3. 작업 대상 파일을 `.raw/`로 이동
4. 이동 시 `source_uuid` 발급
5. 정규화 및 원본 참조 구조(`source_ref`) 기록
6. Evidence Object 생성
7. Hermes Curator가 처리
8. 기존 Bundle 갱신 또는 신규 Bundle 생성
9. OKF/Profile 검증
10. Validator 통과 시 자동 Git Commit
11. 기본 검색 인덱스 또는 파일 검색 갱신

### 흐름 B: AI Agent 조회

1. Agent가 MCP Tool 호출
2. MCP가 Knowledge Service에 위임
3. Service가 Bundle, 기본 검색 결과, Frontmatter, 링크를 조합
4. 결과를 Context Package로 반환

## 5. 아키텍처 결정

- Source of Truth는 Git이다.
- Git으로 관리되는 프로젝트 루트 전체가 복원 기준이다.
- 실제 지식 저장소 기준 경로는 루트 아래 `knowledge/`다.
- 경로 표현은 절대 경로가 아니라 프로젝트 루트 상대 경로를 사용한다.
- `bundles/`와 Evidence Record, 그리고 템플릿/스키마/정책 문서는 OKF 구조를 유지한다.
- `inbox/`, `.raw/`, `evidence/`는 비Markdown 원본 파일을 포함할 수 있다.
- 검색 인덱스는 캐시이며 기준 데이터가 아니다.
- MVP 검색은 OS 파일 검색, Frontmatter 필터, Markdown 링크 추적, Evidence Record 검색으로 시작한다.
- Evidence와 Bundle은 별도 경로에 저장한다.
- Inventory와 Audit은 Frontmatter에서 재생성하며 별도 Source of Truth를 만들지 않는다.
- Archive는 경로를 이동하지 않고 Bundle 상태와 복구 조건으로 표현한다.
- 기본 검색과 Runtime Context는 Active Bundle만 사용한다.
- `evidence/`는 처리 완료된 Evidence Original과 Evidence Record를 보존하는 계층이며, Bundle 참조를 위한 근거 앵커다.
- 10MB 이하 외부 Evidence Original은 External-file Evidence Manifest와 함께 Git에 추적한다. 10MB 초과 원본은 Git에서 제외하고 별도 원본 저장소에 보존하며, External-file Evidence Manifest에는 checksum과 보관 위치를 기록한다.
- `inbox/`와 `.raw/`는 운영 큐이며, 공식 지식의 최종 저장 위치가 아니다.
- `bundles/`는 정제된 공식 지식을 저장하는 경로이며, 저장 시 반드시 OKF 구조를 만족해야 한다.
- 외부 Agent는 MCP만 사용한다. Hermes는 저장소를 인식하는 운영 Agent이며, 운영 작업과 사용자 요청 처리 모두에서 Knowledge Service를 사용한다.
- 사람이 직접 수정하는 문서는 Markdown 중심으로 유지한다.
- Bundle 스키마 검증은 `표준 OKF 원칙 + Example Organization OKF Profile` 조합으로 수행한다.
- 표준 OKF는 구조적 상호운용 표면을 제공하고, 의미적 강제는 저장소 프로파일이 담당한다.
- 표준 OKF 소비자는 optional field 누락, unknown key, broken link를 허용해야 한다.

## 6. 리스크

- OKF 적용 범위가 초기 단계에서 애매할 수 있다.
- Evidence 품질이 낮으면 Bundle 품질도 낮아진다.
- 검색 계층이 먼저 복잡해질 수 있다. MVP에서는 기본 검색 범위를 넘기지 않는다.
- 수동 편집과 자동 정제 간 충돌 가능성이 있다.

## 7. 업무 실행과 지식 환류

사용자 요청을 실제 작업으로 연결하는 구조는 [16-workflow-execution.md](16-workflow-execution.md)를 따른다.

- 공식 절차는 `type: runbook`인 OKF Bundle로 관리한다.
- Hermes는 활성 Runbook을 선택하고 필수 입력, 승인 지점, 완료 기준을 기준으로 작업을 조정한다.
- 실행 중 Runtime Task 상태는 공식 지식이 아니므로 `knowledge/` 밖의 `.runtime/tasks/`에 저장한다.
- 완료·실패·검토 필요 결과는 Outcome Inbox Item으로 수집하고, 검사·승인·변환 후 Outcome Evidence로 Curator 흐름에 되돌린다.
- Task 실행 결과가 Validator와 Reviewer를 우회해 공식 Bundle을 직접 변경해서는 안 된다.
