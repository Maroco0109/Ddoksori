# OAuth 소셜 로그인 설정 가이드

**작업 ID**: `feature/34-e2e`
**최종 업데이트**: 2026-01-28

---

## 📋 개요

이 가이드는 DDOKSORI 챗봇에 Google, Kakao, Naver 소셜 로그인을 설정하는 방법을 단계별로 설명합니다.

### 지원하는 OAuth Providers

| Provider | 인증 방식 | 사용자 정보 | 비고 |
|----------|----------|-----------|------|
| Google | OAuth 2.0 | email, name, picture | 이메일 자동 인증됨 |
| Kakao | OAuth 2.0 | email, nickname, profile_image | REST API 키 사용 |
| Naver | OAuth 2.0 | email, name, profile_image | Client Secret 필수 |

---

## 🔐 Google OAuth 설정

### 1단계: Google Cloud Console 접속

1. https://console.cloud.google.com/ 접속
2. Google 계정으로 로그인

### 2단계: 프로젝트 생성

1. 상단 프로젝트 선택 드롭다운 클릭
2. "새 프로젝트" 클릭
3. 프로젝트 정보 입력:
   - **프로젝트 이름**: DDOKSORI (또는 원하는 이름)
   - **조직**: 없음 (개인) 또는 소속 조직
4. "만들기" 클릭
5. 프로젝트 생성 완료 대기 (30초-1분)

### 3단계: OAuth 동의 화면 설정

1. 좌측 메뉴: **APIs & Services** → **OAuth consent screen**
2. User Type 선택:
   - **External** 선택 (일반 사용자용)
   - "만들기" 클릭
3. **앱 정보** 입력:
   - 앱 이름: `DDOKSORI`
   - 사용자 지원 이메일: 본인 이메일
   - 앱 로고: (선택사항) 로고 이미지 업로드
4. **개발자 연락처 정보**:
   - 이메일 주소: 본인 이메일
5. "저장 후 계속" 클릭
6. **범위 (Scopes)** 페이지:
   - "범위 추가 또는 삭제" 클릭
   - 다음 범위 선택:
     - `.../auth/userinfo.email`
     - `.../auth/userinfo.profile`
     - `openid`
   - "업데이트" 클릭
   - "저장 후 계속" 클릭
7. **테스트 사용자** 페이지:
   - (개발 중에만 필요) "테스트 사용자 추가" 클릭
   - 테스트 계정 이메일 입력
   - "저장 후 계속" 클릭
8. "대시보드로 돌아가기" 클릭

### 4단계: OAuth 2.0 Client ID 생성

1. 좌측 메뉴: **APIs & Services** → **Credentials**
2. 상단 "+ CREATE CREDENTIALS" 클릭
3. "OAuth 2.0 Client ID" 선택
4. **애플리케이션 유형**: Web application
5. **이름**: DDOKSORI Development (또는 원하는 이름)
6. **승인된 JavaScript 원본** (선택사항):
   - `http://localhost:5173` (프론트엔드 개발 서버)
7. **승인된 리디렉션 URI** (필수):
   - 개발 환경: `http://localhost:8000/api/auth/google/callback`
   - 프로덕션: `https://your-domain.com/api/auth/google/callback`
8. "만들기" 클릭

### 5단계: Client ID & Secret 저장

1. 팝업 창에 **Client ID**와 **Client Secret** 표시됨
2. 안전한 곳에 복사하여 저장
3. 또는 JSON 다운로드 (나중에 다시 볼 수 있음)

**예시**:
```
Client ID: 123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
Client secret: GOCSPX-AbCdEfGhIjKlMnOpQrStUvWxYz
```

### 6단계: 환경 변수 설정

`backend/.env` 파일에 추가:
```bash
GOOGLE_CLIENT_ID=123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-AbCdEfGhIjKlMnOpQrStUvWxYz
```

### 7단계: 테스트

1. 백엔드 재시작: `uvicorn app.main:app --reload`
2. 프론트엔드 접속: `http://localhost:5173`
3. "로그인" → "Google로 계속하기" 클릭
4. Google 계정 선택
5. 권한 동의 (첫 로그인 시)
6. 리다이렉트 후 로그인 완료

**성공 확인**:
- 헤더에 사용자 이름 표시
- DB에 사용자 레코드 생성:
  ```sql
  SELECT * FROM users WHERE provider = 'google';
  ```

---

## 🟡 Kakao OAuth 설정

### 1단계: Kakao Developers 접속

1. https://developers.kakao.com/ 접속
2. Kakao 계정으로 로그인

### 2단계: 애플리케이션 등록

1. 상단 메뉴: **내 애플리케이션**
2. "애플리케이션 추가하기" 클릭
3. 앱 정보 입력:
   - **앱 이름**: DDOKSORI
   - **사업자명**: 개인 또는 회사명
4. "저장" 클릭

### 3단계: 플랫폼 설정

