# 중복 YAML 프론트매터 Validator 탐지

- Issue ID: `issue-20260724T100826Z-6ca73ea0`
- Recorded at: 2026-07-24T10:08:26.064175+00:00
- Reported by: codex
- Reported from: agent
- Area: validator
- Severity: medium
- Release observed: unknown
- Status: open

## Summary

Evidence 또는 Bundle 파일에 두 번째 YAML 프론트매터 블록이 삽입되면 필드 해석이 불명확해질 수 있으므로 Validator가 이를 명시적으로 거부해야 한다.

## Expected result

관리 대상 Markdown 문서는 정확히 하나의 YAML 프론트매터 블록만 포함하며, 중복 블록은 Validator 오류로 보고한다.

## Actual result

기존 파서는 첫 블록만 읽고 뒤의 블록을 본문으로 취급할 수 있었다.

## Impact

손상된 메타데이터가 검증을 통과하거나 비결정적으로 해석될 위험이 있다.

## Reproduction or context

유효한 첫 YAML 프론트매터 닫힘 바로 뒤에 두 번째 YAML 블록을 추가한 Markdown을 validate 한다.

## Related paths or artifacts

- `src/circled_wiki/core/frontmatter.py`
- `workspace/tests/unit/test_validator.py`

## Improvement hint

파서에서 연속된 두 번째 YAML 프론트매터 블록을 거부하고 회귀 테스트로 고정한다.

## Cause hypothesis

과거 텍스트 append 기반 갱신이 닫힘과 새 시작 구분자를 중복 삽입했다.

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
