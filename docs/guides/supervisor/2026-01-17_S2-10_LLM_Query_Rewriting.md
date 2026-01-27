# S2-10: LLM 기반 쿼리 재작성 (Phase 3)

**작성일**: 2026-01-17
**담당**: AI/MAS System Engineer
**상태**: 완료

## 개요

복잡한 법률 용어가 포함된 사용자 쿼리를 EXAONE 3.5 2.4B를 사용하여 일상어로 변환하는 기능 구현. 검색 품질 향상을 목표로 하며, 100ms 하드 타임아웃으로 지연시간 제약을 보장.

### 목표

- 검색 정확도: 60-70% (Phase 1 규칙 기반) → 85-95%
- 지연시간: ≤100ms (하드 타임아웃)
- 캐시 히트율: ≥60%

## 아키텍처

```
User Query: "청약철회권 행사가 가능한가요?"
     ↓
[Complexity Check] ─── Simple Query ───→ Rule-based expansion (Phase 1)
     │
     └─── Complex Query ───→ [Cache Check]
                                  │
                      ┌──── Hit ──┴── Miss ────┐
                      ↓                        ↓
               Return cached            EXAONE rewrite (90ms timeout)
                                              ↓
                                        Cache result
                                              ↓
                              "구매 취소 환불 받을 수 있나요"
                                              ↓
                              Continue with rewritten query
```

## 구현 내용

### 1. QueryCache (`backend/app/llm/query_cache.py`)

LRU 캐시 + Pre-seeded 법률 용어 매핑.

```python
from app.llm import QueryCache

cache = QueryCache(maxsize=1000)

# Pre-seeded 법률 용어 자동 로드
cache.get("청약철회")  # → "구매 취소 환불"
cache.get("손해배상")  # → "피해 보상"

# 커스텀 캐싱
cache.set("복잡한 쿼리", "간단한 쿼리")
```

**Pre-seeded 법률 용어 (50+)**:

| 법률 용어 | 일상어 변환 |
|-----------|-------------|
| 청약철회 | 구매 취소 환불 |
| 채무불이행 | 약속 안 지킴 계약 위반 |
| 하자담보책임 | 불량 제품 수리 교환 |
| 손해배상 | 피해 보상 |
| 계약해제 | 계약 취소 |
| 위약금 | 취소 수수료 벌금 |
| 소멸시효 | 청구 기한 만료 |
| 전자상거래 | 온라인 쇼핑 인터넷 구매 |

### 2. QueryRewriter (`backend/app/llm/query_rewriter.py`)

EXAONE 기반 쿼리 재작성기.

```python
from app.llm import get_query_rewriter

rewriter = get_query_rewriter()  # 싱글톤

# 복잡도 판단
if rewriter.is_complex_query("청약철회권 행사 가능한가요", "dispute"):
    # LLM 재작성 (90ms 타임아웃)
    result = rewriter.rewrite("청약철회권 행사 가능한가요", {
        'query_type': 'dispute',
        'keywords': ['청약철회권', '행사']
    })
    # → "구매 취소 환불 가능한가요"
```

**복잡도 판단 기준**:

1. 법률 용어 1개 이상 포함 (LEGAL_TERMS 100+개)
2. 쿼리 길이 50자 초과
3. 격식체 종결 표현 (입니다, 습니다, 하는지, 인지, 여부)

**타임아웃 처리**:

```python
async def rewrite_with_timeout(self, query, context):
    try:
        result = await asyncio.wait_for(
            self._call_exaone(query, context),
            timeout=0.09  # 90ms
        )
        return result
    except asyncio.TimeoutError:
        # 규칙 기반 폴백
        return self._rule_based_rewrite(query, context)
```

### 3. Query Analysis 통합 (`backend/app/orchestrator/nodes/query_analysis.py`)

`_expand_query_by_type()` 함수에 LLM 재작성 통합.

```python
def _expand_query_by_type(
    query: str,
    query_type: Literal['dispute', 'general', 'law', 'criteria'],
    onboarding: Optional[OnboardingInfo],
    extracted_info: Dict[str, str],
    keywords: List[str],
    use_llm: bool = True  # NEW
) -> tuple[str, str]:
    # S2-10: LLM 기반 쿼리 재작성 시도
    if use_llm and USE_LLM_REWRITE and LLM_REWRITE_AVAILABLE:
        rewriter = get_query_rewriter()
        if rewriter.is_complex_query(query, query_type):
            llm_rewritten = rewriter.rewrite(query, {...})
            if llm_rewritten:
                return llm_rewritten, "llm_rewrite: ..."

    # 기존 규칙 기반 확장 (Phase 1)
    # ...
```

