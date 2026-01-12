# 똑소리 - 소비자 권익 보호 플랫폼

소비자 권익 보호를 위한 AI 상담 및 분쟁조정 플랫폼의 프론트엔드 프로젝트입니다.

> 📖 **폴더 구조 및 FSD 아키텍처에 대한 상세 설명은 [README2.md](./README2.md)를 참조하세요.**

## 기술 스택

- **프레임워크**: React 19 + TypeScript
- **빌드 도구**: Vite 7
- **스타일링**: TailwindCSS 3
- **라우팅**: React Router 6
- **상태 관리**: Zustand 5
- **서버 상태**: TanStack Query (React Query) 5
- **애니메이션**: GSAP + Lenis (스무스 스크롤)
- **아이콘**: Lucide React
- **유틸리티**: clsx, class-variance-authority

## 프로젝트 구조 (간략)

```
front/
├── public/                  # 정적 파일
│   └── logo-*.png          # 로고 이미지 파일들
├── src/
│   ├── app/                # 애플리케이션 설정
│   │   ├── providers/      # React Context Providers
│   │   ├── App.tsx         # 최상위 App 컴포넌트
│   │   ├── RootLayout.tsx  # 레이아웃 컴포넌트
│   │   └── routes.tsx      # 라우팅 설정
│   ├── features/           # 기능별 모듈
│   │   ├── auth/           # 인증 관련
│   │   ├── board/          # 게시판
│   │   ├── chat/           # AI 챗봇
│   │   ├── home/           # 홈페이지
│   │   └── procedure/      # 절차 안내
│   ├── shared/             # 공유 리소스
│   │   ├── api/            # API 클라이언트
│   │   ├── assets/         # 이미지 등 에셋 파일
│   │   ├── config/         # 설정 파일들
│   │   ├── lib/            # 유틸리티 함수
│   │   ├── styles/         # 전역 스타일
│   │   ├── types/          # 타입 정의
│   │   └── ui/             # 공통 UI 컴포넌트
│   ├── store/              # 전역 상태 관리
│   ├── widgets/            # 위젯 컴포넌트
│   ├── main.tsx            # 애플리케이션 진입점
│   └── vite-env.d.ts       # Vite 타입 정의
├── index.html              # HTML 템플릿
├── vite.config.ts          # Vite 설정
├── tsconfig.json           # TypeScript 설정
├── tailwind.config.ts      # TailwindCSS 설정
├── postcss.config.js       # PostCSS 설정
├── eslint.config.js        # ESLint 설정
├── components.json         # UI 컴포넌트 설정
└── package.json            # 프로젝트 의존성
```

---

## 상세 프로젝트 구조

### 📁 루트 디렉토리

#### 설정 파일들

- **`package.json`**: 프로젝트 메타데이터 및 의존성 관리
  - React 19, TypeScript 최신 버전 사용
  - Vite를 번들러로 사용
  - dev, build, lint, preview 스크립트 제공

- **`vite.config.ts`**: Vite 빌드 도구 설정
  - React 플러그인 적용
  - `@` 경로 별칭을 `./src`로 설정하여 import 간소화

- **`tsconfig.json`**: TypeScript 컴파일러 설정
  - ES2020 타겟, strict 모드 활성화
  - Path alias (`@/*`) 설정
  - React JSX 지원

- **`tsconfig.node.json`**: Vite 설정 파일용 TypeScript 설정
  - Node 환경에서 실행되는 설정 파일 전용

- **`tailwind.config.ts`**: TailwindCSS 커스터마이징 설정
  - 커스텀 컬러 팔레트 정의 (라벤더, 틸 테마)
  - 다크모드 지원 (class 기반)
  - 커스텀 폰트 (Pretendard 등)

- **`postcss.config.js`**: PostCSS 설정
  - TailwindCSS와 Autoprefixer 플러그인 적용

- **`eslint.config.js`**: ESLint 린팅 규칙 설정
  - React 및 React Hooks 규칙 적용
  - 코드 품질 유지

- **`components.json`**: shadcn/ui 컴포넌트 라이브러리 설정
  - UI 컴포넌트 스타일 및 위치 정의

- **`index.html`**: 애플리케이션 HTML 템플릿
  - 메타 태그 (언어, 설명 등)
  - 파비콘 설정
  - React 루트 마운트 포인트

### 📁 `public/`
정적 파일 디렉토리 (빌드 시 그대로 복사됨)

- **`logo-1.png`, `logo-2.png`, `logo-3.png`**:
  - 애플리케이션 로고 이미지 파일들
  - 다양한 크기나 버전의 로고

### 📁 `src/`
애플리케이션 소스 코드 메인 디렉토리

#### 📁 `src/app/` - 애플리케이션 설정 및 진입점

