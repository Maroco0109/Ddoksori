# Frontend-Backend Integration Guide

이 문서는 똑소리(DDokSori) 프로젝트의 Frontend(React)와 Backend(FastAPI)가 어떻게 연결되어 통신하는지 설명합니다.

## 시스템 아키텍처 (System Architecture)

현재 시스템은 **Client-Side Rendering (CSR)** 방식으로 동작하며, 브라우저가 직접 Backend API 서버로 요청을 보냅니다.

```mermaid
graph LR
    User[Web Browser] -- HTTP Request --> Frontend[Frontend Server\n(Vite/Nginx: 5173)]
    User -- AJAX/Fetch (port 8000) --> Backend[Backend Server\n(FastAPI: 8000)]
    Backend -- SQL --> DB[(PostgreSQL)]
```

* **Frontend**: React 앱이 브라우저에서 실행되며, API 호출 시 `http://localhost:8000` (또는 설정된 URL)으로 직접 요청을 보냅니다.
* **Backend**: FastAPI 서버가 `0.0.0.0:8000`에서 리스닝하며, CORS 설정을 통해 Frontend의 요청을 허용합니다.

---

## 1. Frontend 설정 (API Client)

Frontend는 `fetch` API를 래핑한 커스텀 클라이언트를 사용하여 Backend와 통신합니다.

### API Client 구현

위치: `frontend/src/shared/api/client.ts`

```typescript
// 환경 변수에서 기본 API 주소를 가져오거나, 없으면 localhost:8000을 기본값으로 사용
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = {
  get: async <T>(endpoint: string, params?: Record<string, any>): Promise<T> => {
    // ... URL 파라미터 처리 및 fetch 호출
  },
  post: async <T>(endpoint: string, data?: any): Promise<T> => {
    // ... JSON Body와 함께 POST 요청
  }
  // ... PUT, DELETE 구현
};
```

### 환경 변수 설정

`frontend` 디렉토리 내 `.env` 파일이나 `docker-compose.yml` 또는 실행 시 환경 변수를 통해 API 주소를 변경할 수 있습니다.

> [!NOTE]
> 코드상에서는 `VITE_API_BASE_URL`을 참조하고 있으나, 일부 설정(Docker 등)에서 명칭이 다를 수 있으므로 확인이 필요합니다. 현재 기본값(`http://localhost:8000`)으로 로컬 개발 환경에서 정상 작동합니다.

---

## 2. Backend 설정 (CORS)

Backend는 브라우저의 Cross-Origin 요청을 허용하기 위해 **CORS(Cross-Origin Resource Sharing)** 가 설정되어 있습니다.

### CORS 미들웨어 설정

위치: `backend/app/main.py`

```python
# 환경 변수에서 허용할 Origin 목록을 가져옴 (기본값: http://localhost:5173)
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)
```

이 설정 덕분에 포트가 다른 `localhost:5173` (Frontend)에서 `localhost:8000` (Backend)로 보내는 요청이 차단되지 않고 처리됩니다.

---

## 3. Docker Compose 연결

Docker Compose 환경에서는 각 컨테이너가 포트 포워딩을 통해 호스트 머신의 포트에 매핑됩니다.

위치: `docker-compose.yml`

```yaml
services:
  backend:
    ports:
      - "8000:8000"  # 호스트의 8000번 포트를 컨테이너의 8000번으로 연결
    environment:
      - CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

  frontend:
    ports:
      - "5173:5173"  # 호스트의 5173번 포트를 컨테이너의 5173번으로 연결
    environment:
      # 주의: 현재 코드(client.ts)는 VITE_API_BASE_URL을 사용합니다.
      # 아래 설정은 매칭되지 않아 무시되지만, 코드의 기본값(localhost:8000) 덕분에 작동합니다.
      # 명확한 설정을 위해 코드를 수정하거나 아래 변수명을 VITE_API_BASE_URL로 변경하는 것이 좋습니다.
      - VITE_API_URL=http://localhost:8000 
```

> [!IMPORTANT]
> Frontend는 브라우저(Host OS)에서 실행되므로, API URL은 Docker 내부 네트워크 주소(예: `http://backend:8000`)가 아닌 **호스트에서 접근 가능한 주소(`http://localhost:8000`)** 여야 합니다.

---

## 연결 테스트 및 문제 해결

### 연결 확인 방법

1. **Backend 상태 확인**: 브라우저에서 [http://localhost:8000/health](http://localhost:8000/health) 접속 시 `{"status": "healthy"}` 응답 확인.
2. **API 호출 확인**: Frontend 앱 사용 중 개발자 도구(F12) > Network 탭에서 `search` 또는 `chat` 요청이 `200 OK`로 성공하는지 확인.

### 자주 발생하는 문제 (Troubleshooting)

| 증상 | 원인 | 해결 방법 |
| :--- | :--- | :--- |
| **CORS Error** (Console) | Backend의 `CORS_ORIGINS`에 Frontend 주소가 없음 | Backend 설정을 확인하거나 `.env`의 `CORS_ORIGINS`에 현재 브라우저 주소(`http://localhost:5173` 등)를 추가하세요. |
| **Connection Refused** | Backend 서버가 꺼져있거나 포트가 다름 | `docker ps`로 `ddoksori_backend` 컨테이너가 실행 중인지 확인하고, 포트 8000이 열려있는지 확인하세요. |
| **Network Error** | API URL 설정이 잘못됨 | Frontend가 바라보는 `API_BASE_URL`이 올바른지 확인하세요. |