## 환경 변수 설정

```bash
# .env 파일

# 쿼리 재작성 기능 활성화 (기본: false)
QUERY_REWRITE_ENABLED=true

# 캐시 크기 (기본: 1000)
QUERY_REWRITE_CACHE_SIZE=1000

# LLM 호출 타임아웃 (기본: 90ms)
QUERY_REWRITE_TIMEOUT=90

# 총 지연시간 예산 (기본: 100ms)
QUERY_REWRITE_TOTAL_BUDGET=100

# LLM 트리거 최소 복잡도 (기본: 1)
QUERY_REWRITE_MIN_COMPLEXITY=1
```

## 지연시간 예산

| 단계 | 목표 | 비고 |
|------|------|------|
| 복잡도 체크 | 1-5ms | 문자열 매칭 |
| 캐시 조회 | 1-2ms | 인메모리 해시 |
| EXAONE 호출 | ≤90ms | 하드 타임아웃 |
| 캐시 히트 총합 | ≤10ms | 빠른 경로 |
| 캐시 미스 총합 | ≤100ms | 타임아웃 보장 |

## 테스트

### 테스트 실행

```bash
PYTHONPATH=/home/maroco/LLM/backend \
python -m pytest scripts/testing/orchestrator/test_query_rewriter.py -v
```

### 테스트 커버리지 (29개 테스트)

| 카테고리 | 테스트 수 | 설명 |
|----------|-----------|------|
| QueryCache | 6 | 캐시 동작, LRU, 스레드 안전성 |
| Complexity | 6 | 복잡도 판단 로직 |
| Rule-based | 3 | 규칙 기반 폴백 |
| LLM Integration | 4 | LLM 호출, 에러 처리 |
| Latency | 2 | 지연시간 제약 |
| Stats | 1 | 통계 반환 |
| Singleton | 1 | 싱글톤 패턴 |
| Legal Terms | 4 | 용어 목록 완전성 |
| System Prompt | 2 | 프롬프트 검증 |

## 시스템 프롬프트

```
당신은 소비자 분쟁 상담 검색 시스템의 쿼리 변환기입니다.
사용자의 법률 용어나 복잡한 표현을 일반인이 사용하는 쉬운 한국어로 변환하세요.

규칙:
1. 법률 용어를 일상어로: 청약철회권 → 구매 취소, 채무불이행 → 약속 안 지킴
2. 핵심 키워드 유지: 품목명, 금액, 기간 등
3. 검색에 최적화된 짧은 문장으로 변환 (10-30자)
4. 원래 의도를 왜곡하지 않음
5. 반드시 변환된 쿼리만 출력 (설명 없이)

예시:
입력: "전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부"
출력: 온라인 쇼핑 구매 취소 환불 가능한지
```

## 파일 구조

```
backend/
├── app/
│   ├── llm/
│   │   ├── __init__.py           # 모듈 exports (수정)
│   │   ├── exaone_client.py      # S2-8 기존
│   │   ├── query_cache.py        # NEW: LRU 캐시
│   │   └── query_rewriter.py     # NEW: 쿼리 재작성기
│   └── orchestrator/
│       └── nodes/
│           └── query_analysis.py # LLM 통합 (수정)
├── scripts/
│   └── testing/
│       └── orchestrator/
│           └── test_query_rewriter.py  # NEW: 테스트
└── .env.example                  # 설정 추가 (수정)
```

## 롤아웃 전략

1. **Feature Flag**: `QUERY_REWRITE_ENABLED=false` 기본값
2. **단계적 활성화**: 10% → 50% → 100%
3. **모니터링**: 지연시간, 캐시 히트율, LLM 에러율
4. **A/B 테스트**: LLM 재작성 vs 규칙 기반 검색 품질 비교

## 의존성

- EXAONE 3.5 2.4B (S2-8에서 배포됨)
- `ExaoneLLMClient` 클래스 (기존)
- RunPod/Local GPU 폴백 (기존)

## 관련 PR

- S2-8: EXAONE 3.5 2.4B 통합
- S2-9: BGE-M3 Sparse 통합
