# Circled Wiki

Circled Wiki는 Git과 Markdown을 기반으로 조직 지식을 수집·검토·발행하고, AI Agent가 안전하게 조회·운영할 수 있게 하는 Python 기반 Knowledge Operating System입니다.

이 저장소는 **제품의 Source of Truth**입니다. 여기서 구현, Runtime 규칙, 설치·업그레이드 도구, 테스트와 제품 문서를 관리합니다. 실제 조직 지식과 운영 중 생성되는 작업물은 설치된 Wiki의 `knowledge/`와 `workspace/`에 속하며, 일반 업그레이드가 이를 덮어쓰지 않습니다.

## 구성

```text
circled-wiki/
├── src/circled_wiki/
│   ├── runtime/       # 설치 Wiki에서 실행되는 CLI, Core, MCP, worker
│   └── engineering/   # Source repository 전용 Issue·release·receipt 도구
├── tests/             # 단위·통합 테스트
├── docs/              # 제품 기획·설계 Reference
├── agent-rules/       # 설치 Wiki Runtime 작업 Profile
├── product-agent-rules/ # 제품 개발·release·배포 Profile
├── OPERATING_RULES.md # Runtime 전역 운영 규약
├── PRODUCT_ENGINEERING_RULES.md
├── workspace/         # 제품 Issue·release 이력 Working Plane
└── pyproject.toml
```

경계는 다음과 같습니다.

| 구분 | 정본 | 역할 |
| --- | --- | --- |
| 제품 개발 | `PRODUCT_ENGINEERING_RULES.md`, `product-agent-rules/` | 구현·테스트·release·배포 절차 |
| 설치 Wiki 운영 | `OPERATING_RULES.md`, `agent-rules/` | 지식 수집·검토·발행·조회 규칙 |
| 공식 지식 | 설치 Wiki의 `knowledge/` | Bundle과 Evidence |
| 제품 작업 이력 | `workspace/` | 운영 Issue, release manifest, receipt |

`circled-wiki`는 Runtime CLI 이름이고, `circled_wiki`는 Python package 이름입니다. 제품 전용 CLI는 `circled-wiki-product`입니다.

## 시작하기

Python 3.9 이상이 필요합니다. 개발 환경에서는 editable 설치와 개발 의존성을 함께 설치합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

설치하지 않고 저장소에서 바로 실행할 수도 있습니다.

```sh
PYTHONPATH=src python3 -m circled_wiki.runtime.cli.__main__ --help
PYTHONPATH=src python3 -m circled_wiki.engineering.cli --help
```

## 검증

변경 전후에는 Runtime Validator와 전체 테스트를 실행합니다.

