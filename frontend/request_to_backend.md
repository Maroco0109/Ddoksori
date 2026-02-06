# Backend API 요청사항 문서

프론트엔드에서 필요한 Backend API 구현 요청사항을 정리한 문서입니다.

## 목차

### Part 1: 소셜 로그인 & 사용자 인증
1. [JWT란?](#1-jwt란)
2. [환경변수 설정](#2-환경변수-설정)
3. [필요한 라이브러리 설치](#3-필요한-라이브러리-설치)
4. [OAuth 라우터 구현](#4-oauth-라우터-구현)
5. [회원탈퇴 API](#5-회원탈퇴-api)
6. [마이페이지 API](#6-마이페이지-api)

### Part 2: 관리자 기능
7. [관리자 인증 API](#7-관리자-인증-api)
8. [관리자 대시보드 API](#8-관리자-대시보드-api)
9. [게시글 관리 API](#9-게시글-관리-api)
10. [댓글 관리 API](#10-댓글-관리-api)
11. [회원 관리 API](#11-회원-관리-api)
12. [신고 관리 API](#12-신고-관리-api)

### Part 3: 공통 사항
13. [보안 및 인증](#13-보안-및-인증)
14. [에러 처리](#14-에러-처리)
15. [추가 요구사항](#15-추가-요구사항)
16. [구현 우선순위](#16-구현-우선순위)

---

# Part 1: 소셜 로그인 & 사용자 인증

## 1. JWT란?

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

## 2. 환경변수 설정

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

## 3. 필요한 라이브러리 설치

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

## 4. OAuth 라우터 구현

### 4.1. `backend/app/api/auth.py` 파일 생성

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


def verify_jwt_token(token: str) -> dict:
    """JWT 토큰을 검증하고 payload를 반환합니다."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


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
    payload = verify_jwt_token(token)
    return {
        "valid": True,
        "user": {
            "id": payload.get("user_id"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "provider": payload.get("provider"),
        }
    }
```

### 4.2. 라우터 등록

**`backend/app/api/__init__.py` 수정**

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

**`backend/app/main.py` 수정**

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

### 4.3. 테스트

**1. 백엔드 서버 실행**

```bash
# Docker 사용 시
docker-compose down
docker-compose up --build

# 로컬 실행 시
cd backend
python -m uvicorn app.main:app --reload
```

**2. API 문서 확인**

브라우저에서 접속: http://localhost:8000/docs

`/auth/google`과 `/auth/naver` 엔드포인트가 표시되어야 합니다.

**3. 프론트엔드에서 테스트**

1. 프론트엔드 실행: `npm run dev`
2. "1초 만에 시작하기" 버튼 클릭
3. "Google로 계속하기" 또는 "네이버로 계속하기" 클릭
4. 소셜 로그인 후 프론트엔드로 돌아오며 URL에 `?token=...` 파라미터가 붙음

**4. 토큰 검증 테스트**

```bash
curl "http://localhost:8000/auth/verify?token=YOUR_JWT_TOKEN"
```

---

## 5. 회원탈퇴 API

### 5.1. API 명세

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

### 5.2. 백엔드 구현

`backend/app/api/auth.py`에 추가:

```python
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

### 5.3. 백엔드 구현 시 주의사항

1. **데이터베이스 트랜잭션 사용**: 모든 삭제 작업을 하나의 트랜잭션으로 묶어서 처리
2. **외래키 제약조건 고려**: 삭제 순서를 올바르게 설정 (자식 데이터 → 부모 데이터)
3. **소프트 삭제 옵션**: 완전 삭제 대신 `is_deleted` 플래그를 사용하여 복구 가능하게 구현 가능
4. **로그 남기기**: 감사(audit) 목적으로 회원탈퇴 로그 저장
5. **개인정보 보호법 준수**: 관련 법규에 따라 데이터 삭제 정책 수립

### 5.4. 데이터베이스 예시 (PostgreSQL)

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

## 6. 마이페이지 API

마이페이지에서 사용자의 게시글 및 댓글 정보를 조회하는 API가 필요합니다.

### 6.1. 내 게시글 목록 조회 API

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

### 6.2. 내가 댓글을 단 게시글 목록 조회 API

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

### 6.3. 백엔드 구현 예시 (FastAPI)

```python
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter(prefix="/api/users", tags=["User"])

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

### 6.4. 데이터베이스 스키마 예시

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

### 6.5. 구현 시 주의사항

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

# Part 2: 관리자 기능

## 7. 관리자 인증 API

### 7.1. 관리자 로그인

**엔드포인트**: `POST /api/admin/login`

**Request Body**:
```json
{
  "username": "admin_id",
  "password": "encrypted_password"
}
```

**Response**:
```json
{
  "admin": {
    "id": "admin_uuid",
    "username": "admin_name",
    "email": "admin@example.com",
    "role": "admin" | "super_admin"
  },
  "token": "jwt_token"
}
```

**설명**:
- 관리자 ID와 비밀번호를 받아 인증 처리
- 비밀번호는 암호화되어 전송됨
- 성공 시 JWT 토큰 발급 (role 필드에 "admin" 포함)
- 실패 시 401 Unauthorized 반환

---

## 8. 관리자 대시보드 API

### 8.1. 통계 데이터 조회

**엔드포인트**: `GET /api/admin/stats`

**Headers**: `Authorization: Bearer {admin_token}`

**Response**:
```json
{
  "totalUsers": 1234,
  "totalPosts": 5678,
  "totalComments": 9012,
  "pendingReports": 5,
  "suspendedUsers": 3,
  "todayNewUsers": 12,
  "todayNewPosts": 34
}
```

**설명**: 관리자 대시보드에 표시할 통계 데이터 반환

---

## 9. 게시글 관리 API

### 9.1. 게시글 목록 조회 (관리자용)

**엔드포인트**: `GET /api/admin/posts`

**Headers**: `Authorization: Bearer {admin_token}`

**Query Parameters**:
- `searchType`: "title" | "author" | "title_author" | "keyword"
- `searchKeyword`: string
- `category`: string (optional)
- `isPublic`: boolean (optional)
- `page`: number (default: 1)
- `limit`: number (default: 20)

**Response**:
```json
{
  "data": [
    {
      "id": 1,
      "category": "카테고리",
      "title": "게시글 제목",
      "content": "게시글 내용",
      "author": "작성자명",
      "authorId": "user_uuid",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-02T00:00:00Z",
      "views": 100,
      "likes": 10,
      "commentsCount": 5,
      "isPublic": true,
      "isDeleted": false
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 10,
    "totalItems": 200,
    "itemsPerPage": 20
  }
}
```

### 9.2. 게시글 상세 조회 (관리자용)

**엔드포인트**: `GET /api/admin/posts/{postId}`

**Headers**: `Authorization: Bearer {admin_token}`

**Response**: 위와 동일한 게시글 객체

### 9.3. 게시글 공개/비공개 전환

**엔드포인트**: `PUT /api/admin/posts/{postId}/visibility`

**Headers**: `Authorization: Bearer {admin_token}`

**Request Body**:
```json
{
  "isPublic": false
}
```

**Response**:
```json
{
  "success": true,
  "message": "게시글이 비공개 처리되었습니다."
}
```

**설명**: 정책 위반 게시글을 비공개 처리

### 9.4. 게시글 삭제

**엔드포인트**: `DELETE /api/admin/posts/{postId}`

**Headers**: `Authorization: Bearer {admin_token}`

**Response**:
```json
{
  "success": true,
  "message": "게시글이 삭제되었습니다."
}
```

**설명**: 정책 위반 게시글을 완전 삭제 (soft delete 권장)

### 9.5. 공지사항 작성

**엔드포인트**: `POST /api/admin/posts/notice`

**Headers**: `Authorization: Bearer {admin_token}`

**Request Body**:
```json
{
  "title": "공지사항 제목",
  "content": "공지사항 내용",
  "isPinned": true
}
```

**Response**:
```json
{
  "success": true,
  "postId": 123,
  "message": "공지사항이 작성되었습니다."
}
```

---

## 10. 댓글 관리 API

### 10.1. 댓글 목록 조회 (관리자용)

**엔드포인트**: `GET /api/admin/comments`

**Headers**: `Authorization: Bearer {admin_token}`

**Query Parameters**:
- `postId`: number (optional)
- `page`: number
- `limit`: number

**Response**:
```json
{
  "data": [
    {
      "id": 1,
      "postId": 123,
      "content": "댓글 내용",
      "author": "작성자명",
      "authorId": "user_uuid",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-02T00:00:00Z",
      "isPublic": true,
      "isDeleted": false
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 5,
    "totalItems": 100,
    "itemsPerPage": 20
  }
}
```

### 10.2. 댓글 공개/비공개 전환

**엔드포인트**: `PUT /api/admin/comments/{commentId}/visibility`

**Headers**: `Authorization: Bearer {admin_token}`

**Request Body**:
```json
{
  "isPublic": false
}
```

### 10.3. 댓글 삭제

**엔드포인트**: `DELETE /api/admin/comments/{commentId}`

**Headers**: `Authorization: Bearer {admin_token}`

---

## 11. 회원 관리 API

### 11.1. 회원 목록 조회

**엔드포인트**: `GET /api/admin/users`

**Headers**: `Authorization: Bearer {admin_token}`

**Query Parameters**:
- `searchKeyword`: string (이름 또는 이메일)
- `status`: "active" | "suspended" | "banned"
- `provider`: "google" | "naver"
- `page`: number
- `limit`: number

**Response**:
```json
{
  "data": [
    {
      "id": "user_uuid",
      "name": "사용자명",
      "email": "user@example.com",
      "provider": "google",
      "createdAt": "2024-01-01T00:00:00Z",
      "lastLoginAt": "2024-01-15T00:00:00Z",
      "status": "active",
      "postCount": 10,
      "commentCount": 50,
      "reportCount": 0
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 10,
    "totalItems": 200,
    "itemsPerPage": 20
  }
}
```

### 11.2. 회원 상세 조회

**엔드포인트**: `GET /api/admin/users/{userId}`

**Headers**: `Authorization: Bearer {admin_token}`

**Response**: 위와 동일한 사용자 객체

### 11.3. 회원 상태 변경 (계정 정지/해제)

**엔드포인트**: `PUT /api/admin/users/{userId}/status`

**Headers**: `Authorization: Bearer {admin_token}`

**Request Body**:
```json
{
  "status": "suspended" | "active" | "banned"
}
```

**Response**:
```json
{
  "success": true,
  "message": "사용자 상태가 변경되었습니다."
}
```

**설명**:
- `active`: 정상 활성 상태
- `suspended`: 일시 정지 (재활성화 가능)
- `banned`: 영구 정지

---

## 12. 신고 관리 API

### 12.1. 신고 목록 조회

**엔드포인트**: `GET /api/admin/reports`

**Headers**: `Authorization: Bearer {admin_token}`

**Query Parameters**:
- `type`: "post" | "comment"
- `status`: "pending" | "reviewed" | "resolved" | "rejected"
- `page`: number
- `limit`: number

**Response**:
```json
{
  "data": [
    {
      "id": 1,
      "type": "post",
      "targetId": 123,
      "targetTitle": "게시글 제목",
      "targetContent": "게시글 또는 댓글 내용",
      "reporterId": "user_uuid",
      "reporterName": "신고자명",
      "reason": "욕설 및 비방",
      "createdAt": "2024-01-01T00:00:00Z",
      "status": "pending",
      "adminNote": null
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 2,
    "totalItems": 40,
    "itemsPerPage": 20
  }
}
```

### 12.2. 신고 상세 조회

**엔드포인트**: `GET /api/admin/reports/{reportId}`

**Headers**: `Authorization: Bearer {admin_token}`

**Response**: 위와 동일한 신고 객체

### 12.3. 신고 처리 상태 변경

**엔드포인트**: `PUT /api/admin/reports/{reportId}/status`

**Headers**: `Authorization: Bearer {admin_token}`

**Request Body**:
```json
{
  "status": "reviewed" | "resolved" | "rejected",
  "adminNote": "처리 내용 또는 사유"
}
```

**Response**:
```json
{
  "success": true,
  "message": "신고 처리 상태가 변경되었습니다."
}
```

**설명**:
- `pending`: 대기 중
- `reviewed`: 검토 완료
- `resolved`: 처리 완료 (조치 완료)
- `rejected`: 기각됨

---

# Part 3: 공통 사항

## 13. 보안 및 인증

### 13.1. 관리자 권한 확인

- 모든 `/api/admin/*` 엔드포인트는 관리자 권한이 필요합니다.
- JWT 토큰의 `role` 필드로 관리자 여부를 확인해야 합니다.
- 일반 사용자가 접근 시 `403 Forbidden` 반환

**구현 예시**:

```python
def verify_admin_token(request: Request):
    """관리자 토큰 검증"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = auth_header.replace("Bearer ", "")
    payload = verify_jwt_token(token)

    # 관리자 권한 확인
    if payload.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")

    return payload
```

### 13.2. 비밀번호 암호화

- 관리자 로그인 시 비밀번호는 클라이언트에서 전송되기 전에 암호화됩니다.
- 서버에서는 암호화된 비밀번호를 복호화하여 검증해야 합니다.
- 또는 HTTPS를 사용하고 서버에서 해싱 처리하는 방식도 가능합니다.

### 13.3. 감사 로그

- 관리자의 모든 작업(게시글 삭제, 사용자 정지 등)은 감사 로그에 기록되어야 합니다.
- 로그에는 다음 정보가 포함되어야 합니다:
  - 관리자 ID
  - 작업 유형
  - 대상 (게시글 ID, 사용자 ID 등)
  - 작업 시간
  - 작업 사유 (선택적)

**데이터베이스 스키마 예시**:

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    admin_id VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,  -- 'delete_post', 'suspend_user', etc.
    target_type VARCHAR(50),  -- 'post', 'user', 'comment'
    target_id INTEGER,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 14. 에러 처리

모든 API는 다음과 같은 에러 형식을 사용합니다:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "에러 메시지"
  }
}
```

주요 에러 코드:
- `UNAUTHORIZED`: 인증 실패 (401)
- `FORBIDDEN`: 권한 없음 (403)
- `NOT_FOUND`: 리소스를 찾을 수 없음 (404)
- `VALIDATION_ERROR`: 입력 데이터 유효성 검증 실패 (400)
- `INTERNAL_ERROR`: 서버 내부 오류 (500)

---

## 15. 추가 요구사항

### 15.1. 페이지네이션

- 모든 목록 조회 API는 페이지네이션을 지원해야 합니다.
- Response에 다음 메타데이터 포함:

```json
{
  "data": [...],
  "pagination": {
    "currentPage": 1,
    "totalPages": 10,
    "totalItems": 200,
    "itemsPerPage": 20
  }
}
```

### 15.2. 정렬 및 필터링

- 게시글, 댓글, 회원 목록은 정렬 및 필터링을 지원해야 합니다.
- Query Parameters에 `sortBy`, `sortOrder` 추가 가능

### 15.3. CORS 설정

- Frontend에서 API 호출 시 CORS 에러가 발생하지 않도록 설정 필요

**FastAPI 설정 예시**:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 프론트엔드 URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 15.4. 데이터베이스에 사용자 저장

현재는 JWT에만 사용자 정보를 저장하지만, 실제 운영 환경에서는:
- PostgreSQL에 users 테이블 생성
- 소셜 로그인 시 사용자 정보 저장 또는 업데이트
- JWT에는 user_id만 저장

### 15.5. Refresh Token 구현

- Access Token 만료 시간을 짧게 (15분)
- Refresh Token으로 새 Access Token 발급
- 보안 강화

### 15.6. 프로덕션 배포 시

- `JWT_SECRET_KEY`: 강력한 랜덤 문자열로 변경
- `FRONTEND_URL`: 실제 도메인으로 변경
- Google/Naver 개발자 콘솔에서 프로덕션 리다이렉트 URI 추가
- State 저장소를 Redis로 변경 (in-memory 대신)

---

## 16. 구현 우선순위

### 1. 필수 (상 중요도)
- **소셜 로그인**: Google, Naver OAuth 구현
- **JWT 토큰 인증**: 토큰 생성 및 검증
- **관리자 로그인/로그아웃**
- **게시글 조회/삭제/비공개 처리**
- **회원 목록 조회 및 계정 정지/해제**
- **마이페이지 API**: 내 게시글, 댓글 단 게시글 조회

### 2. 중요 (중 중요도)
- **회원탈퇴 API**
- **공지사항 작성**
- **댓글 조회/삭제/비공개 처리**
- **통계 데이터 조회**

### 3. 선택적 (하 중요도)
- **신고 관리 기능**
- **감사 로그 시스템**
- **Refresh Token 구현**

---

## 17. 참고사항

- 모든 날짜/시간은 ISO 8601 형식 (UTC) 사용
- 모든 텍스트 필드는 XSS 방지를 위해 이스케이프 처리 필요
- 관리자 작업은 트랜잭션으로 처리하여 일관성 보장
- Rate limiting을 적용하여 API 남용 방지

---

## 문의

구현 중 문제가 있으면 프론트엔드 담당자에게 연락하세요.

**프론트엔드 준비사항**:
- Google과 Naver OAuth 클릭 핸들러는 이미 구현되어 있습니다.
- 관리자 페이지 UI는 구현되어 있으며 API 연동만 필요합니다.
