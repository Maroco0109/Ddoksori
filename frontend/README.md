# Frontend — DDOKSORI 소비자 분쟁 해결 플랫폼

> **스택**: React 19 · TypeScript (strict) · Vite · TailwindCSS · Zustand · TanStack Query

---

## 목차

1. [모듈 구조](#모듈-구조)
2. [라우팅](#라우팅)
3. [기능 모듈](#기능-모듈)
4. [상태 관리](#상태-관리)
5. [인증 체계](#인증-체계)
6. [기술 스택](#기술-스택)
7. [실행 방법](#실행-방법)
8. [테스트](#테스트)

---

## 모듈 구조

```
frontend/src/
├── main.tsx                     # React 앱 엔트리 포인트
├── app/                         # 앱 설정 및 라우팅
│   ├── App.tsx                  # 루트 컴포넌트 (QueryProvider + Router)
│   ├── RootLayout.tsx           # 전체 레이아웃 (Header + Sidebar + Outlet)
│   ├── routes.tsx               # 라우트 정의 (createBrowserRouter)
│   └── providers/               # QueryProvider, RouterProvider
│
├── features/                    # 기능별 모듈 (Feature-Sliced Design)
│   ├── admin/                   # 관리자 시스템 (별도 인증)
│   ├── auth/                    # OAuth 2.0 인증 (Google, Naver)
│   ├── board/                   # 커뮤니티 게시판
│   ├── chat/                    # AI 상담 챗봇
│   ├── home/                    # 랜딩 페이지
│   ├── mypage/                  # 마이페이지 (프로필, 이력)
│   └── procedure/               # 분쟁조정 절차 안내
│
├── shared/                      # 공유 모듈
│   ├── api/                     # HTTP 클라이언트, 서비스
│   ├── components/              # MarkdownRenderer 등 공통 컴포넌트
│   ├── config/                  # 라우트, 카테고리, 스토리지 키 상수
│   ├── lib/                     # 유틸리티 (citation, streaming, storage, cn)
│   ├── styles/                  # globals.css (Tailwind 지시어)
│   ├── types/                   # TypeScript 타입 (auth, chat, admin, post)
│   └── ui/                      # 기본 UI 컴포넌트 (Button, Input)
│
├── store/                       # 전역 Zustand 스토어
│   └── ui.store.ts              # UI 상태 (사이드바, 모달)
│
└── widgets/                     # 크로스 피처 컴포넌트
    └── Sidebar.tsx              # 네비게이션 사이드바
```

경로 별칭: `@/` → `frontend/src/`

---

## 라우팅

### 메인 레이아웃 (RootLayout)

| 경로 | 페이지 | 인증 |
|------|--------|------|
| `/` | HomePage | 불필요 |
| `/procedure` | ProcedurePage | 불필요 |
| `/chat` | ChatPage | 불필요 |
| `/board` | BoardPage | 불필요 |
| `/mypage` | MyPage | **필수** (미인증 시 홈으로 리다이렉트) |
| `/*` | 404 → 홈 리다이렉트 | - |

### 독립 라우트

| 경로 | 페이지 | 설명 |
|------|--------|------|
| `/auth/callback` | AuthCallback | OAuth 콜백 처리 (JWT 추출 → 스토어 저장) |
| `/admin/login` | AdminLoginPage | 관리자 로그인 |

### 관리자 라우트 (AdminGuard + AdminLayout)

| 경로 | 페이지 | 설명 |
|------|--------|------|
| `/admin/dashboard` | AdminDashboard | 대시보드 통계 |
| `/admin/posts` | AdminPostsPage | 게시글 관리 |
| `/admin/users` | AdminUsersPage | 사용자 관리 |
| `/admin/reports` | AdminReportsPage | 신고 관리 |

---

## 기능 모듈

### admin/ — 관리자 시스템

별도 인증 체계를 가진 관리자 패널.

| 파일 | 설명 |
|------|------|
| `AdminGuard.tsx` | 관리자 인증 가드 (미인증 시 `/admin/login` 리다이렉트) |
| `AdminLayout.tsx` | 관리자 전용 레이아웃 (사이드 네비게이션) |
| `AdminLoginPage.tsx` | 관리자 로그인 페이지 |
| `admin.store.ts` | 관리자 인증 Zustand 스토어 |
| `pages/AdminDashboard.tsx` | 대시보드 (통계, 최근 활동) |
| `pages/AdminPostsPage.tsx` | 게시글 관리 (승인/삭제) |
| `pages/AdminUsersPage.tsx` | 사용자 관리 (조회/정지/차단) |
| `pages/AdminReportsPage.tsx` | 신고 관리 (검토/처리) |

### auth/ — OAuth 인증

| 파일 | 설명 |
|------|------|
| `auth.store.ts` | 사용자 인증 스토어 (user, token, isAuthenticated) |
| `AuthCallback.tsx` | OAuth 콜백 핸들러 (URL 파라미터 → 스토어) |
| `LoginModal.tsx` | 로그인 모달 (Google, Naver 소셜 로그인) |

### chat/ — AI 상담 챗봇

| 파일 | 설명 |
|------|------|
| `ChatPage.tsx` | 메인 채팅 페이지 (분쟁/일반 상담 분리) |
| `chat.store.ts` | 채팅 세션·메시지 스토어 |
| `components/MessageBubble.tsx` | AI/사용자 메시지 버블 (마크다운 렌더링) |
| `components/CitationModal.tsx` | 인용 출처 모달 (기관, URL, 유사도) |
| `components/FollowupChips.tsx` | 후속 질문 칩 UI |
| `components/SafetyWarning.tsx` | 증거 부족 경고 |
| `components/StatusIndicator.tsx` | 연결 상태 표시 |
| `hooks/useChatMutation.ts` | 채팅 API 호출 훅 (React Query) |
| `hooks/useStreamingChat.ts` | SSE 스트리밍 채팅 훅 |

### mypage/ — 마이페이지

| 기능 | 설명 |
|------|------|
| 닉네임 편집 | 인라인 편집, 한글 가중치(1.6배) 검증 |
| 채팅 이력 | 분쟁/일반 세션 목록, 클릭 시 복원 |
| 내 게시글 | 작성한 게시글 페이지네이션 |
| 댓글 단 게시글 | 댓글 단 게시글 목록 |
| 계정 관리 | 로그아웃, 계정 삭제 (이중 확인) |

### board/ — 커뮤니티 게시판

카테고리: 전체, 분쟁해결사례, 질문답변, 꿀팁노하우
기능: 검색/필터, CRUD, 페이지네이션, 반응형 (모바일 카드 / 데스크톱 테이블)

### home/ — 랜딩 페이지

히어로 섹션, 피처 그리드, 통계, Bell 캐릭터 인터랙션 (GSAP + Lenis 스크롤)

### procedure/ — 절차 안내

분쟁조정 절차 단계별 시각화

---

## 상태 관리

4개 Zustand 스토어로 분산 관리.

| 스토어 | 위치 | 영속성 | 스토리지 키 |
|--------|------|--------|------------|
| `useAuthStore` | `features/auth/auth.store.ts` | localStorage | `user-data` |
| `useAdminStore` | `features/admin/admin.store.ts` | localStorage | `admin-auth-storage` |
| `useChatStore` | `features/chat/chat.store.ts` | localStorage (로그인) / sessionStorage (게스트) | 커스텀 |
| `useUIStore` | `store/ui.store.ts` | 메모리 (비영속) | - |

### 세션 관리

| 사용자 유형 | 저장소 | 만료 | 세션 수 |
|------------|--------|------|---------|
| 로그인 | localStorage | `expiresAt: null` (무제한) | 무제한 |
| 게스트 | sessionStorage | 7일 | 제한적 |

로그인 시 `transferGuestSessions()`로 게스트 세션 자동 이전.

---

## 인증 체계

### 사용자 인증 (OAuth 2.0)

```
사용자 → LoginModal (Google/Naver 버튼)
            ↓
    Backend /auth/{provider}
            ↓
    OAuth Provider (Google/Naver)
            ↓
    Backend /auth/{provider}/callback → JWT 생성
            ↓
    Frontend /auth/callback?token=...&user=...
            ↓
    AuthCallback.tsx → auth.store → localStorage
            ↓
    이후 요청: Authorization: Bearer <JWT>
```

### 관리자 인증 (별도 시스템)

```
관리자 → /admin/login
            ↓
    Backend /api/admin/login → 관리자 JWT
            ↓
    admin.store → localStorage
            ↓
    AdminGuard → /admin/* 접근 허용
```

---

## 기술 스택

| 분류 | 기술 | 버전 |
|------|------|------|
| 프레임워크 | React | 19.2.0 |
| 언어 | TypeScript | 5.9.3 |
| 빌드 | Vite | 7.2.4 |
| 스타일링 | TailwindCSS | 3.4.19 |
| 상태관리 | Zustand | 5.0.9 |
| 서버 상태 | TanStack React Query | 5.90.16 |
| 라우팅 | React Router DOM | 6.28.0 |
| 애니메이션 | GSAP | 3.14.2 |
| 스크롤 | Lenis | 1.3.17 |
| 아이콘 | Lucide React | 0.562.0 |
| 마크다운 | React Markdown | 10.1.0 |
| 코드 하이라이트 | react-syntax-highlighter | 16.1.0 |
| 유틸리티 | clsx, tailwind-merge, CVA | 2.1.1, 3.4.0, 0.7.1 |

---

## 실행 방법

```bash
# 의존성 설치
npm install

# 환경변수 설정
# .env 파일: VITE_API_BASE_URL=http://localhost:8000

# 개발 서버
npm run dev          # http://localhost:5173

# 프로덕션 빌드
npm run build
npm run preview

# 린트
npm run lint         # ESLint
npm run lint -- --fix

# Docker
docker build -t ddoksori-frontend -f frontend/Dockerfile frontend/
docker run -p 80:80 ddoksori-frontend
```

---

## 테스트

### 단위 테스트 (Vitest)

```bash
npm test             # 전체 실행
npm run test:watch   # Watch 모드
```

### E2E 테스트 (Playwright)

24개 테스트, 5개 파일.

```bash
npm run test:e2e     # 전체 E2E 실행
npx playwright test --ui  # UI 모드
```

| 테스트 파일 | 커버리지 |
|------------|----------|
| `admin.spec.ts` | 관리자 인증, 라우트 가드 |
| `auth.spec.ts` | OAuth 흐름, 콜백, MyPage 리다이렉트 |
| `chat.spec.ts` | 채팅 페이지 렌더링, 메시지 전송 |
| `mypage.spec.ts` | 인증 리다이렉트, 프로필 표시 |
| `routes.spec.ts` | 네비게이션, 404 처리 |

---

## 색상 팔레트

```typescript
// tailwind.config.ts
colors: {
  'dark-navy': '#2B2D42',     // 텍스트, 배경
  'gray-purple': '#555B6E',   // 부가 텍스트
  'lavender': '#B8A9C9',      // AI 메시지, 경계
  'beige-pink': '#D4C5D0',    // 강조
  'ivory': '#FAF0E6',         // 배경
  'deep-teal': '#0A7E8C',     // 분쟁 상담, 주 CTA
  'mint-green': '#8ECFC0',    // 일반 상담, 호버
  'coral': '#E9967A',         // 추가 강조
}
```

| 용도 | 색상 | 클래스 |
|------|------|--------|
| 분쟁 상담 | Deep Teal | `bg-deep-teal` |
| 일반 상담 | Mint Green | `bg-mint-green` |
| AI 메시지 | Lavender | `bg-lavender` |
| 전체 배경 | Ivory | `bg-ivory` |