```sh
PYTHONPATH=src python3 -m circled_wiki.runtime.cli.__main__ validate
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

개발 의존성을 설치했다면 아래 명령도 사용할 수 있습니다.

```sh
python3 -m pytest
```

## 새 Wiki 설치 또는 안전한 업그레이드

이 **제품 저장소를 작업 폴더로 Agent를 실행한 뒤**, 설치할 대상 프로젝트를 지정해 설치 또는 업그레이드를 요청할 수 있습니다. 대상은 `knowledge/` 폴더 자체가 아니라 이를 포함할 프로젝트 루트입니다.

```text
/path/to/wiki-project에 Circled Wiki를 설치해줘.
```

```text
/path/to/wiki-project의 Circled Wiki를 업그레이드해줘.
```

Agent는 먼저 변경 계획과 보존 대상을 확인하고, 적용이 승인된 경우에만 설치·업그레이드를 수행합니다. CLI로 직접 실행할 때도 계획을 먼저 확인한 뒤에만 `--apply`를 사용합니다.

```sh
circled-wiki bootstrap-circled-wiki --target /path/to/wiki-project
circled-wiki bootstrap-circled-wiki --target /path/to/wiki-project --apply
```

설치·업그레이드는 관리 자산만 갱신하며, 기존 `knowledge/`, `workspace/`, 설치 로컬 설정은 보존합니다. 자세한 Gate와 복구 절차는 [bootstrap-circled-wiki.md](product-agent-rules/bootstrap-circled-wiki.md)를 따릅니다.

## 실제 운영 방법

Circled Wiki는 별도의 상시 Agent 프로세스를 강제하지 않습니다. 설치가 끝난 뒤에는 **설치한 Wiki 프로젝트 폴더를 작업 폴더로 열고**, 그 폴더를 볼 수 있는 운영 Agent(Codex, Hermes 또는 연동 Agent)에게 지식 관리와 조회를 요청하는 방식으로 사용합니다.

```text
설치한 Wiki 프로젝트
├── knowledge/       # 공식 지식, Inbox, Evidence, Bundle
├── workspace/       # 설치본의 작업·대기 상태
└── .circled-wiki/   # Runtime 규칙, 설정, 설치 CLI
```

운영 Agent는 요청을 받으면 `.circled-wiki/AGENT_ROUTER.md`와 `.circled-wiki/OPERATING_RULES.md`를 읽고, 요청에 맞는 작업 Profile을 선택합니다. 따라서 제품 source repository를 열어 두는 대신, 실제로 운영할 Wiki 프로젝트를 Agent의 작업 기준으로 지정해야 합니다.

### 운영 사례

| 운영 영역 | Inbox에 수집할 자료 | Wiki에 물어볼 수 있는 내용 |
| --- | --- | --- |
| 고객지원·운영 | 고객 문의 응대 기준, 서비스 변경 안내, 장애 대응 절차, 업무 인수인계 문서 | “고객 문의에 답변하는 현재 기준을 알려줘.” |
| 인사·경영지원 | 신규 입사자 안내, 비용 정산 기준, 내부 승인 절차, 사내 정책 문서 | “신규 입사자의 첫 주 준비 절차를 알려줘.” |

### Obsidian 보관함으로 사용하기

Obsidian에서는 프로젝트 전체가 아니라 설치한 Wiki의 `knowledge/` 폴더를 보관함(Vault)으로 엽니다. 이렇게 하면 사람은 Obsidian에서 지식을 읽고 검토·보완하고, 운영 Agent는 같은 Vault를 규칙에 따라 관리합니다.

```text
knowledge/
├── inbox/       # 새로 수집되어 처리 대기 중인 자료
├── evidence/    # 출처·checksum과 함께 보존하는 처리 완료 원본
└── bundles/     # Evidence를 근거로 정리·발행한 공식 지식 문서
```

- `bundles/`에는 정책, 가이드, 결정, Runbook 등 공식 지식이 Markdown과 YAML Frontmatter로 저장됩니다. 기본 검색은 활성(`active`) Bundle을 대상으로 합니다.
- `evidence/`에는 Bundle의 근거가 되는 원본과 메타데이터가 보존됩니다. 무결성 기록이므로 원문을 직접 수정하지 않습니다.

Obsidian에서 편집한 공식 지식도 발행 전에는 운영 Agent의 검토와 Validator를 거쳐야 합니다. 자세한 편집 원칙은 [Obsidian 사용 가이드](docs/10-obsidian-guidelines.md)를 참고합니다.

### 1. 새 자료를 Inbox에 넣기

먼저 문서, 파일 또는 대화를 Inbox에 수집합니다. Agent에게 자료를 전달하거나 아래 Capture 명령을 사용하면, 원본과 수집 메타데이터가 `knowledge/inbox/<provider>/`에 안전하게 적재됩니다. 원본 파일을 단순 복사해 Inbox 상태를 직접 만들기보다 이 절차를 사용하는 것이 checksum, 출처와 민감정보 검토 이력을 보존하는 방법입니다. 자료의 제목·수집 목적·출처를 함께 제공하고, 빠진 필수 정보가 있으면 Agent가 필요한 항목만 확인합니다.

CLI로 직접 수집해야 할 때는 설치 폴더에서 제공되는 실행 파일을 사용합니다.

```sh
cd /path/to/wiki-project
python3 .circled-wiki/bin/circled-wiki.py capture-document \
  --provider manual \
  --file ./customer-support-guideline.md \
  --title "고객 문의 응대 기준" \
  --why-collected "고객 응대 기준을 최신화하기 위한 원본 수집" \
  --intended-use customer-support \
  --idempotency-key "customer-support-guideline-2026-08"
