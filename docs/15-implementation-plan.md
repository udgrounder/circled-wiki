# MVP 구현 설계서

## 1. 목적과 범위

이 문서는 설계 문서 세트를 실제로 동작하는 최소 제품(MVP)으로 옮기는 구현 기준이다.
상위 기준은 [02-architecture.md](02-architecture.md), [03-okf-spec.md](03-okf-spec.md),
[04-evidence-model.md](04-evidence-model.md), [06-knowledge-service.md](06-knowledge-service.md)를 따른다.
충돌 시 상위 기준 문서가 우선한다.

이번 구현의 완료 범위는 아래의 단일 흐름이다.

```text
inbox 원본 1개
  -> .raw 이동 및 source_uuid 발급
  -> evidence 원본 + manifest 생성
  -> Bundle 생성
  -> OKF 최소 / Example Organization Profile 검증
  -> 기본 검색으로 Bundle과 Evidence Record 조회
  -> 활성 Runbook 탐색 및 runtime Task 준비
  -> 작업 결과를 Outcome Evidence로 환류
```

MCP와 자동 Git commit 경계는 구현되었다. LLM 기반 의미 판단은 Hermes가 담당하고, 외부 Provider 수집과
스케줄은 지정 Batch의 책임으로 분리한다. Core API는 CLI, MCP, Worker가 공통으로 재사용한다.

## 2. 구현 구조

```text
src/circled_wiki/
├── core/             # 파일 모델, frontmatter, 검증, ingest, 검색, 서비스
├── cli/              # argparse 기반의 얇은 사람/스크립트용 인터페이스
├── mcp/              # 지식 조회·검증과 Workflow 실행 준비/결과 환류 어댑터
├── worker/           # 후속 scheduler/작업 실행기의 자리
├── integrations/     # 후속 provider별 수집 어댑터의 자리
└── config/           # 프로젝트 상대경로 기반 설정
tests/
├── unit/             # 모델, 파서, Validator의 독립 단위 테스트
└── integration/      # inbox에서 검색까지의 흐름 테스트
```

`knowledge/`는 구현 코드가 아닌 Git/Obsidian 기준 지식 저장소다. 모든 경로는 project root
상대값을 입력으로 받고, 코드나 설정에 개발 머신 절대 경로를 기록하지 않는다.

## 3. Core 경계

| 모듈 | 책임 | 직접 알면 안 되는 것 |
| --- | --- | --- |
| `models` | Bundle, Evidence Record, 검증 결과의 구조화 표현 | CLI/MCP 출력 형식 |
| `frontmatter` | Markdown YAML frontmatter 파싱과 렌더링 | 파일 검색 전략 |
| `validator` | OKF v0.1 최소 규칙과 Profile 규칙을 분리 검증 | Git commit 여부 |
| `ingest` | inbox -> .raw -> evidence 원본/manifest 이동과 UUID·checksum 처리 | Bundle 의미 판단 |
| `repository` | Bundle/Evidence Record 읽기와 경로 탐색 | 운영자용 출력 |
| `search` | `rg` 우선 검색과 Python fallback, filter/link 확장 | MCP tool 프로토콜 |
| `workflow` | 실행 Runbook 탐색, Task 스냅샷, Outcome Evidence 환류 | Hermes의 LLM 의미 판단 |
| `service` | 위 모듈을 조합한 구조화 API | UI/transport 세부사항 |

## 4. 데이터 및 검증 기준

### 4.1 OKF v0.1 최소 적합성

- 예약 파일(`index.md`, `log.md`)을 제외한 관리 대상 Markdown은 파싱 가능한 YAML frontmatter를 가진다.
- `type`은 비어 있지 않다.

### 4.2 Example Organization OKF Profile

Bundle은 `id`, `bundle_uuid`, `title`, `type`, `status`, `summary`, `updated_at`, `evidence`를
가져야 하며 `evidence`는 빈 배열일 수 없다. `id`와 파일명은 동일한 `bundle_uuid`를 사용한다.
조직 특화 메타데이터는 `extensions` 이외의 위치에 추가하지 않는다.
`type: runbook`은 `bundles/<domain>/runbooks/`에만 저장한다. `active` Bundle은 Owner와 검토 기한을
포함한 `extensions.governance`를 가진다.

External-file Evidence Manifest는 Evidence Original과 같은 basename으로 두며, `type: evidence`, `source_uuid`, `provider`,
`source_ref`, `captured_at`, `status`, `checksum`, `original_file`을 관리한다. Bundle과 Evidence의
Bundle `evidence` 참조는 Evidence 존재 여부로 검사한다.
일반 Evidence는 수집 이유와 적용 대상을 `extensions.capture_context`에 기록한다.

