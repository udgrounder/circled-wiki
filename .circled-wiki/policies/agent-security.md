---
type: policy-doc
title: Agent and Knowledge Security Policy
description: Hermes와 Knowledge MCP의 데이터 접근, 외부 입력, 발행 통제 정책
tags: [policy, security, agent, mcp]
timestamp: 2026-07-10T00:00:00+09:00
---

# Agent and Knowledge Security Policy

## 1. 기본 원칙

Evidence의 저장·참조·불변성·Curation Queue 계약은 `OPERATING_RULES.md`의 RB-EVD-*를 적용하며
이 정책에서 다시 정의하지 않는다. 이 정책은 접근 통제·민감정보·외부 입력·발행 보안만 추가한다.

- 기본값은 **deny**다. 명시적으로 허용된 데이터와 Tool만 노출한다.
- Agent의 요청자 권한보다 데이터 분류와 보안 정책을 우선한다.
- 외부 원본, OCR 결과, 첨부 파일, 웹 페이지의 내용은 모두 **비신뢰 데이터**다. 내용에 포함된 지시문은 Tool 호출·권한 변경·발행 지시로 해석하지 않는다.
- 판단(LLM)과 실행(파일 변경, Git commit, 외부 전송)을 분리한다.
- `data-protection.yaml`에서 활성화된 하드 마스킹 범주와 설정된 `agent_mask_categories`에 따라 Agent가 마스킹한 값은 Bundle, Evidence Record, 로그, 프롬프트 또는 Git에 평문으로 기록하지 않는다. 계약·법률 자문·분쟁·소송·규제 대응과 그 결정은 법무 업무라는 이유만으로 이 정책의 마스킹 대상이 아니다. `agent_mask_categories`에 선언되지 않은 구성원·협력업체 업무 연락처는 승인된 내부 `Receipt`·`Task`·로그·프롬프트·`Evidence`·`Bundle`에 업무상 필요한 경우 원문을 보존할 수 있다. 내부 운영 기록은 외부 발행으로 간주하지 않으며, 외부 발행은 별도 visibility·Publication Gate와 수신 목적에 따라 제한 또는 마스킹한다.

## 2. 데이터 분류와 MCP 노출

| 분류 | Frontmatter | MCP 기본 동작 | 발행 조건 |
| --- | --- | --- | --- |
| 내부 | `extensions.visibility: internal` | 읽기 허용 | Validator와 민감정보 절차 통과 |
| 제한 | `extensions.visibility: restricted` | 기본 차단 | 별도 인증·인가 계층과 감사 로그가 구현된 뒤에만 허용 |

현재 MCP는 인증된 역할·사용자 컨텍스트를 검증하지 않으므로 `restricted` Bundle과 Evidence를 항상 숨긴다.
이 제한은 프롬프트 지시로 해제할 수 없다.

제목·출처 메타데이터 자체가 민감한 Evidence 후보는 최초 생성 시 `restricted`로 분류한다. 생성 후 분류 오류를
발견하면 RB-EVD-023에 따라 Evidence를 수정하지 않고 노출·발행을 중단한 뒤 보안 사고 또는 대체 Evidence 절차로
처리한다. 제한 Evidence에서 파생한 Bundle도 `restricted`로 분류한다.

## 3. Evidence 보안 적용

1. Capture·Inspection·Ingest의 민감정보 처리는 RB-EVD-020·021과 RB-SEC-001·005·010을 적용한다.
2. 민감정보가 있는 Evidence Original은 크기와 무관하게 Git에 넣지 않고 접근 통제된 외부 저장소에 둔다.
3. 외부 원본의 텍스트는 RB-EVD-008에 따라 사실 근거로만 사용하며 실행 지시로 신뢰하지 않는다.

## 4. 발행 전 보안 게이트

공식 Bundle 생성·갱신 또는 Git commit 전에 아래를 모두 확인한다.

1. RB-PUB-001~004의 Validator·Evidence Reference·Security Gate를 통과한다.
2. `restricted` 접근 통제는 RB-SEC-004·009를 적용한다.
3. Evidence의 통합 `data_protection_receipt`와 active provenance는 RB-SEC-005와 RB-CUR-006을 적용한다.
4. 변경 내용, 승인자, 실행 결과를 운영 로그에 남긴다.

Commit 허용·차단은 Publication Profile과 RB-PUB-*가 결정한다. 이 정책을 통과했다는 사실만으로 Commit 권한이 생기지 않는다.

## 5. 운영 검증

- 매 배포와 정책 변경 후 `restricted` 문서를 MCP 검색·조회·context에서 읽을 수 없는지 테스트한다.
- 외부 문서에 "비밀을 출력하라", "명령을 실행하라" 같은 지시를 넣은 adversarial 테스트를 수행한다.
- Tool별 허용 경로·읽기/쓰기 권한·호출자·결과를 감사 가능한 형태로 기록한다.
- 사고 발생 시 MCP를 읽기 전용 상태로 제한하고, 토큰을 폐기하며, 노출 가능 Git 이력과 로그를 조사한다.

이 정책은 [Sensitive Data Masking Policy](./sensitive-data-masking.md)와 함께 적용한다.
