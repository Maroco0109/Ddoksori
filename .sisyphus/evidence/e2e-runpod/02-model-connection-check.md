# 모델 연결 점검 절차

## 1. 개요

Runpod 엔드포인트의 네트워크 접근성, 포트 개방 여부, 인증 헤더, 타임아웃을 검증하는 절차입니다.

**검증 범위**:
- Health Check 엔드포인트 접근성 (HTTP 200)
- Chat Completions API 호출 가능 여부
- 백엔드 컨테이너에서의 실제 egress 경로 확인
- 실패 시 원인 분류 및 진단

---

## 2. Health Check 검증

### 2.1 URL 구성 규칙

Runpod vLLM 서버의 health 엔드포인트는 다음 규칙으로 구성됩니다:

**Python 로직** (코드 구현):
```python
# backend/app/llm/exaone_client.py, tool_calling_client.py
base_url = runpod_url.rstrip('/').replace('/v1', '')
health_url = f"{base_url}/health"
```

**Bash 동등 로직**:
```bash
# 1. 환경 변수에서 EXAONE_RUNPOD_URL 읽기
#    예: https://<pod-id>-8000.proxy.runpod.net/v1
#    또는: http://localhost:19080/v1

# 2. 후행 슬래시 제거
BASE_URL="${EXAONE_RUNPOD_URL%/}"

# 3. /v1 경로 제거
BASE_URL="${BASE_URL//\/v1/}"

# 4. /health 엔드포인트 추가
HEALTH_URL="${BASE_URL}/health"
```

**예시**:
- 입력: `https://abc123-8000.proxy.runpod.net/v1`
- 처리: `https://abc123-8000.proxy.runpod.net/v1` → `https://abc123-8000.proxy.runpod.net` → `/v1` 제거 → `https://abc123-8000.proxy.runpod.net`
- 결과: `https://abc123-8000.proxy.runpod.net/health`

---

### 2.2 Host에서 실행

**목적**: Runpod 엔드포인트의 네트워크 접근성 및 포트 개방 여부 확인

**전제 조건**:
- 환경 변수 설정: `EXAONE_RUNPOD_URL`, `EXAONE_RUNPOD_API_KEY`
- curl 또는 wget 설치

**실행 명령**:
```bash
#!/bin/bash
set -e

# 환경 변수 로드 (필요시)
# source backend/.env

# URL 구성
BASE_URL="${EXAONE_RUNPOD_URL%/}"
BASE_URL="${BASE_URL//\/v1/}"
HEALTH_URL="${BASE_URL}/health"

echo "Health Check URL: $HEALTH_URL"

# Health Check 실행
curl -fsS "$HEALTH_URL" \
  -w "\nHTTP Status: %{http_code}\n" \
  -o /tmp/health_response.txt

# 응답 확인
echo "Response:"
cat /tmp/health_response.txt
```

**성공 응답**:
```
HTTP Status: 200
```

**실패 응답 예시**:
```
curl: (7) Failed to connect to abc123-8000.proxy.runpod.net port 443: Connection refused
HTTP Status: 000
```

---

### 2.3 Backend 컨테이너에서 실행

**목적**: 백엔드 컨테이너 내부에서 Runpod로의 실제 egress 경로 확인 (운영 환경 시뮬레이션)

**전제 조건**:
- Docker Compose 실행 중 (`docker compose up -d`)
- 백엔드 컨테이너 이름: `backend`

**Python/requests 예시** (curl 의존성 제거):
```bash
docker compose exec backend python - <<'PY'
import os
import requests

# 환경 변수에서 URL 읽기
runpod_url = os.environ.get('EXAONE_RUNPOD_URL')
if not runpod_url:
    print("ERROR: EXAONE_RUNPOD_URL not set")
    exit(1)

# URL 구성 (Python 로직)
base_url = runpod_url.rstrip('/').replace('/v1', '')
health_url = f"{base_url}/health"

print(f"Health Check URL: {health_url}")

try:
    # Health Check 실행 (5초 타임아웃)
    response = requests.get(health_url, timeout=5)
    print(f"HTTP Status: {response.status_code}")
    print(f"Response Body (first 200 chars):\n{response.text[:200]}")
    
    if response.status_code == 200:
        print("\n✓ Health Check PASSED")
        exit(0)
    else:
        print(f"\n✗ Health Check FAILED: {response.status_code}")
        exit(1)
        
except requests.exceptions.Timeout:
    print("✗ TIMEOUT: Runpod server not responding within 5 seconds")
    exit(1)
except requests.exceptions.ConnectionError as e:
    print(f"✗ CONNECTION ERROR: {e}")
    exit(1)
except Exception as e:
    print(f"✗ ERROR: {e}")
    exit(1)
PY
```