검증 결과는 다음을 분리해 반환한다.

- `okf_errors`: 공개 OKF 최소 포맷 위반
- `profile_errors`: 저장소 프로파일 위반
- `warnings`: unknown field, unknown type, broken link 등 소비를 거부하지 않는 경고

## 5. 단계별 개발 순서와 완료 조건

1. **프로젝트 골격**: Python 패키지, 테스트 구조, 상대 경로 설정을 만든다.
2. **파일 모델과 frontmatter**: Markdown/YAML을 읽고 안전하게 렌더링한다.
3. **Validator**: 최소 OKF와 Profile을 분리해 검사하는 테스트를 통과시킨다.
4. **Evidence ingest**: 원본을 보존하고 UUID, SHA-256, manifest를 생성한다. 성공한 `.raw/` 항목은 제거하고 실패/검토 항목은 보존한다.
5. **Knowledge Service와 검색**: Bundle/Evidence Record 읽기, 키워드/필터 검색, context 초안을 제공한다.
6. **CLI**: `validate`, `ingest-evidence`, `search`, `read-bundle`을 Core API의 얇은 표현 계층으로 제공한다.
7. **통합 검증**: 임시 저장소에서 ingest부터 search까지 실행하고, 기존 `knowledge/` 관리 문서도 검증한다.

완료된 후속 기반 단계:

- **Knowledge MCP**: 읽기·검증 Tool과 Workflow Task 준비·결과 환류 Tool을 stdio JSON-RPC로 제공한다.
  `prepare_task`는 `.runtime/`만 변경하고 `record_outcome`은 결과를 Evidence로 수집한다.
- **Curation MCP**: inbox 제한 Evidence ingest, Draft 생성, optimistic revision 기반 Bundle 변경과 검증 실패 원복을 제공한다.
- **Worker 유지보수 작업**: 외부 scheduler가 호출할 수 있는 idempotent 검증·문서 집계 작업을 제공한다.
- **Workflow 실행 기반**: 활성 Runbook 검증, Workflow 탐색, `.runtime/tasks/` 상태 분리,
  위험 기반 유효성 계산, 만료·명시적 요청 Refresh Task, `record_outcome`의 Evidence 환류를 제공한다.
  Hermes의 실제 단계 수행과 Tool 선택은 이 Core 계약을 사용한다.
- **Runbook Learning Loop**: 최신 `available` Evidence 기반 변화 판정, 독립 Agent 검증, Outcome 임계치 기반
  개선 Task와 중복 Refresh 방지를 제공한다. Outcome은 Runbook을 직접 수정하지 않는다.
- **Knowledge Quality**: Candidate Evidence 평가, Active-only 기본 검색, 파생 Inventory·Audit, Claim Support,
  Archive lifecycle, Artifact Profile과 구조화 Outcome을 제공한다.

각 단계는 해당 테스트와 전체 `validate`가 통과해야 다음 단계로 진행한다. Validator 실패 상태에서는
발행하거나 commit하지 않는다. Validator와 보안 게이트를 모두 통과한 `knowledge/` 변경은 Hermes 운영 흐름에서 자동 commit한다.

## 6. 보류 결정

- MCP는 Core와 CLI가 안정된 뒤 읽기 도구부터 추가한다.
- Hermes의 Bundle 의미 판단은 LLM 운영 정책에 맡기고 Core는 검증·적용 경계를 제공한다.
- 외부 provider 수집과 scheduler는 지정 Batch가 소유한다. webhook, vector DB, GraphRAG는 `docs/13-future-work.md`의 관리 범위를 유지한다.
- Git commit은 Validator와 보안 게이트 통과 후 Hermes 운영 흐름이 자동 수행한다.

## 7. 검증 명령 목표

구현 완료 시 아래 명령이 동작해야 한다.

```text
python3 -m pytest
PYTHONPATH=src python3 -m circled_wiki.cli validate
PYTHONPATH=src python3 -m circled_wiki.cli ingest-evidence --provider manual --file <inbox-file> \
  --why-collected <수집-이유> --intended-use <적용-업무>
PYTHONPATH=src python3 -m circled_wiki.cli search --query <query>
PYTHONPATH=src python3 -m circled_wiki.cli audit-knowledge
PYTHONPATH=src python3 -m circled_wiki.cli list-knowledge-inventory
```
