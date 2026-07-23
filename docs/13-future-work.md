# 향후 작업 항목

## 1. 목적

이 문서는 MVP에서 의도적으로 제외한 기능과 설계 보류 항목을 관리한다.

MVP 기준 문서는 현재 운영 가능한 최소 흐름에 집중한다. 아래 항목은 초기 구축 이후 데이터 규모, 사용 빈도, 운영 필요성이 확인되면 다시 검토한다.

## 2. 검색 고도화

### BM25 / SQLite FTS

- 목적: OS 파일 검색 결과에 검색어 관련도 기반 순위를 부여한다.
- 설명: BM25는 검색어 빈도, 문서 길이, 단어 희소성을 함께 고려하는 키워드 랭킹 알고리즘이다.
- 도입 조건: OS 파일 검색 결과가 너무 많아 순위 품질이 문제가 될 때
- 선행 조건: 검색 대상 문서 범위와 인덱스 재생성 정책
- 보류 이유: MVP는 OS 파일 검색으로 충분히 시작할 수 있다.

### Vector Search

- 목적: 키워드가 정확히 일치하지 않아도 의미적으로 가까운 Bundle을 찾는다.
- 도입 조건: OS 파일 검색과 키워드 랭킹만으로 검색 누락이 반복될 때
- 선행 조건: 안정적인 Bundle 품질, chunk 정책, 재색인 정책
- 보류 이유: 초기에는 인덱스 운영 비용과 품질 평가 부담이 더 크다.

### GraphRAG

- 목적: 문서 간 관계와 근거 연결을 그래프로 분석해 복합 질의에 답한다.
- 도입 조건: Bundle 수가 늘고 링크 기반 관계 탐색만으로 부족할 때
- 선행 조건: 안정적인 링크 규칙, backlink 스캔, Evidence-Bundle 무결성
- 보류 이유: 초기에는 Markdown 링크와 Frontmatter 기반 관계 탐색으로 충분하다.

### Hybrid Search

- 목적: BM25, Vector, Graph 결과를 병합한다.
- 도입 조건: 검색 품질 평가 기준과 테스트셋이 생긴 뒤
- 보류 이유: 검색 품질을 측정할 기준 없이 복잡도를 올리면 유지보수가 어려워진다.

## 3. 외부 시스템 실시간/추가 연동

Notion, GitHub 등 외부 수집 스케줄은 지정 Batch가 소유한다. Circled Wiki는 Batch가 inbox에 적재한 원본의
idempotent ingest부터 책임지며 내장 Provider 폴링은 현재 범위에 포함하지 않는다.

아래는 여전히 보류 항목이다.

### 실시간 Webhook 수신

- 목적: 스케줄 폴링 주기보다 더 빠른 반영이 필요할 때 Notion/Slack/GitHub 변경을 즉시 수신한다.
- 도입 조건: 스케줄 폴링 + 수동 트리거로 감당 안 되는 지연 민감 사례가 반복될 때
- 선행 조건: webhook 서명 검증, 수신 큐, 재시도 정책
- 보류 이유: 지식 갱신은 실시간성이 필요하지 않다고 판단했다. 스케줄 폴링과 수동 트리거로 충분히 커버된다.

### Slack / Jira / 회의록 자동 수집

- Slack 자동 동기화
- Jira 자동 동기화
- 회의록 자동 수집

도입 조건:

- Notion/GitHub 스케줄 폴링 운영이 안정화됨
- 중복 감지와 `source_ref` 매핑이 검증됨
- 실패 재시도와 rate limit 정책이 준비됨

## 4. 승인 워크플로우 고도화

MVP에서는 Agent가 Validator를 통과한 변경을 자동 Commit한다.

향후 검토할 항목:

- `draft -> review -> active` 상태 전이
- 도메인 owner 승인
- 민감 문서 별도 승인
- 자동 Commit 대신 Pull Request 생성

## 5. Evidence 원본 복원 정책

현재 정책:

- 처리 완료된 원본 파일은 `knowledge/evidence/`에 보존한다.
- 10MB 이하 원본은 같은 basename의 `.md` manifest와 함께 Git에 추적한다.
- 10MB 초과 원본은 Git에서 제외하고 별도 원본 저장소에 보존한다. Git에는 checksum과 `extensions.storage`를 포함한 manifest만 추적한다.
- Validator와 커밋 전 검사는 10MB 초과 Evidence 원본이 Git에 추가되는 것을 차단한다.
- `source_ref`로 재확보할 수 없는 수동 업로드 대용량 파일도 별도 원본 저장소의 백업 대상이다.

향후 검토할 항목:

- 대용량 원본 저장소의 백업 위치와 접근 제어
- 외부 object storage 연동
- Git LFS 사용 여부

## 6. 운영 관측성

향후 필요 항목:

- ingest 성공/실패 통계
- Validator 실패 유형 집계
- 자동 Commit 로그 대시보드
- 검색 품질 평가 로그
- `review_requested` 처리 지연 리포트

## 7. Git/GitHub 운영 정책

현재 결정:

- 프로젝트 루트 전체를 Git 복원 기준으로 삼는다.
- GitHub 연동 설정은 사용자가 직접 수행한다.
- GitHub 연동 이후 세부 운영 정책을 확정한다.

향후 결정할 항목:

