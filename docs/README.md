# AI Circled Wiki 문서 인덱스

이 디렉터리는 Example Organization의 `AI Knowledge Operating System` 구축을 위한 기획 및 설계 문서 세트다.

## 공식 참고 링크

- Open Definition 2.1: [https://opendefinition.org/od/2.1/en/](https://opendefinition.org/od/2.1/en/)
- Google Cloud OKF 공식 저장소: [https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- Google Cloud OKF 공식 스펙: [https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

## 문서 구성

- `00-project-charter.md`: 프로젝트 기획서
- `01-vision.md`: 비전과 문제 정의
- `02-architecture.md`: 전체 아키텍처
- `03-okf-spec.md`: OKF 적용 및 확장 규격
- `04-evidence-model.md`: Evidence 객체 설계
- `05-hermes-architecture.md`: Hermes 아키텍처
- `06-knowledge-service.md`: 내부 SDK / 서비스 설계
- `07-mcp-spec.md`: 외부 Agent 인터페이스 설계
- `08-sync-pipeline.md`: 수집 및 동기화 파이프라인 설계
- `09-development-roadmap.md`: 단계별 구축 계획
- `10-obsidian-guidelines.md`: 사람 중심 편집 규칙
- `11-implementation-guidelines.md`: 구현 착수 규칙
- `12-runtime-architecture.md`: CLI, MCP, worker 런타임 구조 설계
- `13-future-work.md`: MVP 이후로 미룬 작업 항목
- `14-use-cases-and-flow-diagrams.md`: 유즈케이스와 Mermaid 흐름 다이어그램
- `15-implementation-plan.md`: MVP 구현 범위, 모듈 경계, 검증 및 단계별 완료 조건
- `16-workflow-execution.md`: 실행 가능한 Runbook, Task 상태 분리, Hermes 실행 및 지식 환류 모델
- `17-human-guide.md`: 사람 사용자의 요청, 승인, 결과 확인과 Runbook 운영 가이드
- `18-agent-guide.md`: AI Agent의 MCP Tool 호출, 상태 전이, 보안 및 지식 환류 가이드
- `19-knowledge-governance.md`: 수집 의도, 업무 Rulebook, Runbook 배치, Inquiry, 신선도와 Outcome 승격 규칙
- `20-runbook-refresh.md`: Runbook 위험 기반 유효기간, 즉시 갱신 Trigger와 Refresh Task SOP
- `21-runbook-learning.md`: 실제 실행 Outcome 기반 Runbook 성장, 개선 Trigger와 독립 Agent 검증 모델
- `22-knowledge-quality-and-artifacts.md`: 사용자 레퍼런스 평가, Claim Support, Audit·Inventory, Archive와 산출물 계약
- `23-operational-improvement-plan.md`: 운영 이슈를 원본 개선·릴리스·운영본 업그레이드로 연결하는 지속 개선 계획

## 실제 운영 경로

- Git 복원 기준: 프로젝트 루트 전체
- Obsidian Vault 기준: `knowledge/`
- 설계 문서 기준: `docs/`
- 개선 작업 계획서 기준: `workspace/task/`
- 제품 테스트 기준: `workspace/tests/`

## 문맥 로딩 원칙

- 전역 운영 단일 규약은 루트 `OPERATING_RULES.md`다.
- `docs/`는 기획·상세 설계 Reference이며 Runtime Context가 아니다.
- Bundle·Evidence의 ID, 링크, 양방향 참조 규약은 `docs/26-reference-contract.md`를 단일 기준으로 한다.
- Runtime Agent는 `docs/`를 읽지 않고 전역 운영 규약과 공식 Knowledge Bundle로 동작한다.
- Repository Engineering에서만 `OPERATING_RULES.md`의 Reference Traceability를 통해 필요한 설계 문서를 확인한다.
- `docs/source/`와 역사적 초안은 과거 의사결정 근거가 필요할 때만 읽는다.

## 작업 원칙

- 규약이 코드보다 먼저다.
- 저장소 구조보다 데이터 모델을 먼저 고정한다.
- 운영 Agent는 `OPERATING_RULES.md`를 기준으로 동작한다. 구현 Agent는 필요할 때만 설계 Reference를 확인한다.
- OKF 관련 판단은 `표준 원칙`과 `Example Organization OKF Profile`을 구분해서 읽는다.
