# 비전 문서

## 1. 비전

Example Organization의 모든 핵심 지식이 사람과 AI Agent 모두에게 동일한 형태로 제공되는
`AI Knowledge Operating System`을 구축한다.

## 2. 왜 필요한가

현재 조직 지식은 Notion, Slack, GitHub, 회의록, 운영 문서 등 다양한 위치에 흩어져 있다.
이 구조에서는 다음 문제가 반복된다.

- 최신 정보가 어디 있는지 불명확하다.
- 정책 변경 이력이 추적되지 않는다.
- 원본과 정리본의 관계가 끊긴다.
- AI Agent마다 참고하는 문맥이 달라진다.
- 지식 업데이트가 사람 개인에게 의존한다.
- 자료를 왜 수집했고 어느 업무에 사용할지 남지 않는다.
- 기존 업무 절차와 미해결 질문이 실행 가능한 형태로 연결되지 않는다.

## 3. 목표 상태

목표 상태는 아래와 같다.

- 원본은 Evidence로 저장된다.
- 공식 지식은 OKF Bundle로 저장된다.
- Hermes가 외부 정보의 변경분을 Evidence로 축적하고, 이를 정제해 Bundle을 지속적으로 유지한다.
- 사람은 Obsidian에서 읽고 편집한다.
- Hermes와 다른 AI Agent는 Knowledge MCP를 통해 최신 지식을 사용한다. Hermes는 평소에는 라이브러리를 운영하고, 사용자 요청 시에는 그 라이브러리를 이용해 응답과 작업을 수행한다.
- 반복 업무는 도메인별 Runbook으로 실행되고 결과는 Evidence로 환류된다.
- 조직 맥락, 업무 Rulebook과 미해결 Inquiry가 공식 Bundle로 제공된다.

## 4. 핵심 철학

### Git as Truth

정제된 공식 지식의 기준은 Git 저장소다.

### Human-Friendly Authoring

사람은 Obsidian Vault를 통해 Markdown 문서를 쉽게 읽고 수정한다.

### Evidence-Driven Knowledge

공식 지식은 반드시 근거가 있어야 하며, 근거는 Evidence로 추적 가능해야 한다.
Evidence는 수집 이유와 적용 업무를 함께 기록한다.

### Workflow-Ready Knowledge

하나의 실행 Workflow는 하나의 Runbook으로 관리한다. 실행 결과는 다시 Evidence가 되어 다음 revision의
근거가 되며, 단일 결과를 자동으로 조직 표준으로 일반화하지 않는다.

### OKF-First Design

포맷은 자체 규격이 아니라 OKF를 우선 채택한다.
다만 구현 검증을 위해 저장소 차원의 `Example Organization OKF Profile`을 별도로 둔다.
여기서 OKF는 우선 개방성 기준이며, Bundle 필드 구조는 그 위에 정의한 저장소 프로파일로 고정한다.

### AI Interoperability

특정 AI Agent에 종속되지 않는 공통 인터페이스를 제공한다.

## 5. 비목표

- 처음부터 모든 사내 시스템을 자동 동기화하는 것
- 완벽한 검색 품질을 첫 단계에서 달성하는 것
- Agent 완전 자율 운영을 즉시 구현하는 것

## 6. 설계 판단 기준

아래 기준으로 아키텍처와 구현을 판단한다.

- 추적 가능한가
- 표준에 맞는가
- 사람과 AI가 함께 쓰기 쉬운가
- Source of Truth가 명확한가
- 이후 자동화와 확장에 유리한가
