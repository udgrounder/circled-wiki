# Operational issue records

이 폴더는 Circled Wiki를 운영하면서 발생한 오류, 불편, 누락된 자동화, 개선 제안을 기록하는 로컬 피드백 영역이다.
각 이슈는 OS 개선 검토의 입력일 뿐, 자동 수정·자동 발행·정책 변경의 승인 근거는 아니다.

## Record an issue

프로젝트 root에서 다음 명령을 실행한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py record-system-issue \
  --title "Inbox inspection command returned an unclear error" \
  --summary "The operator could not identify the failed intake item." \
  --reported-by "user-id-or-operator-id" \
  --reported-from user \
  --area cli \
  --severity medium \
  --expected "The command identifies the intake and recovery action." \
  --actual "Only a generic error was returned." \
  --reproduction "Run inspect-inbox with a malformed item." \
  --improvement-hint "Include intake ID and a safe recovery hint." \
  --related-path ".circled-wiki/runtime/circled_wiki/worker/jobs.py"
```

직접 Markdown을 만들 때는 `.circled-wiki/templates/system-issue.md` 형식을 사용한다.

## Triage and closure

Issue는 `open -> triaged -> mitigated -> verified -> resolved` 순서로 상태를 바꾼다. 해결하지 않기로 한 경우에만
`open` 또는 `triaged`에서 `wont_fix`로 전환한다. 상태 전환에는 담당자, 안전한 근거와 검증 결과를 남긴다.

```sh
python3 .circled-wiki/bin/circled-wiki.py update-system-issue \
  --issue "issue-<timestamp>-<id>" \
  --status triaged \
  --actor "system-maintainer" \
  --note "원인과 개선 범위를 검토했다."
```

사용자가 대화·Slack·다른 채널에서 제기한 오류, 불편, 개선 요청도 같은 명령으로 `--reported-from user`를 지정해
기록한다. 사용자 의견은 중요한 개선 입력이지만, 그 자체로 원인·해결책·승인을 확정하지 않는다.

## Rules

- API key, token, password, 개인식별정보, 고객 원문을 기록하지 않는다.
- 관찰된 사실과 추정한 원인을 구분한다.
- 재현 정보, 영향 범위, 기대 결과와 실제 결과를 남긴다.
- Issue 상태만으로 OS·정책·Runbook을 자동 변경하거나 발행하지 않는다.
- upgrade는 이 폴더의 사용자 이슈 파일을 덮어쓰지 않으며, 전체 `.circled-wiki/` 백업에는 포함된다.
