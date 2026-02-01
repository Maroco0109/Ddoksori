# 소셜 로그인 구현 가이드 (백엔드)

프론트엔드에서 Google과 Naver 소셜 로그인 연동을 위해 백엔드 OAuth 엔드포인트가 필요합니다.

## 목차
1. [JWT란?](#jwt란)
2. [필요한 환경변수 설정](#필요한-환경변수-설정)
3. [필요한 라이브러리 설치](#필요한-라이브러리-설치)
4. [OAuth 라우터 구현](#oauth-라우터-구현)
5. [라우터 등록](#라우터-등록)
6. [테스트](#테스트)
7. [회원탈퇴 API 사용법](#회원탈퇴-api-사용법)
8. [마이페이지 API](#마이페이지-api)
9. [추가 고려사항](#추가-고려사항)

---

## JWT란?

**JWT (JSON Web Token)**는 사용자 인증을 위한 토큰 방식입니다.

### 동작 방식
1. 사용자가 소셜 로그인 → 백엔드에서 JWT 토큰 생성
2. 토큰을 프론트엔드에 전달 (URL 파라미터 또는 쿠키)
3. 프론트엔드는 이후 API 요청마다 토큰을 헤더에 포함
4. 백엔드는 토큰을 검증해서 사용자 식별

### JWT 구성
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTIzIn0.signature
│                                      │                            │
└─ Header (암호화 알고리즘)              └─ Payload (사용자 데이터)    └─ Signature (서명)
```

**JWT_SECRET_KEY**: 토큰을 암호화/검증하는 비밀 키 (최소 32자 이상 랜덤 문자열)

---

## 필요한 환경변수 설정

`backend/.env` 파일에 다음을 추가하세요:

```env
# ============================================================================
# OAuth 소셜 로그인 설정
# ============================================================================
# Google OAuth
GOOGLE_CLIENT_ID=발급받은_구글_클라이언트_ID
GOOGLE_CLIENT_SECRET=발급받은_구글_클라이언트_시크릿
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Naver OAuth
NAVER_CLIENT_ID=발급받은_네이버_클라이언트_ID
NAVER_CLIENT_SECRET=발급받은_네이버_클라이언트_시크릿
NAVER_REDIRECT_URI=http://localhost:8000/auth/naver/callback

# JWT 토큰 설정
# JWT_SECRET_KEY: 최소 32자 이상의 랜덤 문자열 (아래 명령어로 생성 가능)
# python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=여기에_랜덤한_긴_문자열_최소32자_입력
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# 프론트엔드 URL (OAuth 완료 후 리다이렉트)
FRONTEND_URL=http://localhost:5173
```

### JWT_SECRET_KEY 생성하는 방법

터미널에서 다음 명령어 실행:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

출력된 문자열을 `JWT_SECRET_KEY`에 입력하세요.

---

## 필요한 라이브러리 설치

```bash
cd backend
pip install httpx PyJWT
```

또는 `requirements.txt`에 추가:
```txt
httpx>=0.25.0
PyJWT>=2.8.0
```

---

## OAuth 라우터 구현

### 1. `backend/app/api/auth.py` 파일 생성

```python
"""
OAuth 인증 라우터

Google, Naver 소셜 로그인을 처리합니다.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
import httpx
import jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# 환경변수
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_REDIRECT_URI = os.getenv("NAVER_REDIRECT_URI", "http://localhost:8000/auth/naver/callback")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_jwt_secret_key_change_this")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# State 관리 (간단한 in-memory, 프로덕션에서는 Redis 사용 권장)
oauth_states = {}


def create_jwt_token(user_data: dict) -> str:
    """JWT 토큰 생성"""
    payload = {
        "user_id": user_data.get("id"),
        "email": user_data.get("email"),
        "name": user_data.get("name"),
        "provider": user_data.get("provider"),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


# ============================================================================
# Google OAuth
# ============================================================================

@router.get("/google")
async def google_login():
    """Google OAuth 로그인 시작"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    # CSRF 방지를 위한 state 생성
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {"provider": "google", "timestamp": datetime.utcnow()}

    # Google OAuth URL
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile&"
        f"state={state}"
    )

    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(code: str, state: str):
    """Google OAuth 콜백 처리"""
    # State 검증
    if state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")

    # State 삭제 (일회용)
    del oauth_states[state]

    try:
        # Access token 교환
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                logger.error(f"Google token error: {token_response.text}")
                raise HTTPException(status_code=400, detail="Failed to get access token")

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            # 사용자 정보 가져오기
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if user_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to get user info")

            user_info = user_response.json()

            # JWT 토큰 생성
            user_data = {
                "id": user_info.get("id"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "provider": "google",
            }

            jwt_token = create_jwt_token(user_data)

            # 프론트엔드로 리다이렉트 (토큰 포함)
            redirect_url = f"{FRONTEND_URL}?token={jwt_token}"
            return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Google OAuth error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")


# ============================================================================
# Naver OAuth
# ============================================================================

@router.get("/naver")
async def naver_login():
    """Naver OAuth 로그인 시작"""
    if not NAVER_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Naver OAuth not configured")

    # CSRF 방지를 위한 state 생성
    state = secrets.token_urlsafe(32)
    oauth_states[state] = {"provider": "naver", "timestamp": datetime.utcnow()}

    # Naver OAuth URL
    naver_auth_url = (
        f"https://nid.naver.com/oauth2.0/authorize?"
        f"client_id={NAVER_CLIENT_ID}&"
        f"redirect_uri={NAVER_REDIRECT_URI}&"
        f"response_type=code&"
        f"state={state}"
    )

    return RedirectResponse(url=naver_auth_url)


@router.get("/naver/callback")
async def naver_callback(code: str, state: str):
    """Naver OAuth 콜백 처리"""
    # State 검증
    if state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")

    # State 삭제 (일회용)
    del oauth_states[state]

    try:
        # Access token 교환
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://nid.naver.com/oauth2.0/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": NAVER_CLIENT_ID,
                    "client_secret": NAVER_CLIENT_SECRET,
                    "code": code,
                    "state": state,
                },
            )

            if token_response.status_code != 200:
                logger.error(f"Naver token error: {token_response.text}")
                raise HTTPException(status_code=400, detail="Failed to get access token")

            token_data = token_response.json()
            access_token = token_data.get("access_token")

            # 사용자 정보 가져오기
            user_response = await client.get(
                "https://openapi.naver.com/v1/nid/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if user_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to get user info")

            user_data_response = user_response.json()
            user_info = user_data_response.get("response", {})

            # JWT 토큰 생성
            user_data = {
                "id": user_info.get("id"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("profile_image"),
                "provider": "naver",
            }

            jwt_token = create_jwt_token(user_data)

            # 프론트엔드로 리다이렉트 (토큰 포함)
            redirect_url = f"{FRONTEND_URL}?token={jwt_token}"
            return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"Naver OAuth error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OAuth failed: {str(e)}")


# ============================================================================
# 토큰 검증 (옵션)
# ============================================================================

@router.get("/verify")
async def verify_token(token: str):
    """JWT 토큰 검증"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return {
            "valid": True,
            "user": {
                "id": payload.get("user_id"),
                "email": payload.get("email"),
                "name": payload.get("name"),
                "provider": payload.get("provider"),
            }
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ============================================================================
# 회원탈퇴 API
# ============================================================================

def verify_jwt_token(token: str) -> dict:
    """JWT 토큰을 검증하고 payload를 반환합니다."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.delete("/delete-account")
async def delete_account(request: Request):
    """
    회원탈퇴 API

    Authorization 헤더에 JWT 토큰을 포함하여 요청해야 합니다.
    사용자 계정 및 관련 데이터를 모두 삭제합니다.
    """
    # Authorization 헤더에서 토큰 추출
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.replace("Bearer ", "")

    # 토큰 검증
    payload = verify_jwt_token(token)
    user_id = payload.get("user_id")

    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    try:
        # TODO: 데이터베이스에서 사용자 관련 데이터 삭제
        # 1. 사용자의 모든 채팅 세션 삭제
        #    await db.execute("DELETE FROM chat_sessions WHERE user_id = ?", (user_id,))
        #
        # 2. 사용자의 모든 채팅 메시지 삭제
        #    await db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        #
        # 3. 사용자 계정 삭제
        #    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        #
        # 4. 기타 사용자 관련 데이터 삭제 (예: 파일 업로드, 즐겨찾기 등)
        #    await db.execute("DELETE FROM user_files WHERE user_id = ?", (user_id,))

        logger.info(f"User account deleted: user_id={user_id}")

        return {
            "success": True,
            "message": "회원탈퇴가 완료되었습니다."
        }

    except Exception as e:
        logger.error(f"Failed to delete account: user_id={user_id}, error={str(e)}")
        raise HTTPException(status_code=500, detail="회원탈퇴 처리 중 오류가 발생했습니다.")
```

---

## 라우터 등록

### 1. `backend/app/api/__init__.py` 수정

```python
from .health import router as health_router
from .chat import router as chat_router
from .search import router as search_router
from .case import router as case_router
from .metrics import router as metrics_router
from .auth import router as auth_router  # 추가

# ... 기존 코드 ...

__all__ = [
    # 라우터
    'health_router',
    'chat_router',
    'search_router',
    'case_router',
    'metrics_router',
    'auth_router',  # 추가
    # ... 나머지 ...
]
```

### 2. `backend/app/main.py` 수정

```python
# API 라우터 import
from app.api import (
    health_router,
    chat_router,
    search_router,
    case_router,
    metrics_router,
    auth_router,  # 추가
)

# ... 기존 코드 ...

# 라우터 등록
app.include_router(health_router)
app.include_router(auth_router)  # 추가
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(case_router)
app.include_router(metrics_router)
```

---

## 테스트

### 1. 백엔드 서버 실행

```bash
# Docker 사용 시
docker-compose down
docker-compose up --build

# 로컬 실행 시
cd backend
python -m uvicorn app.main:app --reload
```

### 2. API 문서 확인

브라우저에서 접속: http://localhost:8000/docs

`/auth/google`과 `/auth/naver` 엔드포인트가 표시되어야 합니다.

### 3. 프론트엔드에서 테스트

1. 프론트엔드 실행: `npm run dev`
2. "1초 만에 시작하기" 버튼 클릭
3. "Google로 계속하기" 또는 "네이버로 계속하기" 클릭
4. 소셜 로그인 후 프론트엔드로 돌아오며 URL에 `?token=...` 파라미터가 붙음

### 4. 토큰 검증 테스트

```bash
curl "http://localhost:8000/auth/verify?token=YOUR_JWT_TOKEN"
```

---

## 회원탈퇴 API 사용법

### API 명세

**엔드포인트**: `DELETE /auth/delete-account`

**헤더**:
```
Authorization: Bearer {JWT_TOKEN}
```

**응답 성공 (200)**:
```json
{
  "success": true,
  "message": "회원탈퇴가 완료되었습니다."
}
```

**응답 실패 (401, 500)**:
```json
{
  "detail": "에러 메시지"
}
```

### 프론트엔드 연동 예시

프론트엔드의 `MyPage.tsx`에서 다음과 같이 호출합니다:

```typescript
const handleDeleteAccount = async () => {
  const token = useAuthStore.getState().token;

  if (!token) {
    alert('로그인이 필요합니다.');
    return;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/auth/delete-account`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('회원탈퇴 처리 중 오류가 발생했습니다.');
    }

    const data = await response.json();

    // 로그아웃 처리
    logout();
    navigate(ROUTES.HOME);
    alert(data.message);

  } catch (error) {
    console.error('Delete account error:', error);
    alert('회원탈퇴 처리 중 오류가 발생했습니다.');
  }
};
```

### 백엔드 구현 시 주의사항

1. **데이터베이스 트랜잭션 사용**: 모든 삭제 작업을 하나의 트랜잭션으로 묶어서 처리
2. **외래키 제약조건 고려**: 삭제 순서를 올바르게 설정 (자식 데이터 → 부모 데이터)
3. **소프트 삭제 옵션**: 완전 삭제 대신 `is_deleted` 플래그를 사용하여 복구 가능하게 구현 가능
4. **로그 남기기**: 감사(audit) 목적으로 회원탈퇴 로그 저장
5. **개인정보 보호법 준수**: 관련 법규에 따라 데이터 삭제 정책 수립

### 데이터베이스 예시 (PostgreSQL)

```sql
-- 트랜잭션으로 안전하게 삭제
BEGIN;

-- 1. 채팅 메시지 삭제
DELETE FROM chat_messages WHERE session_id IN (
    SELECT id FROM chat_sessions WHERE user_id = :user_id
);

-- 2. 채팅 세션 삭제
DELETE FROM chat_sessions WHERE user_id = :user_id;

-- 3. 사용자 파일 삭제
DELETE FROM user_files WHERE user_id = :user_id;

-- 4. 사용자 계정 삭제
DELETE FROM users WHERE id = :user_id;

COMMIT;
```

---

## 마이페이지 API

마이페이지에서 사용자의 게시글 및 댓글 정보를 조회하는 API가 필요합니다.

### 1. 내 게시글 목록 조회 API

**엔드포인트**: `GET /api/users/me/posts`

**헤더**:
```
Authorization: Bearer {JWT_TOKEN}
```

**쿼리 파라미터**:
- `page` (optional): 페이지 번호 (기본값: 1)
- `limit` (optional): 페이지당 항목 수 (기본값: 10)

**응답 성공 (200)**:
```json
{
  "posts": [
    {
      "id": 4,
      "category": "무엇이든/물어보세요",
      "title": "환불 절차가 궁금합니다",
      "date": "2025.12.17",
      "views": 567,
      "likes": 89,
      "comments": 34
    },
    {
      "id": 3,
      "category": "소비자/꿀팁/노하우",
      "subCategory": null,
      "title": "소비자분쟁 조정 신청할 때 꼭 알아야 할 3가지",
      "date": "2025.12.18",
      "views": 456,
      "likes": 78,
      "comments": 23
    }
  ],
  "total": 2,
  "page": 1,
  "totalPages": 1
}
```

### 2. 내가 댓글을 단 게시글 목록 조회 API

**엔드포인트**: `GET /api/users/me/commented-posts`

**헤더**:
```
Authorization: Bearer {JWT_TOKEN}
```

**쿼리 파라미터**:
- `page` (optional): 페이지 번호 (기본값: 1)
- `limit` (optional): 페이지당 항목 수 (기본값: 10)

**응답 성공 (200)**:
```json
{
  "posts": [
    {
      "id": 1,
      "category": "분쟁해결사례/공유",
      "title": "당근마켓 사기 피해 복구 성공했습니다",
      "date": "2025.12.20",
      "views": 234,
      "likes": 45,
      "comments": 12,
      "myCommentDate": "2025.12.21",
      "myCommentContent": "정말 도움이 되는 정보네요. 감사합니다!"
    },
    {
      "id": 6,
      "category": "소비자/꿀팁/노하우",
      "title": "전자제품 AS 받을 때 꼭 챙겨야 할 것들",
      "date": "2025.12.15",
      "views": 523,
      "likes": 92,
      "comments": 19,
      "myCommentDate": "2025.12.16",
      "myCommentContent": "유용한 팁 감사합니다."
    }
  ],
  "total": 2,
  "page": 1,
  "totalPages": 1
}
```

### 3. 백엔드 구현 예시 (FastAPI)

```python
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/api/users", tags=["User"])

def verify_jwt_token(token: str) -> dict:
    """JWT 토큰 검증 (앞서 구현한 함수 재사용)"""
    # ... JWT 검증 로직
    pass

def get_current_user(request: Request):
    """현재 로그인한 사용자 정보 가져오기"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = auth_header.replace("Bearer ", "")
    payload = verify_jwt_token(token)
    return payload


@router.get("/me/posts")
async def get_my_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    내가 작성한 게시글 목록 조회
    """
    user_id = current_user.get("user_id")

    # TODO: 데이터베이스에서 사용자의 게시글 조회
    # offset = (page - 1) * limit
    #
    # query = """
    #     SELECT
    #         p.id,
    #         p.category,
    #         p.sub_category,
    #         p.title,
    #         p.created_at as date,
    #         p.views,
    #         p.likes,
    #         COUNT(c.id) as comments
    #     FROM posts p
    #     LEFT JOIN comments c ON p.id = c.post_id
    #     WHERE p.user_id = :user_id AND p.is_deleted = false
    #     GROUP BY p.id
    #     ORDER BY p.created_at DESC
    #     LIMIT :limit OFFSET :offset
    # """
    #
    # posts = await db.fetch_all(query, {"user_id": user_id, "limit": limit, "offset": offset})
    #
    # total_query = "SELECT COUNT(*) FROM posts WHERE user_id = :user_id AND is_deleted = false"
    # total = await db.fetch_val(total_query, {"user_id": user_id})

    return {
        "posts": [],  # 실제 데이터베이스에서 조회한 결과
        "total": 0,
        "page": page,
        "totalPages": 0
    }


@router.get("/me/commented-posts")
async def get_my_commented_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    내가 댓글을 단 게시글 목록 조회
    """
    user_id = current_user.get("user_id")

    # TODO: 데이터베이스에서 사용자가 댓글을 단 게시글 조회
    # offset = (page - 1) * limit
    #
    # query = """
    #     SELECT DISTINCT
    #         p.id,
    #         p.category,
    #         p.title,
    #         p.created_at as date,
    #         p.views,
    #         p.likes,
    #         COUNT(DISTINCT c2.id) as comments,
    #         MAX(c1.created_at) as myCommentDate,
    #         (
    #             SELECT content
    #             FROM comments
    #             WHERE post_id = p.id AND user_id = :user_id
    #             ORDER BY created_at DESC
    #             LIMIT 1
    #         ) as myCommentContent
    #     FROM posts p
    #     INNER JOIN comments c1 ON p.id = c1.post_id AND c1.user_id = :user_id
    #     LEFT JOIN comments c2 ON p.id = c2.post_id
    #     WHERE p.is_deleted = false AND c1.is_deleted = false
    #     GROUP BY p.id
    #     ORDER BY MAX(c1.created_at) DESC
    #     LIMIT :limit OFFSET :offset
    # """
    #
    # posts = await db.fetch_all(query, {"user_id": user_id, "limit": limit, "offset": offset})
    #
    # total_query = """
    #     SELECT COUNT(DISTINCT p.id)
    #     FROM posts p
    #     INNER JOIN comments c ON p.id = c.post_id
    #     WHERE c.user_id = :user_id AND p.is_deleted = false AND c.is_deleted = false
    # """
    # total = await db.fetch_val(total_query, {"user_id": user_id})

    return {
        "posts": [],  # 실제 데이터베이스에서 조회한 결과
        "total": 0,
        "page": page,
        "totalPages": 0
    }
```

### 4. 프론트엔드 연동 예시

```typescript
// 내 게시글 목록 가져오기
const fetchMyPosts = async (page: number = 1) => {
  const token = useAuthStore.getState().token;
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  try {
    const response = await fetch(`${API_BASE_URL}/api/users/me/posts?page=${page}&limit=10`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('게시글 조회 실패');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Fetch my posts error:', error);
    return { posts: [], total: 0, page: 1, totalPages: 0 };
  }
};

// 내가 댓글을 단 게시글 목록 가져오기
const fetchMyCommentedPosts = async (page: number = 1) => {
  const token = useAuthStore.getState().token;
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  try {
    const response = await fetch(`${API_BASE_URL}/api/users/me/commented-posts?page=${page}&limit=10`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      throw new Error('댓글 단 게시글 조회 실패');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Fetch commented posts error:', error);
    return { posts: [], total: 0, page: 1, totalPages: 0 };
  }
};
```

### 5. 데이터베이스 스키마 예시

```sql
-- 게시글 테이블
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    category VARCHAR(100) NOT NULL,
    sub_category VARCHAR(100),  -- 분쟁해결사례 공유의 세부 카테고리
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    views INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 댓글 테이블
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,
    likes INTEGER DEFAULT 0,
    is_deleted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 추가 (성능 최적화)
CREATE INDEX idx_posts_user_id ON posts(user_id);
CREATE INDEX idx_comments_user_id ON comments(user_id);
CREATE INDEX idx_comments_post_id ON comments(post_id);
```

### 6. 구현 시 주의사항

1. **페이지네이션**: 10개씩 페이지네이션 처리 필수
2. **성능 최적화**:
   - 인덱스 활용
   - 필요한 컬럼만 SELECT
   - JOIN 최소화
3. **삭제된 데이터 제외**: `is_deleted = false` 조건 필수
4. **정렬**:
   - 내 게시글: 최신 작성일순 (`created_at DESC`)
   - 댓글 단 게시글: 최근 댓글 작성일순 (`MAX(comment.created_at) DESC`)
5. **권한 검증**: JWT 토큰을 통한 사용자 인증 필수

---

## 추가 고려사항

### 1. 데이터베이스에 사용자 저장

현재는 JWT에만 사용자 정보를 저장하지만, 실제 운영 환경에서는:
- PostgreSQL에 users 테이블 생성
- 소셜 로그인 시 사용자 정보 저장 또는 업데이트
- JWT에는 user_id만 저장

### 2. Refresh Token 구현

- Access Token 만료 시간을 짧게 (15분)
- Refresh Token으로 새 Access Token 발급
- 보안 강화

### 3. 프로덕션 배포 시

- `JWT_SECRET_KEY`: 강력한 랜덤 문자열로 변경
- `FRONTEND_URL`: 실제 도메인으로 변경
- Google/Naver 개발자 콘솔에서 프로덕션 리다이렉트 URI 추가
- State 저장소를 Redis로 변경 (in-memory 대신)

---

## 문의

구현 중 문제가 있으면 프론트엔드 담당자에게 연락하세요.

**프론트엔드 준비사항**: Google과 Naver OAuth 클릭 핸들러는 이미 구현되어 있습니다.
