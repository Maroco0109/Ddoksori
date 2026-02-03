# DDOKSORI E2E 수동 테스트 가이드

> AI_MEMO.md 기반 - MAS v2 아키텍처 반영, RDS 전용 환경에서의 전체 시스템 검증 절차
>
> **최종 업데이트**: 2026-01-29 (MAS v2 반영: 3개 Retrieval Agent, gpt-4o-mini Supervisor)

## 📋 목차

1. [사전 준비](#1-사전-준비)
2. [환경 변수 설정](#2-환경-변수-설정)
3. [Docker 서비스 시작](#3-docker-서비스-시작)
4. [Health Check (서비스 상태 확인)](#4-health-check-서비스-상태-확인)
5. [LLM 모델 연결 테스트](#5-llm-모델-연결-테스트)
6. [Frontend-Backend 연동 테스트](#6-frontend-backend-연동-테스트)
7. [E2E 시나리오 테스트](#7-e2e-시나리오-테스트)
8. [증거 수집](#8-증거-수집)

---

## 1. 사전 준비

### 1.1 필수 조건

**시스템 요구사항:**
- Docker & Docker Compose 설치
- Python 3.10+ (conda env: dsr)
- Node.js 18+
- curl 설치

### 1.2 API 키 확인

**필수 API 키 (.env에 설정):**
- `OPENAI_API_KEY` - gpt-4o-mini Supervisor/QueryAnalyst/Draft/Review, Embedding
- `ANTHROPIC_API_KEY` - Claude 3 Haiku (Fallback용)

### 1.3 선택 사항: RunPod vLLM (EXAONE)

EXAONE은 Retrieval Agent의 Query Rewrite에 사용됩니다. 3개의 Retrieval Agent (Law, Criteria, Case)가 병렬로 실행되므로, 성능 최적화를 위해 **에이전트별 독립 vLLM 인스턴스**를 구성할 수 있습니다.

#### 옵션 A: 공유 인스턴스 (기본)

모든 Retrieval Agent가 1개의 EXAONE 인스턴스를 공유합니다.

**SSH 터널링 설정:**
```bash
ssh -L 19010:localhost:9010 root@<pod-ip>
```

또는 Proxy URL 사용:
```
https://<pod-id>-9010.proxy.runpod.net/v1
```

#### 옵션 B: 에이전트별 독립 인스턴스 (병렬 처리 최적화)

3개의 Retrieval Agent 각각에 독립 vLLM 인스턴스를 할당하여 완전한 병렬 처리를 구현합니다.

**SSH 터널링 설정 (3개 포트):**
```bash
# Law Agent용 (포트 19010)
ssh -L 19010:localhost:9010 root@<pod-ip-1> -N &

# Criteria Agent용 (포트 19011)
ssh -L 19011:localhost:9010 root@<pod-ip-2> -N &

# Case Agent용 (포트 19012)
ssh -L 19012:localhost:9010 root@<pod-ip-3> -N &
```

> **Fallback**: EXAONE 연결 실패 시 `gpt-4.1-nano`로 자동 폴백됩니다.

---

## 2. 환경 변수 설정

### 2.1 .env 파일 수정

```bash
cd /home/maroco/LLM
cp .env.example .env
# 아래 값들을 실제 환경에 맞게 수정
```

### 2.2 핵심 환경 변수 (Model Architecture Refactor 반영)

#### 모델 아키텍처 설정

```bash
MODEL_SUPERVISOR=gpt-4o-mini
MODEL_QUERY_ANALYST=gpt-4o-mini
MODEL_DRAFT_AGENT=gpt-4o-mini
MODEL_REVIEW_AGENT=gpt-4o-mini
MODEL_RETRIEVAL_LLM=LGAI-EXAONE/EXAONE-4.0-1.2B
MODEL_RETRIEVAL_FALLBACK=gpt-4.1-nano
MAX_RETRY_COUNT=1

# EXAONE vLLM 공유 설정 (RunPod SSH 터널링 시)
MODEL_EXAONE_BASE_URL=http://localhost:19010/v1
MODEL_EXAONE_API_KEY=empty
PORT_EXAONE_VLLM=19010
```

#### Retrieval Agent별 LLM 설정 (병렬 처리 최적화, 선택 사항)

3개 Retrieval Agent에 독립 vLLM 인스턴스를 할당할 때 사용합니다.
설정하지 않으면 공유 `MODEL_EXAONE_BASE_URL`을 사용합니다.

```bash
# 에이전트별 EXAONE vLLM URL
RETRIEVAL_LLM_LAW_URL=http://localhost:19010/v1
RETRIEVAL_LLM_CRITERIA_URL=http://localhost:19011/v1
RETRIEVAL_LLM_CASE_URL=http://localhost:19012/v1

# Query Rewrite 타임아웃 (초)
RETRIEVAL_LLM_TIMEOUT=3.0
```

#### 임베딩 설정 (text-embedding-3-large로 변경됨)

```bash
USE_OPENAI_EMBEDDING=true
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_DIMENSION=1536
```

#### 데이터베이스 설정 (RDS)

```bash
DB_HOST=your-instance.xxxx.region.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=readonly_user
DB_PASSWORD=<your_password>
```

#### MAS Supervisor 그래프

```bash
MAS_SUPERVISOR_ENABLED=true
MAS_SUPERVISOR_CANARY_PERCENT=0
```

---

## 3. Docker 서비스 시작

### 3.0. 루트에 .env 파일 확인
```bash
# .env 파일은 프로젝트 루트에 위치해야 합니다
ls -la .env
```

### 3.1 서비스 시작

```bash
cd /home/maroco/LLM

# 전체 서비스 시작
docker compose up -d

# 서비스 상태 확인
docker compose ps
```

**예상 결과:**
```
NAME                    STATUS         PORTS
ddoksori_backend        running        0.0.0.0:8000->8000/tcp
ddoksori_frontend       running        0.0.0.0:5173->5173/tcp
ddoksori_cloudbeaver    running        0.0.0.0:8978->8978/tcp
ddoksori_redis          running        0.0.0.0:6379->6379/tcp
```

> **참고**: Backend는 `.env` 파일의 `DB_HOST` 설정을 통해 RDS에 연결됩니다.

### 3.2 서비스 중지

```bash
docker compose down
```

### 3.3 로그 확인

```bash
# 특정 컨테이너 로그
docker logs ddoksori_backend

# 실시간 로그 (follow)
docker logs -f ddoksori_backend

# 최근 N줄만
docker logs --tail 100 ddoksori_backend

# docker compose로 보기
docker compose logs backend
docker compose logs -f backend --tail 100
```

---

## 4. Health Check (서비스 상태 확인)

### 4.1 기본 서버 상태

**루트 엔드포인트 - 서버 정보:**
```bash
curl -s http://localhost:8000/
```

**예상 응답:**
```json
{
  "message": "똑소리 API 서버가 정상적으로 실행 중입니다.",
  "version": "0.4.1",
  "retrieval_mode": "hybrid",
  "features": ["Hybrid RAG 검색 (Dense + Lexical + RRF)", "LLM 답변 생성"]
}
```

### 4.2 데이터베이스 연결 확인

```bash
curl -s http://localhost:8000/health | jq
```

**예상 응답 (성공):**
```json
{"status": "healthy", "database": "connected"}
```

**예상 응답 (실패):**
```json
{"status": "unhealthy", "error": "connection refused"}
```

### 4.3 LLM 모델 상태 확인

**Supervisor LLM (gpt-4o-mini via OpenAI API):**
```bash
curl -s http://localhost:8000/health/llm/supervisor | jq
```

**예상 응답:**
```json
{"status": "healthy", "model": "gpt-4o-mini (OpenAI API)"}
```

**EXAONE LLM (RunPod vLLM) - 선택 사항:**
```bash
curl -s http://localhost:8000/health/llm/exaone | jq
```

**예상 응답 (RunPod 연결됨):**
```json
{"status": "healthy", "url": "http://localhost:19010/v1"}
```

**예상 응답 (RunPod 없음):**
```json
{"status": "unhealthy", "error": "EXAONE URL not configured"}
```

### 4.4 임베딩 상태 확인

```bash
curl -s http://localhost:8000/health/embedding | jq
```

**예상 응답 (OpenAI Embedding 사용 시):**
```json
{"status": "healthy", "type": "OpenAI Embedding"}
```

---

## 5. LLM 모델 연결 테스트

### 5.1 RunPod EXAONE 연결 테스트 (선택 사항)

**SSH 터널링 확인:**
```bash
# SSH 터널 상태 확인
ps aux | grep "ssh.*19010"

# 터널 없으면 시작
ssh -L 19010:localhost:9010 root@<pod-ip> -N &
```

**Health Check:**
```bash
# vLLM Health Check
curl -s http://localhost:19010/health
```

**예상 응답:**
```json
{"status":"ok"}
```

**Chat Completions 테스트:**
```bash
curl -s http://localhost:19010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct",
    "messages": [{"role": "user", "content": "안녕하세요"}],
    "max_tokens": 50
  }' | jq
```

> **예상 응답:** `choices[0].message.content`에 응답 포함

### 5.2 OpenAI API 연결 테스트

**API 키 확인:**
```bash
echo $OPENAI_API_KEY | head -c 10
```

**직접 테스트 (선택):**
```bash
curl -s https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" | jq '.data | length'
```

---

## 6. Frontend-Backend 연동 테스트

### 6.1 Frontend 접속

**브라우저에서 접속:**
```bash
open http://localhost:5173
```

**또는 curl로 확인:**
```bash
curl -s http://localhost:5173 | head -20
```

### 6.2 API 직접 호출 테스트

**간단한 검색 테스트:**
```bash
curl -s http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "청약철회",
    "top_k": 3
  }' | jq '.results | length'
```

**예상 결과:** `3` (3개의 검색 결과)

**채팅 API 테스트:**
```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "환불 받을 수 있나요?",
    "chat_type": "general",
    "top_k": 5
  }' | jq '{answer: .answer[:200], sources_count: (.sources | length)}'
```

**예상 결과:**
```json
{
  "answer": "환불 관련 답변 (처음 200자)...",
  "sources_count": 5
}
```

---

## 7. E2E 시나리오 테스트

### 7.1 시나리오 1: 정상 동작 (분쟁 상담)

**복잡한 법률 질의로 전체 파이프라인 테스트:**
```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부",
    "chat_type": "dispute",
    "debug": true,
    "top_k": 5
  }' | jq '{
    answer_preview: .answer[:300],
    sources_count: (.sources | length),
    has_evidence: .has_sufficient_evidence,
    node_timings: .node_timings
  }'
```

**성공 기준:**
- `answer_preview`: 법률 조항을 인용한 답변
- `sources_count`: 1 이상 (출처 포함)
- `has_evidence`: true
- `node_timings`: 각 노드별 실행 시간 기록

### 7.2 시나리오 2: 일반 상담

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "인터넷으로 산 옷이 마음에 안 들어요. 반품 가능한가요?",
    "chat_type": "general",
    "debug": true,
    "top_k": 5
  }' | jq '{
    answer_preview: .answer[:300],
    model: .model,
    total_time_ms: .total_time_ms
  }'
```

### 7.3 시나리오 3: Fallback 동작 테스트 (EXAONE 없을 때)

**EXAONE 없이도 시스템이 정상 동작하는지 확인 (gpt-4.1-nano로 자동 폴백):**
```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "하자담보책임 기간이 얼마인가요?",
    "chat_type": "dispute",
    "top_k": 5
  }' | jq '.answer[:200]'
```

> **확인 기준:** 답변이 생성되면 Fallback 정상 동작

### 7.4 시나리오 4: Retrieval Agent 병렬 처리 테스트

3개 Retrieval Agent (Law, Criteria, Case)가 병렬로 Query Rewrite를 수행하는지 확인합니다.

**debug 모드로 node_timings 확인:**
```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "전자상거래법 청약철회 기간과 분쟁해결기준",
    "chat_type": "dispute",
    "debug": true,
    "top_k": 5
  }' | jq '{
    retrieval_timings: .node_timings | to_entries | map(select(.key | startswith("retrieval_")))
  }'
```

**성공 기준:**
- 3개 Retrieval Agent의 타이밍이 기록됨
- 에이전트별 독립 URL 설정 시: 타이밍이 유사 (병렬 처리)
- 공유 URL 사용 시: 타이밍에 약간의 순차 대기 발생 가능

**로그에서 Query Rewrite 확인:**
```bash
docker compose logs backend --tail 50 | grep -E "domain=(law|criteria|case).*rewrite"
```

### 7.5 Backend 로그 확인

**Docker 사용 시:**
```bash
docker compose logs backend --tail 100 | grep -E "(QueryRewriter|Supervisor|Draft|Review|Retrieval)"
```

**로컬 실행 시:**
```bash
tail -100 backend/app.log | grep -E "(QueryRewriter|Supervisor|Draft|Review|Retrieval)"
```

**확인할 로그 패턴:**
- `[Supervisor] LLM 결정: model=gpt-4o-mini` - Supervisor 동작
- `[Retrieval] domain=law rewrite` - Law Agent Query Rewrite
- `[Retrieval] domain=criteria rewrite` - Criteria Agent Query Rewrite
- `[Retrieval] domain=case rewrite` - Case Agent Query Rewrite
- `[Draft] 답변 생성 완료` - Draft Agent 동작
- `[LegalReview] 검토 완료` - Review Agent 동작
- `Using fallback model: gpt-4.1-nano` - EXAONE 폴백 발생

---

## 8. 증거 수집

### 8.1 증거 폴더 생성

```bash
mkdir -p .sisyphus/evidence/e2e-manual/$(date +%Y%m%d)
```

### 8.2 Health Check 결과 저장

```bash
DATE=$(date +%Y%m%d)
BASE=".sisyphus/evidence/e2e-manual/$DATE"

curl -s http://localhost:8000/health > "$BASE/health-db.json"
curl -s http://localhost:8000/health/llm/supervisor > "$BASE/health-supervisor.json"
curl -s http://localhost:8000/health/llm/exaone > "$BASE/health-exaone.json"
curl -s http://localhost:8000/health/embedding > "$BASE/health-embedding.json"
```

### 8.3 E2E 테스트 결과 저장

**분쟁 상담 테스트:**
```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부",
    "chat_type": "dispute",
    "debug": true,
    "top_k": 5
  }' > "$BASE/chat-dispute.json"
```

**일반 상담 테스트:**
```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "환불 받을 수 있나요?",
    "chat_type": "general",
    "debug": true,
    "top_k": 5
  }' > "$BASE/chat-general.json"
```

### 8.4 Backend 로그 저장

**Docker 사용 시:**
```bash
docker compose logs backend --no-color > "$BASE/backend.log"
```

**로컬 실행 시:**
```bash
cp backend/app.log "$BASE/backend.log"
```

### 8.5 결과 요약 확인

**저장된 파일 확인:**
```bash
ls -la "$BASE/"
```

**테스트 결과 요약:**
```bash
echo "=== E2E 테스트 결과 요약 ==="
echo "Health (DB): $(jq -r '.status' $BASE/health-db.json)"
echo "Health (Supervisor): $(jq -r '.status' $BASE/health-supervisor.json)"
echo "Health (EXAONE): $(jq -r '.status' $BASE/health-exaone.json)"
echo "Health (Embedding): $(jq -r '.status' $BASE/health-embedding.json)"
echo "Chat (Dispute) Sources: $(jq '.sources | length' $BASE/chat-dispute.json)"
echo "Chat (General) Sources: $(jq '.sources | length' $BASE/chat-general.json)"
```

---

## 🎯 테스트 성공 기준 체크리스트

| 항목 | 명령어 | 성공 기준 |
|------|--------|----------|
| DB 연결 | `curl localhost:8000/health` | `"status": "healthy"` |
| Supervisor LLM | `curl localhost:8000/health/llm/supervisor` | `"status": "healthy"` |
| Embedding | `curl localhost:8000/health/embedding` | `"status": "healthy"` |
| 검색 API | `curl localhost:8000/search -d ...` | 결과 1개 이상 |
| 채팅 API | `curl localhost:8000/chat -d ...` | 답변 생성 |
| Frontend | `http://localhost:5173` | 페이지 로드 |
| E2E 분쟁상담 | 복잡한 법률 질의 | 출처 포함 답변 |
| Retrieval 병렬 | `debug: true` + node_timings | 3개 Agent 타이밍 기록 |
| Fallback 동작 | EXAONE 없이 테스트 | gpt-4.1-nano로 답변 생성 |

---

## ⚠️ 문제 해결

### DB 연결 실패 (RDS)

**RDS 엔드포인트 직접 연결 테스트:**
```bash
psql -h <rds-endpoint> -U readonly_user -d ddoksori -c "SELECT 1;"
```

**확인 사항:**
- RDS 엔드포인트 주소가 올바른지 확인
- AWS 보안 그룹에서 현재 IP의 5432 포트 인바운드가 허용되어 있는지 확인
- Readonly 계정 권한이 올바른지 확인 (`GRANT SELECT ON ALL TABLES`)
- `backend/.env`의 `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` 값 확인

### Backend 시작 실패

**로그 확인:**
```bash
docker compose logs backend --tail 50
```

> **일반적인 원인:** `.env` 파일 누락 또는 API 키 오류

### Frontend 연결 오류

**Backend URL 확인:**
```bash
grep VITE_API frontend/.env
```

**CORS 설정 확인:**
```bash
grep CORS_ORIGINS backend/.env
```