- **`App.tsx`**:
  - 최상위 애플리케이션 컴포넌트
  - QueryProvider와 RouterProvider로 앱을 래핑
  - 전역 컨텍스트 프로바이더 구성

- **`RootLayout.tsx`**:
  - 모든 페이지에 공통으로 적용되는 레이아웃 컴포넌트
  - 사이드바, 헤더 등 공통 UI 요소 포함
  - Outlet으로 하위 라우트 렌더링

- **`routes.tsx`**:
  - React Router 라우팅 설정
  - 주요 라우트: /, /procedure, /chat, /board
  - 404 처리 및 리다이렉션 로직

##### 📁 `src/app/providers/` - Context Providers

- **`QueryProvider.tsx`**:
  - TanStack Query (React Query) 설정
  - 서버 상태 관리 및 캐싱 전략 구성
  - DevTools 포함 (개발 환경)

- **`RouterProvider.tsx`**:
  - React Router 프로바이더 설정
  - 라우팅 컨텍스트 제공

#### 📁 `src/features/` - 기능별 모듈 (Feature-Sliced Design)

##### 📁 `src/features/auth/` - 인증 기능

- **`auth.store.ts`**:
  - Zustand를 사용한 인증 상태 관리
  - 로그인/로그아웃 상태, 사용자 정보 관리

- **`LoginModal.tsx`**:
  - 로그인 모달 컴포넌트
  - 사용자 인증 UI

##### 📁 `src/features/board/` - 게시판 기능

- **`BoardPage.tsx`**:
  - 게시판 메인 페이지
  - 게시글 목록 표시

- **`board.types.ts`**:
  - 게시판 관련 TypeScript 타입 정의
  - Post, Comment 등의 인터페이스

###### 📁 `src/features/board/components/`

- **`WritePost.tsx`**:
  - 새 게시글 작성 컴포넌트
  - 제목, 내용, 카테고리 입력 폼

- **`EditPost.tsx`**:
  - 게시글 수정 컴포넌트
  - 기존 게시글 데이터 로드 및 수정

- **`PostDetail.tsx`**:
  - 게시글 상세 보기 컴포넌트
  - 댓글 표시 및 작성 기능

##### 📁 `src/features/chat/` - AI 챗봇 기능

- **`ChatPage.tsx`**:
  - AI 챗봇 메인 페이지
  - 채팅 인터페이스 및 메시지 표시

- **`chat.store.ts`**:
  - 채팅 상태 관리 (Zustand)
  - 메시지 히스토리, 채팅방 정보 관리

##### 📁 `src/features/home/` - 홈페이지

- **`HomePage.tsx`**:
  - 랜딩 페이지
  - 서비스 소개, 주요 기능 안내

##### 📁 `src/features/procedure/` - 절차 안내

- **`ProcedurePage.tsx`**:
  - 소비자 분쟁 조정 절차 안내 페이지
  - 단계별 프로세스 설명

#### 📁 `src/shared/` - 공유 리소스 및 유틸리티

##### 📁 `src/shared/api/` - API 통신

- **`client.ts`**:
  - REST API 클라이언트 구현
  - GET, POST, PUT, DELETE 메서드 제공
  - 환경변수로 API 베이스 URL 설정
  - 에러 핸들링 포함

##### 📁 `src/shared/assets/` - 에셋 파일

- **`icons/`**:
  - `icon-1.png`, `icon-2.png`, `icon-3.png`: 홈페이지 스토리텔링 애니메이션 아이콘
  - `logo-1.png`, `logo-2.png`, `logo-3.png`: 애플리케이션 로고 이미지
  - `procedure-1.png`, `procedure-2.png`, `procedure-3.png`: 조정절차 안내 이미지

##### 📁 `src/shared/config/` - 설정 파일

- **`index.ts`**:
  - 설정 파일들의 재내보내기 인덱스

- **`routes.ts`**:
  - 라우트 경로 상수 정의
  - HOME, PROCEDURE, CHAT, BOARD

- **`categories.ts`**:
  - 게시판 카테고리 설정
  - 분쟁 유형 분류

- **`query-keys.ts`**:
  - React Query 캐시 키 정의
  - API 쿼리 관리 용이성

- **`storage-keys.ts`**:
  - localStorage/sessionStorage 키 상수
  - 토큰, 사용자 정보 등 저장 키

##### 📁 `src/shared/lib/` - 유틸리티 함수

- **`utils.ts`**:
  - 범용 유틸리티 함수 모음
  - clsx, tailwind-merge 통합 (cn 함수)

- **`date.ts`**:
  - 날짜/시간 관련 유틸리티
  - 포맷팅, 상대 시간 표시

- **`number.ts`**:
  - 숫자 관련 유틸리티
  - 통화 포맷, 천 단위 구분

- **`validation.ts`**:
  - 폼 유효성 검사 함수
  - 이메일, 전화번호 등 검증

