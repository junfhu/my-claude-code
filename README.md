# cczip — Claude Code Source Analysis

> Anthropic의 공식 CLI 도구인 **Claude Code**의 소스코드를 분석하기 위한 레포지토리입니다.
>
> 참고: [트윗 원문](https://x.com/Fried_rice/status/2038894956459290963)

---

## 개요

Claude Code는 터미널에서 직접 Claude와 대화하며 소프트웨어 엔지니어링 작업을 수행할 수 있는 CLI 도구입니다. 이 레포는 해당 도구의 `src/` 디렉토리를 분석 목적으로 아카이빙한 것입니다.

- **언어**: TypeScript
- **런타임**: Bun
- **터미널 UI**: React + [Ink](https://github.com/vadimdemedes/ink) (React for CLI)
- **규모**: 약 1,900개 파일, 512,000+ 라인

---

## 디렉토리 구조

```
src/
├── main.tsx                 # 엔트리포인트 (Commander.js 기반 CLI 파싱)
├── commands.ts              # 커맨드 레지스트리
├── tools.ts                 # 툴 레지스트리
├── Tool.ts                  # 툴 타입 정의
├── QueryEngine.ts           # LLM 쿼리 엔진 (Anthropic API 호출 핵심)
├── context.ts               # 시스템/유저 컨텍스트 수집
├── cost-tracker.ts          # 토큰 비용 추적
│
├── commands/                # 슬래시 커맨드 구현 (~50개)
├── tools/                   # 에이전트 툴 구현 (~40개)
├── components/              # Ink UI 컴포넌트 (~140개)
├── hooks/                   # React 훅
├── services/                # 외부 서비스 연동
├── screens/                 # 전체 화면 UI (Doctor, REPL, Resume)
├── types/                   # TypeScript 타입 정의
├── utils/                   # 유틸리티 함수
│
├── bridge/                  # IDE 연동 브릿지 (VS Code, JetBrains)
├── coordinator/             # 멀티 에이전트 코디네이터
├── plugins/                 # 플러그인 시스템
├── skills/                  # 스킬 시스템
├── keybindings/             # 키바인딩 설정
├── vim/                     # Vim 모드
├── voice/                   # 음성 입력
├── remote/                  # 원격 세션
├── server/                  # 서버 모드
├── memdir/                  # 메모리 디렉토리 (영속 기억)
├── tasks/                   # 태스크 관리
├── state/                   # 상태 관리
├── migrations/              # 설정 마이그레이션
├── schemas/                 # 설정 스키마 (Zod)
├── entrypoints/             # 초기화 로직
├── ink/                     # Ink 렌더러 래퍼
├── buddy/                   # 컴패니언 스프라이트 (Easter egg)
├── native-ts/               # 네이티브 타입스크립트 유틸
├── outputStyles/            # 출력 스타일링
├── query/                   # 쿼리 파이프라인
└── upstreamproxy/           # 프록시 설정
```

---

## 핵심 아키텍처

### 1. 툴 시스템 (`src/tools/`)

Claude Code가 사용하는 모든 도구의 구현체입니다. 각 툴은 독립적인 디렉토리에 정의되어 있습니다.

| 툴 | 설명 |
|---|---|
| `BashTool` | 셸 명령 실행 |
| `FileReadTool` | 파일 읽기 (이미지, PDF, 노트북 포함) |
| `FileWriteTool` | 파일 생성/덮어쓰기 |
| `FileEditTool` | 파일 부분 수정 (string replacement) |
| `GlobTool` | 파일 패턴 매칭 검색 |
| `GrepTool` | ripgrep 기반 콘텐츠 검색 |
| `WebFetchTool` | URL 콘텐츠 가져오기 |
| `WebSearchTool` | 웹 검색 |
| `AgentTool` | 서브에이전트 생성 |
| `SkillTool` | 스킬 실행 |
| `MCPTool` | MCP 서버 툴 호출 |
| `LSPTool` | Language Server Protocol 연동 |
| `NotebookEditTool` | Jupyter 노트북 편집 |
| `TaskCreateTool` / `TaskUpdateTool` | 태스크 생성/관리 |
| `SendMessageTool` | 에이전트 간 메시지 전송 |
| `TeamCreateTool` / `TeamDeleteTool` | 팀 에이전트 관리 |
| `EnterPlanModeTool` / `ExitPlanModeTool` | 계획 모드 전환 |
| `EnterWorktreeTool` / `ExitWorktreeTool` | Git worktree 격리 |
| `ToolSearchTool` | 지연 로드된 툴 검색 |
| `CronCreateTool` | 스케줄 트리거 생성 |
| `RemoteTriggerTool` | 원격 트리거 |
| `SleepTool` | 프로액티브 모드 대기 |
| `SyntheticOutputTool` | 구조화된 출력 생성 |

### 2. 커맨드 시스템 (`src/commands/`)

사용자가 `/`로 시작하는 슬래시 커맨드입니다.

| 커맨드 | 설명 |
|---|---|
| `/commit` | Git 커밋 생성 |
| `/review` | 코드 리뷰 |
| `/compact` | 컨텍스트 압축 |
| `/mcp` | MCP 서버 관리 |
| `/config` | 설정 관리 |
| `/doctor` | 환경 진단 |
| `/login` / `/logout` | 인증 |
| `/memory` | 영속 기억 관리 |
| `/skills` | 스킬 관리 |
| `/tasks` | 태스크 관리 |
| `/vim` | Vim 모드 토글 |
| `/diff` | 변경사항 확인 |
| `/cost` | 비용 확인 |
| `/theme` | 테마 변경 |
| `/context` | 컨텍스트 시각화 |
| `/pr_comments` | PR 코멘트 확인 |
| `/resume` | 이전 세션 복원 |
| `/share` | 세션 공유 |
| `/desktop` | 데스크톱 앱 연결 |
| `/mobile` | 모바일 앱 연결 |

### 3. 서비스 레이어 (`src/services/`)

| 서비스 | 설명 |
|---|---|
| `api/` | Anthropic API 클라이언트, 파일 API, 부트스트랩 |
| `mcp/` | Model Context Protocol 서버 연결 및 관리 |
| `oauth/` | OAuth 2.0 인증 플로우 |
| `lsp/` | Language Server Protocol 매니저 |
| `analytics/` | GrowthBook 기반 피처 플래그 및 분석 |
| `plugins/` | 플러그인 로더 |
| `compact/` | 대화 컨텍스트 압축 |
| `policyLimits/` | 조직 정책 제한 |
| `remoteManagedSettings/` | 원격 관리 설정 |
| `extractMemories/` | 자동 기억 추출 |
| `tokenEstimation.ts` | 토큰 수 추정 |
| `teamMemorySync/` | 팀 메모리 동기화 |

### 4. 브릿지 시스템 (`src/bridge/`)

IDE 확장(VS Code, JetBrains)과 Claude Code CLI를 연결하는 양방향 통신 레이어입니다.

- `bridgeMain.ts` — 브릿지 메인 루프
- `bridgeMessaging.ts` — 메시지 프로토콜
- `bridgePermissionCallbacks.ts` — 권한 콜백
- `replBridge.ts` — REPL 세션 브릿지
- `jwtUtils.ts` — JWT 기반 인증
- `sessionRunner.ts` — 세션 실행 관리

### 5. 권한 시스템 (`src/hooks/toolPermission/`)

모든 툴 호출에 대해 권한을 검사하는 시스템입니다. 사용자에게 승인/거부를 요청하거나, 설정된 권한 모드(`default`, `plan`, `bypassPermissions`, `auto` 등)에 따라 자동으로 처리합니다.

### 6. 피처 플래그

Bun의 `bun:bundle` feature flag를 활용한 데드코드 제거:

```typescript
import { feature } from 'bun:bundle'

// 빌드 시점에 비활성 코드를 완전히 제거
const voiceCommand = feature('VOICE_MODE')
  ? require('./commands/voice/index.js').default
  : null
```

주요 피처 플래그: `PROACTIVE`, `KAIROS`, `BRIDGE_MODE`, `DAEMON`, `VOICE_MODE`, `AGENT_TRIGGERS`, `MONITOR_TOOL` 등

---

## 주요 파일 상세

### `QueryEngine.ts` (~46K 라인)

LLM API 호출의 핵심 엔진입니다. 스트리밍 응답 처리, 툴 호출 루프, thinking 모드, 재시도 로직, 토큰 카운팅 등을 담당합니다.

### `Tool.ts` (~29K 라인)

모든 툴의 기본 타입과 인터페이스를 정의합니다. 툴 입력 스키마, 권한 모델, 진행 상태 타입 등이 포함됩니다.

### `commands.ts` (~25K 라인)

모든 슬래시 커맨드의 등록과 실행을 관리합니다. 조건부 임포트를 통해 환경별로 다른 커맨드 세트를 로드합니다.

### `main.tsx`

Commander.js 기반의 CLI 파서 + React/Ink 렌더러 초기화. 시작 시 MDM 설정, 키체인 프리페치, GrowthBook 초기화 등을 병렬로 수행합니다.

---

## 기술 스택

| 카테고리 | 기술 |
|---|---|
| 런타임 | [Bun](https://bun.sh) |
| 언어 | TypeScript (strict) |
| 터미널 UI | [React](https://react.dev) + [Ink](https://github.com/vadimdemedes/ink) |
| CLI 파싱 | [Commander.js](https://github.com/tj/commander.js) (extra-typings) |
| 스키마 검증 | [Zod v4](https://zod.dev) |
| 검색 | [ripgrep](https://github.com/BurntSushi/ripgrep) (Grep 툴) |
| 프로토콜 | [MCP SDK](https://modelcontextprotocol.io), LSP |
| API | [Anthropic SDK](https://docs.anthropic.com) |
| 텔레메트리 | OpenTelemetry + gRPC |
| 피처 플래그 | GrowthBook |
| 인증 | OAuth 2.0, JWT, macOS Keychain |

---

## 주목할만한 설계 패턴

### 병렬 프리페치

시작 시간을 최적화하기 위해 MDM 설정, 키체인, API preconnect 등을 병렬로 프리페치합니다.

```typescript
// main.tsx — 모듈 임포트 전에 side-effect로 실행
startMdmRawRead()
startKeychainPrefetch()
```

### 지연 로딩 (Lazy Loading)

무거운 모듈(OpenTelemetry ~400KB, gRPC ~700KB)은 실제로 필요할 때까지 `import()`로 지연 로딩합니다.

### 에이전트 스웜

`AgentTool`을 통해 서브에이전트를 생성하고, `coordinator/`가 멀티에이전트 오케스트레이션을 담당합니다. `TeamCreateTool`로 팀 단위 병렬 작업도 지원합니다.

### 스킬 시스템

`skills/` 디렉토리에 재사용 가능한 워크플로우를 정의하고, `SkillTool`로 실행합니다. 사용자가 커스텀 스킬을 추가할 수 있습니다.

### 플러그인 아키텍처

`plugins/` 를 통해 빌트인 플러그인과 서드파티 플러그인을 로드합니다.

---

## 라이선스

이 레포지토리는 분석 및 학습 목적으로만 사용됩니다. 원본 소스코드의 저작권은 [Anthropic](https://www.anthropic.com)에 있습니다.