**성공 응답**:
```
Health Check URL: https://abc123-8000.proxy.runpod.net/health
HTTP Status: 200
Response Body (first 200 chars):
{"status":"ok"}

✓ Health Check PASSED
```

**실패 응답 예시**:
```
Health Check URL: https://abc123-8000.proxy.runpod.net/health
✗ TIMEOUT: Runpod server not responding within 5 seconds
```

---

## 3. Chat Completions 호출 검증

### 3.1 Host에서 실행

**목적**: Runpod vLLM API의 chat/completions 엔드포인트 호출 가능 여부 확인

**전제 조건**:
- 환경 변수: `EXAONE_RUNPOD_URL`, `EXAONE_RUNPOD_API_KEY`, `EXAONE_MODEL`
- curl 설치

**실행 명령**:
```bash
#!/bin/bash
set -e

# 환경 변수 로드 (필요시)
# source backend/.env

# 필수 환경 변수 확인
if [ -z "$EXAONE_RUNPOD_URL" ]; then
    echo "ERROR: EXAONE_RUNPOD_URL not set"
    exit 1
fi

if [ -z "$EXAONE_MODEL" ]; then
    echo "ERROR: EXAONE_MODEL not set"
    exit 1
fi

# 기본값 설정
API_KEY="${EXAONE_RUNPOD_API_KEY:-dummy}"
TIMEOUT="${EXAONE_TIMEOUT:-10}"

echo "Chat Completions Test"
echo "URL: $EXAONE_RUNPOD_URL/chat/completions"
echo "Model: $EXAONE_MODEL"
echo "Timeout: ${TIMEOUT}s"
echo ""

# Chat Completions 호출
curl -fsS "$EXAONE_RUNPOD_URL/chat/completions" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${API_KEY}" \
  -d '{
    "model":"'"$EXAONE_MODEL"'",
    "messages":[{"role":"user","content":"ping"}],
    "max_tokens":16
  }' \
  --max-time "$TIMEOUT" \
  -w "\nHTTP Status: %{http_code}\n" \
  -o /tmp/chat_response.txt

echo "Response:"
cat /tmp/chat_response.txt
```

**성공 응답 예시**:
```
Chat Completions Test
URL: https://abc123-8000.proxy.runpod.net/v1/chat/completions
Model: LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct
Timeout: 10s

Response:
{"id":"chatcmpl-...","object":"chat.completion","created":1234567890,"model":"LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct","choices":[{"index":0,"message":{"role":"assistant","content":"pong"},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}
HTTP Status: 200
```

**실패 응답 예시**:
```
curl: (28) Operation timeout. The timeout was reached
HTTP Status: 000
```

---

### 3.2 Backend 컨테이너에서 실행

**목적**: 백엔드 컨테이너 내부에서 Chat Completions API 호출 가능 여부 확인

