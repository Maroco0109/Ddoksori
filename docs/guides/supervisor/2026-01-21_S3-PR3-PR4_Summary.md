# S3-PR3 + S3-PR4 완성 요약

> **작성일**: 2026-01-21
> **상태**: ✅ 완료 (테스트 28개 통과)

---

## 📋 개요

Sprint 3에서 **하이브리드 도구 선택(@tool calling)** 과 **A/B 테스트 프레임워크**를 완성했습니다.

이를 통해 다음을 달성했습니다:
- ✅ 도구 선택의 **유연성** 및 **확장성** 향상 (규칙 기반 + LLM 기반)
- ✅ 모델/프롬프트 변경 효과를 **정량적으로 측정** 가능
- ✅ 의사결정 근거 확보를 위한 **통계적 검증** 인프라 구축

---

## 🎯 S3-PR3: 하이브리드 도구 선택

### 핵심 구성

| 항목 | 설명 |
|:---|:---|
| **기본 모드** | 규칙 기반 (ActionRegistry) - 안정성 우선 |
| **선택 모드** | LLM 기반 (@tool 데코레이터) - 유연성 |
| **모드 전환** | 환경 변수 `USE_LLM_TOOLS` |
| **폴백** | LLM 실패/타임아웃 시 즉시 규칙 기반으로 복구 |

### 구현 파일

```
backend/
├── app/agents/react/
│   ├── tools.py                    # @tool 데코레이터 (4가지 도구)
│   └── react_act.py                # HybridToolExecutor
├── app/llm/
│   └── tool_calling_client.py      # LLM 클라이언트 (bind_tools 지원)
├── .env.example                    # 환경 변수
└── scripts/testing/
    ├── test_hybrid_tools.py        # 통합 테스트 (28개) ✅
    └── test_runpod_tool_calling.py # RunPod 연동 테스트 (14개) ✅
```

### 테스트 결과

```bash
# S3-PR3 하이브리드 테스트: 28/28 통과 ✅
pytest backend/scripts/testing/test_hybrid_tools.py -v

# RunPod 도구 선택 테스트: 14/14 통과 ✅
pytest backend/scripts/testing/test_runpod_tool_calling.py -v
```

**테스트 항목**:
- ✅ 클라이언트 초기화
- ✅ 헬스체크 (성공/실패/타임아웃)
- ✅ 가용성 캐싱
- ✅ 도구 바인딩
- ✅ 폴백 메커니즘
- ✅ 정확도 측정
- ✅ 지연시간 측정 (< 10ms)
- ✅ E2E 통합 시나리오

### 환경 변수

```bash
# .env 설정
USE_LLM_TOOLS=false                 # true: LLM 기반, false: 규칙 기반 (기본)
LLM_TOOL_TIMEOUT_MS=5000            # LLM 도구 선택 타임아웃
EXAONE_RUNPOD_URL=http://...        # RunPod vLLM 서버
EXAONE_RUNPOD_API_KEY=...           # RunPod API 키
```

### 배포 단계

| 단계 | 기간 | 비율 | 활동 |
|:---|:---:|:---:|:---|
| Phase 1 | 1-2주 | 0% | @tool 준비, 테스트 |
| Phase 2 | 1개월 | 5-10% | 복잡한 쿼리에만 LLM 적용 |
| Phase 3 | 1-2개월 | 50%+ | 안정성 확인 후 확대 |
| Phase 4 | 지속 | 100% | 완전 자율 (규칙은 Fallback) |

---

## 📊 S3-PR4: A/B 테스트 프레임워크

### 핵심 기능

| 기능 | 설명 |
|:---|:---|
| **실험 생성** | 실험명, Variant, 트래픽 분배 설정 |
| **Variant 할당** | 일관된 할당 (MD5 해싱 기반) |
| **메트릭 기록** | 실험 결과 자동 기록 |
| **리포트** | Variant별 메트릭 집계 및 비교 |

### 구현 파일

```
backend/
├── app/experiments/
│   ├── manager.py                  # ABTestManager (핵심 로직)
│   ├── models.py                   # SQLAlchemy 모델
│   ├── routes.py                   # API 라우터
│   ├── schemas.py                  # Pydantic 스키마
│   └── dashboard_routes.py         # 대시보드 API 🆕
├── database/migrations/
│   └── 003_ab_testing_framework.sql # DB 마이그레이션
└── scripts/testing/
    └── test_ab_framework.py        # 통합 테스트 (10개) ✅
```

### 테스트 결과

```bash
# S3-PR4 A/B 테스트: 10/10 통과 ✅
pytest backend/scripts/testing/test_ab_framework.py -v
```

**테스트 항목**:
- ✅ 실험 생성 및 조회
- ✅ 일관된 variant 할당 (deterministic)
- ✅ 트래픽 분배 정확성 (1000명 시뮬레이션, 오차 < 5%)
- ✅ 메트릭 기록 및 조회
- ✅ 리포트 API 응답
- ✅ 성능: `get_variant` < 10ms
- ✅ 중복 처리
- ✅ 정확도 비교

### DB 스키마

