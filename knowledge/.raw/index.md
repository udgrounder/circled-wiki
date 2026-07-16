---
type: workspace
title: Raw Processing Queue
description: 처리 중 입력과 임시 작업 상태 보관소
tags: [raw, processing, staging]
timestamp: 2026-07-08T00:00:00+09:00
---

# Raw Processing Queue

이 디렉터리는 `inbox/`에서 들어온 입력이 실제 처리 대상으로 전환된 뒤 머무는 숨김 작업 공간이다. 성공한 작업의 원본은 `evidence/`에 보존하고 `.raw/`에서는 삭제한다.

## 용도

- UUID가 발급된 원본 입력의 처리 중 임시 보관
- 정규화 중인 입력 보관
- 처리 중 상태의 작업 파일 저장
- 큐레이션 중간 산출물 저장
- 실패 또는 검토 필요 항목의 재처리 대기

## 흐름

1. 입력은 `inbox/`로 들어온다.
2. 작업 대상은 `.raw/`로 이동하며 `source_uuid`를 발급받는다.
3. 원본은 `evidence/`에 보존되고, 정제 결과는 `bundles/`에 반영된다.
4. 처리 성공 시 `.raw/` 항목은 삭제한다.
5. 실패 또는 검토 필요 시 `.raw/` 또는 별도 검토 큐에서 재처리한다.
