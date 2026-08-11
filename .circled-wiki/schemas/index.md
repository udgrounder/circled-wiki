---
type: catalog
title: Schemas
description: 검증 스키마와 데이터 규칙
tags: [schemas]
timestamp: 2026-07-08T00:00:00+09:00
---

# Schemas

## Runtime YAML 규칙

Runtime이 읽는 설치별 YAML 설정·정책·taxonomy는 같은 이름의 JSON Schema를 이 폴더에 둔다. 새 파일 또는 형식 변경은
Schema 작성·`schema_version` 선언·이 목록 등록·공용 `validate_yaml_payload` 연결·`circled-wiki validate-configuration`
검증을 하나의 변경으로 완료한다. 세부 의무와 제외 대상은 `OPERATING_RULES.md`의 RB-KNW-028을 따른다.

## 버전 관리

`$schema`는 JSON Schema 문법의 버전이고, YAML `schema_version`은 운영 데이터 계약의 버전이다. 이 둘은 다르게
관리한다. [Schema Registry](./schema-registry.json)는 YAML 경로별 현재 버전과 지원 Schema를 색인한다. 호환을 깨는
변경은 새 `schema_version`과 새 Schema 파일을 추가하고 이전 파일을 보존한다. 모든 Runtime YAML Schema는 처음부터
`<name>.schema.v<version>.json`으로 병존시킨다. 자세한 승격·migration·지원 종료 규칙은 RB-KNW-029를 따른다.

모든 Schema의 `$id`는 `https://schemas.circled-wiki.invalid/` 아래의 절대 URI를 사용한다. 이는 외부 네트워크
조회용 주소가 아니라 내부 `$ref`의 안정적인 base URI다. 상대 경로 `$id`는 지원하는 JSON Schema 해석기 사이에서
fragment `$ref`를 다르게 결합할 수 있으므로 사용하지 않는다.

- [Bundle JSON Schema](./bundle.schema.json)
- [Evidence Record JSON Schema](./evidence-manifest.schema.json)
- [Curation Taxonomy JSON Schema v1](./curation-taxonomy.schema.v1.json)
- [Installation Configuration JSON Schema v1](./config.schema.v1.json)
- [Data Protection Policy JSON Schema v1](./data-protection.schema.v1.json)
- [User Notification JSON Schema v1](./user-notification.schema.v1.json)
- [Runtime YAML Schema Registry](./schema-registry.json)
