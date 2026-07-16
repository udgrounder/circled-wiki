---
type: catalog
title: Evidence Store
description: 원본 근거 저장소 루트
tags: [evidence]
timestamp: 2026-07-08T00:00:00+09:00
---

# Evidence Store

원본 입력은 provider별로 저장한다. `evidence/`는 정제본이 아니라 원본 파일 자체를 보존하는 위치이며, 각 공식 Evidence는 참조와 검증을 위한 manifest를 함께 가진다.

처리 완료된 원본 파일은 이 위치에 보존한다. 10MB 이하 원본은 같은 basename의 `.md` manifest와 함께 Git에 추적한다. 10MB 초과 원본은 별도 원본 저장소에 보존하고, Git에는 checksum과 보관 위치를 담은 manifest만 추적한다.

- [Notion](./notion/index.md)
- [Slack](./slack/index.md)
- [GitHub](./github/index.md)
- [Meetings](./meetings/index.md)