- **`storage.ts`**:
  - localStorage/sessionStorage 래퍼
  - 타입 안전한 스토리지 접근

- **`session.ts`**:
  - 세션 관리 유틸리티
  - 토큰 저장/조회/삭제

##### 📁 `src/shared/styles/` - 전역 스타일

- **`globals.css`**:
  - 전역 CSS 스타일
  - TailwindCSS 기본 레이어 import
  - 커스텀 CSS 변수 및 기본 스타일
  - 스크롤바 스타일링 (회색 계열 테마)

##### 📁 `src/shared/types/` - TypeScript 타입 정의

- **`index.ts`**:
  - 타입 정의 재내보내기

- **`common.ts`**:
  - 공통 타입 정의
  - ApiResponse, Pagination 등

- **`auth.ts`**:
  - 인증 관련 타입
  - User, LoginRequest, AuthResponse

- **`post.ts`**:
  - 게시글 관련 타입
  - Post, Comment, Category

- **`chat.ts`**:
  - 채팅 관련 타입
  - Message, ChatRoom, ChatParticipant

##### 📁 `src/shared/ui/` - 공통 UI 컴포넌트

- **`button.tsx`**:
  - 재사용 가능한 버튼 컴포넌트
  - variant, size 등 props 지원
  - class-variance-authority로 스타일 관리

- **`input.tsx`**:
  - 재사용 가능한 입력 필드 컴포넌트
  - 에러 상태, 레이블 등 지원

#### 📁 `src/store/` - 전역 상태 관리

- **`index.ts`**:
  - 스토어 통합 인덱스
  - 모든 스토어 재내보내기

- **`ui.store.ts`**:
  - UI 상태 관리 (Zustand)
  - 모달, 사이드바 열림/닫힘 등

#### 📁 `src/widgets/` - 위젯 컴포넌트

- **`Sidebar.tsx`**:
  - 사이드바 네비게이션 컴포넌트
  - 메뉴 항목: 홈, 조정신청 절차, AI 상담, 자유게시판
  - AI 상담 하위 메뉴: 새 상담 시작, 상담 내역
  - 채팅 기록이 많을 때 스크롤 지원
  - 반응형 디자인 (데스크톱/모바일)

#### 루트 레벨 파일

- **`main.tsx`**:
  - React 애플리케이션 진입점
  - ReactDOM.createRoot로 앱 마운트
  - StrictMode 래핑

- **`vite-env.d.ts`**:
  - Vite 환경 변수 TypeScript 타입 정의
  - import.meta.env 타입 지원

### 📁 `dist/`
빌드 출력 디렉토리 (프로덕션 빌드 결과물)

- 번들링된 JavaScript, CSS 파일
- 최적화된 정적 자산

### 📁 `node_modules/`
NPM 패키지 의존성 디렉토리

## 주요 기능

### 1. 홈페이지 (/)
- 서비스 소개 및 메인 랜딩 페이지
- GSAP 애니메이션 효과

### 2. 절차 안내 (/procedure)
- 소비자 분쟁 조정 절차 단계별 설명
- 시각적 프로세스 가이드

### 3. AI 챗봇 (/chat)
- 소비자 상담 AI 챗봇
- 실시간 대화형 인터페이스
- 상담 이력 저장

### 4. 게시판 (/board)
- 소비자 사례 공유 게시판
- 게시글 작성/수정/삭제/조회
- 카테고리별 분류
- 댓글 기능

## 개발 가이드

### 설치

```bash
npm install
```

### 개발 서버 실행

```bash
npm run dev
```

- 개발 서버: http://localhost:5173

### 프로덕션 빌드

```bash
npm run build
```

### 빌드 결과 미리보기

```bash
npm run preview
```

### 린팅

```bash
npm run lint
```

## 아키텍처 원칙

### Feature-Sliced Design (FSD)
- **features/**: 비즈니스 로직과 UI가 결합된 기능 단위
- **shared/**: 재사용 가능한 코드 (API, 유틸, 컴포넌트)
- **app/**: 애플리케이션 설정 및 프로바이더
- **widgets/**: 복합 UI 컴포넌트

### Path Alias
- `@/*` → `src/*` 경로로 간결한 import

### 상태 관리 전략
- **로컬 상태**: React useState/useReducer
- **전역 UI 상태**: Zustand
- **서버 상태**: TanStack Query (캐싱, 동기화)

### 스타일링 전략
- TailwindCSS 유틸리티 클래스
- 커스텀 컬러 팔레트 (라벤더, 틸)
- 반응형 디자인 지원

## 환경 변수

`.env` 파일에서 설정:

```env
VITE_API_BASE_URL=http://localhost:3000/api
```

## 브라우저 지원

- Chrome (최신)
- Firefox (최신)
- Safari (최신)
- Edge (최신)
