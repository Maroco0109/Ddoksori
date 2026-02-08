# 자유게시판 DB 연동 구현 결과 보고서

**작성일:** 2026-02-06
**작성자:** Claude Code
**상태:** ✅ 구현 완료

---

## 개요

자유게시판(커뮤니티 게시판) 기능을 Mock 데이터 기반에서 AWS RDS PostgreSQL 연동으로 전환했습니다. 게시글, 댓글, 좋아요, 신고 기능이 모두 백엔드 API와 연동되며, 마이페이지에서도 실시간으로 데이터가 반영됩니다.

---

## 구현 완료 기능

### 게시글 기능
| 기능 | 상태 | 설명 |
|------|------|------|
| 게시글 목록 조회 | ✅ | 카테고리 필터링, 검색, 페이지네이션 |
| 게시글 상세 조회 | ✅ | 조회수 자동 증가 |
| 게시글 작성 | ✅ | 카테고리, 서브카테고리 선택 |
| 게시글 수정 | ✅ | 본인 게시글만 수정 가능, 수정일 표시 |
| 게시글 삭제 | ✅ | 본인 게시글만 삭제 가능 (소프트 삭제) |
| 게시글 좋아요 | ✅ | 토글 방식, 좋아요 수 실시간 반영 |
| 게시글 신고 | ✅ | 타인 게시글만 신고 가능 |

### 댓글 기능
| 기능 | 상태 | 설명 |
|------|------|------|
| 댓글 목록 조회 | ✅ | 대댓글 포함 계층 구조 |
| 댓글 작성 | ✅ | - |
| 대댓글 작성 | ✅ | 1단 제한 (대댓글의 대댓글 불가) |
| 댓글 수정 | ✅ | 본인 댓글만 수정 가능, 수정일 표시 |
| 댓글 삭제 | ✅ | 본인 댓글만 삭제 가능 |
| 댓글 좋아요 | ✅ | 토글 방식 |
| 댓글 신고 | ✅ | 타인 댓글만 신고 가능 |

### 마이페이지 연동
| 기능 | 상태 | 설명 |
|------|------|------|
| 내 게시글 목록 | ✅ | 실시간 API 연동 |
| 내가 댓글 단 게시글 | ✅ | 실시간 API 연동 |
| 게시글 클릭 시 상세 이동 | ✅ | 자유게시판 상세 페이지로 이동 |

---

## 데이터베이스 설계

### ERD (Entity Relationship Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           COMMUNITY BOARD ERD                                    │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐       ┌──────────────────────┐       ┌──────────────────┐
│      users       │       │   community_category │       │  community_post  │
├──────────────────┤       ├──────────────────────┤       ├──────────────────┤
│ PK user_id (VARCHAR)│◄──┐   │ PK id (UUID)         │   ┌──►│ PK id (UUID)     │
│    email         │   │   │    category_key      │   │   │ FK user_id       │──┐
│    name          │   │   │    category_name     │   │   │ FK category_id   │──┼───►
│    provider      │   │   │    display_name      │   │   │    sub_category  │  │
│    created_at    │   │   │    sort_order        │   │   │    title         │  │
└──────────────────┘   │   └──────────────────────┘   │   │    content       │  │
                       │              │               │   │    preview       │  │
                       │              │               │   │    view_count    │  │
                       │              └───────────────┘   │    like_count    │  │
                       │                                  │    comment_count │  │
                       │                                  │    status        │  │
                       │                                  │    created_at    │  │
                       │                                  │    edited_at     │  │
                       │                                  └──────────────────┘  │
                       │                                           │            │
                       │                                           │            │
         ┌─────────────┼───────────────────────────────────────────┼────────────┘
         │             │                                           │
         │             │     ┌──────────────────────┐              │
         │             │     │  community_comment   │              │
         │             │     ├──────────────────────┤              │
         │             │     │ PK id (UUID)         │◄─────────────┤
         │             └────►│ FK user_id           │              │
         │                   │ FK post_id           │──────────────┘
         │                   │ FK parent_comment_id │───┐ (self-reference)
         │                   │    content           │   │
         │                   │    like_count        │   │
         │                   │    status            │   │
         │                   │    created_at        │◄──┘
         │                   │    edited_at         │
         │                   └──────────────────────┘
         │                              │
         │                              │
