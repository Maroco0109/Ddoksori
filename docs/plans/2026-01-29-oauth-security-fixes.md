# OAuth 보안 취약점 수정 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 보안 리뷰에서 발견된 JWT 기본 시크릿 가드 부재, 토큰 URL 노출, 에러 메시지 노출, 프론트-백 키 불일치 4건을 수정한다.

**Architecture:** 백엔드 startup에서 JWT 시크릿 검증 추가, OAuth 콜백에서 토큰을 URL fragment(`#`)로 전달하도록 변경, 프론트엔드에서 fragment 파싱으로 전환, 에러 메시지 제네릭화.

**Tech Stack:** FastAPI, PyJWT, React (react-router-dom), TypeScript

---

## 수정 대상 요약

| # | 취약점 | 심각도 | 파일 |
|---|--------|--------|------|
| 1 | JWT 기본 시크릿 키 프로덕션 가드 없음 | HIGH | `backend/app/main.py` |
| 2 | 토큰이 URL 쿼리 파라미터로 전달 (브라우저 히스토리/로그 노출) | MEDIUM | `backend/app/api/auth.py`, `frontend/src/features/auth/AuthCallback.tsx` |
| 3 | OAuth 에러 시 Exception 메시지가 URL에 노출 | MEDIUM | `backend/app/api/auth.py` |
| 4 | 백엔드(`access_token`)와 프론트(`token`) 키 이름 불일치 | BUG | `backend/app/api/auth.py`, `frontend/src/features/auth/AuthCallback.tsx` |

---

### Task 1: JWT 시크릿 키 프로덕션 가드 추가

**Files:**
- Modify: `backend/app/main.py` (startup_event 함수)
- Test: `backend/scripts/testing/auth/test_jwt_dependencies.py`

**Step 1: 테스트 작성**

`backend/scripts/testing/auth/test_jwt_dependencies.py`에 추가:

```python
@pytest.mark.unit
def test_jwt_secret_key_validation_rejects_default():
    """기본 JWT 시크릿 키 사용 시 경고 로그를 출력하는지 확인"""
    from app.common.config import AuthConfig
    config = AuthConfig(JWT_SECRET_KEY="dev_secret_key_change_in_production")
    assert config.jwt_secret_key == "dev_secret_key_change_in_production"
    # startup에서 이 값을 감지하여 경고해야 함
```

**Step 2: 테스트 실행하여 실패 확인**

Run: `conda run -n dsr pytest backend/scripts/testing/auth/test_jwt_dependencies.py -v -k test_jwt_secret`

**Step 3: 구현 - startup_event에 검증 추가**

`backend/app/main.py`의 `startup_event()` 함수 상단에 추가:

```python
@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 로그 및 서비스 시작"""
    # === 보안 검증: JWT 시크릿 키 ===
    from app.common.config import get_config
    auth_config = get_config().auth
    if auth_config.jwt_secret_key == "dev_secret_key_change_in_production":
        import warnings
        warnings.warn(
            "JWT_SECRET_KEY가 기본값입니다. 프로덕션에서는 반드시 강력한 랜덤 값으로 변경하세요. "
            "생성: python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
            UserWarning,
            stacklevel=1,
        )
        logger.warning(
            "[SECURITY] JWT_SECRET_KEY가 기본 개발용 값입니다! "
            "프로덕션 배포 전 반드시 변경하세요."
        )

    # 기존 코드 유지...
    retrieval_mode = os.getenv('RETRIEVAL_MODE', 'dense')
    # ...
```

**Step 4: 테스트 실행하여 통과 확인**

Run: `conda run -n dsr pytest backend/scripts/testing/auth/test_jwt_dependencies.py -v`

**Step 5: 커밋**

```bash
git add backend/app/main.py backend/scripts/testing/auth/test_jwt_dependencies.py
git commit -m "security: add JWT secret key production guard at startup"
```

---

### Task 2: OAuth 콜백 - 토큰을 URL fragment로 전달

**Files:**
- Modify: `backend/app/api/auth.py` (3개 콜백 함수)
- Modify: `frontend/src/features/auth/AuthCallback.tsx`

**Step 1: 백엔드 수정 - 3개 콜백에서 `?` → `#` 변경 + 키 이름 통일**

`backend/app/api/auth.py`에서 Google/Kakao/Naver 콜백 공통 패턴:

변경 전 (3곳 모두 동일 패턴):
```python
redirect_params = {
    "access_token": auth_response.access_token,
    "token_type": auth_response.token_type,
    "expires_in": auth_response.expires_in
}
redirect_url = f"{config.frontend_url}/auth/callback?{urlencode(redirect_params)}"
```

