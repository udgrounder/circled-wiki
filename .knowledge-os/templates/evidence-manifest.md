---
type: template
title: Evidence Record Template
description: External-file Evidence Manifest와 Embedded Evidence Document의 공통 템플릿
tags: [template, evidence]
timestamp: 2026-07-09T00:00:00+09:00
---

# Evidence Record Template

아래 기본형은 외부 Evidence Original을 설명하는 External-file Evidence Manifest다. 시스템이 직접 생성한
텍스트는 문서 후반의 Embedded Evidence Document 변형을 사용한다.
파일명 `evidence-manifest.md`는 기존 설치 자산과의 호환성을 위해 유지한다.

```yaml
---
type: evidence
id: evidence://campingtalk/{provider}/{yyyy}/{mm}/{dd}/{source_uuid}
title: {title}
source_uuid: {source_uuid}
provider: {provider}
source_ref:
  provider: {provider}
  provider_url: {provider_url}
  locator: {page|section|sheet|slide|timestamp|fragment}
  external_id: {external_id}
  captured_from: {captured_from}
  snapshot_at: {snapshot_at}
captured_at: {captured_at}
status: new
processed_at:
curated_into: []
checksum: {checksum}
language: ko
original_file: {name}_{source_uuid}.{ext}
original_file_git_tracked: true
derived_files: []
extensions:
  content_mode: external_file
  checksum_scope: original_file
  availability: {available|metadata_only|temporarily_unavailable|access_denied|missing}
  capture_context:
    why_collected: {수집 이유}
    intended_use:
      - {적용할 업무 또는 지식 ID}
    reuse_value: {high|medium|low}
    retention_class: {workflow_reference|decision_record|outcome|general_reference|ephemeral}
    sensitivity_review: {completed|required|not_applicable}
    business_context: {업무 맥락}
    key_questions: []
    expected_outputs: []
  review_state: pending
  visibility: internal
  pii_scanned: false
  pii_masked: false
  storage:
    class: git
---
```

## Summary

원본 요약을 작성한다.

## Processing Notes

처리 중 확인한 사항을 작성한다.

## Source Notes

원본 시스템, 수집 방식, 재확보 방법을 작성한다.

시스템이 직접 생성한 대화·Outcome 텍스트는 별도 원본 파일 없이 동일한 Evidence Markdown에
포함한다. 이 경우 `original_file`을 제거하고 다음 필드와 불변 원문 구역을 사용한다.

```markdown
extensions:
  content_mode: embedded
  checksum_scope: original_content
  capture_fidelity: verbatim
  conversation_capture:
    capture_type: conversation
    thread_ref: {thread_ref}
  capture_context:
    sensitivity_review: required
  pii_scanned: false

# Original Conversation

<!-- ORIGINAL_CONTENT_START -->원문을 그대로 보존한다.<!-- ORIGINAL_CONTENT_END -->
```