┌────────┴─────────┐      ┌─────────────┴──────────┐      ┌──────────────────┐
│community_post_like│      │community_comment_like │      │ community_report │
├──────────────────┤      ├──────────────────────┤      ├──────────────────┤
│ PK id (UUID)     │      │ PK id (UUID)         │      │ PK id (UUID)     │
│ FK post_id       │      │ FK comment_id        │      │ FK reporter_id   │
│ FK user_id       │      │ FK user_id           │      │    target_type   │
│    created_at    │      │    created_at        │      │    target_id     │
│                  │      │                      │      │    reason        │
│ UQ(post_id,      │      │ UQ(comment_id,       │      │    status        │
│    user_id)      │      │    user_id)          │      │    created_at    │
└──────────────────┘      └──────────────────────┘      └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│ 관계 설명:                                                                       │
│  • users 1:N community_post (사용자는 여러 게시글 작성 가능)                      │
│  • users 1:N community_comment (사용자는 여러 댓글 작성 가능)                     │
│  • community_category 1:N community_post (카테고리당 여러 게시글)                 │
│  • community_post 1:N community_comment (게시글당 여러 댓글)                      │
│  • community_comment 1:N community_comment (댓글의 대댓글, self-reference)       │
│  • community_post 1:N community_post_like (게시글당 여러 좋아요)                  │
│  • community_comment 1:N community_comment_like (댓글당 여러 좋아요)              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 테이블 상세 명세

#### 1. community_category (카테고리)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | UUID | PK, DEFAULT gen_random_uuid() | 카테고리 고유 ID |
| category_key | VARCHAR(50) | NOT NULL, UNIQUE | 카테고리 키 (case-sharing, qna, tips) |
| category_name | VARCHAR(100) | NOT NULL | 카테고리 전체 이름 |
| display_name | VARCHAR(100) | NOT NULL | 표시용 이름 (슬래시 구분) |
| sort_order | INT | UNIQUE | 정렬 순서 |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 생성 시각 |

**초기 데이터:**
| category_key | category_name | display_name | sort_order |
|--------------|---------------|--------------|------------|
| case-sharing | 분쟁해결사례 공유 | 분쟁해결사례/공유 | 1 |
| qna | 무엇이든 물어보세요 | 무엇이든/물어보세요 | 2 |
| tips | 소비자 꿀팁/노하우 | 소비자/꿀팁/노하우 | 3 |

#### 2. community_post (게시글)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | UUID | PK, DEFAULT gen_random_uuid() | 게시글 고유 ID |
| user_id | VARCHAR(255) | NOT NULL, FK → users(user_id) | 작성자 ID |
| category_id | UUID | NOT NULL, FK → community_category(id) | 카테고리 ID |
| sub_category | VARCHAR(100) | - | 서브 카테고리 (pre-mediation, mediation) |
| title | VARCHAR(100) | NOT NULL | 제목 |
| content | TEXT | NOT NULL | 내용 |
| preview | VARCHAR(200) | - | 목록 미리보기 |
| view_count | INT | NOT NULL, DEFAULT 0 | 조회수 |
| like_count | INT | NOT NULL, DEFAULT 0 | 좋아요 수 (캐싱) |
| comment_count | INT | NOT NULL, DEFAULT 0 | 댓글 수 (캐싱) |
| status | community_content_status | NOT NULL, DEFAULT 'normal' | 상태 (normal/hidden/deleted) |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 생성 시각 |
| updated_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 시스템 수정 시각 |
| edited_at | TIMESTAMP WITH TIME ZONE | - | 사용자 편집 시각 |
| deleted_at | TIMESTAMP WITH TIME ZONE | - | 삭제 시각 |

**인덱스:**
- `idx_post_category_created` (category_id, created_at DESC)
- `idx_post_user_created` (user_id, created_at DESC)
- `idx_post_status_created` (status, created_at DESC)
- `idx_post_category_status_created` (category_id, status, created_at DESC)

