---
type: template
title: Claim Support Template
description: 중요 주장과 Evidence 지원 상태를 표현하는 템플릿
tags: [template, claim-support, evidence]
timestamp: 2026-07-14T00:00:00+09:00
---

# Claim Support Template

이 템플릿은 Agent 응답이나 검토 산출물에서 정책·보안·가격·법률·외부 등록 요건·성과 수치처럼 중요한
주장의 지원 상태를 표현한다. 공식 Bundle로 승격할 때는 YAML Frontmatter와 아래 Markdown 구획을 사용한다.

```yaml
claim: {주장}
support_status: {verified|limited|inferred|needs_review}
evidence_ids:
  - evidence://campingtalk/{provider}/{yyyy}/{mm}/{dd}/{source_uuid}
checked_at: {checked_at}
scope: {적용 범위}
limitations: []
```

## 확인된 내용

원본 Evidence로 직접 확인한 내용을 작성한다.

## 제한된 근거

근거가 있지만 적용 범위나 표본이 제한된 내용을 작성한다.

## 추정

Evidence에서 직접 확인되지 않은 해석을 작성한다.

## 확인 필요

근거 부족 또는 최신성 재확인이 필요한 내용을 작성한다.
