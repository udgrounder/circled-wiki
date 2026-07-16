---
type: catalog
title: Campingtalk Knowledge Vault
description: Campingtalk 내부 지식 저장소 루트
tags: [knowledge, vault, root]
timestamp: 2026-07-08T00:00:00+09:00
---

# Campingtalk Knowledge Vault

이 디렉터리는 Campingtalk의 실제 지식 저장소이자 Obsidian Vault 기준 경로다.

## 하위 구조

- [Bundles](./bundles/index.md)
- [Evidence](./evidence/index.md)
- [Inbox](./inbox/index.md)
- [Raw Processing](./.raw/index.md)

## 운영 원칙

- 사람은 이 디렉터리를 Obsidian에서 직접 연다.
- 공식 지식은 `bundles/` 아래에서 관리한다.
- 원본 근거는 `evidence/` 아래에 저장한다.
- Evidence는 수집 이유와 적용 업무를 함께 기록한다.
- 실행 Workflow는 `bundles/<domain>/runbooks/`에서 관리한다.
- 수집 대기 항목은 `inbox/`에서 관리한다.
- 처리 중 작업 상태는 `.raw/`에서 관리한다. 성공한 원본은 `evidence/`에 보존하고 `.raw/`에서는 삭제한다.
- 운영 템플릿·스키마·시스템 정책은 이 Vault가 아니라 프로젝트의 `.knowledge-os/`에서 관리한다.
