# 프로젝트 기획서

## 공식 참고 링크

- Open Definition 2.1: [https://opendefinition.org/od/2.1/en/](https://opendefinition.org/od/2.1/en/)
- Google Cloud OKF 공식 저장소: [https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- Google Cloud OKF 공식 스펙: [https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)

## 1. 프로젝트명

Campingtalk AI Knowledge Operating System

## 2. 추진 배경

Campingtalk 내부의 정책, 제품 지식, 운영 지식, 고객 응대 기준, 개발 문맥은 여러 도구에 분산되어 있다.
이 상태에서는 사람이 정보를 찾는 비용이 높고, AI Agent도 일관된 최신 지식을 사용하기 어렵다.

따라서 단순 위키가 아니라, 원본 수집부터 정제, 검증, 검색, AI 제공까지 포함하는
지식 운영 체계를 구축할 필요가 있다.

## 3. 프로젝트 목표

- 사내 지식을 Git 기반으로 일관되게 축적한다.
- 공식 지식과 원본 데이터를 분리해 관리한다.
- OKF 기반 표준 포맷으로 지식을 관리한다.
- 자료의 수집 이유와 적용 업무를 함께 보존해 목적 없는 축적을 방지한다.
- 도메인별 Runbook으로 기존 업무 지식을 실행 가능한 Workflow로 제공한다.
- Hermes가 지식 라이브러리를 지속적으로 수집·정제·검증·갱신하고, 사용자 요청 시 그 지식을 사용하는 운영 Agent가 되도록 한다.
- Codex, Claude Code, Gemini 등 여러 Agent가 동일한 인터페이스로 지식을 사용하게 한다.
- 사용자 제공 레퍼런스와 Agent 산출물을 근거 수준·검증자·적용 범위와 함께 평가한다.
- 지식 Inventory와 Audit을 저장된 중복 문서가 아니라 재생 가능한 파생 조회로 제공한다.

## 4. 기대 효과

- 지식 탐색 시간 단축
- 정책/운영 문서 품질 향상
- AI Agent 응답 정확도 향상
- 조직 지식의 추적성과 감사 가능성 확보
- 신규 팀원 온보딩 비용 절감

## 5. 범위

### 포함 범위

- 지식 저장소 구조 설계
- Evidence 저장 모델 정의
- OKF Bundle 작성 규칙 정의
- Hermes 역할 설계
- Knowledge Service 및 MCP 인터페이스 정의
- 검색 및 동기화 파이프라인 설계
- Business Rulebook, Runbook, Inquiry와 지식 신선도 거버넌스
- Claim Support, Reference Assessment, Archive lifecycle, Artifact Profile과 구조화 Outcome

### 제외 범위

- 실시간 webhook 기반 외부 SaaS 연동 구현
- `docs/13-future-work.md`에 분리한 보류 항목의 실제 구현
- 실제 사내 인증/권한 체계 세부 구현

## 6. 성공 기준

- 공식 문서가 Open Definition의 개방성 원칙과 저장소 프로파일을 함께 만족한다.
- 공식 문서가 `Campingtalk OKF Profile` 검증을 통과한다.
- 모든 공식 문서가 Evidence를 추적할 수 있다.
- 주요 AI Agent가 공통 MCP 인터페이스로 지식을 조회할 수 있다.
- Hermes가 외부 정보의 변경분을 지속적으로 Evidence와 Bundle에 반영하고, 사용자 요청 시 출처 있는 지식을 활용한다.
- 주요 반복 업무가 `bundles/<domain>/runbooks/`의 검증된 Workflow로 실행된다.
- 활성 지식은 Owner와 다음 검토 기한을 가진다.
- 비활성 지식은 기본 Context에서 제외되고 명시적 조사에서만 사용된다.
- 중요한 주장은 Evidence 지원 상태를 구분하며 사용자 레퍼런스는 독립 검증 없이 자동 채택되지 않는다.
- 구현팀이 문서만으로 서비스 골격을 만들 수 있다.

## 7. 산출물

- 문서 저장소
- AGENTS 규칙 문서
- 데이터 모델 스펙
- 컴포넌트 아키텍처 문서
- 단계별 구현 로드맵

## 8. 추진 원칙

- Git Repository를 Source of Truth로 사용한다.
- Obsidian은 사람 편집 UI로 사용한다.
- OKF를 준수하고 필요한 범위만 확장한다.
- 확장은 `extensions`와 별도 프로파일 규칙으로만 정의한다.
- 모든 지식은 Evidence를 기반으로 관리한다.
- 구현보다 설계를 먼저 고정한다.
