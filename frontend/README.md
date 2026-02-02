# Frontend 구조 및 설명

> **똑소리 프로젝트** - 한국 소비자 분쟁 조정 RAG 챗봇 프론트엔드

## 목차
1. [폴더 및 파일 구조도](#폴더-및-파일-구조도)
2. [핵심 아키텍처](#핵심-아키텍처)
3. [주요 특징](#주요-특징)
4. [기술 스택](#기술-스택)
5. [상태 관리 상세 (Zustand)](#상태-관리-상세-zustand)
6. [주요 페이지 및 컴포넌트](#주요-페이지-및-컴포넌트)
7. [데이터 흐름](#데이터-흐름)

---

## 폴더 및 파일 구조도

```
frontend/
│
├── 📄 환경 설정 파일
│   ├── package.json                   # npm 패키지 의존성 및 스크립트
│   ├── tsconfig.json                  # TypeScript 설정 (strict 모드)
│   ├── tsconfig.node.json             # Node.js용 TypeScript 설정
│   ├── vite.config.ts                 # Vite 빌드 설정 (경로 별칭 @/* 포함)
│   ├── tailwind.config.ts             # Tailwind CSS 테마 및 색상 팔레트
│   ├── postcss.config.js              # PostCSS 설정
│   ├── eslint.config.js               # ESLint 규칙
│   └── Dockerfile                     # Docker 컨테이너 빌드 설정
│
├── 📄 index.html                      # HTML 엔트리 포인트 (Vite SPA)
│
└── 📁 src/                            # 소스 코드 루트
    │
    ├── main.tsx                       # ★ React 앱 엔트리 포인트
    │                                  # - ReactDOM.createRoot 렌더링
    │                                  # - 전역 스타일 import
    │
    ├── vite-env.d.ts                  # Vite 환경 타입 선언
    │
    ├── 🚀 app/ - 앱 설정 및 라우팅
    │   ├── App.tsx                    # ★ 루트 앱 컴포넌트
    │   │                              # - QueryProvider 래핑
    │   │                              # - RouterProvider 설정
    │   │
    │   ├── RootLayout.tsx             # ★ 전체 레이아웃 컴포넌트
    │   │                              # - 헤더 (로고 + "1초 만에 시작하기" 버튼)
    │   │                              # - Sidebar 렌더링
    │   │                              # - LoginModal 렌더링
    │   │                              # - Outlet (페이지 렌더링 영역)
    │   │                              # - 스크롤 위치 복원
    │   │
    │   ├── routes.tsx                 # 라우트 정의
    │   │                              # - HOME: /
    │   │                              # - PROCEDURE: /procedure
    │   │                              # - CHAT: /chat
    │   │                              # - BOARD: /board
    │   │
    │   └── providers/                 # Context Providers
    │       ├── QueryProvider.tsx      # React Query 설정
    │       │                          # - staleTime: 5분
    │       │                          # - retry: 1번
    │       │                          # - DevTools 포함
    │       │
    │       └── RouterProvider.tsx     # React Router 설정
    │                                  # - BrowserRouter 기반
    │
    ├── 🎯 features/ - 기능별 모듈 (Feature-based 구조)
    │   │
    │   ├── auth/ - 인증 기능
    │   │   ├── auth.store.ts          # ★ 인증 상태관리 (Zustand)
    │   │   │                          # - user, token, isAuthenticated 상태
    │   │   │                          # - localStorage persist 지원
    │   │   │                          # - 로그인/로그아웃 액션
    │   │   │
    │   │   └── LoginModal.tsx         # 로그인/회원가입 모달
    │   │                              # - 제목: "1초 만에 시작하기"
    │   │                              # - 소셜 로그인 (카카오, 네이버)
    │   │                              # - 폼 검증
    │   │
    │   ├── chat/ - AI 상담 챗봇 기능
    │   │   ├── ChatPage.tsx           # ★ 메인 채팅 페이지 (800+ 줄)
    │   │   │                          # - 분쟁 상담 섹션 (틸 색상)
    │   │   │                          # - 일반 상담 섹션 (민트 색상)
    │   │   │                          # - 온보딩 폼 (분쟁 상담용)
    │   │   │                          # - 메시지 입력 및 전송
    │   │   │                          # - 스트리밍 애니메이션
    │   │   │
    │   │   ├── chat.store.ts          # ★ 채팅 상태관리 (Zustand)
    │   │   │                          # - 분쟁/일반 메시지 배열
    │   │   │                          # - 세션 관리 (저장/로드/삭제)
    │   │   │                          # - 게스트 세션 24시간 만료
    │   │   │
    │   │   ├── components/            # 채팅 관련 컴포넌트
    │   │   │   ├── MessageBubble.tsx  # ★ 메시지 버블 컴포넌트
    │   │   │   │                      # - AI/사용자 메시지 구분
    │   │   │   │                      # - 마크다운 렌더링
    │   │   │   │                      # - 인용 [N] 클릭 지원
    │   │   │   │
    │   │   │   ├── CitationModal.tsx  # 인용 출처 모달
    │   │   │   │                      # - 출처 기관, URL, 결정일 표시
    │   │   │   │                      # - 유사도 점수 표시
    │   │   │   │
    │   │   │   └── SafetyWarning.tsx  # 안전 경고 컴포넌트
    │   │   │                          # - 증거 부족 시 표시
    │   │   │                          # - 추가 질문 목록
    │   │   │
    │   │   └── hooks/                 # 커스텀 훅
    │   │       └── useChatMutation.ts # API 호출 훅 (React Query)
    │   │
    │   ├── board/ - 자유게시판 기능
    │   │   ├── BoardPage.tsx          # ★ 게시판 메인 페이지 (800+ 줄)
    │   │   │                          # - 카테고리 탭 (전체/분쟁해결/Q&A/꿀팁)
    │   │   │                          # - 검색 및 필터
    │   │   │                          # - 페이지네이션
    │   │   │                          # - 반응형 (모바일: 카드, 데스크톱: 테이블)
    │   │   │
    │   │   ├── board.types.ts         # 게시판 타입 정의
    │   │   │
    │   │   └── components/            # 게시판 컴포넌트
    │   │       ├── WritePost.tsx      # 글 작성 컴포넌트
    │   │       ├── PostDetail.tsx     # 글 상세보기 컴포넌트
    │   │       └── EditPost.tsx       # 글 수정 컴포넌트
    │   │
    │   ├── home/ - 홈페이지
    │   │   └── HomePage.tsx           # ★ 랜딩 페이지 (240+ 줄)
    │   │                              # - Lenis 부드러운 스크롤
    │   │                              # - 히어로 섹션 (슬로건 + CTA)
    │   │                              # - 피처 그리드 (3열)
    │   │                              # - 통계 섹션
    │   │                              # - Bell 캐릭터 인터랙션 섹션
    │   │
    │   └── procedure/ - 절차 안내
    │       └── ProcedurePage.tsx      # 분쟁조정 절차 안내 페이지
    │
    ├── 📦 shared/ - 공유 모듈
    │   │
    │   ├── api/ - API 클라이언트
    │   │   ├── client.ts              # ★ HTTP 클라이언트 (fetch 기반)
    │   │   │                          # - GET, POST, PUT, DELETE 메서드
    │   │   │                          # - JSON 자동 처리
    │   │   │                          # - VITE_API_BASE_URL 환경변수
    │   │   │
    │   │   └── chat.service.ts        # 채팅 API 서비스
    │   │                              # - sendMessage(): /chat 호출
    │   │
    │   ├── assets/ - 정적 자산
    │   │   └── icons/                 # 아이콘 이미지
    │   │       ├── logo-*.png         # 똑소리 로고
    │   │       ├── bell_1.png         # Bell 캐릭터 (상담 전, 화난 표정)
    │   │       ├── bell_2.png         # Bell 캐릭터 (상담 후, 웃는 표정)
    │   │       ├── procedure-*.png    # 절차 안내 이미지
    │   │       └── ...                # 기타 아이콘
    │   │
    │   ├── components/ - 공유 컴포넌트
    │   │   ├── index.ts               # 컴포넌트 export
    │   │   └── MarkdownRenderer.tsx   # ★ 마크다운 렌더러
    │   │                              # - react-markdown 기반
    │   │                              # - 인용 [N] 파싱 및 클릭 처리
    │   │                              # - 코드 하이라이트 지원
    │   │
    │   ├── config/ - 설정 상수
    │   │   ├── index.ts               # 설정 export
    │   │   ├── routes.ts              # 라우트 경로 상수
    │   │   ├── categories.ts          # 게시판 카테고리 상수
    │   │   ├── storage-keys.ts        # LocalStorage 키 상수
    │   │   └── query-keys.ts          # React Query 키 상수
    │   │
    │   ├── lib/ - 유틸리티 함수
    │   │   ├── citation.tsx           # ★ 인용 추출/렌더링 유틸
    │   │   │                          # - extractCitations(): 텍스트에서 [N] 추출
    │   │   │                          # - renderWithCitations(): JSX 변환
    │   │   │
    │   │   ├── streaming.ts           # 스트리밍 애니메이션 유틸
    │   │   │                          # - 글자 하나씩 나타나는 효과
    │   │   │
    │   │   ├── storage.ts             # ★ 스토리지 래퍼
    │   │   │                          # - localStorage/sessionStorage 추상화
    │   │   │                          # - JSON 자동 파싱
    │   │   │
    │   │   ├── session.ts             # 세션 ID 생성
    │   │   │                          # - 게스트 세션 UUID 생성
    │   │   │
    │   │   ├── date.ts                # 날짜 포맷팅 유틸
    │   │   ├── number.ts              # 숫자 포맷팅 유틸
    │   │   ├── validation.ts          # 폼 검증 유틸
    │   │   └── utils.ts               # 일반 유틸 (cn 함수 등)
    │   │
    │   ├── styles/
    │   │   └── globals.css            # 전역 CSS (Tailwind 지시어)
    │   │
    │   ├── types/ - TypeScript 타입
    │   │   ├── index.ts               # 타입 export
    │   │   ├── common.ts              # 공통 타입
    │   │   ├── auth.ts                # 인증 관련 타입
    │   │   ├── chat.ts                # 채팅 관련 타입
    │   │   ├── chat.types.ts          # ★ 백엔드 API 계약 타입
    │   │   │                          # - ChatAPIRequest/Response
    │   │   │                          # - SourceMetadata (출처 정보)
    │   │   │                          # - Citation (인용 정보)
    │   │   │                          # - MessageWithCitations
    │   │   │
    │   │   └── post.ts                # 게시판 관련 타입
    │   │
    │   └── ui/ - 기본 UI 컴포넌트
    │       ├── button.tsx             # Button 컴포넌트 (CVA 기반)
    │       └── input.tsx              # Input 컴포넌트
    │
    ├── 🗄️ store/ - 전역 상태관리
    │   ├── index.ts                   # 스토어 export
    │   └── ui.store.ts                # UI 상태관리 (Zustand)
    │                                  # - 사이드바 열림/닫힘
    │                                  # - 로그인 모달 열림/닫힘
    │
    └── 🧩 widgets/ - 위젯 컴포넌트
        └── Sidebar.tsx                # ★ 사이드바 네비게이션
                                       # - 로고
                                       # - 네비게이션 메뉴
                                       # - 새 채팅 버튼
                                       # - 채팅 세션 목록
                                       # - 로그인/로그아웃 버튼
```

---

## 핵심 아키텍처

### React 앱 구조 (컴포넌트 트리)

```
main.tsx
    │
    └── App.tsx
        │
        └── QueryProvider (React Query)
            │
            └── RouterProvider (React Router)
                │
                └── RootLayout
                    │
                    ├── Sidebar (widgets/)
                    │   ├── 로고
                    │   ├── 네비게이션 메뉴
                    │   ├── 새 채팅 버튼
                    │   ├── 채팅 세션 목록
                    │   └── 로그인/로그아웃
                    │
                    ├── LoginModal (features/auth/)
                    │   ├── 제목: "1초 만에 시작하기"
                    │   └── 소셜 로그인 버튼 (카카오, 네이버)
                    │
                    └── <Outlet /> (페이지 렌더링)
                        │
                        ├── HomePage (/)
                        │   ├── 히어로 섹션 (슬로건 + CTA 버튼)
                        │   ├── 피처 그리드 (3열)
                        │   ├── 통계 섹션
                        │   └── Bell 캐릭터 인터랙션 섹션
                        │
                        ├── ChatPage (/chat)
                        │   ├── 분쟁 상담 섹션
                        │   │   ├── DisputeForm (온보딩)
                        │   │   └── ChatMessages
                        │   │       └── MessageBubble
                        │   │           └── MarkdownRenderer
                        │   │               └── CitationModal
                        │   │
                        │   └── 일반 상담 섹션
                        │       └── ChatMessages
                        │           └── MessageBubble
                        │
                        ├── BoardPage (/board)
                        │   ├── 카테고리 탭
                        │   ├── 검색바
                        │   ├── 게시글 목록/카드
                        │   ├── 페이지네이션
                        │   └── WritePost / PostDetail / EditPost
                        │
                        └── ProcedurePage (/procedure)
```

### 상태 관리 아키텍처 (Zustand)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Zustand 스토어 구조                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐   ┌──────────────────────┐               │
│  │    useAuthStore      │   │    useChatStore      │               │
│  │   (features/auth)    │   │   (features/chat)    │               │
│  ├──────────────────────┤   ├──────────────────────┤               │
│  │ • user               │   │ • disputeMessages    │               │
│  │ • token              │   │ • generalMessages    │               │
│  │ • isAuthenticated    │   │ • chatSessions       │               │
│  │ • login()            │   │ • currentSessionId   │               │
│  │ • logout()           │   │ • saveChatSession()  │               │
│  │                      │   │ • loadChatSessions() │               │
│  │ [localStorage]       │   │ • startNewChat()     │               │
│  │   persist            │   │                      │               │
│  └──────────────────────┘   │ [localStorage]       │               │
│                             │   로그인 사용자       │               │
│                             │ [sessionStorage]     │               │
│                             │   비로그인 사용자     │               │
│                             └──────────────────────┘               │
│                                                                     │
│  ┌──────────────────────┐                                          │
│  │     useUIStore       │                                          │
│  │      (store/)        │                                          │
│  ├──────────────────────┤                                          │
│  │ • isSidebarOpen      │                                          │
│  │ • isLoginModalOpen   │                                          │
│  │ • toggleSidebar()    │                                          │
│  │ • openLoginModal()   │                                          │
│  │                      │                                          │
│  │ [메모리 only]         │                                          │
│  └──────────────────────┘                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 주요 특징

### 1. Feature-based 폴더 구조

- **모듈화**: 기능별로 폴더 분리 (auth, chat, board, home, procedure)
- **응집도**: 관련 컴포넌트, 스토어, 훅이 같은 폴더에 위치
- **확장성**: 새 기능 추가 시 features/ 하위에 폴더만 추가

```
features/
├── auth/          # 인증 기능 전담
├── chat/          # AI 상담 기능 전담
├── board/         # 게시판 기능 전담
├── home/          # 홈페이지 전담
└── procedure/     # 절차 안내 전담
```

### 2. 분쟁/일반 상담 분리 UI

```
┌─────────────────────────────────────────────────────────────────┐
│                        ChatPage                                  │
├────────────────────────────┬────────────────────────────────────┤
│     분쟁 상담 (Teal)        │      일반 상담 (Mint)              │
├────────────────────────────┼────────────────────────────────────┤
│  • 온보딩 폼 필수           │  • 자유로운 질문                    │
│    - 구매일자               │  • 바로 채팅 시작                   │
│    - 구매처                 │                                    │
│    - 플랫폼                 │                                    │
│    - 품목                   │                                    │
│    - 금액                   │                                    │
│    - 분쟁 상세              │                                    │
│                            │                                    │
│  • 구조화된 정보 수집        │  • 일반적인 소비자 문의             │
└────────────────────────────┴────────────────────────────────────┘
```

### 3. 인용 시스템 (Citation)

- **마크다운 내 [N] 인용**: 텍스트에서 `[1]`, `[2]` 등 자동 감지
- **클릭 시 모달**: 출처 상세 정보 표시
- **출처 정보**:
  - 기관명 (source_org)
  - 문서 제목 (doc_title)
  - 결정일 (decision_date)
  - URL (url)
  - 유사도 점수 (similarity)

### 4. Safety Guardrails (안전 장치)

```typescript
// 백엔드 응답
{
  has_sufficient_evidence: false,  // 증거 부족
  clarifying_questions: [
    "분쟁 발생 날짜가 언제인가요?",
    "구입한 제품의 구체적인 명칭은?"
  ]
}

// 프론트엔드 렌더링
┌─────────────────────────────────────┐
│ ⚠️ 추가 정보가 필요합니다           │
│                                     │
│ • 분쟁 발생 날짜가 언제인가요?       │
│ • 구입한 제품의 구체적인 명칭은?     │
└─────────────────────────────────────┘
```

### 5. 세션 관리

| 사용자 유형 | 저장소 | 세션 수 | 만료 |
|------------|--------|---------|------|
| 로그인 사용자 | localStorage | 무제한 | 없음 |
| 비로그인 사용자 | sessionStorage | 최대 1개 | 24시간 |

### 6. 반응형 디자인

```
모바일 (< 768px)        태블릿 (768px ~)        데스크톱 (1024px ~)
┌────────────────┐     ┌────────────────┐     ┌────────────────────────┐
│   사이드바 숨김  │     │  사이드바 접힘  │     │ 사이드바 │   콘텐츠    │
│                │     │                │     │  고정    │             │
│    전체 폭     │     │    좌우 패딩   │     │         │  max-w-7xl  │
│    카드 뷰     │     │               │     │         │  테이블 뷰   │
└────────────────┘     └────────────────┘     └────────────────────────┘
```

### 7. 스트리밍 애니메이션

- AI 응답 시 글자가 하나씩 나타나는 타이핑 효과
- `streaming.ts` 유틸리티로 구현
- 사용자 경험 향상

---

## 기술 스택

| 분류 | 기술 | 버전 |
|------|------|------|
| **프레임워크** | React | 19.2.0 |
| **언어** | TypeScript | 5.9.3 |
| **빌드 도구** | Vite | 7.2.4 |
| **스타일링** | Tailwind CSS | 3.4.19 |
| **상태관리** | Zustand | 5.0.9 |
| **데이터 페칭** | TanStack React Query | 5.90.16 |
| **라우팅** | React Router DOM | 6.28.0 |
| **애니메이션** | GSAP | 3.14.2 |
| **스크롤** | Lenis | 1.3.17 |
| **아이콘** | Lucide React | 0.562.0 |
| **마크다운** | React Markdown | 10.1.0 |
| **코드 하이라이트** | react-syntax-highlighter | 16.1.0 |
| **유틸리티** | clsx, tailwind-merge | 2.1.1, 3.4.0 |

---

## 상태 관리 상세 (Zustand)

> 총 3개의 Zustand 스토어로 분산 상태 관리

### 스토어 요약

| 스토어 | 위치 | 역할 | 지속성 |
|--------|------|------|--------|
| **useAuthStore** | features/auth/auth.store.ts | 인증 상태 | localStorage (persist) |
| **useChatStore** | features/chat/chat.store.ts | 채팅 메시지/세션 | localStorage/sessionStorage |
| **useUIStore** | store/ui.store.ts | UI 상태 (사이드바, 모달) | 메모리 |

---

### 1. useAuthStore (인증 스토어)

```typescript
interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  register: (data: RegisterData) => Promise<void>;
}
```

**특징**:
- localStorage에 자동 persist
- 로그인 시 게스트 세션 자동 이전
- JWT 토큰 관리

---

### 2. useChatStore (채팅 스토어)

```typescript
interface ChatState {
  // 상태
  currentSessionId: string | null;      // 현재 세션 ID
  activeChatType: 'dispute' | 'general' | null;
  chatSessions: ChatSession[];          // 저장된 세션 목록
  disputeMessages: MessageWithCitations[];  // 분쟁 상담 메시지
  generalMessages: MessageWithCitations[];  // 일반 상담 메시지
  isDisputeLoading: boolean;
  isGeneralLoading: boolean;
  isFormSubmitted: boolean;             // 온보딩 폼 제출 여부

  // Actions
  loadChatSessions: (isLoggedIn: boolean) => void;
  saveChatSession: (type, messages, isLoggedIn) => void;
  deleteChatSession: (sessionId, isLoggedIn) => void;
  refreshSessionTime: (sessionId) => void;
  startNewChat: () => void;
}
```

**특징**:
- 로그인 사용자: localStorage에 무제한 저장
- 비로그인 사용자: sessionStorage에 최대 1개, 24시간 만료
- 세션 자동 저장/복원

---

### 3. useUIStore (UI 스토어)

```typescript
interface UIState {
  isSidebarOpen: boolean;
  isLoginModalOpen: boolean;

  // Actions
  toggleSidebar: () => void;
  openLoginModal: () => void;
  closeLoginModal: () => void;
}
```

**특징**:
- 메모리에만 저장 (새로고침 시 초기화)
- 사이드바, 모달 상태 관리

---

### 스토어 사용 예시

```typescript
// 컴포넌트에서 사용
import { useAuthStore } from '@/features/auth/auth.store';
import { useChatStore } from '@/features/chat/chat.store';

function ChatPage() {
  const { isAuthenticated } = useAuthStore();
  const { disputeMessages, saveChatSession } = useChatStore();

  // 메시지 저장
  saveChatSession('dispute', disputeMessages, isAuthenticated);
}
```

---

## 주요 페이지 및 컴포넌트

### 페이지 요약

| 페이지 | 경로 | 파일 | 설명 |
|--------|------|------|------|
| **홈** | `/` | HomePage.tsx | 랜딩 페이지, GSAP 애니메이션 |
| **AI 상담** | `/chat` | ChatPage.tsx | 분쟁/일반 상담 챗봇 |
| **게시판** | `/board` | BoardPage.tsx | 자유게시판 CRUD |
| **절차 안내** | `/procedure` | ProcedurePage.tsx | 분쟁조정 절차 설명 |

---

### 1. ChatPage (AI 상담 페이지)

**위치**: `src/features/chat/ChatPage.tsx`

**구조**:
```
ChatPage
├── 헤더 (채팅 타입 표시)
│
├── 분쟁 상담 섹션 (좌측, Teal 색상)
│   ├── DisputeOnboardingForm (초기)
│   │   ├── 구매일자 입력
│   │   ├── 구매처 입력
│   │   ├── 플랫폼 선택
│   │   ├── 품목 입력
│   │   ├── 금액 입력
│   │   └── 분쟁 상세 입력
│   │
│   └── ChatArea (폼 제출 후)
│       ├── MessageList
│       │   └── MessageBubble (반복)
│       │       ├── AI 메시지 (마크다운 + 인용)
│       │       └── 사용자 메시지
│       │
│       └── MessageInput
│
└── 일반 상담 섹션 (우측, Mint 색상)
    └── ChatArea
        ├── MessageList
        └── MessageInput
```

**주요 기능**:
- 온보딩 폼으로 구조화된 정보 수집
- 마크다운 렌더링 (코드 하이라이트 포함)
- 인용 클릭 시 모달로 출처 확인
- 스트리밍 타이핑 애니메이션
- 세션 자동 저장

---

### 2. BoardPage (게시판 페이지)

**위치**: `src/features/board/BoardPage.tsx`

**구조**:
```
BoardPage
├── 헤더
│   ├── 제목 ("자유게시판")
│   └── 글쓰기 버튼
│
├── 카테고리 탭
│   ├── 전체
│   ├── 분쟁해결사례
│   ├── 질문답변
│   └── 꿀팁노하우
│
├── 검색바
│   ├── 검색 타입 (제목/작성자/내용/제목+내용)
│   └── 검색 입력
│
├── 게시글 목록
│   ├── 데스크톱: 테이블 뷰
│   └── 모바일: 카드 뷰
│
├── 페이지네이션
│   ├── 페이지당 개수 (10/30/50)
│   └── 페이지 번호
│
└── 모달/서브페이지
    ├── WritePost (글 작성)
    ├── PostDetail (글 상세)
    └── EditPost (글 수정)
```

**카테고리 타입**:
| 카테고리 | 설명 |
|----------|------|
| `all` | 전체 |
| `resolution` | 분쟁해결사례 |
| `qna` | 질문답변 |
| `tips` | 꿀팁노하우 |

---

### 3. HomePage (홈페이지)

**위치**: `src/features/home/HomePage.tsx`

**구조**:
```
HomePage
├── 히어로 섹션
│   ├── 메인 타이틀 ("똑똑한 소비자의 권리, 똑소리가 지켜드립니다")
│   └── CTA 버튼 (무료 상담 시작하기)
│
├── 피처 그리드 (3열)
│   ├── AI 챗봇
│   ├── 실제 공공 데이터
│   └── 커뮤니티를 통한 경험 공유
│
├── 통계 섹션
│   ├── 무료 (AI 상담 비용)
│   ├── 즉시 (24/7 실시간 상담)
│   └── 유일 (소비자 커뮤니티)
│
└── Bell 캐릭터 인터랙션 섹션
    ├── 안내 텍스트 ("저를 쓰다듬어 주세요!")
    ├── Bell 이미지 (상담 전/후 전환)
    │   ├── bell_1.png (화난 표정) → 마우스/터치로 쓰다듬기
    │   └── bell_2.png (웃는 표정) → 쓰다듬기 완료 시 전환
    ├── 상태 텍스트 ("상담 받기 전/후의 모습")
    └── 진행 바 (쓰다듬기 진행률 표시)
```

**인터랙션**:
- Bell 캐릭터 쓰다듬기: 마우스/터치 이동 시 진행 바 증가
- 10회 쓰다듬기 완료 시 화난 표정 → 웃는 표정으로 전환
- 쓰로틀링(150ms) 적용으로 자연스러운 인터랙션

**스크롤**:
- Lenis: 부드러운 스크롤 효과

---

### 4. 공통 컴포넌트

| 컴포넌트 | 위치 | 설명 |
|----------|------|------|
| **Sidebar** | widgets/Sidebar.tsx | 네비게이션 사이드바 |
| **LoginModal** | features/auth/LoginModal.tsx | 로그인/회원가입 모달 |
| **MessageBubble** | features/chat/components/ | 채팅 메시지 버블 |
| **MarkdownRenderer** | shared/components/ | 마크다운 렌더러 |
| **CitationModal** | features/chat/components/ | 인용 출처 모달 |
| **Button** | shared/ui/button.tsx | 버튼 컴포넌트 (CVA) |
| **Input** | shared/ui/input.tsx | 입력 컴포넌트 |

---

## 데이터 흐름

### 1. API 통신 흐름

```
사용자 입력
    │
    ▼
ChatPage (메시지 전송)
    │
    ▼
useChatMutation (React Query)
    │
    ▼
chat.service.ts - sendMessage()
    │
    ▼
client.ts - POST /chat
    │
    ▼
Backend API (FastAPI :8000)
    │
    ▼
응답 수신 (ChatAPIResponse)
    │
    ├── answer: 마크다운 답변
    ├── sources: 출처 메타데이터 배열
    ├── has_sufficient_evidence: 증거 충분 여부
    └── clarifying_questions: 추가 질문
    │
    ▼
citation.tsx - extractCitations()
    │
    ▼
MessageWithCitations 생성
    │
    ▼
useChatStore - 메시지 저장
    │
    ▼
MessageBubble - 렌더링
    │
    ├── MarkdownRenderer (답변)
    └── CitationModal (인용 클릭 시)
```

### 2. 상태 저장 흐름

```
메시지 생성
    │
    ▼
useChatStore.saveChatSession()
    │
    ├── 로그인 사용자?
    │   ├── YES → localStorage (무제한)
    │   └── NO  → sessionStorage (1개, 24시간)
    │
    ▼
storage.ts - set()
    │
    ▼
JSON 직렬화 후 저장
```

### 3. 세션 복원 흐름

```
앱 시작 / 새로고침
    │
    ▼
RootLayout 마운트
    │
    ▼
useChatStore.loadChatSessions(isLoggedIn)
    │
    ├── 저장소에서 세션 로드
    ├── 만료된 세션 필터링 (비로그인)
    └── chatSessions 상태 업데이트
    │
    ▼
Sidebar에 세션 목록 표시
    │
    ▼
세션 클릭 → 메시지 복원
```

---

## 색상 팔레트

### Tailwind 커스텀 색상

```typescript
// tailwind.config.ts
colors: {
  // Primary Palette
  'dark-navy': '#2B2D42',      // 텍스트, 배경
  'gray-purple': '#555B6E',    // 부가 텍스트
  'lavender': '#B8A9C9',       // AI 메시지, 경계
  'beige-pink': '#D4C5D0',     // 강조
  'ivory': '#FAF0E6',          // 배경

  // Accent Palette
  'deep-teal': '#0A7E8C',      // 분쟁 상담, 주 CTA
  'mint-green': '#8ECFC0',     // 일반 상담, 호버
  'coral': '#E9967A',          // 추가 강조
}
```

### 사용 예시

| 용도 | 색상 | Tailwind 클래스 |
|------|------|-----------------|
| 분쟁 상담 배경 | Deep Teal | `bg-deep-teal` |
| 일반 상담 배경 | Mint Green | `bg-mint-green` |
| 텍스트 | Dark Navy | `text-dark-navy` |
| AI 메시지 배경 | Lavender | `bg-lavender` |
| 전체 배경 | Ivory | `bg-ivory` |

---

## API 연동

### Base URL

```typescript
// .env
VITE_API_BASE_URL=http://localhost:8000
```

### 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/chat` | RAG 기반 답변 생성 |
| POST | `/search` | 벡터 검색만 수행 |
| GET | `/health` | 서버 상태 확인 |

### 요청/응답 타입

```typescript
// 요청
interface ChatAPIRequest {
  message: string;
  top_k?: number;
  chunk_types?: string[];
  agencies?: string[];
}

// 응답
interface ChatAPIResponse {
  answer: string;
  chunks_used: number;
  model: string;
  sources: SourceMetadata[];
  has_sufficient_evidence: boolean;
  clarifying_questions: string[];
}

// 출처 메타데이터
interface SourceMetadata {
  doc_id: string;
  chunk_id: string;
  chunk_type: string;
  source_org: string;
  url: string | null;
  decision_date: string | null;
  doc_title: string;
  similarity: number;
}
```

---

## 실행 방법

### 1. 의존성 설치
```bash
npm install
```

### 2. 환경변수 설정
```bash
# .env 파일 생성
VITE_API_BASE_URL=http://localhost:8000
```

### 3. 개발 서버 실행
```bash
npm run dev
# http://localhost:5173 에서 실행
```

### 4. 프로덕션 빌드
```bash
npm run build
npm run preview
```

### 5. Docker 실행
```bash
docker build -t ddoksori-frontend .
docker run -p 80:80 ddoksori-frontend
```

---

## 참고 사항

- **React 버전**: 19.2.0 (최신 버전)
- **TypeScript**: strict 모드 활성화
- **경로 별칭**: `@/*` → `./src/*`
- **반응형**: Mobile-first 설계
- **브라우저 지원**: 최신 Chrome, Firefox, Safari, Edge
