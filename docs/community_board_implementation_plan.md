# 자유게시판 DB 연동 구현 계획서

## 현재 상태 분석

### Frontend 상태

**자유게시판 (BoardPage.tsx)**
- `BoardPage.tsx`에 30개의 Mock 데이터가 하드코딩되어 있음
- 게시글 작성/수정/삭제, 댓글/대댓글 기능이 **프론트엔드 로컬 상태**로만 동작
- 검색, 필터링, 페이지네이션 UI 구현 완료

**마이페이지 (MyPage.tsx)**
- `myBoardPosts` - 하드코딩된 Mock 데이터 (255-274줄)
- `commentedPosts` - 하드코딩된 Mock 데이터 (277-298줄)
- Backend API 호출 없이 Mock 데이터만 표시 중
- UI 구현 완료: "내 게시글", "내가 댓글을 단 게시글" 섹션

### Backend 상태
- `board_db.py`: 마이페이지용 기본 쿼리 존재 (테이블 미생성으로 동작 안함)
- `users.py`: `/api/users/me/posts`, `/api/users/me/commented-posts` 엔드포인트 존재 (테이블 미생성으로 동작 안함)
- **게시글 CRUD API 미구현**
- **댓글 CRUD API 미구현**

### RDS 연결 정보
- Host: `ddoksori-postgres.czocsimuw0dc.ap-northeast-2.rds.amazonaws.com`
- Port: `5432`
- Database: `ddoksori`
- User: `postgres`

---

## 구현 단계

### Phase 1: Mock 데이터 백업

**작업 내용:**
1. `BoardPage.tsx`의 `initialPosts` 배열 추출 (30개 게시글)
2. `PostDetail.tsx`의 댓글/대댓글 샘플 데이터 추출
3. `MyPage.tsx`의 `myBoardPosts`, `commentedPosts` 배열 추출
4. JSON 파일로 저장: `LLM/data/backup/mock_board_data.json`

**백업 파일 구조:**
```json
{
  "posts": [...],
  "comments": [...],
  "mypage_mock": {
    "myBoardPosts": [...],
    "commentedPosts": [...]
  },
  "backup_date": "2026-02-06",
  "source_files": ["BoardPage.tsx", "PostDetail.tsx", "MyPage.tsx"]
}
```

---

### Phase 2: RDS 테이블 설계

현재 코드 기반으로 실제 필요한 테이블 구조를 설계합니다.

#### 2.1 community_category (카테고리)

```sql
CREATE TABLE community_category (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_key VARCHAR(50) NOT NULL UNIQUE,  -- 'case-sharing', 'qna', 'tips'
    category_name VARCHAR(100) NOT NULL,        -- '분쟁해결사례 공유'
    display_name VARCHAR(100) NOT NULL,         -- '분쟁해결사례/공유'
    sort_order INT UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 초기 데이터
INSERT INTO community_category (category_key, category_name, display_name, sort_order) VALUES
('case-sharing', '분쟁해결사례 공유', '분쟁해결사례/공유', 1),
('qna', '무엇이든 물어보세요', '무엇이든/물어보세요', 2),
('tips', '소비자 꿀팁/노하우', '소비자/꿀팁/노하우', 3);
```

#### 2.2 community_post (게시글)

```sql
CREATE TYPE community_content_status AS ENUM ('normal', 'hidden', 'deleted');

CREATE TABLE community_post (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    category_id UUID NOT NULL REFERENCES community_category(id),
    sub_category VARCHAR(100),                   -- 분쟁해결사례 전용 (pre-mediation, mediation)
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    preview VARCHAR(200),                        -- 목록 미리보기용
    view_count INT NOT NULL DEFAULT 0,
    like_count INT NOT NULL DEFAULT 0,
    comment_count INT NOT NULL DEFAULT 0,
    status community_content_status NOT NULL DEFAULT 'normal',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    edited_at TIMESTAMP WITH TIME ZONE,          -- 사용자 편집 시점
    deleted_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT chk_post_status_deleted CHECK (
        (status = 'deleted') = (deleted_at IS NOT NULL)
    )
);

-- 인덱스
CREATE INDEX idx_post_category_created ON community_post(category_id, created_at DESC);
CREATE INDEX idx_post_user_created ON community_post(user_id, created_at DESC);
CREATE INDEX idx_post_status_created ON community_post(status, created_at DESC);
```