#### 3. community_comment (댓글/대댓글)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | UUID | PK, DEFAULT gen_random_uuid() | 댓글 고유 ID |
| post_id | UUID | NOT NULL, FK → community_post(id) ON DELETE CASCADE | 게시글 ID |
| user_id | VARCHAR(255) | NOT NULL, FK → users(user_id) | 작성자 ID |
| parent_comment_id | UUID | FK → community_comment(id) ON DELETE CASCADE | 부모 댓글 ID (대댓글인 경우) |
| content | TEXT | NOT NULL | 댓글 내용 |
| like_count | INT | NOT NULL, DEFAULT 0 | 좋아요 수 |
| status | community_content_status | NOT NULL, DEFAULT 'normal' | 상태 |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 생성 시각 |
| updated_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 시스템 수정 시각 |
| edited_at | TIMESTAMP WITH TIME ZONE | - | 사용자 편집 시각 |
| deleted_at | TIMESTAMP WITH TIME ZONE | - | 삭제 시각 |

**제약조건:**
- `chk_comment_not_self_ref`: parent_comment_id가 자기 자신을 참조할 수 없음

**인덱스:**
- `idx_comment_post_created` (post_id, created_at)
- `idx_comment_parent` (parent_comment_id)
- `idx_comment_user` (user_id, created_at DESC)
- `idx_comment_post_status_created` (post_id, status, created_at)

#### 4. community_post_like (게시글 좋아요)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | UUID | PK, DEFAULT gen_random_uuid() | 좋아요 고유 ID |
| post_id | UUID | NOT NULL, FK → community_post(id) ON DELETE CASCADE | 게시글 ID |
| user_id | VARCHAR(255) | NOT NULL, FK → users(user_id) ON DELETE CASCADE | 사용자 ID |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 생성 시각 |

**제약조건:**
- `uq_post_like` UNIQUE (post_id, user_id) - 중복 좋아요 방지

#### 5. community_comment_like (댓글 좋아요)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | UUID | PK, DEFAULT gen_random_uuid() | 좋아요 고유 ID |
| comment_id | UUID | NOT NULL, FK → community_comment(id) ON DELETE CASCADE | 댓글 ID |
| user_id | VARCHAR(255) | NOT NULL, FK → users(user_id) ON DELETE CASCADE | 사용자 ID |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 생성 시각 |

**제약조건:**
- `uq_comment_like` UNIQUE (comment_id, user_id) - 중복 좋아요 방지

#### 6. community_report (신고)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | UUID | PK, DEFAULT gen_random_uuid() | 신고 고유 ID |
| reporter_id | VARCHAR(255) | NOT NULL, FK → users(user_id) | 신고자 ID |
| target_type | report_target_type | NOT NULL | 신고 대상 유형 (post/comment) |
| target_id | UUID | NOT NULL | 신고 대상 ID |
| reason | TEXT | NOT NULL | 신고 사유 |
| status | report_status | NOT NULL, DEFAULT 'pending' | 처리 상태 |
| created_at | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 생성 시각 |
| reviewed_at | TIMESTAMP WITH TIME ZONE | - | 검토 시각 |
| reviewed_by | VARCHAR(255) | FK → users(user_id) | 검토자 ID |

**인덱스:**
- `idx_report_status` (status, created_at DESC)
- `idx_report_target` (target_type, target_id)
- `idx_report_reporter` (reporter_id)

### ENUM 타입

```sql
-- 게시글/댓글 상태
CREATE TYPE community_content_status AS ENUM ('normal', 'hidden', 'deleted');

-- 신고 대상 유형
CREATE TYPE report_target_type AS ENUM ('post', 'comment');

-- 신고 처리 상태
CREATE TYPE report_status AS ENUM ('pending', 'reviewed', 'resolved', 'dismissed');
```

### 트리거 (자동 카운트 업데이트)

| 트리거명 | 테이블 | 동작 |
|----------|--------|------|
| trigger_community_post_updated_at | community_post | UPDATE 시 updated_at 자동 갱신 |
| trigger_community_comment_updated_at | community_comment | UPDATE 시 updated_at 자동 갱신 |
| trigger_update_post_comment_count | community_comment | INSERT/DELETE/UPDATE 시 게시글의 comment_count 자동 갱신 |
| trigger_update_post_like_count | community_post_like | INSERT/DELETE 시 게시글의 like_count 자동 갱신 |
| trigger_update_comment_like_count | community_comment_like | INSERT/DELETE 시 댓글의 like_count 자동 갱신 |