**Python/requests 예시**:
```bash
docker compose exec backend python - <<'PY'
import os
import requests
import json

# 환경 변수 읽기
runpod_url = os.environ.get('EXAONE_RUNPOD_URL')
api_key = os.environ.get('EXAONE_RUNPOD_API_KEY', 'dummy')
model = os.environ.get('EXAONE_MODEL')
timeout = int(os.environ.get('EXAONE_TIMEOUT', '10'))

if not runpod_url or not model:
    print("ERROR: EXAONE_RUNPOD_URL or EXAONE_MODEL not set")
    exit(1)

print("Chat Completions Test")
print(f"URL: {runpod_url}/chat/completions")
print(f"Model: {model}")
print(f"Timeout: {timeout}s")
print("")

try:
    # Chat Completions 호출
    response = requests.post(
        f"{runpod_url}/chat/completions",
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        },
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': 'ping'}],
            'max_tokens': 16
        },
        timeout=timeout
    )
    
    print(f"HTTP Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response (first 300 chars):\n{json.dumps(data, ensure_ascii=False)[:300]}")
        
        # 응답 검증
        if 'choices' in data and len(data['choices']) > 0:
            content = data['choices'][0].get('message', {}).get('content', '')
            print(f"\nAssistant Response: {content}")
            print("\n✓ Chat Completions PASSED")
            exit(0)
        else:
            print("\n✗ Invalid response format")
            exit(1)
    else:
        print(f"Response:\n{response.text[:300]}")
        print(f"\n✗ Chat Completions FAILED: {response.status_code}")
        exit(1)
        
except requests.exceptions.Timeout:
    print("✗ TIMEOUT: Runpod server not responding within timeout")
    exit(1)
except requests.exceptions.ConnectionError as e:
    print(f"✗ CONNECTION ERROR: {e}")
    exit(1)
except Exception as e:
    print(f"✗ ERROR: {e}")
    exit(1)
PY
```

**성공 응답**:
```
Chat Completions Test
URL: https://abc123-8000.proxy.runpod.net/v1/chat/completions
Model: LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct
Timeout: 10s

HTTP Status: 200
Response (first 300 chars):
{"id":"chatcmpl-...","object":"chat.completion","created":1234567890,"model":"LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct","choices":[{"index":0,"message":{"role":"assistant","content":"pong"},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}

Assistant Response: pong

✓ Chat Completions PASSED
```

---

## 4. 실패 시 진단 절차

### 4.1 원인 분류 체크리스트

실패 응답을 받았을 때 다음 순서로 원인을 진단합니다:

#### 1️⃣ **DNS 오류** (도메인 해석 실패)

**증상**:
```
curl: (6) Could not resolve host: abc123-8000.proxy.runpod.net
```

**진단**:
```bash
# DNS 해석 확인
nslookup abc123-8000.proxy.runpod.net
# 또는
dig abc123-8000.proxy.runpod.net
```

**해결 방법**:
- Runpod 대시보드에서 Pod ID 확인
- 올바른 도메인 형식: `https://<pod-id>-<port>.proxy.runpod.net`
- 네트워크 연결 확인 (인터넷 접속 가능 여부)
- DNS 서버 변경 (8.8.8.8 등)

---

#### 2️⃣ **포트 오류** (포트 개방 안 됨)

**증상**:
```
curl: (7) Failed to connect to abc123-8000.proxy.runpod.net port 443: Connection refused
```

**진단**:
```bash
# 포트 접근성 확인 (nc 또는 telnet)
nc -zv abc123-8000.proxy.runpod.net 443
# 또는
telnet abc123-8000.proxy.runpod.net 443
```

**해결 방법**:
- Runpod Pod 상태 확인 (Running 상태인지)
- vLLM 서버 포트 확인 (기본: 8000)
- Runpod 방화벽 규칙 확인
- SSH 터널링 사용 시 터널 상태 확인

---

#### 3️⃣ **라우팅 오류** (경로 오류)

**증상**:
```
HTTP Status: 404
{"error":"Not Found"}
```

**진단**:
```bash
# 올바른 경로 확인
curl -fsS "https://abc123-8000.proxy.runpod.net/health"
curl -fsS "https://abc123-8000.proxy.runpod.net/v1/health"
```

**해결 방법**:
- URL 경로 확인: `/health` vs `/v1/health`
- 코드 규칙 재확인: `rstrip('/').replace('/v1', '')`
- vLLM 라우팅 설정 확인

---

#### 4️⃣ **인증 오류** (API 키 또는 헤더)

**증상**:
```
HTTP Status: 401
{"error":"Unauthorized"}
```

**진단**:
```bash
# 인증 헤더 확인
curl -fsS "https://abc123-8000.proxy.runpod.net/v1/chat/completions" \
  -H "Authorization: Bearer ${EXAONE_RUNPOD_API_KEY}"

# 헤더 없이 시도
curl -fsS "https://abc123-8000.proxy.runpod.net/v1/chat/completions"
```

