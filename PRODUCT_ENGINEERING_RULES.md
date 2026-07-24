# Circled Wiki Product Engineering Rules

**Status:** Normative
**Applies to:** 이 source repository에서 제품을 개발·검증·설치·배포하는 Agent

## Product Boundary

- 이 저장소는 Wiki 콘텐츠를 직접 운영하는 설치본이 아니라 Circled Wiki 제품의 Source of Truth다.
- Product Agent는 코드, Runtime 규칙, 설치·업그레이드 도구, 테스트와 제품 문서를 변경한다.
- 설치본의 Runtime Agent는 `.circled-wiki/AGENT_ROUTER.md`와 `.circled-wiki/OPERATING_RULES.md`를 사용한다.
- Product Profile과 source-only 문서는 Runtime release에 포함하지 않는다.

## Change Invariants

- 변경 Scope와 사용자 소유 파일을 구분하고 기존 작업 트리 변경을 보존한다.
- 설치·upgrade는 `knowledge/`, `workspace/`, 설치 로컬 config를 관리 자산으로 등록하거나 덮어쓰지 않는다.
- 실제 조직명, 사용자 원문, credential, 머신 절대 경로와 설치별 비밀 식별자를 제품 기본값에 하드코딩하지 않는다.
- 운영 Issue는 사용자의 명시적 수집 요청, 사용자 검토와 Triage 없이 제품 변경 권한이 되지 않는다.
- 제품 수정 완료는 운영 설치본에서 검증된 해결을 의미하지 않는다.

## Issue Improvement Flow

```text
operational issue
  -> explicit intake request
  -> workspace/issue/inbox
  -> archive history review
  -> user review
  -> triage
  -> engineering
  -> release
  -> deployment
  -> independent runtime verification
  -> workspace/issue/archived/YYYY/MM/YYYYMMDDTHHMMSSZ-<canonical-key>-vNNNN.md
```

- 이동 대상 운영 Issue는 Git에 추적·커밋되어 있고 미커밋 변경이 없어야 한다.
- 이동 실패 시 원본이 남아 있는지 확인하고 성공을 주장하지 않는다.
- 재발·회귀는 날짜별 Archive 파일의 동일 canonical key·occurrence와 해결책·회귀 테스트·검증 결과를 검토한다.
- Workspace Issue Archive는 `YYYY/MM` 날짜 폴더에 파일 하나씩 보관하며, 파일명과 Frontmatter에 occurrence를 보존한다.
  Archive는 삭제 대체물이 아니라 처리 완료 이력이며 Git이 이동 전 원본의 복구 수단이다.

## Verification and Publication

- 관련 테스트와 `circled_wiki.cli validate`를 통과한다.
- 배포 release는 Runtime Router, Runtime Profile allowlist와 관리 자산 checksum을 재현할 수 있어야 한다.
- `knowledge/`와 설치본 `workspace/`의 보존을 canary upgrade에서 확인한다.
- Commit, push, 외부 배포는 각각 명시적으로 승인된 범위에서만 수행한다.

## Rule Precedence

```text
PRODUCT_ENGINEERING_RULES
  > selected Product Profile
  > approved change or deployment scope
  > implementation preference
```

하위 지침은 보존·보안·검토·검증 Gate를 완화할 수 없다.