#### 2.3 community_comment (댓글/대댓글)

```sql
CREATE TABLE community_comment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES community_post(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    parent_comment_id UUID REFERENCES community_comment(id),  -- NULL이면 댓글, 있으면 대댓글
    content TEXT NOT NULL,
    like_count INT NOT NULL DEFAULT 0,
    status community_content_status NOT NULL DEFAULT 'normal',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    edited_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT chk_comment_not_self_ref CHECK (parent_comment_id IS NULL OR parent_comment_id <> id),
    CONSTRAINT chk_comment_status_deleted CHECK (
        (status = 'deleted') = (deleted_at IS NOT NULL)
    )
);

-- 인덱스
CREATE INDEX idx_comment_post_created ON community_comment(post_id, created_at);
CREATE INDEX idx_comment_parent ON community_comment(parent_comment_id);
CREATE INDEX idx_comment_user ON community_comment(user_id, created_at DESC);
```

#### 2.4 community_post_like (게시글 좋아요)

```sql
CREATE TABLE community_post_like (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES community_post(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_post_like UNIQUE (post_id, user_id)
);

CREATE INDEX idx_post_like_user ON community_post_like(user_id, created_at DESC);
```

#### 2.5 community_comment_like (댓글 좋아요)

```sql
CREATE TABLE community_comment_like (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id UUID NOT NULL REFERENCES community_comment(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_comment_like UNIQUE (comment_id, user_id)
);

CREATE INDEX idx_comment_like_user ON community_comment_like(user_id, created_at DESC);
```

#### 2.6 community_report (신고)

```sql
CREATE TYPE report_target_type AS ENUM ('post', 'comment');
CREATE TYPE report_status AS ENUM ('pending', 'reviewed', 'resolved', 'dismissed');

CREATE TABLE community_report (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id UUID NOT NULL REFERENCES users(id),
    target_type report_target_type NOT NULL,
    target_id UUID NOT NULL,                     -- post_id 또는 comment_id
    reason TEXT NOT NULL,
    status report_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewed_by UUID REFERENCES users(id)
);

CREATE INDEX idx_report_status ON community_report(status, created_at DESC);
CREATE INDEX idx_report_target ON community_report(target_type, target_id);
```

---

### Phase 3: Backend API 구현

#### 3.1 파일 구조

```
backend/app/
├── api/
│   └── board.py              # 게시판 API 라우터 (신규)
├── board/
│   ├── board_db.py           # DB 레이어 (확장)
│   ├── schemas.py            # Pydantic 스키마 (신규)
│   └── service.py            # 비즈니스 로직 (신규)
└── main.py                   # 라우터 등록
```

#### 3.2 API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| **게시글** |
| GET | `/api/board/posts` | 게시글 목록 (검색/필터/페이지네이션) |
| GET | `/api/board/posts/{post_id}` | 게시글 상세 |
| POST | `/api/board/posts` | 게시글 작성 |
| PUT | `/api/board/posts/{post_id}` | 게시글 수정 |
| DELETE | `/api/board/posts/{post_id}` | 게시글 삭제 (소프트) |
| POST | `/api/board/posts/{post_id}/like` | 게시글 좋아요 토글 |
| POST | `/api/board/posts/{post_id}/report` | 게시글 신고 |
| **댓글** |
| GET | `/api/board/posts/{post_id}/comments` | 댓글 목록 |
| POST | `/api/board/posts/{post_id}/comments` | 댓글 작성 |
| PUT | `/api/board/comments/{comment_id}` | 댓글 수정 |
| DELETE | `/api/board/comments/{comment_id}` | 댓글 삭제 |
| POST | `/api/board/comments/{comment_id}/like` | 댓글 좋아요 토글 |
| POST | `/api/board/comments/{comment_id}/report` | 댓글 신고 |
| POST | `/api/board/comments/{comment_id}/replies` | 대댓글 작성 |
| **카테고리** |
| GET | `/api/board/categories` | 카테고리 목록 |