1. 생성된 앱 선택
2. 좌측 메뉴: **플랫폼**
3. "Web 플랫폼 등록" 클릭
4. **사이트 도메인** 입력:
   - 개발: `http://localhost:5173`
   - 프로덕션: `https://your-domain.com`
5. "저장" 클릭

### 4단계: 카카오 로그인 활성화

1. 좌측 메뉴: **제품 설정** → **카카오 로그인**
2. **카카오 로그인 활성화** ON으로 전환
3. **Redirect URI** 등록:
   - "Redirect URI 등록" 버튼 클릭
   - 개발: `http://localhost:8000/api/auth/kakao/callback`
   - 프로덕션: `https://your-domain.com/api/auth/kakao/callback`
4. "저장" 클릭

### 5단계: 동의 항목 설정

1. 좌측 메뉴: **제품 설정** → **카카오 로그인** → **동의항목**
2. 필요한 정보 설정:
   - **닉네임**: 필수 동의
   - **프로필 사진**: 선택 동의
   - **카카오계정(이메일)**: 필수 동의
3. "저장" 클릭

### 6단계: Client Secret 발급 (선택사항, 권장)

1. 좌측 메뉴: **제품 설정** → **카카오 로그인** → **보안**
2. "Client Secret" 섹션
3. "코드 생성" 버튼 클릭
4. 생성된 Secret 복사

**보안 강화**: Client Secret을 사용하면 보안이 강화됩니다 (선택사항이지만 권장).

### 7단계: REST API 키 확인

1. 좌측 메뉴: **앱 설정** → **요약 정보**
2. **앱 키** 섹션에서 **REST API 키** 복사

**예시**:
```
REST API 키: abc123def456ghi789jkl012mno345pq
Client Secret: xyz987uvw654tsr321qpo876nml543k
```

### 8단계: 환경 변수 설정

`backend/.env` 파일에 추가:
```bash
KAKAO_CLIENT_ID=abc123def456ghi789jkl012mno345pq
KAKAO_CLIENT_SECRET=xyz987uvw654tsr321qpo876nml543k  # 선택사항
```

### 9단계: 테스트

1. 백엔드 재시작
2. "로그인" → "Kakao로 계속하기" 클릭
3. Kakao 계정 로그인
4. 동의 및 계속 (첫 로그인 시)

**성공 확인**:
```sql
SELECT * FROM users WHERE provider = 'kakao';
```

---

## 🟢 Naver OAuth 설정

### 1단계: Naver Developers 접속

1. https://developers.naver.com/ 접속
2. Naver 계정으로 로그인

### 2단계: 애플리케이션 등록

1. 상단 메뉴: **Application** → **애플리케이션 등록**
2. "애플리케이션 등록하기" 클릭 (또는 콘솔로 이동)
3. 애플리케이션 정보 입력:
   - **애플리케이션 이름**: DDOKSORI
   - **사용 API**: **네이버 로그인** 체크
4. "등록하기" 클릭

### 3단계: 로그인 오픈 API 설정

1. 생성된 애플리케이션 선택
2. **API 설정** 탭 클릭
3. **네이버 로그인** 섹션:
   - **제공 정보 선택**:
     - 회원이름 (필수)
     - 이메일 주소 (필수)
     - 프로필 사진 (선택)
   - **로그인 오픈 API 서비스 환경**:
     - **PC 웹** 체크
4. **서비스 URL** 입력:
   - 개발: `http://localhost:5173`
   - 프로덕션: `https://your-domain.com`
5. **네이버 아이디로 로그인 Callback URL** 입력:
   - 개발: `http://localhost:8000/api/auth/naver/callback`
   - 프로덕션: `https://your-domain.com/api/auth/naver/callback`
6. "수정" 버튼 클릭하여 저장

### 4단계: Client ID & Secret 확인

1. **개요** 탭 클릭
2. **Application 정보** 섹션:
   - **Client ID**: 복사
   - **Client Secret**: 복사

**예시**:
```
Client ID: AbCdEfGhIj
Client Secret: KlMnOpQrSt
```

### 5단계: 환경 변수 설정

`backend/.env` 파일에 추가:
```bash
NAVER_CLIENT_ID=AbCdEfGhIj
NAVER_CLIENT_SECRET=KlMnOpQrSt
```

### 6단계: 테스트

1. 백엔드 재시작
2. "로그인" → "Naver로 계속하기" 클릭
3. Naver 계정 로그인
4. 동의 및 계속

**성공 확인**:
```sql
SELECT * FROM users WHERE provider = 'naver';
```

---

## 🌐 프로덕션 환경 설정

### URL 변경

**중요**: 프로덕션 배포 시 모든 OAuth 앱에서 리디렉션 URI를 업데이트해야 합니다.

#### Google
1. Google Cloud Console → Credentials
2. OAuth 2.0 Client ID 선택
3. **승인된 리디렉션 URI** 추가:
   - `https://your-domain.com/api/auth/google/callback`
