---
type: catalog
title: Knowledge Bundles
description: 공식 지식 Bundle과 도메인 폴더 안내
tags: [knowledge, bundles, catalog, active-knowledge, readme]
timestamp: 2026-07-08T00:00:00+09:00
---

# Knowledge Bundles

정제된 공식 지식 문서는 이 디렉터리 아래에 도메인별로 저장한다. 파일 위치는 탐색용이며, 영구 참조는
`bundle/{organization_id}/{filename}.md` ID를 사용한다.

## 규칙

- `bundles/`에 저장되는 문서는 반드시 OKF 구조를 따라야 한다.
- 모든 문서는 Markdown 본문과 YAML Frontmatter를 가진다.
- Bundle은 정제된 결과물이어야 하며, 최소 1개 이상의 Evidence를 참조해야 한다.
- 초안, 정책, 가이드, 결정문 등은 모두 Bundle로 저장될 수 있지만 포맷은 일관돼야 한다.
- 실행 Workflow는 각 도메인의 `runbooks/` 아래 `type: runbook`으로 저장한다.
- Business Rulebook은 관련 Policy·Guide·Runbook을 연결하는 `type: guide`로 도메인 루트에 저장한다.
- `active` Bundle은 Owner와 신선도 Governance를 가진다.
- `draft` Bundle은 후보이며 기본 질의·Workflow 실행 결과에는 포함하지 않는다.
- Bundle의 `tags`에는 최소 `bundles`, 문서 type, domain을 기록한다.

## 검토 흐름

`Evidence → Draft Bundle → Reviewer → Owner·Security Gate → Active Bundle`

## 도메인 폴더

| 폴더 | 저장 대상 |
| --- | --- |
| `company/` | 전사 공통 정책, 조직 맥락, 공통 가이드와 결정 |
| `product/` | 제품 원칙, 요구사항, 제품 의사결정과 학습 |
| `engineering/` | 개발 원칙, 시스템 설계, 기술 운영 가이드와 결정 |
| `cs/` | 고객 지원 정책, 응대 가이드와 고객 관련 결정 |
| `operations/` | 운영 정책, 서비스 운영 가이드와 업무 기준 |
| `marketing/` | 마케팅 정책, 채널 운영 가이드와 캠페인 학습 |

실행 가능한 Runbook은 각 도메인의 `runbooks/` 하위에 `type: runbook`으로 저장한다. 도메인과 Runbook
하위 폴더에는 별도 index 또는 README를 자동 생성·갱신하지 않는다.

## 파일 배치 예시

```text
bundles/
  marketing/
    channel-guide_<bundle_uuid>.md
    runbooks/
      campaign-launch_<bundle_uuid>.md
```

파일 경로는 탐색을 위한 것이고, 공식 참조에는 Bundle Frontmatter의 `bundle/{organization_id}/{filename}.md`
ID를 사용한다.