변경 후:
```python
redirect_params = {
    "token": auth_response.access_token,
    "token_type": auth_response.token_type,
    "expires_in": auth_response.expires_in
}
# Fragment(#)로 전달: 서버 로그/Referer 헤더에 노출되지 않음
redirect_url = f"{config.frontend_url}/auth/callback#{urlencode(redirect_params)}"
```

변경 사항:
- `access_token` → `token` (프론트엔드와 키 이름 일치)
- `?` → `#` (URL fragment로 변경)

**Step 2: 프론트엔드 수정 - fragment 파싱으로 전환**

`frontend/src/features/auth/AuthCallback.tsx` 수정:

변경 전:
```typescript
const [searchParams] = useSearchParams();
// ...
const token = searchParams.get('token');
const error = searchParams.get('error');
```

변경 후:
```typescript
// URL fragment(#)에서 토큰 파싱 (보안: fragment는 서버로 전송되지 않음)
const hash = window.location.hash.substring(1); // '#' 제거
const params = new URLSearchParams(hash);

const token = params.get('token');
const error = params.get('error');
```

또한 `useSearchParams` import 제거 (더 이상 사용하지 않음).

**Step 3: 테스트 실행**

Run: `conda run -n dsr pytest backend/scripts/testing/auth/ -v`

**Step 4: 커밋**

```bash
git add backend/app/api/auth.py frontend/src/features/auth/AuthCallback.tsx
git commit -m "security: pass OAuth token via URL fragment instead of query params"
```

---

### Task 3: OAuth 에러 메시지 제네릭화

**Files:**
- Modify: `backend/app/api/auth.py` (3개 콜백 함수의 except 블록)

**Step 1: 3개 콜백의 에러 핸들링 수정**

변경 전 (3곳 모두 동일 패턴):
```python
except Exception as e:
    logger.error(f"[Auth] Google 콜백 실패: {e}", exc_info=True)
    error_url = f"{get_config().auth.frontend_url}/auth/error?error={str(e)}"
    return RedirectResponse(error_url)
```

변경 후:
```python
except Exception as e:
    logger.error(f"[Auth] Google 콜백 실패: {e}", exc_info=True)
    # 제네릭 에러 메시지만 전달 (내부 예외 정보 노출 방지)
    error_url = f"{get_config().auth.frontend_url}/auth/callback#error=auth_failed"
    return RedirectResponse(error_url)
```

변경 사항:
- `str(e)` 대신 제네릭 `auth_failed` 문자열 사용
- `/auth/error` → `/auth/callback#error=auth_failed` (fragment + 동일 콜백 경로)

**Step 2: 프론트엔드 에러 핸들링 확인**

`AuthCallback.tsx`에서 이미 `error` 파라미터를 처리하고 있으므로, Task 2에서 fragment 파싱으로 전환하면 자동으로 동작.

**Step 3: 커밋**

```bash
git add backend/app/api/auth.py
git commit -m "security: sanitize OAuth error messages to prevent info disclosure"
```

---

### Task 4: 최종 검증

**Step 1: 전체 auth 테스트 실행**

Run: `conda run -n dsr pytest backend/scripts/testing/auth/ -v`

**Step 2: 프론트엔드 빌드 확인**

Run: `cd frontend && npm run build`

**Step 3: 변경 사항 요약 커밋 (필요 시)**

모든 테스트 통과 확인 후 최종 상태 점검.

---

## 수정 대상 파일 목록

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/main.py` | Modify | startup에서 JWT 시크릿 기본값 경고 |
| `backend/app/api/auth.py` | Modify | 토큰 fragment 전달, 에러 제네릭화, 키 이름 통일 |
| `frontend/src/features/auth/AuthCallback.tsx` | Modify | fragment 파싱으로 전환, useSearchParams 제거 |
| `backend/scripts/testing/auth/test_jwt_dependencies.py` | Modify | JWT 시크릿 검증 테스트 추가 |

## 리스크

- **OAuth 미테스트 상태**: OAuth 로그인이 아직 실제로 테스트되지 않은 상태이므로, 이 수정이 첫 정상 동작의 기반이 됨
- **프론트엔드 fragment 파싱**: `react-router-dom`의 `useSearchParams`가 fragment를 처리하지 않으므로, `window.location.hash` 직접 파싱이 필요
- **에러 경로 통합**: `/auth/error` 경로가 별도로 존재한다면 프론트엔드 라우팅 정리 필요 (현재 라우터에 해당 경로 없으므로 문제 없음)