```sql
-- 실험 정의
CREATE TABLE experiments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,    -- 실험명
    description TEXT,
    status VARCHAR(50),                   -- 'active', 'paused', 'completed'
    traffic_split_config JSONB,           -- {'A': 50, 'B': 50}
    created_at TIMESTAMP DEFAULT NOW()
);

-- 실험 결과
CREATE TABLE experiment_outcomes (
    id SERIAL PRIMARY KEY,
    experiment_id INTEGER REFERENCES experiments,
    subject_id VARCHAR(255),              -- 세션_id
    variant VARCHAR(50),                  -- 'A', 'B'
    metric_name VARCHAR(255),             -- 'accuracy', 'latency' 등
    metric_value FLOAT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(experiment_id, subject_id, metric_name)
);
```

### API 엔드포인트

**코어 API**:
- `POST /api/v1/experiments` - 실험 생성
- `GET /api/v1/experiments/{name}/variant` - Variant 할당
- `POST /api/v1/experiments/{name}/track` - 메트릭 기록
- `GET /api/v1/experiments/{name}/report` - 리포트 조회

**대시보드 API** 🆕:
- `GET /api/v1/experiments/dashboard/overview` - 전체 개요
- `GET /api/v1/experiments/dashboard/experiments` - 실험 목록
- `GET /api/v1/experiments/dashboard/experiments/{name}` - 실험 상세
- `GET /api/v1/experiments/dashboard/experiments/{name}/metrics` - 시계열 메트릭
- `GET /api/v1/experiments/dashboard/experiments/{name}/comparison` - Variant 비교
- `GET /api/v1/experiments/dashboard/experiments/{name}/stats` - 통계 분석

---

## 🔄 통합 활용 예시

### 시나리오: 도구 선택 모드 A/B 테스트

**Step 1: 실험 생성**
```python
manager.create_experiment(
    name="tool_calling_comparison",
    variants=["rule_based", "llm_based"],
    traffic_split={"rule_based": 50, "llm_based": 50}
)
```

**Step 2: 세션별 Variant 할당**
```python
variant = manager.get_variant("tool_calling_comparison", session_id)

if variant == "llm_based":
    os.environ['USE_LLM_TOOLS'] = 'true'  # LLM 모드 활성화
else:
    os.environ['USE_LLM_TOOLS'] = 'false' # 규칙 기반 모드
```

**Step 3: 메트릭 기록**
```python
manager.track_outcome(
    experiment_name="tool_calling_comparison",
    subject_id=session_id,
    metric_name="tool_selection_accuracy",
    metric_value=calculate_accuracy(response),
    metadata={"query_type": "dispute", "agency": "KCA"}
)
```

**Step 4: 결과 분석**
```python
# 1주일 후...
report = manager.get_report("tool_calling_comparison")

# 결과 예시
{
    "variants": {
        "rule_based": {
            "count": 500,
            "metrics": {"tool_selection_accuracy": 0.82}
        },
        "llm_based": {
            "count": 510,
            "metrics": {"tool_selection_accuracy": 0.88}
        }
    }
}

# 개선율: (0.88 - 0.82) / 0.82 = 7.3% ↑
```

---

## 📈 대시보드 API 활용

### 대시보드 개요 조회
```bash
curl http://localhost:8000/api/v1/experiments/dashboard/overview
```

응답:
```json
{
  "total_experiments": 3,
  "active_experiments": 2,
  "completed_experiments": 1,
  "total_subjects": 15000,
  "summary": [
    {
      "name": "tool_calling_comparison",
      "status": "active",
      "subjects": 1020
    }
  ]
}
```

### Variant 비교 분석
```bash
curl http://localhost:8000/api/v1/experiments/dashboard/experiments/tool_calling_comparison/comparison
```

응답:
```json
{
  "experiment": "tool_calling_comparison",
  "comparison": {
    "answer_quality": {
      "variant_a": "rule_based",
      "variant_b": "llm_based",
      "value_a": 0.82,
      "value_b": 0.88,
      "improvement": 0.0732,
      "winner": "llm_based",
      "stat_sig": true
    }
  }
}
```

---

## 📊 완료 기준 체크리스트

### S3-PR3 ✅

- ✅ `@tool` 데코레이터로 4가지 도구 재정의
- ✅ HybridToolExecutor 구현 (규칙 + LLM)
- ✅ 환경 변수로 모드 전환 가능
- ✅ 타임아웃/실패 시 자동 폴백
- ✅ E2E 테스트 28개 모두 통과
- ✅ Tool Use 정확도 측정 가능 (목표: 85%+)

### S3-PR4 ✅

- ✅ `experiments` 및 `experiment_outcomes` 테이블
- ✅ 일관된 variant 할당 (MD5 해싱)
- ✅ 트래픽 분배 정확성 (오차 < 5%)
- ✅ 메트릭 기록 및 조회 기능
- ✅ 리포트 API (각 variant별 메트릭 포함)
- ✅ `get_variant` 성능 < 10ms
- ✅ 통합 테스트 10개 모두 통과
- ✅ 대시보드 API (시각화 데이터) 🆕