```

### 2. Inbox 자료 처리 맡기기

자료가 Inbox에 들어간 뒤에는 다음처럼 요청하면 됩니다.

```text
Inbox 자료를 처리해줘.
```

Agent가 설치본의 Router와 Runtime 규칙을 읽고 처리 단계를 판단합니다. Inbox 항목을 업무성으로 분류하고, 원본·checksum·출처를 확인하며, 민감정보 검토를 거쳐 안전한 항목을 Evidence로 변환합니다. 이어서 Curation Queue에서 기존 Bundle 갱신 또는 새 지식 후보를 제안합니다. 원본이 불명확하거나 민감정보·의미 변경·발행 승인이 필요한 경우에만 이유와 필요한 다음 조치를 알려줍니다.

### 3. Wiki 운영 Agent에게 지식 물어보기

일상적인 사용자는 파일 경로나 CLI를 알 필요 없이, 운영 Agent에게 질문합니다. Agent는 기본적으로 활성(`active`) Bundle과 연결된 Evidence를 검색하고, 필요한 Bundle을 읽은 뒤 출처와 함께 답합니다.

```text
고객 문의에 답변하는 현재 기준을 알려줘. 근거 문서와 적용 시점도 함께 보여줘.
```

```text
신규 입사자의 첫 주 준비 절차가 있으면 찾아서, 현재 팀에 적용할 수 있는지 알려줘.
```

질문에 맞는 공식 지식이나 실행 가능한 Runbook이 없으면 Agent는 이를 추정해 표준 절차로 만들지 않고, 확인 가능한 근거와 일회성 계획 또는 추가 수집·검토 요청을 구분해 제시합니다.

## Runtime의 기본 흐름

```text
원본 수집 → Inbox 검사·민감정보 검토 → Evidence 변환
       → Curation 후보·검토 → Bundle 발행 → 검색·Workflow 활용
```

대표 명령은 다음과 같습니다. 실제 운영에서는 설치 Wiki의 Runtime 규칙과 단계별 Profile을 먼저 확인해야 합니다.

```sh
# 현재 관리 문서 검증
python3 .circled-wiki/bin/circled-wiki.py validate

# 원본을 Inbox에 수집
python3 .circled-wiki/bin/circled-wiki.py capture-document --help

# Inbox 상태 검사 및 처리
python3 .circled-wiki/bin/circled-wiki.py inspect-inbox --limit 100
python3 .circled-wiki/bin/circled-wiki.py reconcile-inbox --actor <operator> --limit 100

# 공식 지식 검색 및 읽기
python3 .circled-wiki/bin/circled-wiki.py search --help
python3 .circled-wiki/bin/circled-wiki.py read-bundle --help
```

운영 절차는 [사람 사용자 가이드](docs/17-human-guide.md), [Agent 가이드](docs/18-agent-guide.md), [Runtime 작업 Profile](agent-rules/README.md)을 참고합니다. `OPERATING_RULES.md`가 Runtime 규약의 유일한 정본이며, 문서 설명과 충돌할 경우 규약과 Validator를 우선합니다.

## 제품 Issue·release 작업

운영에서 발견된 문제를 제품 개선으로 연결할 때는 다음 순서를 지킵니다.

```text
명시적 Issue 수집 → 사용자 검토 → triage → 구현·회귀 테스트
→ release 준비 → 승인된 배포 → 독립 Runtime 검증
```

제품 CLI는 `workspace/`를 기본 작업 위치로 사용합니다.

```sh
circled-wiki-product --help
circled-wiki-product intake-operational-issue --help
circled-wiki-product prepare-release --help
```

Issue 수집·triage·release·배포는 각각 별도의 Profile과 Gate를 따릅니다. 제품 변경이 완료됐다는 사실만으로 설치 Wiki의 운영 문제가 해결됐다고 처리하지 않습니다.

## 주요 문서

- [제품 개발 규칙](PRODUCT_ENGINEERING_RULES.md)
- [제품 작업 Profile](product-agent-rules/README.md)
- [Runtime 전역 운영 규약](OPERATING_RULES.md)
- [Runtime 작업 Profile](agent-rules/README.md)
- [설계 문서 인덱스](docs/README.md)
- [구현 계획](docs/15-implementation-plan.md)
- [MVP 이후 작업](docs/13-future-work.md)

## 개발 원칙

- 조직명, 자격 증명, 사용자 원문, 머신 절대 경로를 제품 기본값에 넣지 않습니다.
- `knowledge/`와 설치된 Wiki의 `workspace/`는 사용자 관리 자산으로 취급합니다.
- Runtime 배포물에 Product Profile과 source-only 제품 문서를 포함하지 않습니다.
- 커밋·push·외부 배포는 명시적으로 승인된 범위에서만 수행합니다.
