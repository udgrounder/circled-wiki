# 개발 로드맵

## Phase 1. 문서 및 저장소 기반 구축

- `docs/` 문서 세트 작성
- `AGENTS.md` 규칙 확정
- 저장소 구조 확정
- OKF 템플릿 정의
- Campingtalk OKF Profile 정의
- `index.md` / `log.md` 보조 문서 규칙 정의
- Evidence 원본 Git 제외와 manifest 추적 정책 정의
- 도메인별 `runbooks/` 배치, Rulebook·Inquiry·Organization Context 모델 정의

산출물:

- 문서 저장소
- 초기 디렉터리 구조
- 운영 규칙 초안

## Phase 2. Evidence 레이어 구축

- Evidence 경로 규칙 구현
- URI 규칙 구현
- 상태 모델 구현
- `capture_context` 수집 목적 검증 구현
- `inbox -> .raw -> evidence -> bundles` 처리 구현
- `.raw` 성공 시 즉시 삭제, 실패/검토 시 보존 구현
- 참조 무결성 검사 초안
- Bundle/Evidence 교차 검증 초안
- OKF v0.1 최소 적합성과 Profile 적합성 분리 구현
- unknown field / broken link 허용 소비 정책 구현

산출물:

- Evidence 스키마
- 샘플 데이터
- Validator 일부

## Phase 3. Hermes Curator 구축

- Evidence -> Bundle 처리 흐름 구현
- 중복 검사 및 신규 생성 판단
- OKF 검증 연동
- Profile Validator 연동
- Validator 통과 후 자동 Commit
- Outcome의 Runbook·Guide·Example 승격 후보 분류

산출물:

- Curator 초안
- 리뷰 기준
- 실패 처리 정책

## Phase 4. Knowledge Service 구축

- Bundle/Evidence 읽기
- OS 파일 검색 기반 검색
- Frontmatter 필터 검색
- Markdown 링크와 backlink 확장
- Evidence manifest 검색
- Context Builder
- Runbook 신선도와 Inquiry 조회
- Active-only 기본 검색과 명시적 비활성 상태 조회
- Frontmatter 기반 Knowledge Inventory와 읽기 전용 Audit

산출물:

- 내부 SDK
- 테스트 코드

## Phase 5. Knowledge MCP 구축

- Tool 인터페이스 정의
- 읽기/검증 중심 초기 기능 제공
- Validator 통과 후 자동 Commit 정책 정의
- Candidate Evidence 평가와 Claim Support Tool 제공
- 구조화 Outcome과 Artifact Profile 계약 제공

산출물:

- MCP 서버 초안
- Tool 스펙 문서

## Phase 6. 보류 항목 검토

- `13-future-work.md` 항목 재검토
- MVP 운영 결과 기반 우선순위 재정렬
- 구현 대상으로 승격할 항목 선정

산출물:

- 갱신된 로드맵
- 확장 구현 후보 목록

## 권장 구현 순서

1. 문서 읽기
2. 아키텍처 리뷰
3. 저장소 골격 생성
4. Evidence 모델 구현
5. Knowledge Service 구현
6. MCP 구현
7. Hermes 연동
8. 보류 항목 재검토
