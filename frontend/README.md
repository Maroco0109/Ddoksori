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
    │   ├── RootLayout.tsx             # ★ 전체 레이아웃 컴포넌트 (3.7KB)
    │   │                              # - 헤더 (로고 + "1초 만에 시작하기" 버튼)
    │   │                              # - Sidebar 렌더링
    │   │                              # - LoginModal 렌더링
    │   │                              # - Outlet (페이지 렌더링 영역)
    │   │                              # - 스크롤 위치 복원 (페이지 전환 시 최상단)
    │   │                              # - 세션 자동 로드 및 만료 확인
    │   │
    │   ├── routes.tsx                 # 라우트 정의
    │   │                              # - HOME: /
    │   │                              # - PROCEDURE: /procedure
    │   │                              # - CHAT: /chat
    │   │                              # - BOARD: /board
    │   │                              # - MYPAGE: /mypage
    │   │                              # - ADMIN_LOGIN: /admin/login
    │   │                              # - ADMIN_DASHBOARD: /admin/dashboard
    │   │                              # - ADMIN_POSTS: /admin/posts
    │   │                              # - ADMIN_USERS: /admin/users
    │   │                              # - ADMIN_REPORTS: /admin/reports
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
    │   ├── admin/ - 관리자 기능
    │   │   ├── admin.store.ts         # ★ 관리자 인증 상태관리 (Zustand)
    │   │   │                          # - admin, adminToken, isAdminAuthenticated 상태
    │   │   │                          # - localStorage persist 지원
    │   │   │                          # - 관리자 로그인/로그아웃 액션
    │   │   │
    │   │   ├── mockData.ts            # 관리자 테스트용 Mock 데이터
    │   │   │                          # - 통계, 게시글, 회원, 신고 Mock 데이터
    │   │   │                          # - 테스트 계정(admin/test1234) 사용 시 활성화
    │   │   │
    │   │   ├── AdminGuard.tsx         # 관리자 권한 체크 컴포넌트
    │   │   │                          # - 비인증 시 로그인 페이지로 리다이렉트
    │   │   │
    │   │   ├── AdminLoginPage.tsx     # 관리자 로그인 페이지
    │   │   │                          # - ID/비밀번호 입력
    │   │   │                          # - 테스트 계정 로그인 버튼
    │   │   │
    │   │   ├── AdminLayout.tsx        # 관리자 페이지 레이아웃
    │   │   │                          # - 좌측 사이드바 (네비게이션, 로그아웃)
    │   │   │                          # - 우측 콘텐츠 영역
    │   │   │
    │   │   └── pages/                 # 관리자 페이지 컴포넌트
    │   │       ├── AdminDashboard.tsx # 관리자 대시보드
    │   │       │                      # - 통계 카드 (회원/게시글/댓글/신고)
    │   │       │                      # - 빠른 작업 링크
    │   │       │                      # - 시스템 알림
    │   │       │
    │   │       ├── AdminPostsPage.tsx # 게시글 관리 페이지
    │   │       │                      # - 게시글 목록 조회 (검색, 필터링)
    │   │       │                      # - 게시글 상세 조회/비공개/삭제
    │   │       │                      # - 공지사항 작성
    │   │       │
    │   │       ├── AdminUsersPage.tsx # 회원 관리 페이지
    │   │       │                      # - 회원 목록 조회 (검색, 필터링)
    │   │       │                      # - 회원 상세 정보 조회
    │   │       │                      # - 계정 상태 변경 (활성/정지/영구정지)
    │   │       │
    │   │       └── AdminReportsPage.tsx # 신고 관리 페이지
    │   │                              # - 신고 목록 조회 (유형, 상태별)
    │   │                              # - 신고 상세 조회
    │   │                              # - 신고 처리 상태 변경
    │   │                              # - 관리자 메모 작성
    │   │
    │   ├── auth/ - 인증 기능
    │   │   ├── auth.store.ts          # ★ 인증 상태관리 (Zustand)
    │   │   │                          # - user, token, isAuthenticated 상태
    │   │   │                          # - localStorage persist 지원
    │   │   │                          # - 로그인/로그아웃 액션
    │   │   │                          # - 게스트 세션 자동 이전
    │   │   │
    │   │   └── LoginModal.tsx         # 로그인/회원가입 모달
    │   │                              # - 제목: "1초 만에 시작하기"
    │   │                              # - 소셜 로그인 (Google, 네이버)
    │   │
    │   ├── chat/ - AI 상담 챗봇 기능
    │   │   ├── ChatPage.tsx           # ★ 메인 채팅 페이지 (32KB)
    │   │   │                          # - 분쟁 상담 섹션 (틸 색상)
    │   │   │                          # - 일반 상담 섹션 (민트 색상)
    │   │   │                          # - 온보딩 폼 (분쟁 상담용)
    │   │   │                          # - 메시지 입력 및 전송
    │   │   │                          # - SSE 스트리밍 지원
    │   │   │
    │   │   ├── chat.store.ts          # ★ 채팅 상태관리 (Zustand, 6.9KB)
    │   │   │                          # - 분쟁/일반 메시지 배열
    │   │   │                          # - 세션 관리 (저장/로드/삭제)
    │   │   │                          # - 게스트 세션 24시간 만료
    │   │   │                          # - 로그인 사용자 무제한 저장
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
    │   │   │   ├── SafetyWarning.tsx  # 안전 경고 컴포넌트
    │   │   │   │                      # - 증거 부족 시 표시
    │   │   │   │                      # - 전문가 상담 권고
    │   │   │   │
    │   │   │   └── StatusIndicator.tsx # 상태 표시기
    │   │   │                          # - SSE 스트리밍 상태 표시
    │   │   │
    │   │   └── hooks/                 # 커스텀 훅
    │   │       ├── useChatMutation.ts # API 호출 훅 (React Query)
    │   │       │                      # - 폼 데이터 → API 형식 변환
    │   │       │
    │   │       └── useStreamingChat.ts # SSE 스트리밍 훅
    │   │                              # - 실시간 처리 상태 수신
    │   │                              # - node, status, progress 이벤트
    │   │
    │   ├── board/ - 자유게시판 기능
    │   │   ├── BoardPage.tsx          # ★ 게시판 메인 페이지 (33KB)
    │   │   │                          # - 로그인 체크 (비로그인 시 안내)
    │   │   │                          # - 카테고리 탭 (전체/분쟁해결/Q&A/꿀팁)
    │   │   │                          # - 검색 및 필터 (제목/닉네임/내용)
    │   │   │                          # - 페이지네이션 (10/30/50개)
    │   │   │                          # - 반응형 (모바일: 카드, 데스크톱: 테이블)
    │   │   │                          # - 닉네임 표시 (2행 지원)
    │   │   │
    │   │   ├── board.types.ts         # 게시판 타입 정의
    │   │   │                          # - BoardPost, BoardCategoryId
    │   │   │                          # - BoardSearchType, BoardPostForm
    │   │   │
    │   │   └── components/            # 게시판 컴포넌트
    │   │       ├── WritePost.tsx      # 글 작성 컴포넌트
    │   │       │                      # - 카테고리 선택
    │   │       │                      # - 세부 카테고리 (분쟁해결사례)
    │   │       │                      # - 데이터 활용 안내 공지
    │   │       │
    │   │       ├── PostDetail.tsx     # 글 상세보기 컴포넌트 (27KB)
    │   │       │                      # - 댓글/대댓글 시스템
    │   │       │                      # - 좋아요 기능
    │   │       │                      # - 수정/삭제 (작성자 전용)
    │   │       │                      # - 신고 기능
    │   │       │
    │   │       └── EditPost.tsx       # 글 수정 컴포넌트
    │   │                              # - 기존 데이터 로드
    │   │                              # - 카테고리 매핑
    │   │
    │   ├── home/ - 홈페이지
    │   │   └── HomePage.tsx           # ★ 랜딩 페이지 (7.7KB)
    │   │                              # - 히어로 섹션 (슬로건 + CTA)
    │   │                              # - 피처 그리드
    │   │                              # - 통계 섹션
    │   │
    │   ├── mypage/ - 마이페이지
    │   │   └── MyPage.tsx             # ★ 마이페이지 (24KB)
    │   │                              # - 닉네임 관리 (가중치 검증)
    │   │                              #   · 한글: 1.6 가중치, 최대 10자
    │   │                              #   · 영문/숫자/특수: 1 가중치, 최대 16자
    │   │                              # - 계정 정보 (이메일)
    │   │                              # - 채팅 이력 (페이지네이션)
    │   │                              # - 작성한 게시물 목록
    │   │                              # - 댓글 단 게시물 목록
    │   │                              # - 로그아웃/회원탈퇴
    │   │
    │   └── procedure/ - 절차 안내
    │       └── ProcedurePage.tsx      # 분쟁조정 절차 안내 페이지 (13KB)
    │                                  # - 단계별 절차 설명
    │                                  # - 이미지 및 텍스트
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
    │   │                              # - healthCheck(): /health 호출
    │   │
    │   ├── assets/ - 정적 자산
    │   │   └── icons/                 # 아이콘 이미지
    │   │       ├── logo-*.png         # 똑소리 로고
    │   │       ├── bell_1.png         # Bell 캐릭터 (상담 전)
    │   │       ├── bell_2.png         # Bell 캐릭터 (상담 후)
    │   │       ├── procedure-*.png    # 절차 안내 이미지
    │   │       └── ...                # 기타 아이콘
    │   │
    │   ├── components/ - 공유 컴포넌트
    │   │   ├── index.ts               # 컴포넌트 export
    │   │   └── MarkdownRenderer.tsx   # ★ 마크다운 렌더러 (4.2KB)
    │   │                              # - react-markdown 기반
    │   │                              # - 인용 [N] 파싱 및 클릭 처리
    │   │                              # - 코드 하이라이트 지원
    │   │                              # - XSS 방지
    │   │
    │   ├── config/ - 설정 상수
    │   │   ├── index.ts               # 설정 export
    │   │   │                          # - SESSION_EXPIRY_DURATION: 24시간
    │   │   │                          # - DEFAULT_PAGE_SIZE: 10
    │   │   │                          # - MAX_TITLE_LENGTH: 100
    │   │   │                          # - MAX_CONTENT_LENGTH: 5000
    │   │   │
    │   │   ├── routes.ts              # 라우트 경로 상수
    │   │   │                          # - HOME, PROCEDURE, CHAT, BOARD, MYPAGE
    │   │   │
    │   │   ├── categories.ts          # 게시판 카테고리 상수
    │   │   │                          # - POST_CATEGORIES
    │   │   │                          # - CATEGORY_LABELS
    │   │   │                          # - CATEGORY_DISPLAY_MAP
    │   │   │
    │   │   ├── storage-keys.ts        # LocalStorage 키 상수
    │   │   │                          # - AUTH_TOKEN, USER_DATA
    │   │   │                          # - CHAT_SESSIONS, TEMP_CHAT_SESSIONS
    │   │   │
    │   │   └── query-keys.ts          # React Query 키 상수
    │   │                              # - AUTH_USER, POSTS, CHAT_SESSIONS
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
    │   │   │                          # - 만료 시간 포맷
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
    │   │   │
    │   │   ├── admin.ts               # 관리자 관련 타입
    │   │   │                          # - Admin, AdminStats
    │   │   │                          # - AdminPost, AdminUser, Report
    │   │   │                          # - UserSearchParams, ReportSearchParams
    │   │   │                          # - PostSearchParams
    │   │   │
    │   │   ├── auth.ts                # 인증 관련 타입
    │   │   │                          # - User (id, name, email, provider, nickname)
    │   │   │                          # - LoginCredentials, AuthResponse
    │   │   │
    │   │   ├── chat.ts                # 채팅 관련 타입
    │   │   │                          # - Message, DisputeForm, ChatSession
    │   │   │                          # - ChatType: 'dispute' | 'general'
    │   │   │
    │   │   ├── chat.types.ts          # ★ 백엔드 API 계약 타입 (4.9KB)
    │   │   │                          # - OnboardingAPIData
    │   │   │                          # - ChatAPIRequest/Response
    │   │   │                          # - SourceMetadata (출처 정보)
    │   │   │                          # - Citation (인용 정보)
    │   │   │                          # - MessageWithCitations
    │   │   │                          # - SSE 이벤트 타입
    │   │   │                          # - StreamingState
    │   │   │
    │   │   └── post.ts                # 게시판 관련 타입
    │   │                              # - Post, Comment, Reply
    │   │                              # - PostFormData, PostFilters
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
    │                                  # - 채팅 이력 열림/닫힘
    │
    └── 🧩 widgets/ - 위젯 컴포넌트
        └── Sidebar.tsx                # ★ 사이드바 네비게이션 (14KB)
                                       # - 로고
                                       # - 네비게이션 메뉴
                                       # - 새 채팅 버튼
                                       # - 채팅 세션 목록
                                       #   · 실시간 만료 시간 표시
                                       #   · 세션 삭제/새로고침
                                       # - "1초 만에 시작하기" 버튼
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
                    │   │   ├── 세션 제목
                    │   │   ├── 만료 시간 (비로그인 사용자)
                    │   │   └── 삭제/새로고침 버튼
                    │   └── "1초 만에 시작하기" (비로그인)
                    │
                    ├── LoginModal (features/auth/)
                    │   ├── 제목: "1초 만에 시작하기"
                    │   └── 소셜 로그인 버튼 (Google, 카카오, 네이버)
                    │
                    └── <Outlet /> (페이지 렌더링)
                        │
                        ├── HomePage (/)
                        │   ├── 히어로 섹션 (슬로건 + CTA 버튼)
                        │   ├── 피처 그리드
                        │   └── 통계 섹션
                        │
                        ├── ChatPage (/chat)
                        │   ├── 분쟁 상담 섹션
                        │   │   ├── DisputeForm (온보딩)
                        │   │   └── ChatMessages
                        │   │       └── MessageBubble
                        │   │           ├── MarkdownRenderer
                        │   │           ├── CitationModal
                        │   │           └── SafetyWarning
                        │   │
                        │   └── 일반 상담 섹션
                        │       └── ChatMessages
                        │           └── MessageBubble
                        │
                        ├── BoardPage (/board)
                        │   ├── 로그인 체크
                        │   ├── 카테고리 탭
                        │   ├── 검색바
                        │   ├── 게시글 목록/카드
                        │   ├── 페이지네이션
                        │   └── WritePost / PostDetail / EditPost
                        │
                        ├── MyPage (/mypage)
                        │   ├── 닉네임 관리
                        │   ├── 계정 정보
                        │   ├── 채팅 이력
                        │   ├── 작성한 게시물
                        │   └── 댓글 단 게시물
                        │
                        ├── ProcedurePage (/procedure)
                        │
                        ├── AdminLoginPage (/admin/login)
                        │   ├── 로그인 폼 (ID/비밀번호)
                        │   └── 테스트 계정 로그인 버튼
                        │
                        └── AdminLayout (/admin/*)
                            │
                            ├── 좌측 사이드바
                            │   ├── 대시보드
                            │   ├── 게시글 관리
                            │   ├── 회원 관리
                            │   ├── 신고 관리
                            │   └── 로그아웃
                            │
                            └── <Outlet /> (관리자 페이지)
                                │
                                ├── AdminDashboard (/admin/dashboard)
                                │   ├── 통계 카드 (회원/게시글/댓글/신고)
                                │   ├── 빠른 작업 (공지작성/신고처리)
                                │   └── 시스템 알림
                                │
                                ├── AdminPostsPage (/admin/posts)
                                │   ├── 검색 필터 바
                                │   ├── 게시글 목록 테이블
                                │   ├── 게시글 상세 모달
                                │   └── 공지사항 작성 모달
                                │
                                ├── AdminUsersPage (/admin/users)
                                │   ├── 검색 필터 바
                                │   ├── 회원 목록 테이블
                                │   ├── 회원 상세 정보 모달
                                │   └── 상태 변경 드롭다운
                                │
                                └── AdminReportsPage (/admin/reports)
                                    ├── 검색 필터 바
                                    ├── 신고 목록 테이블
                                    └── 신고 상세 처리 모달
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
│  │ • logout()           │   │ • activeChatType     │               │
│  │                      │   │ • saveChatSession()  │               │
│  │ [localStorage]       │   │ • loadChatSessions() │               │
│  │   persist            │   │ • startNewChat()     │               │
│  └──────────────────────┘   │ • deleteSession()    │               │
│                             │ • refreshSession()   │               │
│                             │                      │               │
│  ┌──────────────────────┐   │ [localStorage]       │               │
│  │   useAdminStore      │   │   로그인 사용자       │               │
│  │  (features/admin)    │   │ [sessionStorage]     │               │
│  ├──────────────────────┤   │   비로그인 사용자     │               │
│  │ • admin              │   │   24시간 만료         │               │
│  │ • adminToken         │   └──────────────────────┘               │
│  │ • isAdminAuth        │                                          │
│  │ • adminLogin()       │                                          │
│  │ • adminLogout()      │                                          │
│  │                      │                                          │
│  │ [localStorage]       │                                          │
│  │   persist            │                                          │
│  └──────────────────────┘                                          │
│                                                                     │
│  ┌──────────────────────┐                                          │
│  │     useUIStore       │                                          │
│  │      (store/)        │                                          │
│  ├──────────────────────┤                                          │
│  │ • isSidebarOpen      │                                          │
│  │ • isAuthModalOpen    │                                          │
│  │ • isChatHistoryOpen  │                                          │
│  │ • toggleSidebar()    │                                          │
│  │ • setIsAuthModalOpen│                                          │
│  │ • toggleChatHistory()│                                          │
│  │                      │                                          │
│  │ [메모리 only]         │                                          │
│  └──────────────────────┘                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 라우팅

### 메인 레이아웃 (RootLayout)

- **모듈화**: 기능별로 폴더 분리 (auth, chat, board, home, mypage, procedure)
- **응집도**: 관련 컴포넌트, 스토어, 훅이 같은 폴더에 위치
- **확장성**: 새 기능 추가 시 features/ 하위에 폴더만 추가

```
features/
├── auth/          # 인증 기능 전담
├── chat/          # AI 상담 기능 전담
├── board/         # 게시판 기능 전담
├── home/          # 홈페이지 전담
├── mypage/        # 마이페이지 전담
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
│  • SSE 스트리밍 지원         │  • SSE 스트리밍 지원                │
└────────────────────────────┴────────────────────────────────────┘
```

### 관리자 라우트 (AdminGuard + AdminLayout)

| 경로 | 페이지 | 설명 |
|------|--------|------|
| `/admin/dashboard` | AdminDashboard | 대시보드 통계 |
| `/admin/posts` | AdminPostsPage | 게시글 관리 |
| `/admin/users` | AdminUsersPage | 사용자 관리 |
| `/admin/reports` | AdminReportsPage | 신고 관리 |

### 4. SSE 스트리밍 (Server-Sent Events)

- **실시간 처리 상태**: 노드별 진행 상황 표시
- **이벤트 타입**:
  - `status`: 현재 작업 노드 (retrieval, generation 등)
  - `node`: 노드 이름
  - `progress`: 진행률 (0-100)
  - `complete`: 최종 답변 및 출처
- **StatusIndicator**: 처리 중 상태 시각화

### 5. Safety Guardrails (안전 장치)

## 기능 모듈

### admin/ — 관리자 시스템

### 6. 세션 관리

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

**특징**:
- 실시간 만료 시간 표시
- 세션 시간 새로고침 기능
- 로그인 시 게스트 세션 자동 이전

### 7. 게시판 시스템

**카테고리 구조**:
```
전체
├── 분쟁해결사례 공유
│   ├── 조정 이전 단계에서 해결
│   └── 조정을 통한 해결
├── 무엇이든 물어보세요
└── 소비자 꿀팁/노하우
```

**주요 기능**:
- 로그인 필수 (비로그인 시 안내 메시지)
- 닉네임 표시 (2행 지원, 가중치 제한)
- 검색 (제목/닉네임/내용/제목+내용)
- 댓글/대댓글 시스템
- 좋아요, 조회수
- 수정/삭제 (작성자 전용)
- 신고 기능

**데이터 활용 안내**:
- "분쟁해결사례 공유" 카테고리 작성 시 안내 표시
- 민감한 정보 마스킹 및 AI 학습 데이터 활용 고지

### 8. 마이페이지 기능

**닉네임 관리**:
- 가중치 기반 길이 제한
  - 한글: 1자 = 1.6 가중치 (최대 10자)
  - 영문/숫자/특수문자: 1자 = 1 가중치 (최대 16자)
  - 총 가중치: 16 이하
- 실시간 문자 수 표시
- 수정 및 저장 기능

**이력 관리**:
- 채팅 이력 (페이지네이션)
- 작성한 게시물 목록
- 댓글 단 게시물 목록

### 9. 관리자 기능

**인증 및 권한**:
- 관리자 전용 로그인 (ID/비밀번호)
- 테스트 계정: admin / test1234
- AdminGuard로 라우트 보호
- JWT 토큰 기반 인증

**대시보드**:
```
┌─────────────────────────────────────────────────────────┐
│                     관리자 대시보드                       │
├──────────────┬──────────────┬──────────────┬────────────┤
│ 전체 회원     │ 전체 게시글   │ 전체 댓글     │ 대기 신고  │
│ 1,247명      │ 3,892개      │ 12,456개     │ 8건        │
│ +23 오늘     │ +67 오늘     │              │ 처리 필요   │
└──────────────┴──────────────┴──────────────┴────────────┘

┌──────────────────────┬──────────────────────────────────┐
│   빠른 작업           │      시스템 알림                  │
├──────────────────────┼──────────────────────────────────┤
│ • 공지사항 작성       │ ⚠️ 처리 대기 중인 신고 8건        │
│ • 신고 처리하기       │ ⚠️ 정지 상태 사용자 3명           │
│ • 정지된 계정 관리    │                                  │
└──────────────────────┴──────────────────────────────────┘
```

**게시글 관리**:
- 검색/필터링 (제목, 작성자, 카테고리, 공개상태)
- 게시글 상세 조회
- 공개/비공개 전환
- 게시글 삭제
- 공지사항 작성 (상단 고정 옵션)

**회원 관리**:
- 회원 목록 조회 (이름/이메일 검색)
- 가입 경로 필터 (Google, Naver)
- 회원 상세 정보 (활동 내역 포함)
- 계정 상태 변경:
  - active: 정상 활성
  - suspended: 일시 정지
  - banned: 영구 정지

**신고 관리**:
- 신고 목록 조회 (유형, 상태별 필터)
- 신고 상세 조회 (대상 내용, 신고 사유)
- 처리 상태 변경:
  - pending: 대기 중
  - reviewed: 검토 완료
  - resolved: 처리 완료
  - rejected: 기각
- 관리자 메모 작성

**Mock 데이터 지원**:
- 테스트 계정 로그인 시 자동으로 Mock 데이터 사용
- 실제 Backend API 없이도 기능 테스트 가능
- 통계, 게시글, 회원, 신고 데이터 포함

### 10. 반응형 디자인

```
모바일 (< 768px)        태블릿 (768px ~)        데스크톱 (1024px ~)
┌────────────────┐     ┌────────────────┐     ┌────────────────────────┐
│   사이드바 숨김  │     │  사이드바 접힘  │     │ 사이드바 │   콘텐츠    │
│                │     │                │     │  고정    │             │
│    전체 폭     │     │    좌우 패딩   │     │         │  max-w-7xl  │
│    카드 뷰     │     │    카드 뷰     │     │         │  테이블 뷰   │
└────────────────┘     └────────────────┘     └────────────────────────┘
```

---

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

> 총 4개의 Zustand 스토어로 분산 상태 관리

### procedure/ — 절차 안내

| 스토어 | 위치 | 역할 | 지속성 |
|--------|------|------|--------|
| **useAuthStore** | features/auth/auth.store.ts | 사용자 인증 상태 | localStorage (persist) |
| **useAdminStore** | features/admin/admin.store.ts | 관리자 인증 상태 | localStorage (persist) |
| **useChatStore** | features/chat/chat.store.ts | 채팅 메시지/세션 | localStorage/sessionStorage |
| **useUIStore** | store/ui.store.ts | UI 상태 (사이드바, 모달) | 메모리 |

---

## 상태 관리

```typescript
interface AuthState {
  user: User | null;            // 사용자 정보 (닉네임 포함)
  token: string | null;
  isAuthenticated: boolean;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  register: (data: RegisterData) => Promise<void>;
  setUser: (user: User) => void;  // 사용자 정보 업데이트
}
```

**특징**:
- localStorage에 자동 persist
- 로그인 시 게스트 세션 자동 이전
- JWT 토큰 관리
- 닉네임 업데이트 지원

### 세션 관리

### 2. useAdminStore (관리자 스토어)

```typescript
interface AdminAuthState {
  admin: Admin | null;          // 관리자 정보
  adminToken: string | null;    // 관리자 JWT 토큰
  isAdminAuthenticated: boolean;

  // Actions
  adminLogin: (admin: Admin, token: string) => void;
  adminLogout: () => void;
}
```

**특징**:
- localStorage에 자동 persist
- 관리자 전용 인증 시스템
- 일반 사용자 인증과 독립적으로 관리
- 테스트 토큰(test-token-1234) 지원

---

### 3. useChatStore (채팅 스토어)

```typescript
interface ChatState {
  // 상태
  currentSessionId: string | null;
  activeChatType: 'dispute' | 'general' | null;
  chatSessions: ChatSession[];
  disputeMessages: MessageWithCitations[];
  generalMessages: MessageWithCitations[];
  isDisputeLoading: boolean;
  isGeneralLoading: boolean;
  isFormSubmitted: boolean;

  // Actions
  loadChatSessions: (isLoggedIn: boolean) => void;
  saveChatSession: (type, messages, isLoggedIn) => void;
  deleteChatSession: (sessionId, isLoggedIn) => void;
  refreshSessionTime: (sessionId) => void;  // 세션 만료 시간 갱신
  startNewChat: () => void;
  setCurrentSessionId: (id: string) => void;
  setActiveChatType: (type: 'dispute' | 'general') => void;
}
```

**특징**:
- 로그인 사용자: localStorage에 무제한 저장
- 비로그인 사용자: sessionStorage에 최대 1개, 24시간 만료
- 세션 자동 저장/복원
- 실시간 만료 시간 관리

---

### 4. useUIStore (UI 스토어)

```typescript
interface UIState {
  isSidebarOpen: boolean;
  isAuthModalOpen: boolean;
  isChatHistoryOpen: boolean;

  // Actions
  toggleSidebar: () => void;
  setIsSidebarOpen: (open: boolean) => void;
  setIsAuthModalOpen: (open: boolean) => void;
  toggleChatHistory: () => void;
}
```

**특징**:
- 메모리에만 저장 (새로고침 시 초기화)
- 사이드바, 로그인 모달, 채팅 이력 상태 관리

---

### 스토어 사용 예시

```typescript
// 일반 사용자 컴포넌트에서 사용
import { useAuthStore } from '@/features/auth/auth.store';
import { useChatStore } from '@/features/chat/chat.store';
import { useUIStore } from '@/store/ui.store';

function ChatPage() {
  const { isAuthenticated, user } = useAuthStore();
  const { disputeMessages, saveChatSession } = useChatStore();
  const { setIsAuthModalOpen } = useUIStore();

  // 메시지 저장
  saveChatSession('dispute', disputeMessages, isAuthenticated);

  // 로그인 모달 열기
  if (!isAuthenticated) {
    setIsAuthModalOpen(true);
  }
}

// 관리자 컴포넌트에서 사용
import { useAdminStore } from '@/features/admin/admin.store';

function AdminDashboard() {
  const { isAdminAuthenticated, adminToken } = useAdminStore();

  // 테스트 모드 확인
  const isTestMode = adminToken === 'test-token-1234';

  // Mock 데이터 또는 실제 API 사용
  if (isTestMode) {
    const data = getMockData('/api/admin/stats');
  } else {
    const data = await apiClient.get('/api/admin/stats');
  }
}
```

---

## 주요 페이지 및 컴포넌트

### 페이지 요약

| 페이지 | 경로 | 파일 | 크기 | 설명 |
|--------|------|------|------|------|
| **홈** | `/` | HomePage.tsx | 7.7KB | 랜딩 페이지 |
| **AI 상담** | `/chat` | ChatPage.tsx | 32KB | 분쟁/일반 상담 챗봇, SSE 스트리밍 |
| **게시판** | `/board` | BoardPage.tsx | 33KB | 자유게시판 CRUD, 로그인 필수 |
| **마이페이지** | `/mypage` | MyPage.tsx | 24KB | 닉네임 관리, 이력 조회 |
| **절차 안내** | `/procedure` | ProcedurePage.tsx | 13KB | 분쟁조정 절차 설명 |
| **관리자 로그인** | `/admin/login` | AdminLoginPage.tsx | - | 관리자 인증 |
| **관리자 대시보드** | `/admin/dashboard` | AdminDashboard.tsx | - | 통계 및 빠른 작업 |
| **게시글 관리** | `/admin/posts` | AdminPostsPage.tsx | - | 게시글 관리, 공지사항 작성 |
| **회원 관리** | `/admin/users` | AdminUsersPage.tsx | - | 회원 조회, 계정 상태 변경 |
| **신고 관리** | `/admin/reports` | AdminReportsPage.tsx | - | 신고 조회, 처리 상태 변경 |

---

### 1. ChatPage (AI 상담 페이지)

**위치**: `src/features/chat/ChatPage.tsx` (32KB)

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
│       │       ├── 사용자 메시지
│       │       ├── CitationModal (인용 클릭 시)
│       │       └── SafetyWarning (전문가 상담 필요)
│       │
│       ├── StatusIndicator (SSE 진행 상태)
│       └── MessageInput
│
└── 일반 상담 섹션 (우측, Mint 색상)
    └── ChatArea
        ├── MessageList
        ├── StatusIndicator
        └── MessageInput
```

**주요 기능**:
- 온보딩 폼으로 구조화된 정보 수집
- 마크다운 렌더링 (코드 하이라이트 포함)
- 인용 클릭 시 모달로 출처 확인
- SSE 스트리밍으로 실시간 처리 상태 표시
- 세션 자동 저장

**SSE 스트리밍**:
```typescript
// useStreamingChat 훅 사용
const { streamingState, startStreaming } = useStreamingChat({
  onComplete: (data) => {
    // 최종 답변 수신
    addMessage(data.answer, data.sources);
  }
});

// 실시간 상태 표시
{streamingState.isActive && (
  <StatusIndicator
    currentNode={streamingState.currentNode}
    progress={streamingState.progress}
  />
)}
```

---

### 2. BoardPage (게시판 페이지)

**위치**: `src/features/board/BoardPage.tsx` (33KB)

**구조**:
```
BoardPage
├── 로그인 체크
│   └── 비로그인 시: 안내 메시지 + "로그인하러 가기" 버튼
│
├── 헤더
│   ├── 제목 ("자유게시판")
│   └── 글쓰기 버튼
│
├── 카테고리 탭
│   ├── 전체
│   ├── 분쟁해결사례 공유
│   ├── 무엇이든 물어보세요
│   └── 소비자 꿀팁/노하우
│
├── 검색바
│   ├── 검색 타입 (제목/닉네임/내용/제목+내용)
│   └── 검색 입력
│
├── 게시글 목록
│   ├── 데스크톱: 테이블 뷰 (닉네임 2행 지원)
│   └── 모바일: 카드 뷰
│
├── 페이지네이션
│   ├── 페이지당 개수 (10/30/50)
│   └── 페이지 번호
│
└── 모달/서브페이지
    ├── WritePost (글 작성)
    │   ├── 카테고리 선택
    │   ├── 세부 카테고리 (분쟁해결사례)
    │   └── 데이터 활용 안내 (분쟁해결사례)
    │
    ├── PostDetail (글 상세)
    │   ├── 본문
    │   ├── 댓글/대댓글
    │   ├── 좋아요
    │   ├── 수정/삭제 (작성자)
    │   └── 신고 (타인)
    │
    └── EditPost (글 수정)
```

**카테고리 구조**:
| 카테고리 ID | 표시명 | 세부 카테고리 |
|------------|--------|--------------|
| `all` | 전체 | - |
| `case-sharing` | 분쟁해결사례 공유 | 조정 이전/조정을 통한 |
| `qna` | 무엇이든 물어보세요 | - |
| `tips` | 소비자 꿀팁/노하우 | - |

**닉네임 표시**:
- 컬럼 너비: 144px (w-36)
- 2행 표시 지원 (line-clamp-2)
- 긴 닉네임 자동 줄바꿈

---

### 3. MyPage (마이페이지)

**위치**: `src/features/mypage/MyPage.tsx` (24KB)

**구조**:
```
MyPage
├── 프로필 섹션
│   ├── 닉네임 관리
│   │   ├── 표시: 닉네임 + 수정 버튼
│   │   └── 수정 모드
│   │       ├── 입력 필드
│   │       ├── 저장/취소 버튼
│   │       └── 가중치 표시 (한글 N자 + 영문 M자 (용량: X/16))
│   │
│   ├── 계정 정보
│   │   └── 이메일 주소
│   │
│   └── 로그아웃/회원탈퇴 버튼
│
├── 내 상담 내역 (페이지네이션)
│   └── 채팅 세션 목록
│
├── 내 게시글 (페이지네이션)
│   └── 작성한 게시물 목록
│
└── 내가 댓글을 단 게시글 (페이지네이션)
    └── 댓글 단 게시물 목록
```

**닉네임 가중치 시스템**:
```typescript
// 한글: 1.6 가중치, 영문/숫자/특수: 1 가중치
const calculateNicknameWeight = (nickname: string) => {
  let weight = 0;
  for (const char of nickname) {
    if (/[ㄱ-ㅎ|ㅏ-ㅣ|가-힣]/.test(char)) {
      weight += 1.6;  // 한글
    } else {
      weight += 1;    // 영문/숫자/특수문자
    }
  }
  return weight <= 16;  // 최대 16
};

// 예시:
// "한글열자" (10자) = 10 × 1.6 = 16 ✅
// "English16chars!!" (16자) = 16 × 1 = 16 ✅
// "한글다섯" (5자) + "English8" (8자) = 8 + 8 = 16 ✅
```

---

### 4. 관리자 페이지

**위치**: `src/features/admin/pages/`

**구조**:
```
AdminLayout (/admin/*)
├── 좌측 사이드바 (w-56)
│   ├── 로고
│   ├── 메뉴
│   │   ├── 대시보드
│   │   ├── 게시글 관리
│   │   ├── 회원 관리 🧑‍🤝‍🧑
│   │   └── 신고 관리
│   └── 로그아웃 (타원형 버튼)
│
└── 우측 콘텐츠 영역
    │
    ├── AdminDashboard
    │   ├── 통계 카드 (4개)
    │   │   ├── 전체 회원 (오늘 신규)
    │   │   ├── 전체 게시글 (오늘 신규)
    │   │   ├── 전체 댓글
    │   │   └── 대기 중인 신고
    │   │
    │   ├── 빠른 작업
    │   │   ├── 공지사항 작성
    │   │   ├── 신고 처리하기
    │   │   └── 정지된 계정 관리
    │   │
    │   └── 시스템 알림
    │       ├── 대기 중인 신고 알림
    │       └── 정지된 사용자 알림
    │
    ├── AdminPostsPage
    │   ├── 검색 필터
    │   │   ├── 검색 타입 (제목/작성자/키워드)
    │   │   ├── 공개상태 필터
    │   │   └── 카테고리 필터
    │   │
    │   ├── 게시글 목록 테이블
    │   │   ├── ID, 카테고리, 제목
    │   │   ├── 작성자, 작성일
    │   │   ├── 조회/좋아요/댓글
    │   │   └── 공개상태, 작업
    │   │
    │   ├── 게시글 상세 모달
    │   │   ├── 전체 내용 보기
    │   │   ├── 공개/비공개 전환
    │   │   └── 삭제
    │   │
    │   └── 공지사항 작성 모달
    │       ├── 제목, 내용 입력
    │       ├── 상단 고정 옵션
    │       └── 정책 공지 템플릿
    │
    ├── AdminUsersPage
    │   ├── 검색 필터
    │   │   ├── 이름/이메일 검색
    │   │   ├── 상태 필터
    │   │   └── 가입 경로 필터
    │   │
    │   ├── 회원 목록 테이블
    │   │   ├── ID, 이름, 이메일
    │   │   ├── 가입경로, 가입일
    │   │   ├── 게시글/댓글/신고 수
    │   │   └── 상태, 작업
    │   │
    │   ├── 회원 상세 모달
    │   │   ├── 기본 정보
    │   │   ├── 가입일, 최근 로그인
    │   │   └── 활동 내역 (게시글/댓글/신고)
    │   │
    │   └── 상태 변경 드롭다운
    │       ├── 활성화 (active)
    │       ├── 정지 (suspended)
    │       └── 영구정지 (banned)
    │
    └── AdminReportsPage
        ├── 검색 필터
        │   ├── 유형 필터 (게시글/댓글)
        │   └── 상태 필터
        │
        ├── 신고 목록 테이블
        │   ├── ID, 유형, 대상 (truncate)
        │   ├── 신고자, 신고 사유
        │   ├── 신고일, 상태
        │   └── 작업 (상세보기)
        │
        └── 신고 상세 모달
            ├── 신고 기본 정보
            ├── 대상 내용 (전체 표시)
            ├── 신고 사유
            ├── 현재 처리 상태
            └── 처리 (대기/검토 완료만)
                ├── 상태 변경 선택
                ├── 관리자 메모 작성
                └── 처리 완료 버튼
```

**주요 기능**:
- 테스트 계정(admin/test1234) 지원
- Mock 데이터로 Backend 없이 테스트 가능
- 테이블 컬럼 너비 최적화 (텍스트 truncate, hover tooltip)
- 확인 대화상자 (삭제, 상태 변경)
- Teal 테마 색상 적용
- 반응형 테이블 (작은 텍스트, 적절한 여백)

# 프로덕션 빌드
npm run build
npm run preview

### 5. 공통 컴포넌트

| 컴포넌트 | 위치 | 크기 | 설명 |
|----------|------|------|------|
| **Sidebar** | widgets/Sidebar.tsx | 14KB | 네비게이션 사이드바, 채팅 이력 |
| **LoginModal** | features/auth/LoginModal.tsx | - | 로그인/회원가입 모달 |
| **MessageBubble** | features/chat/components/ | - | 채팅 메시지 버블 (인용 지원) |
| **MarkdownRenderer** | shared/components/ | 4.2KB | 마크다운 렌더러 (XSS 방지) |
| **CitationModal** | features/chat/components/ | - | 인용 출처 모달 |
| **SafetyWarning** | features/chat/components/ | - | 안전 경고 메시지 |
| **StatusIndicator** | features/chat/components/ | - | SSE 처리 상태 표시 |
| **Button** | shared/ui/button.tsx | - | 버튼 컴포넌트 (CVA) |
| **Input** | shared/ui/input.tsx | - | 입력 컴포넌트 |

---

## 테스트

### 단위 테스트 (Vitest)

```
사용자 입력
    │
    ▼
ChatPage (메시지 전송)
    │
    ▼
useChatMutation (React Query)
    │
    ├─ 폼 데이터 → API 형식 변환
    │  (camelCase → snake_case)
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
    ├── CitationModal (인용 클릭 시)
    └── SafetyWarning (전문가 상담 필요)
```

### 2. SSE 스트리밍 흐름

```
사용자 메시지 전송
    │
    ▼
useStreamingChat - startStreaming()
    │
    ▼
EventSource 연결 (/chat/stream)
    │
    ├─ 이벤트 수신 루프
    │
    ├── status 이벤트
    │   ├─ currentNode 업데이트
    │   └─ StatusIndicator 표시
    │
    ├── progress 이벤트
    │   └─ 진행률 업데이트
    │
    ├── error 이벤트
    │   └─ 에러 처리
    │
    └── complete 이벤트
        ├─ 최종 답변
        ├─ 출처 정보
        ├─ 질문 목록
        └─ onComplete 콜백 실행
            │
            ▼
        MessageWithCitations 생성
            │
            ▼
        useChatStore 저장
            │
            ▼
        화면 렌더링
```

### 3. 상태 저장 흐름

```
메시지 생성
    │
    ▼
useChatStore.saveChatSession()
    │
    ├── 로그인 사용자?
    │   ├── YES → localStorage (무제한)
    │   │         key: CHAT_SESSIONS
    │   │
    │   └── NO  → sessionStorage (1개, 24시간)
    │             key: TEMP_CHAT_SESSIONS
    │
    ▼
storage.ts - set()
    │
    ├─ 세션 메타데이터 저장
    │  ├─ id: UUID
    │  ├─ title: 첫 메시지
    │  ├─ type: dispute | general
    │  ├─ createdAt: 생성 시간
    │  ├─ expiresAt: 만료 시간 (비로그인만)
    │  └─ messages: 메시지 배열
    │
    ▼
JSON 직렬화 후 저장
```

### 4. 세션 복원 흐름

```
앱 시작 / 새로고침
    │
    ▼
RootLayout 마운트
    │
    ├─ useEffect: 세션 로드
    │
    ▼
useChatStore.loadChatSessions(isLoggedIn)
    │
    ├── 저장소에서 세션 로드
    │   ├─ 로그인: localStorage
    │   └─ 비로그인: sessionStorage
    │
    ├── 만료된 세션 필터링 (비로그인만)
    │   └─ expiresAt < Date.now()
    │
    └── chatSessions 상태 업데이트
    │
    ▼
Sidebar에 세션 목록 표시
    │
    ├─ 세션 제목
    ├─ 세션 타입 (분쟁/일반)
    ├─ 만료 시간 (비로그인 사용자)
    │  └─ 실시간 업데이트 (1초마다)
    │
    └─ 삭제/새로고침 버튼
    │
    ▼
세션 클릭
    │
    ├─ setCurrentSessionId(sessionId)
    ├─ 해당 세션의 메시지 로드
    └─ ChatPage로 이동
    │
    ▼
메시지 복원 및 표시
```

### 5. 게스트 → 로그인 세션 이전

```
비로그인 상태에서 채팅
    │
    ├─ sessionStorage에 저장
    │  key: TEMP_CHAT_SESSIONS
    │
    ▼
로그인 실행
    │
    ▼
useAuthStore.login()
    │
    ├─ 로그인 성공
    │
    ▼
게스트 세션 확인
    │
    ├─ sessionStorage에서 로드
    │  key: TEMP_CHAT_SESSIONS
    │
    ├─ 존재하면 이전
    │  ├─ localStorage에 복사
    │  │  key: CHAT_SESSIONS
    │  │
    │  └─ sessionStorage에서 삭제
    │
    ▼
로그인 사용자 세션으로 전환 완료
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
| GET | `/chat/stream` | SSE 스트리밍 (실시간 처리 상태) |
| POST | `/search` | 벡터 검색만 수행 |
| GET | `/health` | 서버 상태 확인 |

### 요청/응답 타입

```typescript
// 요청 (온보딩 폼)
interface OnboardingAPIData {
  purchase_date: string;
  seller: string;
  platform: string;
  product: string;
  amount: string;
  dispute_details: string;
}

// 요청 (채팅)
interface ChatAPIRequest {
  message: string;
  session_id?: string;
  onboarding_data?: OnboardingAPIData;
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
  session_id: string;
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

// SSE 이벤트
interface SSEStatusData {
  node: string;
  status: string;
  progress?: number;
}

interface SSECompleteData {
  answer: string;
  sources: SourceMetadata[];
  has_sufficient_evidence: boolean;
  clarifying_questions: string[];
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

## 주요 파일 크기

| 파일 | 크기 | 역할 |
|------|------|------|
| BoardPage.tsx | 33KB | 게시판 메인 (목록, 상세, 작성, 편집 통합) |
| ChatPage.tsx | 32KB | 채팅 메인 (분쟁/일반 상담, SSE 스트리밍) |
| MyPage.tsx | 24KB | 마이페이지 (프로필, 닉네임, 이력) |
| PostDetail.tsx | 27KB | 게시물 상세 (댓글, 좋아요, 수정/삭제) |
| Sidebar.tsx | 14KB | 네비게이션 및 채팅 이력 |
| ProcedurePage.tsx | 13KB | 절차 설명 페이지 |
| chat.store.ts | 6.9KB | 채팅 상태 관리 |
| chat.types.ts | 4.9KB | 채팅 API 및 SSE 타입 |
| MarkdownRenderer.tsx | 4.2KB | 마크다운 렌더링 |
| RootLayout.tsx | 3.7KB | 레이아웃 및 라우팅 |

---

## 참고 사항

- **React 버전**: 19.2.0 (최신 버전)
- **TypeScript**: strict 모드 활성화
- **경로 별칭**: `@/*` → `./src/*`
- **반응형**: Mobile-first 설계
- **브라우저 지원**: 최신 Chrome, Firefox, Safari, Edge
- **상태 관리**: Zustand (localStorage persist 지원)
- **실시간 통신**: SSE (Server-Sent Events)
- **보안**: XSS 방지, 입력 검증

### 관리자 기능 관련

- **관리자 문서**: `frontend/관리자기능_구현.md` - 구현 완료 보고서
- **Backend API 요청 사항**: `frontend/request_api_to_backend.md` - Backend 개발팀 전달용
- **테스트 계정**:
  - ID: `admin`
  - 비밀번호: `test1234`
  - 토큰: `test-token-1234`
- **Mock 데이터**: `src/features/admin/mockData.ts`
  - 1,247명의 회원 데이터
  - 3,892개의 게시글 데이터
  - 8건의 신고 데이터
  - 소비자 관련 실제 사례 기반
- **색상 테마**: Teal (청록색) - 웹사이트 메인 색상과 통일