---

## API 엔드포인트

### 게시판 API (`/api/board`)

| Method | Endpoint | 인증 | 설명 |
|--------|----------|------|------|
| GET | `/api/board/categories` | 선택 | 카테고리 목록 |
| GET | `/api/board/posts` | 선택 | 게시글 목록 (필터링, 검색, 페이지네이션) |
| GET | `/api/board/posts/{post_id}` | 선택 | 게시글 상세 |
| POST | `/api/board/posts` | 필수 | 게시글 작성 |
| PUT | `/api/board/posts/{post_id}` | 필수 | 게시글 수정 (본인만) |
| DELETE | `/api/board/posts/{post_id}` | 필수 | 게시글 삭제 (본인만) |
| POST | `/api/board/posts/{post_id}/like` | 필수 | 게시글 좋아요 토글 |
| POST | `/api/board/posts/{post_id}/report` | 필수 | 게시글 신고 |
| GET | `/api/board/posts/{post_id}/comments` | 선택 | 댓글 목록 |
| POST | `/api/board/posts/{post_id}/comments` | 필수 | 댓글 작성 |
| PUT | `/api/board/comments/{comment_id}` | 필수 | 댓글 수정 (본인만) |
| DELETE | `/api/board/comments/{comment_id}` | 필수 | 댓글 삭제 (본인만) |
| POST | `/api/board/comments/{comment_id}/like` | 필수 | 댓글 좋아요 토글 |
| POST | `/api/board/comments/{comment_id}/report` | 필수 | 댓글 신고 |
| POST | `/api/board/comments/{comment_id}/replies` | 필수 | 대댓글 작성 |

### 마이페이지 API (`/api/users`)

| Method | Endpoint | 인증 | 설명 |
|--------|----------|------|------|
| GET | `/api/users/me/posts` | 필수 | 내가 작성한 게시글 목록 |
| GET | `/api/users/me/commented-posts` | 필수 | 내가 댓글 단 게시글 목록 |

---

## 파일 구조

### Backend

```
backend/app/
├── api/
│   ├── __init__.py          # board_router 추가
│   ├── board.py              # 게시판 API 라우터 (신규)
│   └── users.py              # 마이페이지 API (수정)
├── board/
│   ├── __init__.py
│   ├── board_db.py           # DB 접근 계층 (전면 재작성)
│   ├── schemas.py            # Pydantic 스키마 (신규)
│   └── service.py            # 비즈니스 로직 (신규)
├── database/
│   └── migrations/
│       └── 005_community_board.sql  # 마이그레이션 SQL
└── main.py                   # board_router 등록
```

### Frontend

```
frontend/src/
├── features/
│   ├── board/
│   │   ├── BoardPage.tsx         # Mock 제거, API 연동 (수정)
│   │   ├── board.types.ts        # 타입 정의 (수정)
│   │   └── components/
│   │       ├── PostDetail.tsx    # API 연동, 수정/삭제 버튼 (수정)
│   │       ├── WritePost.tsx     # API 연동 (수정)
│   │       └── EditPost.tsx      # API 연동 (수정)
│   └── mypage/
│       └── MyPage.tsx            # Mock 제거, API 연동 (수정)
└── shared/
    └── api/
        ├── client.ts             # Admin 토큰 분기 처리 (수정)
        └── board.service.ts      # 게시판 API 서비스 (신규)
```

---

## 수정된 파일 목록

### Backend (신규/수정)

| 파일 | 상태 | 설명 |
|------|------|------|
| `app/api/board.py` | 신규 | 게시판 API 라우터 (15개 엔드포인트) |
| `app/api/__init__.py` | 수정 | board_router 추가 |
| `app/api/users.py` | 수정 | 마이페이지 API가 BoardService 사용 |
| `app/board/schemas.py` | 신규 | Pydantic 스키마 (요청/응답 모델) |
| `app/board/service.py` | 신규 | 비즈니스 로직 계층 |
| `app/board/board_db.py` | 전면 재작성 | 모든 DB 쿼리 구현 |
| `app/main.py` | 수정 | board_router 등록 |
| `app/database/migrations/005_community_board.sql` | 신규 | 테이블/트리거 생성 SQL |