4. "저장"

#### Kakao
1. Kakao Developers → 앱 선택 → 카카오 로그인
2. **Redirect URI** 추가:
   - `https://your-domain.com/api/auth/kakao/callback`
3. "저장"

#### Naver
1. Naver Developers → Application → 앱 선택
2. **Callback URL** 업데이트:
   - `https://your-domain.com/api/auth/naver/callback`
3. "수정"

### 환경 변수 업데이트

`backend/.env` (프로덕션):
```bash
BACKEND_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com

# OAuth credentials는 동일하게 유지
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
KAKAO_CLIENT_ID=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

---

## 🔒 보안 모범 사례

### 1. Client Secret 보호

❌ **절대 하지 말 것**:
- Git에 커밋하지 않기 (`.env` 파일은 `.gitignore`에 추가)
- 프론트엔드 코드에 포함하지 않기
- 공개 저장소에 업로드하지 않기

✅ **권장 사항**:
- 환경 변수로만 관리
- 프로덕션 환경에서 AWS Secrets Manager / GCP Secret Manager 사용
- 주기적으로 Secret 로테이션

### 2. Redirect URI 제한

- 와일드카드 사용 금지 (예: `*.example.com`)
- 정확한 URL만 등록
- 개발/스테이징/프로덕션 환경별로 별도 앱 생성 권장

### 3. HTTPS 필수

프로덕션 환경에서는 반드시 HTTPS 사용:
- OAuth callback URL: `https://...`
- Frontend URL: `https://...`

### 4. State Parameter 검증

이미 구현됨 (`backend/app/api/auth.py`):
```python
# CSRF 방지를 위한 state 검증
if not _verify_and_remove_state(state):
    raise HTTPException(400, "Invalid state")
```

---

## 🐛 문제 해결

### "Invalid redirect URI" 에러

**원인**: OAuth 앱에 등록되지 않은 Redirect URI 사용

**해결**:
1. OAuth 앱 설정에서 정확한 URI 확인
2. 포트 번호 확인 (`:8000` vs `:8080`)
3. HTTP vs HTTPS 확인
4. 끝에 슬래시 (`/`) 여부 확인

**정확한 형식**:
```
http://localhost:8000/api/auth/{provider}/callback
```

---

### "Invalid client" 에러

**원인**: Client ID 또는 Client Secret이 잘못됨

**해결**:
1. `.env` 파일의 ID/Secret 재확인
2. 공백 문자 제거 확인
3. 따옴표 제거 (`.env`에서는 따옴표 불필요)
4. OAuth 앱에서 ID/Secret 다시 복사

---

### "Access denied" 에러 (Google)

**원인**: 테스트 사용자로 등록되지 않은 계정으로 로그인 시도

**해결**:
1. Google Cloud Console → OAuth consent screen
2. "Test users" 섹션에 이메일 추가
3. 또는 앱을 "In production" 상태로 변경 (검토 필요)

---

### Kakao "동의 항목 미설정" 에러

**원인**: 필수 동의 항목이 설정되지 않음

**해결**:
1. Kakao Developers → 카카오 로그인 → 동의항목
2. 이메일을 "필수 동의"로 설정
3. 닉네임을 "필수 동의"로 설정

---

### "Invalid state" 에러

**원인**: OAuth state가 만료됨 (10분 TTL)

**해결**: 로그인 다시 시도 (처음부터)

---

## 📊 OAuth 통계 모니터링

### 로그인 성공률

```sql
-- OAuth 제공자별 사용자 수
SELECT provider, COUNT(*) as user_count
FROM users
GROUP BY provider;

-- 최근 로그인
SELECT provider, email, last_login_at
FROM users
ORDER BY last_login_at DESC
LIMIT 10;

-- OAuth 세션 (선택사항)
SELECT provider, COUNT(*) as session_count
FROM oauth_sessions
GROUP BY provider;
```

### 로그인 실패 추적

백엔드 로그 확인:
```bash
# OAuth 에러 확인
grep -i "oauth\|Invalid state\|Invalid client" backend/logs/app.log

# 최근 1시간 OAuth 에러
grep -i "oauth.*error" backend/logs/app.log | tail -100
```

---

## 📚 참고 문서

### 공식 문서

- **Google OAuth**: https://developers.google.com/identity/protocols/oauth2
- **Kakao Login**: https://developers.kakao.com/docs/latest/ko/kakaologin/common
- **Naver Login**: https://developers.naver.com/docs/login/overview/

### 내부 문서

- **전체 아키텍처**: `/docs/feature/conversational-chatbot-transformation.md`
- **Quick Start Guide**: `/docs/guides/conversational-chatbot-quickstart.md`
- **E2E 테스트**: `/docs/testing/e2e-test-guide.md`

---

**마지막 업데이트**: 2026-01-28
**작성자**: Claude Code
**버전**: 1.0