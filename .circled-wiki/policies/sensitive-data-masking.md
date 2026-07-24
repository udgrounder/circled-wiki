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

Git 히스토리는 되돌리기 어렵다. 마스킹은 커밋 이전 단계에서 반드시 완료되어야 하며,
커밋 이후 발견된 민감정보는 별도 이력 정리(rewrite) 대상으로 취급한다.

## 적용 대상

마스킹은 Git에 실제로 추적되는 텍스트에만 적용한다.

- `knowledge/bundles/**/*.md` 본문
- `knowledge/evidence/**/*.md` Evidence Record 본문 및 `derived_files`로 기록되는 정규화 텍스트
- Git에 추적하려는 10MB 이하 외부 Evidence Original

마스킹 대상이 아닌 것:

- Git에서 제외한 대용량 Evidence 원본은 수정하지 않는다. 원본 자체를 고치는 것은 Evidence 무결성 원칙(04-evidence-model.md)과 충돌한다.
- Git에 올릴 원본에서 민감정보가 탐지되면 자동 마스킹하지 않고 Git 추적을 금지한다. 원본은 접근 통제가 가능한 별도 저장소에 보존하고, Bundle/manifest 쪽 텍스트만 마스킹한다.

## 자동 마스킹 대상 범주

- 고위험 식별자: 주민등록번호, `계좌번호` 또는 `account number`로 명시된 계좌번호, Luhn 검증을 통과한 카드번호
- 자격증명: password, API key, access/refresh token, private key, secret, client secret 및 알려진 provider token 형식

이 Agent의 자동 점검은 이름, 이메일 주소, 전화번호, 일반 계정 ID, 내부 IP·호스트명·URL을 마스킹하지 않는다.
그 값에 별도 조직 정책이 적용되면 해당 정책의 사람 검토 또는 별도 보안 도구가 결정한다.

## 마스킹 표기 규칙

- 지정된 모든 값은 일부도 남기지 않고 `********`로 치환한다.
- 자격증명 label(`api_key=`, `token:`, `password=` 등)은 보존할 수 있지만 값 전체를 `********`로 치환한다.
- 주민등록번호·계좌번호·카드번호도 부분 노출하지 않는다.

## 적용 시점

- Inbox Capture 단계: 어떤 Agent·Adapter가 호출했는지와 무관하게 공통 Capture API가 저장 전에 대화·문서 텍스트와 저장할 텍스트 메타데이터를 자동 점검·마스킹한다. 처리한 범주만 `capture_details.sensitive_data_precheck`에 기록한다.
- Inbox Inspection 단계: Capture 단계의 누락 가능성과 `sensitivity_review` 상태를 확인한다. 자동 점검 범위 밖 개인정보는 자동 변경하지 않는다.
- Evidence 단계: 수집 주체와 독립된 Ingest Agent가 Inbox를 읽어 변환하기 직전에 지정된 범주를 다시 점검한다. 텍스트에서 감지하면 실제 값 없이 범주만 결과에 남기고 마스킹한 안전한 파생본을 Evidence로 만든다. PII Scan 영수증은 선택적 외부 검사 증빙이며 Draft·Commit·Push Gate가 아니다.

## 탐지 결과 처리

- 패턴이 명확한 경우(주민등록번호·명시된 계좌번호·Luhn 카드번호·자격증명): 값은 `********`로 마스킹하고 Capture 메타데이터에 범주만 기록한다.
- 파일 원본, 패턴이 애매한 값 또는 자동 범위 밖 개인정보는 원본을 수정하지 않고 `sensitivity_review: required`로 유지해 사람 검토를 거친다.
- Evidence PII Scan을 실제 수행하고 Scanner·버전·시각·결과·검토자·Receipt와 현재 Evidence checksum이
  결합된 `extensions.pii_scan` 영수증이 있는 Evidence Record만 `extensions.pii_scanned: true`를 기록한다.
  Inbox Sensitive Data Review의 `completed` 또는 `not_applicable`, 1차·2차
  마스킹 확인은 이 값을 자동으로 만들지 않는다. Bundle은 별도 `pii_scanned` 플래그를 두지 않고, 최종 결과 상태를
  `extensions.pii_masked`와 `extensions.visibility`로 관리한다.
- 운영 Agent는 boolean을 직접 편집하지 않고 CLI `record-evidence-pii-scan` 또는 operator MCP
  `record_evidence_pii_scan`으로 외부 검사 결과를 기록한다. 이 작업은 검사를 실행하지 않는다.

## 추적 필드

- `extensions.pii_scanned`: Evidence Record의 실제 Evidence PII Scan 수행 여부
- `extensions.pii_masked`: 마스킹 적용 여부
- `extensions.pii_scan`: Scanner, 버전, 시각, 결과, 검토자, 외부 Receipt, 원문 checksum을 보존하는 검사 증빙
- `extensions.visibility`: `internal`(기본값) 또는 `restricted`. MCP 계층은 `restricted` 문서를 기본 조회 결과에서
  제외하거나 별도 권한 확인 후에만 노출해야 한다.

## 주의사항

- 자동 마스킹은 오탐/미탐 가능성이 있다. 이 기능은 지정된 범주의 보수적 사전 점검일 뿐, 전체 개인정보 검사가 아니다.
- `pii_scanned`는 외부 PII 검사 영수증의 선택적 기록 필드다. 이 자동 점검의 성공·실패와 혼동하거나 Draft·Commit·Push Gate로 사용하지 않는다.