---

## 🚀 실행 가이드

### 1. 환경 설정

```bash
cd backend

# 환경 변수 설정
export EXAONE_RUNPOD_URL=http://your-runpod-url/v1
export EXAONE_RUNPOD_API_KEY=your-api-key
export USE_LLM_TOOLS=false  # 기본: 규칙 기반
export LLM_TOOL_TIMEOUT_MS=5000
```

### 2. DB 마이그레이션

```bash
# 마이그레이션 적용
psql -U postgres -d ddoksori_dev -f backend/database/migrations/003_ab_testing_framework.sql
```

### 3. 테스트 실행

```bash
conda activate dsr
cd backend

# S3-PR3 테스트
pytest scripts/testing/test_hybrid_tools.py -v

# S3-PR4 테스트
pytest scripts/testing/test_ab_framework.py -v

# RunPod 도구 선택 테스트
pytest scripts/testing/test_runpod_tool_calling.py -v

# 전체 테스트
pytest scripts/testing/test_hybrid_tools.py scripts/testing/test_ab_framework.py scripts/testing/test_runpod_tool_calling.py -v
```

### 4. 서버 실행

```bash
# 기본 모드 (규칙 기반)
uvicorn app.main:app --reload

# LLM 기반 모드 (테스트용)
USE_LLM_TOOLS=true uvicorn app.main:app --reload
```

---

## 📦 주요 파일 변경 사항

### 신규 파일

```
backend/scripts/testing/test_runpod_tool_calling.py    # 14개 테스트
backend/app/experiments/dashboard_routes.py             # 대시보드 API
```

### 수정 파일

```
backend/app/agents/react/tools.py              # @tool 데코레이터 추가
backend/app/agents/react/react_act.py          # HybridToolExecutor 통합
backend/app/llm/tool_calling_client.py         # 헬스체크 로직 개선
backend/.env.example                           # 새 환경 변수 추가
```

---

## 🔍 주요 설계 결정사항

| 결정 | 근거 |
|:---|:---|
| **Subject ID: session_id** | 게스트 사용자도 일관성 유지 필요 |
| **Variant 할당: MD5 해싱** | 무상태 설계, 계산 비용 minimal |
| **모드 제어: 환경 변수** | 배포/운영 단순화 |
| **폴백: 즉시** | 법률 도메인에서 신뢰성 우선 |
| **대시보드: 별도 라우터** | API 계층화, 관심사 분리 |

---

## ⚠️ 주의사항

### 1. RunPod vLLM 설정

```bash
# RunPod 컨테이너 실행
docker run -it --gpus all \
  -p 8000:8000 \
  -v $PWD/models:/models \
  vllm/vllm-openai:latest \
  --model LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct
```

### 2. 대시보드 API 보안

```python
# 향후 추가: 인증 및 접근 제어
# - API 키 검증
# - Rate limiting
# - 데이터 마스킹 (개인정보)
```

### 3. 성능 최적화

```python
# 향후 고려사항:
# - 메트릭 캐싱 (Redis)
# - 배치 쓰기
# - 시계열 DB (InfluxDB/TimescaleDB)
```

---

## 📚 참고 문서

| 문서 | 경로 | 내용 |
|:---|:---|:---|
| 종합 가이드 | `/docs/guides/orchestration/2026-01-21_S3-PR3-PR4_Hybrid_Tools_and_AB_Testing.md` | 상세 구현 및 API 문서 |
| AI_MEMO | `/AI_MEMO.md` | 완료 항목 및 결정사항 |
| S3-PR3 상세 | `/docs/plans/S3-PR3.md` | @tool 도입 기술 상세 |
| S3-PR4 상세 | `/docs/plans/S3-PR4.md` | A/B 테스트 기술 상세 |

---

## ✅ 완료 현황

| PR | 항목 | 상태 | 테스트 |
|:---|:---|:---:|:---:|
| S3-PR3 | 하이브리드 도구 선택 | ✅ 완료 | 28/28 |
| S3-PR4 | A/B 테스트 프레임워크 | ✅ 완료 | 10/10 |
| 확장 | 대시보드 API | ✅ 완료 | - |
| 확장 | RunPod 도구 선택 테스트 | ✅ 완료 | 14/14 |
| **합계** | | **✅ 완료** | **52/52** |

---

## 🎯 다음 단계 (Next Actions)

### 즉시 (Week 1)
1. ✅ 프로덕션 환경 변수 설정
2. 실제 RunPod vLLM 서버 연동 테스트
3. 대시보드 프론트엔드 구현 검토

### 단기 (Week 2-3)
1. 도구 선택 모드 A/B 실험 라이브 시작 (5% 트래픽)
2. 메트릭 수집 및 통계 분석
3. 성능/정확도 리포트 작성

### 중기 (Month 2)
1. 추가 실험 설계 (임베딩 모델, LLM 모델 비교)
2. 대시보드 시각화 고도화
3. 통계 검증 추가 (t-test, chi-square)

---

**작성일**: 2026-01-21  
**최종 상태**: ✅ 완료  
**테스트 결과**: 52/52 통과