#### 3.3 스키마 예시

```python
# schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum

class PostCategory(str, Enum):
    CASE_SHARING = "case-sharing"
    QNA = "qna"
    TIPS = "tips"

class PostCreate(BaseModel):
    category: PostCategory
    sub_category: Optional[str] = None
    title: str = Field(..., max_length=100)
    content: str = Field(..., max_length=5000)

class PostResponse(BaseModel):
    id: UUID
    category: str
    category_display: str
    sub_category: Optional[str]
    title: str
    content: str
    preview: str
    author_nickname: str
    author_id: UUID
    view_count: int
    like_count: int
    comment_count: int
    is_liked: bool  # 현재 사용자 좋아요 여부
    is_edited: bool
    created_at: datetime
    edited_at: Optional[datetime]

class CommentCreate(BaseModel):
    content: str = Field(..., max_length=1000)
    parent_comment_id: Optional[UUID] = None

class CommentResponse(BaseModel):
    id: UUID
    content: str
    author_nickname: str
    author_id: UUID
    like_count: int
    is_liked: bool
    is_edited: bool
    created_at: datetime
    edited_at: Optional[datetime]
    replies: List["CommentResponse"] = []
```

---

### Phase 4: Frontend API 연동

#### 4.1 API 클라이언트 추가

```typescript
// frontend/src/shared/api/boardApi.ts

export const boardApi = {
  // 게시글
  getPosts: (params: GetPostsParams) =>
    apiClient.get<PostListResponse>('/api/board/posts', { params }),

  getPost: (postId: string) =>
    apiClient.get<PostDetailResponse>(`/api/board/posts/${postId}`),

  createPost: (data: CreatePostData) =>
    apiClient.post<PostResponse>('/api/board/posts', data),

  updatePost: (postId: string, data: UpdatePostData) =>
    apiClient.put<PostResponse>(`/api/board/posts/${postId}`, data),

  deletePost: (postId: string) =>
    apiClient.delete(`/api/board/posts/${postId}`),

  togglePostLike: (postId: string) =>
    apiClient.post(`/api/board/posts/${postId}/like`),

  reportPost: (postId: string, reason: string) =>
    apiClient.post(`/api/board/posts/${postId}/report`, { reason }),

  // 댓글
  getComments: (postId: string) =>
    apiClient.get<CommentListResponse>(`/api/board/posts/${postId}/comments`),

  createComment: (postId: string, data: CreateCommentData) =>
    apiClient.post(`/api/board/posts/${postId}/comments`, data),

  updateComment: (commentId: string, content: string) =>
    apiClient.put(`/api/board/comments/${commentId}`, { content }),

  deleteComment: (commentId: string) =>
    apiClient.delete(`/api/board/comments/${commentId}`),

  toggleCommentLike: (commentId: string) =>
    apiClient.post(`/api/board/comments/${commentId}/like`),

  createReply: (commentId: string, content: string) =>
    apiClient.post(`/api/board/comments/${commentId}/replies`, { content }),

  // 카테고리
  getCategories: () =>
    apiClient.get<CategoryListResponse>('/api/board/categories'),
};
```

#### 4.2 컴포넌트 수정 사항

| 파일 | 수정 내용 |
|------|----------|
| `BoardPage.tsx` | Mock 데이터 제거, API 호출로 대체, 로딩/에러 상태 추가 |
| `WritePost.tsx` | `onSubmit`에서 API 호출, 성공 시 목록으로 이동 |
| `PostDetail.tsx` | API로 상세 데이터 로드, 댓글 CRUD API 연동 |
| `EditPost.tsx` | API로 기존 데이터 로드, 수정 API 호출 |

---

### Phase 4-2: 마이페이지 연동

마이페이지의 "내 게시글"과 "내가 댓글을 단 게시글" 섹션이 자유게시판과 연동되어야 합니다.

#### 4.2.1 현재 마이페이지 상태

