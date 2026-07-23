# 구현 착수 가이드

## 1. 기본 원칙

- 먼저 `OPERATING_RULES.md`를 읽고 Reference Traceability에서 직접 관련된 설계 문서만 선택한다.
- `docs/` 전체를 선제적으로 읽지 않는다.
- 데이터 모델이 먼저, 검색 엔진 연동은 나중이다.
- Validator가 없는 자동 생성은 금지한다.
- 자동 Commit은 Validator 통과 후에만 허용한다.
- OKF 적합성과 Example Organization OKF Profile 적합성을 별도로 검증한다.

## 2. MVP 정의

MVP는 `Minimum Viable Product`의 약자로, 전체 시스템을 모두 구현하기 전에 가장 작은 단위로 실제 운영 흐름이 끝까지 동작하는 버전이다.

이 프로젝트의 MVP는 다음 흐름을 완료하는 것이다.

```text
inbox 파일 1개
  -> .raw 이동 및 source_uuid 발급
  -> evidence 원본 보존 및 manifest 생성
  -> bundle 생성 또는 갱신
  -> OKF/Profile Validator 통과
  -> 자동 Commit
  -> 기본 검색으로 조회 가능
```

## 3. 첫 구현 대상

가장 먼저 구현할 대상은 다음 순서를 권장한다.

1. Bundle/Evidence 파일 모델
2. OKF Validator
3. Profile Validator
4. Ingest 파이프라인
5. Knowledge Service 읽기 API
6. 기본 검색
7. Curator 초안
8. MCP 읽기 Tool

## 4. 리뷰 프롬프트 예시

```text
OPERATING_RULES.md를 먼저 읽어.
Reference Traceability에서 아키텍처 리뷰에 필요한 문서만 선택해.
OKF와 Example Organization Profile을 구분해 전체 아키텍처를 리뷰해.
수정은 하지 말고 review만 해줘.
```

## 5. 구현 프롬프트 예시

```text
docs/03-okf-spec.md, docs/04-evidence-model.md, docs/06-knowledge-service.md를 기준으로
Python 프로젝트 골격을 생성해.
먼저 Validator와 파일 모델부터 구현해.
```

## 6. 저장소 분리 전략

규모가 커질 경우 아래 분리도 고려한다.

```text
circled-wiki-spec/
  docs/
  AGENTS.md
  decisions/
  roadmap/

circled-wiki/
  src/
  workspace/tests/
  docs/
  pyproject.toml
```

현재 단계에서는 설계 저장소를 먼저 단단하게 만드는 것이 우선이다.