**해결 방법**:
- `EXAONE_RUNPOD_API_KEY` 환경 변수 확인
- vLLM 서버의 인증 요구 여부 확인 (보통 필요 없음)
- 헤더 형식 확인: `Authorization: Bearer <key>`

---

#### 5️⃣ **타임아웃 오류** (응답 지연)

**증상**:
```
curl: (28) Operation timeout. The timeout was reached
HTTP Status: 000
```

**진단**:
```bash
# 타임아웃 값 증가하여 재시도
curl -fsS "https://abc123-8000.proxy.runpod.net/health" \
  --max-time 30

# 응답 시간 측정
curl -fsS "https://abc123-8000.proxy.runpod.net/health" \
  -w "Time: %{time_total}s\n"
```

**해결 방법**:
- Runpod Pod의 GPU 메모리 확인 (모델 로드 중일 수 있음)
- vLLM 서버 로그 확인
- 네트워크 지연 확인 (ping 테스트)
- 타임아웃 값 증가 (환경 변수: `EXAONE_TIMEOUT`)

---

### 4.2 종합 진단 스크립트

```bash
#!/bin/bash

echo "=== Runpod 연결 진단 스크립트 ==="
echo ""

# 환경 변수 확인
echo "1. 환경 변수 확인"
echo "EXAONE_RUNPOD_URL: ${EXAONE_RUNPOD_URL:-NOT SET}"
echo "EXAONE_RUNPOD_API_KEY: ${EXAONE_RUNPOD_API_KEY:-NOT SET}"
echo "EXAONE_MODEL: ${EXAONE_MODEL:-NOT SET}"
echo ""

# DNS 확인
echo "2. DNS 해석 확인"
BASE_URL="${EXAONE_RUNPOD_URL%/}"
BASE_URL="${BASE_URL//\/v1/}"
HOSTNAME=$(echo "$BASE_URL" | sed 's|https://||;s|http://||;s|/.*||')
echo "Hostname: $HOSTNAME"
nslookup "$HOSTNAME" || echo "DNS 해석 실패"
echo ""

# 포트 확인
echo "3. 포트 접근성 확인"
nc -zv "$HOSTNAME" 443 || echo "포트 443 접근 불가"
echo ""

# Health Check
echo "4. Health Check"
HEALTH_URL="${BASE_URL}/health"
echo "URL: $HEALTH_URL"
curl -fsS "$HEALTH_URL" -w "\nHTTP Status: %{http_code}\n" || echo "Health Check 실패"
echo ""

# Chat Completions
echo "5. Chat Completions 호출"
echo "URL: ${EXAONE_RUNPOD_URL}/chat/completions"
curl -fsS "${EXAONE_RUNPOD_URL}/chat/completions" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${EXAONE_RUNPOD_API_KEY:-dummy}" \
  -d '{"model":"'"${EXAONE_MODEL}"'","messages":[{"role":"user","content":"ping"}],"max_tokens":16}' \
  -w "\nHTTP Status: %{http_code}\n" || echo "Chat Completions 호출 실패"
```

---

## 5. 참조 파일

| 파일 | 설명 |
|------|------|
| `backend/app/llm/exaone_client.py` | Health Check 구현 (라인 77-113) |
| `backend/app/llm/tool_calling_client.py` | Tool Calling Health Check (라인 47-77) |
| `backend/.env.example` | 환경 변수 설정 예시 (라인 58-81) |
| `.sisyphus/evidence/e2e-runpod/00-pre-setup-checklist.md` | E2E 사전 준비 체크리스트 |

---

## 6. 실행 순서 권장사항

1. **Host에서 Health Check** → 네트워크/Runpod 접근성 확인
2. **Host에서 Chat Completions** → API 호출 가능 여부 확인
3. **Backend 컨테이너에서 Health Check** → 실제 egress 경로 확인
4. **Backend 컨테이너에서 Chat Completions** → 운영 환경 시뮬레이션
5. **실패 시 진단 절차** → 원인 분류 및 해결

---

## 7. 성공 기준

- [ ] Health Check: HTTP 200 응답
- [ ] Chat Completions: HTTP 200 + 유효한 JSON 응답
- [ ] Host 및 Backend 컨테이너 모두에서 성공
- [ ] 응답 시간이 타임아웃 값 이내 (기본: 5-10초)
