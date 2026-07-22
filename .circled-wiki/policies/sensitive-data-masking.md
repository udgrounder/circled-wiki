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
자격증명이나 개인식별정보가 그대로 노출되지 않도록 하는 최소 규칙을 정의한다.

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

## 마스킹 대상 범주

- 자격증명: password, API key, token, private key, secret, connection string
- 개인식별정보: 주민등록번호, 카드번호, 전화번호, 이메일 주소
- 내부 시스템 정보: 내부 IP, 내부 호스트명, 사내 전용 URL 중 비공개 성격이 강한 값

## 마스킹 표기 규칙

- 기본 규칙: 식별에 필요한 최소 일부만 남기고 나머지는 `*`로 치환한다.
  - 예: `jane.doe@example.com` -> `j***@e***.com`
  - 예: `010-1234-5678` -> `010-****-5678`
- 자격증명(password, API key, token, private key)은 부분 노출 없이 전체를 `********`로 치환한다.
- 계정 ID와 함께 기록된 비밀번호도 비밀번호 값 전체를 `********`로 치환한다. 계정 ID는 업무상 식별이 꼭 필요한 경우에만 최소 범위로 남긴다.
- 주민등록번호, 카드번호는 앞 6자리 또는 앞 4자리까지만 남기고 나머지는 `*`로 치환한다.

## 적용 시점

- Inbox Capture 단계: 저장 전에 대화·문서 텍스트의 명확한 PII와 자격증명을 `*`로 1차 마스킹한다.
- Inbox Inspection 단계: 내용을 다시 읽어 1차 마스킹 누락·과소 마스킹·문맥상 재식별 가능성을 2차 확인한다.
- Evidence 단계: 정규화 텍스트(`derived_files`)를 생성할 때 별도의 실제 PII Scan과 마스킹을 수행한다.
- Bundle 단계: Curator가 Bundle 본문을 생성·수정할 때 커밋 전 최종 Scan을 수행한다.
- 각 단계의 확인을 구분해 기록하며, 커밋 직전 Validator와 Publication Security Review에서 증빙을 확인한다.

## 탐지 결과 처리

- 패턴이 명확한 경우(정규식 매칭): 값은 `*` 표기로 마스킹하고 `extensions.pii_masked: true`로 기록한다.
- 패턴이 애매하거나 고위험으로 판단되는 경우(예: private key block 전체, 대량 개인정보 테이블): 자동 마스킹 대신
  Evidence 상태를 `needs_review`로 전환하고 사람 검토를 거친다.
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

- 자동 마스킹은 오탐/미탐 가능성이 있다. 100% 신뢰하지 말고 `pii_scanned`가 없는 구버전 문서는 우선 재스캔 대상으로 취급한다.
- 마스킹 규칙 자체(정규식 목록)는 구현 시 별도 설정 파일로 관리하고, 이 문서는 규칙의 정책적 기준으로 유지한다.
