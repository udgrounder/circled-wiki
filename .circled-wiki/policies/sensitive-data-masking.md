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

- 고위험 식별자: 주민등록번호, `계좌번호` 또는 `account number`로 명시된 계좌번호, Luhn 검증을 통과한 카드번호,
  `010` 또는 `+82 10` 형식의 휴대전화 번호
- 자격증명: password, API key, access/refresh token, private key, secret, client secret 및 알려진 provider token 형식

이 Agent의 자동 점검은 이름, 이메일 주소, 지역번호·대표번호, 일반 계정 ID, 내부 IP·호스트명·URL을 마스킹하지 않는다.
그 값에 별도 조직 정책이 적용되면 Agent가 해당 정책을 적용하고, 적용할 절차나 근거가 없을 때만 사용자 검토 또는 별도 보안 도구로 전환한다.

## 마스킹 표기 규칙

- 지정된 모든 값은 일부도 남기지 않고 `********`로 치환한다.
- 자격증명 label(`api_key=`, `token:`, `password=` 등)은 보존할 수 있지만 값 전체를 `********`로 치환한다.
- 주민등록번호·계좌번호·카드번호도 부분 노출하지 않는다.

## 적용 시점

- Inbox Capture 단계: 어떤 Agent·Adapter가 호출했는지와 무관하게 공통 Capture API가 저장 전에 대화·문서 텍스트와 저장할 텍스트 메타데이터를 자동 점검·마스킹한다. 처리한 범주만 `capture_details.sensitive_data_precheck`에 기록한다.
- Inbox Inspection 단계: Capture 단계의 누락 가능성과 `sensitivity_review` 상태를 확인한다. 자동 점검 범위 밖 개인정보는 자동 변경하지 않는다.
- Evidence 단계: RB-EVD-021·RB-SEC-010의 독립 재검수와 안전한 파생 입력 절차를 적용한다.

## 탐지 결과 처리

- 패턴이 명확한 경우(주민등록번호·명시된 계좌번호·Luhn 카드번호·휴대전화 번호·자격증명): 값은 `********`로 마스킹하고 Capture 메타데이터에 범주만 기록한다.
- 파일 원본, 패턴이 애매한 값 또는 자동 범위 밖 개인정보는 원본을 수정하지 않고 `sensitivity_review: required`로 유지한다. Agent는 적용 가능한 정책·절차와 근거가 있으면 이를 기록해 처리하고, 없을 때만 사용자에게 문의한다.
- PII Scan 결과와 Evidence 생성값은 RB-EVD-020·RB-SEC-005를 적용한다. Inbox Sensitive Data Review와
  자동 마스킹 결과는 PII Scan Receipt를 대신하지 않는다.
- Inbox 처리 흐름은 CLI `record-inbox-pii-scan` 또는 operator MCP
  `record_inbox_pii_scan`으로 외부 검사 결과를 Evidence 생성 전에 기록한다. 직접 Ingest는 같은 영수증을
  생성 입력으로 전달한다.

## 주의사항

- 자동 마스킹은 오탐/미탐 가능성이 있다. 이 기능은 지정된 범주의 보수적 사전 점검일 뿐, 전체 개인정보 검사가 아니다.
- 자동 마스킹 성공을 `pii_scanned`로 해석하지 않는다. 발행·Commit Gate는 RB-PUB-002·004와 RB-CUR-006을 적용한다.