### Frontend (신규/수정)

| 파일 | 상태 | 설명 |
|------|------|------|
| `shared/api/board.service.ts` | 신규 | 게시판 API 서비스 + 마이페이지 API |
| `shared/api/client.ts` | 수정 | Admin 토큰 분기 처리, localStorage 폴백 |
| `features/board/board.types.ts` | 수정 | API 호환 타입 정의 |
| `features/board/BoardPage.tsx` | 수정 | Mock 제거, API 연동 |
| `features/board/components/PostDetail.tsx` | 수정 | API 연동, 수정/삭제 버튼, 사용자 ID 비교 수정 |
| `features/board/components/WritePost.tsx` | 수정 | 서브카테고리 값 변경 |
| `features/board/components/EditPost.tsx` | 수정 | API 호환 수정 |
| `features/mypage/MyPage.tsx` | 수정 | Mock 제거, API 연동 |

---

## 테스트 결과

### 기능 테스트

| 테스트 항목 | 결과 | 비고 |
|-------------|------|------|
| 게시글 작성 | ✅ 통과 | 모든 카테고리 테스트 완료 |
| 게시글 수정 | ✅ 통과 | 수정일 표시 확인 |
| 게시글 삭제 | ✅ 통과 | 소프트 삭제, 마이페이지 반영 확인 |
| 게시글 좋아요 | ✅ 통과 | 토글 동작 확인 |
| 댓글 작성 | ✅ 통과 | - |
| 대댓글 작성 | ✅ 통과 | 1단 제한 확인 |
| 댓글 수정/삭제 | ✅ 통과 | 마이페이지 반영 확인 |
| 댓글 좋아요 | ✅ 통과 | - |
| 신고 기능 | ✅ 통과 | 게시글/댓글 모두 테스트 |
| 마이페이지 연동 | ✅ 통과 | 실시간 데이터 반영 확인 |
| 마이페이지 → 게시글 이동 | ✅ 통과 | 상세 페이지 정상 이동 |

### 권한 테스트

| 테스트 항목 | 결과 | 비고 |
|-------------|------|------|
| 비로그인 사용자 게시글 조회 | ✅ 통과 | 조회만 가능 |
| 비로그인 사용자 작성 시도 | ✅ 통과 | 401 Unauthorized |
| 본인 게시글 수정/삭제 버튼 | ✅ 통과 | 본인에게만 표시 |
| 타인 게시글 신고 버튼 | ✅ 통과 | 타인에게만 표시 |

---

## 버그 수정 이력

### 1. API Client Admin 토큰 문제
- **증상**: 게시글 작성 시 401 Unauthorized
- **원인**: Admin 토큰이 모든 API에 우선 적용됨
- **해결**: `/api/admin` 엔드포인트에만 admin 토큰 사용하도록 수정

### 2. Zustand Persist Hydration 타이밍 문제
- **증상**: 로그인 후 API 호출 시 토큰이 없음
- **원인**: Zustand persist가 상태 복원하기 전에 API 호출
- **해결**: localStorage에서 직접 토큰 읽기 폴백 추가

### 3. 사용자 ID 필드명 불일치
- **증상**: 본인 게시글에 수정/삭제 버튼이 안 보임
- **원인**: `user?.user_id` 대신 `user?.id` 사용해야 함
- **해결**: PostDetail.tsx의 currentUserId 추출 로직 수정

---

## 향후 개선 사항

1. **조회수 중복 방지**: Redis 캐시로 같은 사용자 중복 조회 방지
2. **이미지 첨부**: 게시글/댓글 이미지 업로드 기능
3. **알림 기능**: 댓글, 좋아요 알림
4. **관리자 기능**: 신고 처리, 게시글/댓글 관리

---

## 마이그레이션 파일 위치

```
backend/app/database/migrations/005_community_board.sql
```

**실행 방법:**
```sql
-- PostgreSQL 클라이언트에서 실행
\i 005_community_board.sql
```

---

*작성일: 2026-02-06*
*작성자: Claude Code*