**MyPage.tsx (255-298줄)**
```typescript
// 현재: 하드코딩된 Mock 데이터
const myBoardPosts = [
  { id: 4, category: '무엇이든/물어보세요', title: '환불 절차가 궁금합니다', ... },
  { id: 3, category: '소비자/꿀팁/노하우', title: '소비자분쟁 조정 신청할 때...', ... },
];

const commentedPosts = [
  { id: 1, category: '분쟁해결사례/공유', title: '당근마켓 사기 피해...', myCommentDate: '2025.12.21' },
  { id: 6, category: '소비자/꿀팁/노하우', title: '전자제품 AS 받을 때...', myCommentDate: '2025.12.16' },
];
```

#### 4.2.2 Backend API 확인

**이미 존재하는 API (users.py)**
```python
@router.get("/api/users/me/posts")
async def get_my_posts(page, limit, current_user):
    # BoardDB.get_user_posts() 호출

@router.get("/api/users/me/commented-posts")
async def get_my_commented_posts(page, limit, current_user):
    # BoardDB.get_user_commented_posts() 호출
```

**BoardDB 쿼리 수정 필요 (board_db.py)**
- 테이블명 변경: `posts` → `community_post`
- 테이블명 변경: `comments` → `community_comment`
- 카테고리 조인 추가: `community_category`
- 사용자 닉네임 조인: `users`

#### 4.2.3 MyPage.tsx 수정 사항

```typescript
// 변경 후: API 호출로 대체
const [myBoardPosts, setMyBoardPosts] = useState<MyPost[]>([]);
const [commentedPosts, setCommentedPosts] = useState<CommentedPost[]>([]);
const [isLoading, setIsLoading] = useState(true);

useEffect(() => {
  const fetchMyPosts = async () => {
    try {
      const [postsRes, commentedRes] = await Promise.all([
        boardApi.getMyPosts({ page: myPostsPage, limit: itemsPerPage }),
        boardApi.getMyCommentedPosts({ page: commentedPostsPage, limit: itemsPerPage }),
      ]);
      setMyBoardPosts(postsRes.posts);
      setCommentedPosts(commentedRes.posts);
    } catch (error) {
      console.error('게시글 로드 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (isAuthenticated) {
    fetchMyPosts();
  }
}, [myPostsPage, commentedPostsPage, isAuthenticated]);
```

#### 4.2.4 마이페이지 ↔ 자유게시판 연동 흐름

```
[마이페이지]                          [자유게시판]
    │                                     │
    ├─ "내 게시글" 클릭 ────────────────→ PostDetail.tsx (상세보기)
    │   navigate(ROUTES.BOARD,            │
    │   { state: { postId, viewType } })  │
    │                                     │
    ├─ "내가 댓글단 게시글" 클릭 ────────→ PostDetail.tsx (상세보기)
    │                                     │
    └─ "게시글 작성하기" 클릭 ──────────→ WritePost.tsx (작성 폼)
```

#### 4.2.5 응답 데이터 형식

**GET /api/users/me/posts 응답**
```json
{
  "posts": [
    {
      "id": "uuid",
      "category": "case-sharing",
      "category_display": "분쟁해결사례/공유",
      "title": "제목",
      "date": "2026.02.06",
      "views": 123,
      "likes": 45,
      "comments": 12
    }
  ],
  "total": 30,
  "page": 1,
  "totalPages": 3
}
```

**GET /api/users/me/commented-posts 응답**
```json
{
  "posts": [
    {
      "id": "uuid",
      "category": "qna",
      "category_display": "무엇이든/물어보세요",
      "title": "게시글 제목",
      "date": "2026.02.05",
      "views": 234,
      "likes": 56,
      "comments": 23,
      "myCommentDate": "2026.02.06",
      "myCommentPreview": "내가 단 댓글 미리보기..."
    }
  ],
  "total": 15,
  "page": 1,
  "totalPages": 2
}
```

---

### Phase 6: 테스트 및 검증

