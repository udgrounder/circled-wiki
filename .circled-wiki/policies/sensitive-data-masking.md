---
type: policy-doc
title: Sensitive Data Masking Policy
description: Bundle/Evidence에 포함된 민감정보 마스킹 규칙
tags: [policy, security, pii]
timestamp: 2026-07-09T00:00:00+09:00
---

# Sensitive Data Masking Policy

## 목적

Git에 커밋되는 지식 산출물(Bundle 본문, Evidence Record, 10MB 이하의 외부 Evidence Original 및 Derived Artifact)에
고위험 식별자와 자격증명이 그대로 노출되지 않도록 하는 최소 규칙을 정의한다. 이 정책의 자동 점검은
일반적인 개인식별정보 전체를 분류하거나 마스킹하지 않는다.
Evidence 수명주기·불변성·PII Receipt의 정식 계약은 `OPERATING_RULES.md`의
RB-EVD-020·021·023과 RB-SEC-001·005·010을 적용하며 이 정책에서 다시 정의하지 않는다.

Git 히스토리는 되돌리기 어렵다. 마스킹은 커밋 이전 단계에서 반드시 완료되어야 하며,
커밋 이후 발견된 민감정보는 별도 이력 정리(rewrite) 대상으로 취급한다.

## 적용 대상

마스킹은 Git에 실제로 추적되는 텍스트에만 적용한다.

- `knowledge/bundles/**/*.md` 본문
- `knowledge/evidence/**/*.md` Evidence Record 본문 및 `derived_files`로 기록되는 정규화 텍스트
- Git에 추적하려는 10MB 이하 외부 Evidence Original

마스킹 대상이 아닌 것:

- Git에서 제외한 대용량 Evidence 원본은 RB-EVD-002·023에 따라 수정하지 않는다.
- Git에 올릴 원본에서 민감정보가 탐지되면 자동 마스킹하지 않고 Git 추적을 금지한다. 원본은 접근 통제가 가능한
  별도 저장소에 보존하고, Evidence 최초 생성 전 후보 텍스트와 Commit 전 Bundle 텍스트만 마스킹한다.

## 자동 마스킹 대상 범주

- 고위험 식별자: 주민등록번호, `계좌번호` 또는 `account number`로 명시된 계좌번호, Luhn 검증을 통과한 카드번호
- 자격증명: password, API key, access/refresh token, private key, secret, client secret 및 알려진 provider token 형식.
  OAuth authorize URL에서는 `client_secret`, authorization `code`, `code_verifier`, `access_token`,
  `refresh_token`, `id_token` 값도 같은 credential 하드 스캔으로 처리한다. `client_id`, `code_challenge`,
  `state`는 인증 자격증명이 아닌 OAuth 흐름 메타데이터이므로 원문을 보존하고 민감도 검토 후보로 전달한다.

이 Agent의 자동 점검은 이름, 지역번호·대표번호, 일반 계정 ID, 내부 IP·호스트명·URL을 기본적으로 마스킹하지 않는다.
휴대전화와 이메일 탐지기도 기능적으로 지원하지만 `data-protection.yaml`의 범주별 토글이 `false`이면 하드
PII 경로에서 처리하지 않는다. 매핑에서 빠진 지원 범주는 `true`로 간주하고, 기본 템플릿은 두 범주를 `false`로
명시한다. 이미 마스킹된 값은 정책을 완화해도 복원하지 않는다.

## 마스킹 표기 규칙

- 지정된 모든 값은 일부도 남기지 않고 `********`로 치환한다.
- 자격증명 label(`api_key=`, `token:`, `password=` 등)은 보존할 수 있지만 값 전체를 `********`로 치환한다.
- 주민등록번호·계좌번호·카드번호도 부분 노출하지 않는다.

## 적용 시점

- Inbox Capture 단계: 어떤 Agent·Adapter가 호출했는지와 무관하게 공통 Capture API가 저장 전에 대화·문서 텍스트와 저장할 텍스트 메타데이터를 자동 점검한다. 하드 마스킹 처리한 범주와 정책 판단 후보 범주를 각각 `capture_details.sensitive_data_precheck`에 기록한다.
- Inbox Inspection 단계: Capture 단계의 누락 가능성과 `sensitivity_review` 상태를 확인한다. 자동 점검 범위 밖 개인정보는 자동 변경하지 않는다.
- Inbox→Evidence 단계: `review-data-protection`이 RB-EVD-020의 PII Scan과 민감도 판단을 통합 수행하고
  최종 후보에 결합된 `data_protection_receipt`를 발행한다. Evidence Ingest는 RB-EVD-021·RB-SEC-010에 따라
  이 Receipt·checksum·생성 스키마와 전환 산출물만 검증한다.

## 탐지 결과 처리

- 하드 마스킹 패턴(`hard_mask_categories: true`인 주민등록번호·계좌번호·Luhn 카드번호·자격증명 등): 값은 `********`로 마스킹하고 Capture 메타데이터에 범주만 기록한다.
- Agent 판단 마스킹(`agent_mask_categories`의 `include` 범위에 해당하는 고객 휴대전화·급여·평가·징계·미공개 사업정보·보안 구성 또는 명시적인 불법 행위 실행·조장·은폐/권리 침해 지시): Agent가 정확한 범위를 판단하면 해당 텍스트만 `********`로 마스킹한다. 정책에 선언되지 않은 구성원·협력업체 업무 연락처와 계약·법률 자문·분쟁·소송·규제 대응 및 그 결정은 법무·업무 내용이라는 이유만으로 마스킹하지 않으며, 명시적인 불법성이 확인되지 않은 법률·계약 내용은 `unlawful_content`로 추정하지 않는다. 범주별 `exclude` 경계와 범위 불명확성을 우선하며, 범위가 실제 마스킹 대상에서 불명확할 때만 사용자 검토로 전환한다. 범주·횟수·근거는 Receipt에 남기되 원래 값은 남기지 않는다. 마스킹된 나머지 내용은 다음 처리 단계로 진행한다.
- 하드 마스킹 후 남은 PII Scan 후보: 탐지된 값은 통합 Data Protection Review에 전달한다. `agent_mask_categories`에 선언된 대상만 Agent가 정확한 범위를 지정해 `********`로 마스킹하며, 선언되지 않은 이메일·업무 연락처 등은 변경하지 않는다. 검토 큐·작업 기록에는 원래 값을 복사하지 않는다.
- 파일 원본, 패턴이 애매한 값 또는 자동 범위 밖 개인정보는 원본을 수정하지 않고 `sensitivity_review: required`로 유지한다. Agent는 적용 가능한 정책·절차와 근거가 있으면 이를 기록해 처리하고, 없을 때만 사용자에게 문의한다.
- PII Scan·민감도 판단 결과와 Evidence 생성값은 RB-EVD-020·RB-SEC-005를 적용한다. 정본은
  `data_protection_receipt`이며 `pii_scan_receipt`와 `sensitivity_inspection`은 호환 projection이다.
- Inbox 처리 흐름은 `review-data-protection`을 호출해 외부 Scanner 결과가 필요한 경우에도 같은 통합
  Receipt에 결합한다. 직접 Ingest는 `passed` 또는 `masked` 통합 Receipt 없이는 허용하지 않는다.

## 주의사항

- 자동 마스킹은 오탐/미탐 가능성이 있다. 이 기능은 지정된 범주의 보수적 사전 점검일 뿐, 전체 개인정보 검사가 아니다.
- 자동 마스킹 성공을 `pii_scanned`로 해석하지 않는다. 발행·Commit Gate는 RB-PUB-002·004와 RB-CUR-006을 적용한다.
