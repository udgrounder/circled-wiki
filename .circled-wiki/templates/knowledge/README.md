---
type: catalog
title: Knowledge
description: 조직 지식 Vault의 구조와 관리 원칙
tags: [knowledge, vault]
---

# Knowledge

이 폴더는 Obsidian Vault이자 조직 지식 관리 영역입니다.

사람과 Agent는 이 README를 기준으로 Vault의 운영·관리 정보를 확인합니다.

## 폴더 구조

- `bundles/`: Evidence를 바탕으로 정제·발행한 공식 지식 문서
- `bundles/.archive/`: 완료·대체·반려된 Bundle을 보관하는 숨김 폴더
- `evidence/`: 원본 근거와 Evidence Record
- `inbox/`: 검사·승인·변환을 기다리는 수집 입력
- `.raw/`: 처리 중인 임시 작업 영역
- `curation-reviews/`: 검토가 필요한 정제 제안 카드

`bundles/<domain>/`, `bundles/<domain>/runbooks/`, `evidence/<provider>/`, `inbox/<provider>/`는
실제 사용에 따라 생성되는 동적 경로입니다. 아직 사용하지 않은 domain·provider 폴더가 없더라도 지원 대상에서
제외된 것은 아닙니다.

## 운영 목록

현재 사용하는 domain과 provider의 이름·용도는 아래에 한 줄씩 기록합니다. 새 domain 또는 provider를 처음
사용하는 변경에서는 같은 변경에서 이 목록을 보완합니다. 이 목록은 Runtime이 강제하는 고정 enum이 아닙니다.

- Domain: 실제 운영 중인 Bundle domain과 용도
- Evidence provider: 실제 운영 중인 Evidence provider와 원본 성격
- Inbox provider: 실제 운영 중인 Inbox provider와 수집 방식

## 관리 원칙

- 이 폴더는 조직의 자산을 관리·운영하는 영역입니다.
- 공식 지식은 `bundles/` 아래에서, 근거 원문은 `evidence/` 아래에서 관리합니다.
- 폴더 구조·역할·운영 흐름 또는 이 폴더의 운영·관리에 필요한 정보가 새로 생기거나 변경되면 이 README의 관련 설명을 함께 갱신합니다.
- 새 domain·provider를 처음 사용하거나 기존 이름의 의미를 바꾸면, 같은 변경에서 이 README의 운영 목록을 갱신합니다.
- 개별 Evidence·Bundle·Inbox 문서의 목록·요약·세부 내용은 이 README에 기록하지 않습니다.
