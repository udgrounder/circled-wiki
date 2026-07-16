---
type: catalog
title: Knowledge Bundles
description: 공식 지식 번들 루트
tags: [knowledge, bundles]
timestamp: 2026-07-08T00:00:00+09:00
---

# Knowledge Bundles

정제된 공식 지식 문서는 이 디렉터리 아래에 도메인별로 저장한다.

## 규칙

- `bundles/`에 저장되는 문서는 반드시 OKF 구조를 따라야 한다.
- 모든 문서는 Markdown 본문과 YAML Frontmatter를 가진다.
- Bundle은 정제된 결과물이어야 하며, 최소 1개 이상의 Evidence를 참조해야 한다.
- 초안, 정책, 가이드, 결정문 등은 모두 Bundle로 저장될 수 있지만 포맷은 일관돼야 한다.
- 실행 Workflow는 각 도메인의 `runbooks/` 아래 `type: runbook`으로 저장한다.
- Business Rulebook은 관련 Policy·Guide·Runbook을 연결하는 `type: guide`로 도메인 루트에 저장한다.
- `active` Bundle은 Owner와 신선도 Governance를 가진다.

- [Company](./company/index.md)
- [Product](./product/index.md)
- [Engineering](./engineering/index.md)
- [CS](./cs/index.md)
- [Operations](./operations/index.md)
- [Marketing](./marketing/index.md)