1. **단위 테스트**: Backend API 엔드포인트별 테스트
2. **통합 테스트**: Frontend-Backend 연동 테스트
3. **시나리오 테스트**:
   - 비로그인 사용자: 목록 조회만 가능
   - 로그인 사용자: 게시글/댓글 작성
   - 작성자: 수정/삭제 가능
   - 비작성자: 신고만 가능
4. **마이페이지 연동 테스트**:
   - 로그인 후 게시글 작성 → 마이페이지 "내 게시글"에 표시 확인
   - 로그인 후 댓글 작성 → 마이페이지 "내가 댓글을 단 게시글"에 표시 확인
   - 마이페이지에서 게시글 클릭 → 자유게시판 상세보기로 이동 확인
   - 게시글 삭제 → 마이페이지 목록에서 제거 확인
5. **탈퇴 사용자 테스트**: "탈퇴한 사용자" 표시 확인

---

## 파일 작업 순서

### Step 1: Mock 데이터 백업
- [ ] `BoardPage.tsx` Mock 데이터 추출
- [ ] `PostDetail.tsx` 댓글/대댓글 Mock 데이터 추출
- [ ] `MyPage.tsx` 마이페이지 Mock 데이터 추출
- [ ] `data/backup/mock_board_data.json` 생성

### Step 2: DB 마이그레이션
- [ ] `backend/migrations/create_community_tables.sql` 생성
- [ ] RDS에 테이블 생성

### Step 3: Backend 구현
- [ ] `backend/app/board/schemas.py` 생성
- [ ] `backend/app/board/board_db.py` 확장
- [ ] `backend/app/board/service.py` 생성
- [ ] `backend/app/api/board.py` 생성
- [ ] `backend/app/main.py` 라우터 등록

### Step 4: Frontend 연동 (자유게시판)
- [ ] `frontend/src/shared/api/boardApi.ts` 생성
- [ ] `frontend/src/shared/types/board.types.ts` 업데이트
- [ ] `BoardPage.tsx` 수정 - Mock 데이터 제거, API 연동
- [ ] `WritePost.tsx` 수정 - 게시글 작성 API 연동
- [ ] `PostDetail.tsx` 수정 - 상세/댓글 API 연동
- [ ] `EditPost.tsx` 수정 - 게시글 수정 API 연동

### Step 5: Frontend 연동 (마이페이지)
- [ ] `backend/app/board/board_db.py` 수정 - 마이페이지 쿼리 테이블명/조인 수정
- [ ] `MyPage.tsx` 수정 - Mock 데이터 제거
- [ ] `MyPage.tsx` 수정 - `/api/users/me/posts` API 연동
- [ ] `MyPage.tsx` 수정 - `/api/users/me/commented-posts` API 연동
- [ ] 마이페이지 → 자유게시판 상세보기 네비게이션 테스트

### Step 6: 테스트
- [ ] Backend API 단위 테스트
- [ ] 자유게시판 E2E 테스트
- [ ] 마이페이지 연동 테스트
- [ ] 마이페이지 → 자유게시판 상세보기 네비게이션 테스트

---

## 참고 사항

### 기존 users 테이블과의 연동
- `users.id`를 FK로 참조
- 탈퇴 사용자(`status='deleted'`)의 게시글/댓글은 보존
- UI에서 닉네임 조회 시 탈퇴 여부 체크

### 대댓글 1단 제한
- Frontend: 대댓글의 답글 버튼 비활성화
- Backend: `parent_comment_id`가 있는 댓글에 대댓글 시도 시 400 에러

### 조회수 증가 정책
- 같은 사용자가 새로고침해도 조회수 증가 (단순 구현)
- 향후 개선: Redis 캐시로 중복 방지

---

## 예상 작업량

| 단계 | 예상 작업량 |
|------|------------|
| Phase 1: Mock 데이터 백업 | 작음 |
| Phase 2: RDS 테이블 설계 | 중간 |
| Phase 3: Backend API 구현 | 큼 |
| Phase 4: Frontend API 연동 (자유게시판) | 큼 |
| Phase 4-2: Frontend API 연동 (마이페이지) | 중간 |
| Phase 6: 테스트 | 중간 |

---

*작성일: 2026-02-06*
*작성자: Claude Code*
