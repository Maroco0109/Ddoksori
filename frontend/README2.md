# Frontend 폴더 구조 가이드

> **기술 스택**: React 19 + Vite 7 + TypeScript + Tailwind CSS
> **아키텍처**: FSD (Feature-Sliced Design)

---

## 목차
1. [요약 버전](#1-요약-버전)
2. [왜 이렇게 폴더를 나누었나? (FSD 아키텍처)](#2-왜-이렇게-폴더를-나누었나-fsd-아키텍처)
3. [자세한 버전](#3-자세한-버전)
4. [로컬 환경에서 프로젝트 실행하기](#4-로컬-환경에서-프로젝트-실행하기)

---

## 1. 요약 버전

```
front/
├── public/              # 정적 파일 (로고 이미지)
├── src/                 # 소스 코드
│   ├── app/             # 앱 초기화 및 라우팅
│   ├── features/        # 기능별 모듈 (페이지 + 로직)
│   │   ├── auth/        # 인증 (로그인/회원가입)
│   │   ├── board/       # 자유게시판
│   │   ├── chat/        # AI 상담 채팅
│   │   ├── home/        # 홈 페이지
│   │   └── procedure/   # 조정신청 절차
│   ├── shared/          # 공용 리소스
│   │   ├── api/         # API 클라이언트
│   │   ├── assets/      # 이미지 등 에셋
│   │   ├── config/      # 설정값 (라우트, 상수)
│   │   ├── lib/         # 유틸리티 함수
│   │   ├── styles/      # 글로벌 CSS
│   │   ├── types/       # TypeScript 타입 정의
│   │   └── ui/          # 공용 UI 컴포넌트
│   ├── store/           # 전역 상태 관리 (Zustand)
│   ├── widgets/         # 레이아웃 위젯 (Sidebar)
│   └── main.tsx         # 앱 진입점
├── index.html           # HTML 템플릿
├── package.json         # 의존성 관리
├── vite.config.ts       # Vite 설정
├── tailwind.config.ts   # Tailwind CSS 설정
└── tsconfig.json        # TypeScript 설정
```

### 핵심 폴더 요약

| 폴더 | 역할 | 주요 파일 |
|------|------|----------|
| `app/` | 앱 설정, 라우팅, 레이아웃 | `App.tsx`, `RootLayout.tsx`, `routes.tsx` |
| `features/` | 각 기능(페이지)별 코드 모음 | `*Page.tsx`, `*.store.ts` |
| `shared/` | 여러 기능에서 공유하는 코드 | 타입, 유틸, 설정, UI 컴포넌트 |
| `store/` | 전역 UI 상태 관리 | `ui.store.ts` |
| `widgets/` | 페이지에 삽입되는 독립 UI 블록 | `Sidebar.tsx` |

---

## 2. 왜 이렇게 폴더를 나누었나? (FSD 아키텍처)

### 핵심 원칙: 의존성 방향

```
app → widgets → features → shared
         ↓
       store (전역 상태)
```

**상위 레이어는 하위 레이어만 import 가능** (역방향 금지)

---

### 각 폴더의 역할

#### shared/ - 공유 자원

```
"누구나 쓸 수 있지만, 누구도 몰라야 함"
```

| 특징 | 설명 |
|------|------|
| 비즈니스 로직 | 없음 |
| 의존성 | 외부 라이브러리만 |
| 예시 | Button, Input, 날짜 포맷 함수, API 클라이언트 |

```tsx
// shared/lib/date.ts - 순수 함수, 비즈니스 로직 없음
export function formatDateTime(date: string) {
  return new Date(date).toLocaleDateString();
}
```

---

#### features/ - 기능 단위

```
"특정 비즈니스 기능을 캡슐화"
```

| 특징 | 설명 |
|------|------|
| 비즈니스 로직 | 해당 기능만 |
| 의존성 | shared만 import 가능 |
| 예시 | ChatPage, BoardPage, LoginModal |

```tsx
// features/chat/ChatPage.tsx - 채팅 기능에만 집중
// features/board/BoardPage.tsx - 게시판 기능에만 집중
```

**장점**: 채팅 기능을 수정해도 게시판에 영향 없음

---

#### widgets/ - 조합 블록

```
"여러 feature를 조합한 독립 UI"
```

| 특징 | 설명 |
|------|------|
| 비즈니스 로직 | 여러 기능 조합 |
| 의존성 | features, shared import 가능 |
| 예시 | Sidebar, Header, Footer |

```tsx
// widgets/Sidebar.tsx
import { useChatStore } from '@/features/chat/chat.store';  // chat
import { useAuthStore } from '@/features/auth/auth.store';  // auth
// → 여러 feature를 알고 있음
```

---

#### store/ - 전역 상태

```
"앱 전체에서 공유하는 상태"
```

| 특징 | 설명 |
|------|------|
| 용도 | UI 상태, 앱 설정 등 |
| 의존성 | shared만 import |
| 예시 | 사이드바 열림/닫힘, 모달 상태 |

```tsx
// store/ui.store.ts - 전역 UI 상태
isSidebarOpen, isAuthModalOpen, isChatHistoryOpen
```

**vs features/\*/\*.store.ts**: 특정 기능 전용 상태는 feature 안에 위치

---

### 왜 이렇게 나누나?

#### 문제 상황 (분리 안 했을 때)

```
src/
├── components/
│   ├── Button.tsx
│   ├── ChatPage.tsx
│   ├── Sidebar.tsx
│   └── LoginModal.tsx
```

→ 파일이 100개가 되면? 어디서 뭘 찾아야 할지 모름

#### 해결 (FSD 적용)

```
"채팅 관련 코드 어디있어?" → features/chat/
"공용 버튼 어디있어?" → shared/ui/
"사이드바 어디있어?" → widgets/
```

---

### 실제 예시로 이해하기

**시나리오**: 채팅 세션 목록을 사이드바에 표시

```
1. shared/lib/date.ts        → 날짜 포맷 함수 (순수)
2. shared/types/chat.ts      → ChatSession 타입 정의
3. features/chat/chat.store  → 채팅 세션 상태 관리
4. widgets/Sidebar.tsx       → 세션 목록 UI 렌더링
5. app/RootLayout.tsx        → Sidebar를 레이아웃에 배치
```

각 레이어가 자기 역할만 담당 → **유지보수 용이**

---

### 한 줄 요약

| 폴더 | 한 줄 정의 |
|------|-----------|
| `shared` | 비즈니스 로직 없는 순수 도구들 |
| `features` | 특정 기능에 종속된 코드 묶음 |
| `widgets` | 여러 기능을 조합한 UI 블록 |
| `store` | 앱 전체가 공유하는 상태 |

---

## 3. 자세한 버전

### 루트 디렉토리

```
front/
├── index.html           # Vite 진입 HTML 템플릿
├── package.json         # npm 의존성 및 스크립트 정의
├── package-lock.json    # 의존성 버전 잠금 파일
├── vite.config.ts       # Vite 빌드 도구 설정
├── tailwind.config.ts   # Tailwind CSS 테마 및 설정
├── postcss.config.js    # PostCSS 설정 (Tailwind 연동)
├── tsconfig.json        # TypeScript 컴파일러 설정
├── tsconfig.node.json   # Node.js용 TypeScript 설정
├── eslint.config.js     # ESLint 코드 린팅 설정
├── components.json      # shadcn/ui 컴포넌트 설정
└── README.md            # 프로젝트 설명 문서
```

---

### public/ - 정적 파일

```
public/
├── assets/              # 정적 에셋 폴더
├── logo-1.png           # 로고 이미지 1
├── logo-2.png           # 로고 이미지 2
└── logo-3.png           # 로고 이미지 3
```

> 빌드 시 그대로 복사되는 정적 파일들

---

### src/ - 소스 코드

#### src/app/ - 앱 초기화 및 라우팅

```
src/app/
├── App.tsx              # 앱 루트 컴포넌트
├── RootLayout.tsx       # 공통 레이아웃 (Sidebar + 메인 영역)
├── routes.tsx           # 라우트 정의 (createBrowserRouter)
└── providers/
    ├── QueryProvider.tsx    # React Query 프로바이더
    └── RouterProvider.tsx   # React Router 프로바이더
```

| 파일 | 설명 |
|------|------|
| `App.tsx` | 모든 프로바이더를 조합하는 최상위 컴포넌트 |
| `RootLayout.tsx` | 사이드바, 헤더, 로그인 모달 등 공통 UI 배치 |
| `routes.tsx` | URL 경로와 페이지 컴포넌트 매핑 |
| `QueryProvider.tsx` | 서버 상태 관리 (React Query) 설정 |
| `RouterProvider.tsx` | 클라이언트 라우팅 설정 |

---

#### src/features/ - 기능별 모듈

FSD 아키텍처에 따라 각 기능(feature)이 독립적으로 구성됩니다.

##### features/auth/ - 인증

```
src/features/auth/
├── auth.store.ts        # 인증 상태 관리 (Zustand)
└── LoginModal.tsx       # 로그인/회원가입 모달 컴포넌트
```

##### features/board/ - 자유게시판

```
src/features/board/
├── board.types.ts       # 게시판 관련 타입 정의
├── BoardPage.tsx        # 게시판 메인 페이지
└── components/
    ├── EditPost.tsx     # 게시글 수정 컴포넌트
    ├── PostDetail.tsx   # 게시글 상세 보기 컴포넌트
    └── WritePost.tsx    # 게시글 작성 컴포넌트
```

##### features/chat/ - AI 상담 채팅

```
src/features/chat/
├── chat.store.ts        # 채팅 상태 관리 (세션, 메시지)
└── ChatPage.tsx         # AI 상담 페이지
```

##### features/home/ - 홈 페이지

```
src/features/home/
└── HomePage.tsx         # 랜딩 페이지 (GSAP 애니메이션)
```

##### features/procedure/ - 조정신청 절차

```
src/features/procedure/
└── ProcedurePage.tsx    # 분쟁조정 신청 절차 안내 페이지
```

---

#### src/shared/ - 공유 리소스

여러 feature에서 공통으로 사용하는 코드들입니다.

##### shared/api/ - API 통신

```
src/shared/api/
└── client.ts            # Axios/Fetch API 클라이언트 설정
```

##### shared/assets/ - 에셋 파일

```
src/shared/assets/
└── icons/
    ├── icon-1.png       # 홈페이지 스토리텔링 아이콘 1
    ├── icon-2.png       # 홈페이지 스토리텔링 아이콘 2
    ├── icon-3.png       # 홈페이지 스토리텔링 아이콘 3
    ├── logo-1.png       # 로고 이미지 1
    ├── logo-2.png       # 로고 이미지 2
    ├── logo-3.png       # 사이드바 로고 (메인 사용)
    ├── procedure-1.png  # 조정절차 이미지 1
    ├── procedure-2.png  # 조정절차 이미지 2
    └── procedure-3.png  # 조정절차 이미지 3
```

##### shared/config/ - 설정값

```
src/shared/config/
├── index.ts             # 설정 통합 export
├── categories.ts        # 카테고리 상수 (게시판 등)
├── query-keys.ts        # React Query 키 상수
├── routes.ts            # 라우트 경로 상수 (ROUTES)
└── storage-keys.ts      # localStorage 키 상수
```

##### shared/lib/ - 유틸리티 함수

```
src/shared/lib/
├── date.ts              # 날짜 포맷팅 함수
├── number.ts            # 숫자 포맷팅 함수
├── session.ts           # 세션 관련 유틸 (시간 계산 등)
├── storage.ts           # localStorage 래퍼 함수
├── utils.ts             # 기타 유틸리티 (cn 함수 등)
└── validation.ts        # 입력값 유효성 검사 함수
```

##### shared/styles/ - 스타일

```
src/shared/styles/
└── globals.css          # 글로벌 CSS (Tailwind, 스크롤바 등)
```

##### shared/types/ - TypeScript 타입

```
src/shared/types/
├── index.ts             # 타입 통합 export
├── auth.ts              # 인증 관련 타입
├── chat.ts              # 채팅 관련 타입
├── common.ts            # 공통 타입
└── post.ts              # 게시글 관련 타입
```

##### shared/ui/ - 공용 UI 컴포넌트

```
src/shared/ui/
├── button.tsx           # 버튼 컴포넌트 (shadcn/ui)
└── input.tsx            # 입력 필드 컴포넌트 (shadcn/ui)
```

---

#### src/store/ - 전역 상태 관리

```
src/store/
├── index.ts             # 스토어 통합 export
└── ui.store.ts          # UI 상태 (사이드바, 모달 등)
```

> Zustand를 사용한 전역 상태 관리

---

#### src/widgets/ - 위젯 컴포넌트

```
src/widgets/
└── Sidebar.tsx          # 좌측 네비게이션 사이드바
```

> 독립적으로 동작하는 복잡한 UI 블록

---

#### 기타 파일

```
src/
├── main.tsx             # 앱 진입점 (ReactDOM.render)
└── vite-env.d.ts        # Vite 환경 타입 선언
```

---

### dist/ - 빌드 결과물

```
dist/
├── index.html           # 빌드된 HTML
└── assets/              # 빌드된 JS, CSS, 이미지
    ├── index-*.js       # 번들링된 JavaScript
    ├── index-*.css      # 번들링된 CSS
    └── *.png            # 최적화된 이미지
```

> `npm run build` 실행 시 생성되는 프로덕션 빌드 파일

---

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                         App.tsx                             │
│  (QueryProvider + RouterProvider 조합)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      RootLayout.tsx                         │
│  ┌──────────┐    ┌────────────────────────────────────┐    │
│  │ Sidebar  │    │            <Outlet />              │    │
│  │ (Widget) │    │  (라우트에 따라 페이지 렌더링)       │    │
│  └──────────┘    └────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ HomePage │       │ ChatPage │       │BoardPage │
    │ (home)   │       │ (chat)   │       │ (board)  │
    └──────────┘       └──────────┘       └──────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        shared/                              │
│  ┌─────┐ ┌──────┐ ┌─────┐ ┌───────┐ ┌─────┐ ┌──────────┐  │
│  │ api │ │config│ │ lib │ │ types │ │ ui  │ │  styles  │  │
│  └─────┘ └──────┘ └─────┘ └───────┘ └─────┘ └──────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 주요 npm 스크립트

```bash
npm run dev      # 개발 서버 실행 (http://localhost:5173)
npm run build    # 프로덕션 빌드 (dist/ 폴더 생성)
npm run preview  # 빌드 결과물 미리보기
npm run lint     # ESLint 코드 검사
```

---

## 참고 사항

- **FSD (Feature-Sliced Design)**: 기능 중심의 폴더 구조로, 각 feature가 독립적으로 관리됩니다.
- **Zustand**: 경량 상태 관리 라이브러리로 `*.store.ts` 파일에서 사용됩니다.
- **shadcn/ui**: Tailwind 기반 UI 컴포넌트 라이브러리 (`shared/ui/`)
- **GSAP + Lenis**: 홈페이지의 스크롤 애니메이션에 사용됩니다.

---

## 4. 로컬 환경에서 프로젝트 실행하기

GitHub에서 프로젝트를 clone 받아 로컬 컴퓨터에서 실행하는 방법을 단계별로 안내합니다.

### Step 1. 사전 요구사항 확인

프로젝트를 실행하기 전에 아래 소프트웨어가 설치되어 있어야 합니다.

#### Node.js 설치

- **필요 버전**: Node.js 18 이상 (20.x LTS 권장)
- **다운로드**: https://nodejs.org/

설치 확인 방법 (터미널/명령 프롬프트에서 실행):

```bash
node --version   # v18.0.0 이상이면 OK
npm --version    # Node.js와 함께 설치됨
```

#### Git 설치 (선택사항)

- 터미널에서 clone 하려면 Git이 필요합니다.
- **다운로드**: https://git-scm.com/
- GitHub에서 ZIP 파일로 다운로드하는 경우 Git 설치는 필요 없습니다.

---

### Step 2. 프로젝트 다운로드

#### 방법 A: Git으로 Clone (권장)

터미널(명령 프롬프트, PowerShell, Git Bash 등)을 열고 아래 명령어를 실행합니다:

```bash
# 원하는 디렉토리로 이동
cd 원하는/경로

# 저장소 클론 (URL은 실제 저장소 주소로 변경하세요)
git clone https://github.com/사용자명/저장소명.git

# 프로젝트 폴더로 이동
cd 저장소명/front
```

#### 방법 B: ZIP 파일로 다운로드

1. GitHub 저장소 페이지에서 **Code** 버튼 클릭
2. **Download ZIP** 선택
3. 다운로드된 ZIP 파일 압축 해제
4. 압축 해제된 폴더 내의 `front` 폴더로 이동

---

### Step 3. 의존성 패키지 설치

프로젝트 폴더(`front`)에서 아래 명령어를 실행하여 필요한 패키지들을 설치합니다:

```bash
npm install
```

이 명령어는 `package.json`에 정의된 모든 의존성 패키지를 `node_modules` 폴더에 설치합니다.

> **참고**: 처음 설치 시 시간이 다소 걸릴 수 있습니다 (보통 1~3분).

설치 완료 후 `node_modules` 폴더가 생성되었는지 확인하세요.

---

### Step 4. 개발 서버 실행

의존성 설치가 완료되면 개발 서버를 실행합니다:

```bash
npm run dev
```

성공적으로 실행되면 아래와 같은 메시지가 표시됩니다:

```
  VITE v7.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: http://xxx.xxx.xxx.xxx:5173/
```

---

### Step 5. 브라우저에서 확인

웹 브라우저를 열고 아래 주소로 접속합니다:

```
http://localhost:5173
```

홈페이지가 정상적으로 표시되면 설정 완료입니다!

---

### 기타 유용한 명령어

| 명령어 | 설명 |
|--------|------|
| `npm run dev` | 개발 서버 실행 (핫 리로드 지원) |
| `npm run build` | 프로덕션 빌드 (`dist/` 폴더 생성) |
| `npm run preview` | 빌드 결과물 로컬 미리보기 |
| `npm run lint` | ESLint로 코드 검사 |

---

### 문제 해결 (Troubleshooting)

#### 1. `npm install` 실패 시

```bash
# npm 캐시 정리 후 재시도
npm cache clean --force
npm install
```

#### 2. 포트 5173이 이미 사용 중인 경우

다른 프로세스가 포트를 사용 중이면 Vite가 자동으로 다른 포트(5174, 5175...)를 사용합니다.
터미널에 표시된 주소를 확인하세요.

#### 3. Node.js 버전이 낮은 경우

Node.js 18 미만 버전에서는 일부 기능이 동작하지 않을 수 있습니다.
최신 LTS 버전으로 업그레이드하세요.

```bash
# 현재 버전 확인
node --version

# nvm 사용 시 (선택사항)
nvm install 20
nvm use 20
```

#### 4. Windows에서 실행 정책 오류 발생 시

PowerShell에서 스크립트 실행이 차단되는 경우:

```powershell
# PowerShell을 관리자 권한으로 실행 후
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

### 프로젝트 구조 요약

```
front/
├── node_modules/     # npm install로 생성 (Git에서 제외됨)
├── src/              # 소스 코드
├── public/           # 정적 파일
├── package.json      # 의존성 정의
├── package-lock.json # 의존성 버전 잠금
└── ...               # 기타 설정 파일
```

> `node_modules/`와 `dist/` 폴더는 `.gitignore`에 의해 Git에서 제외됩니다.
> 따라서 clone 후 반드시 `npm install`을 실행해야 합니다.