- 기본 브랜치와 작업 브랜치 전략
- Agent 자동 Commit 메시지 규칙
- 원격 push 자동화 여부
- GitHub Actions 기반 Validator 실행 여부
- Pull Request 기반 검토 전환 조건

## 8. Bundle 동시 갱신 충돌 방지

현재 정책:

- Evidence 중복 수집/중복 처리는 checksum 기반 사후 정리로 감당 가능하다고 판단해 별도 락 없이 진행한다.
- 다만 같은 Bundle 파일을 여러 Curator/Agent가 동시에 읽고-수정하는 경우, 나중에 쓰는 쪽이 앞선 변경을 덮어쓸 수 있다(lost update).

도입 조건:

- Hermes Curator 또는 Agent가 동시에 여러 개 떠서 같은 Bundle을 수정하는 사례가 실제로 반복될 때
- Worker/Agent 동시 실행 규모가 늘어나 수동 검토로 충돌을 감당하기 어려울 때

향후 검토할 항목:

- 쓰기 전 `updated_at` 또는 `knowledge_revision` 비교 기반 optimistic concurrency
- 충돌 감지 시 재시도 또는 사람 검토 큐로 전환

보류 이유: MVP 단계는 단일 Agent/낮은 동시성을 전제하므로 우선 문서화만 해두고 실제 충돌 빈도를 관찰한다.

## 9. Curator 매칭/반영 신뢰성 개선

현재 정책:

- 신규 Evidence가 들어오면 Curator가 관련 기존 Bundle을 검색해 갱신하거나, 없으면 신규 생성한다.
- 매칭이 애매하면 신규 생성 대신 사람 검토 큐로 전환한다(`docs/05-hermes-architecture.md` 3절, 7절).

문제 인식:

- "신선도" 문제의 실제 원인은 문서가 오래돼서가 아니라, 새 정책(Evidence)이 들어왔는데 관련 기존 Bundle에 반영이 안 되는 경우다.
- 이는 나이 기반 자동 폐기로 해결할 문제가 아니라 매칭 파이프라인의 정확도와 규칙설정 문제다.

향후 검토할 항목:

- Curator의 관련 Bundle 매칭 정확도 측정 방법(매칭 실패율, 검토 큐 전환율 로깅)
- 매칭 실패/애매 사례를 주기적으로 리뷰해 매칭 규칙(키워드, 링크, 태그 가중치 등) 튜닝
- `extensions.review_requested` 처리 지연 모니터링과 연계

보류 이유: MVP 단계에서는 우선 `review_requested` 플래그와 사람 검토 큐로 대응하고, 매칭 정확도의 정량적 개선은 실제 운영 데이터가 쌓인 뒤 진행한다.

## 10. 보류 항목 관리 원칙

- MVP 구현 중 보류한 항목은 이 문서에 추가한다.
- 보류 항목은 도입 조건과 보류 이유를 함께 기록한다.
- 구현이 시작되면 해당 항목을 로드맵 문서로 이동한다.

## 11. MCP 인증·인가 및 감사

현재 정책:

- `restricted` Bundle/Evidence는 인증·인가 계층이 구현되기 전까지 MCP에서 기본 차단한다.
- Validator와 보안 게이트를 통과한 `knowledge/` 변경은 Hermes가 자동 commit한다.

향후 검토할 항목:

- MCP 요청자 identity와 역할 기반 권한(RBAC) 또는 속성 기반 권한(ABAC)
- 요청 단위의 `restricted` 접근 판정과 사용자별 context 격리
- Tool별 읽기/쓰기 권한 및 Hermes 운영 계정의 최소 권한 설정
- 검색·조회·발행·자동 commit의 감사 로그와 이상 접근 탐지

도입 조건:

- Hermes 외에 여러 Agent 또는 여러 사용자가 같은 MCP를 공유할 때
- `restricted` 지식의 정식 조회가 필요할 때

## 12. 출처 위치 인용 및 검색·Curator 평가

현재 정책:

- 수집 시 가능한 경우 `source_ref.provider_url`과 `source_ref.locator`를 기록한다.
- Agent 응답은 외부 원문 URL·위치를 1차 근거로, 보존 Evidence를 보조 근거로 제공한다.

향후 검토할 항목:

- 실제 업무 질문, 기대 Bundle/Evidence, 기대 원문 위치로 구성된 평가 세트
- 검색 적중률, 원문 인용 정확도, 근거 없는 답변 비율, Curator 매칭 실패율 측정
- PDF/DOCX/XLSX 등에서 Hermes 또는 사람이 제공한 페이지·시트·문단 위치의 품질 점검

도입 조건:

- 실제 운영 질문이 누적되어 검색 품질을 정량적으로 비교할 필요가 생길 때

## 13. 자동 commit release gate

현재 정책:

- OKF 최소 규칙, Example Organization Profile, Evidence/Bundle 참조 무결성, 민감정보 마스킹 절차를 통과한 변경만 자동 commit한다. Git 추적 Evidence는 `pii_scanned: true`가 필수다.

향후 검토할 항목:

- 자동 commit 실행기와 commit hash를 남기는 운영 로그
- Git hook 또는 CI에서의 독립 Validator 재실행
- commit 실패 시 재시도, 중복 commit 방지, rollback 절차
- `draft -> review -> active`와 자동 commit의 결합 방식

도입 조건:

- 실제 Git 원격 저장소와 Hermes 운영 계정이 연결되어 자동 commit을 실행할 때
