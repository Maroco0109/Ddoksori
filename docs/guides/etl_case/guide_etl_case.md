# 팀원 B 가이드 - 사례/상담 ETL + 임베딩 + 검색 최적화

> **역할**: 사례/상담 데이터 ETL, 임베딩 생성, 하이브리드 검색 최적화
> **최종 수정**: 2026-01-16

---

## 1. 역할 개요

팀원 B는 ddoksori 시스템의 **검색 인프라**를 담당합니다.

### 주요 책임
- 분쟁 사례(KCA/ECMC/KCDRC) 데이터 적재
- 상담 사례(Counsel) 데이터 적재
- 전체 데이터 임베딩 생성 (KURE-v1, 1024차원)
- 하이브리드 검색 튜닝 (Dense + Lexical + RRF)
- 검색 성능 벤치마크

---

## 2. 담당 파일 목록

### 2.1 데이터 로딩 스크립트 (backend/scripts/data_loading/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `load_cases_to_db.py` | 분쟁/상담 사례 DB 적재 | ★★★ |
| `embed_all_data.py` | 모든 청크 임베딩 생성 | ★★★ |
| `load_all_test_data.py` | 통합 데이터 로딩 오케스트레이터 | ★★★ |
| `embed_law_units_v2.py` | 법령 청크 임베딩 (팀원 A 협업) | ★★☆ |
| `batch_loader.py` | 재사용 가능한 배치 처리 유틸 | ★★☆ |

### 2.2 검색 관련 (backend/rag/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `hybrid_retriever.py` | Dense + Lexical + RRF 퓨전 | ★★★ |
| `specialized_retrievers.py` | 4섹션 구조화 검색기 | ★★★ |
| `retriever.py` | 기본 RAGRetriever (벡터 검색) | ★★☆ |

### 2.3 테스트/검증 (backend/scripts/testing/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `validate_hybrid_retrieval.py` | 하이브리드 검색 검증 | ★★★ |

---

## 3. 파일별 상세 설명

### 3.1 load_cases_to_db.py - 분쟁/상담 사례 적재

**위치**: `backend/scripts/data_loading/load_cases_to_db.py`

#### A) Counsel 데이터 (소비자 상담 기록)

**입력 파일**: `backend/data/counsel/counsel.jsonl`

**사용법**:
```bash
conda activate dsr
python backend/scripts/data_loading/load_cases_to_db.py \
  --counsel backend/data/counsel/counsel.jsonl
```

**정규화 규칙**:
| 필드 | 변환 |
|------|------|
| `doc_id` | 상담 고유 ID |
| `doc_type` | `'counsel_case'` |
| `source_org` | `'consumer.go.kr'` |
| `category_path` | 카테고리 분할 (예: ["금융", "신용카드"]) |
| `chunk_type` | `'problem'`, `'solution'`, `'full'` |

#### B) Dispute 데이터 (중재 사례)

**입력 파일**:
```
backend/data/dispute/
├── kca.jsonl      (~909 사례)
├── ecmc.jsonl     (~811 사례)
└── kcdrc.jsonl    (~295 사례)
```

**사용법**:
```bash
# KCA 사례
python backend/scripts/data_loading/load_cases_to_db.py \
  --dispute backend/data/dispute/kca.jsonl --agency kca

# ECMC 사례
python backend/scripts/data_loading/load_cases_to_db.py \
  --dispute backend/data/dispute/ecmc.jsonl --agency ecmc

# KCDRC 사례
python backend/scripts/data_loading/load_cases_to_db.py \
  --dispute backend/data/dispute/kcdrc.jsonl --agency kcdrc
```

**정규화 규칙**:
| 필드 | 변환 |
|------|------|
| `doc_id` | `"{agency}_{case_no}_{case_index}"` |
| `doc_type` | `'mediation_case'` |
| `chunk_type` | `'facts'`, `'claims'`, `'mediation_outcome'`, `'judgment'` |

**적재 대상 테이블**:
```sql
-- documents
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT,          -- 'counsel_case', 'mediation_case'
    title TEXT,
    source_org TEXT,        -- 'consumer.go.kr', 'KCA', 'ECMC', 'KCDRC'
    category_path TEXT[],
    metadata JSONB
);

-- chunks
CREATE TABLE chunks (
    chunk_id SERIAL PRIMARY KEY,
    doc_id TEXT REFERENCES documents(doc_id),
    chunk_index INT,
    chunk_total INT,
    chunk_type TEXT,
    content TEXT,
    content_length INT,
    embedding vector(1024)  -- pgvector
);
```

---

### 3.2 embed_all_data.py - 임베딩 생성

**위치**: `backend/scripts/data_loading/embed_all_data.py`

**역할**: 모든 청크에 1024차원 KURE-v1 임베딩 추가

**사용법**:
```bash
conda activate dsr
python backend/scripts/data_loading/embed_all_data.py
```

**프로세스**:
```
1. SELECT chunks WHERE embedding IS NULL (우선순위 정렬)
   - counsel_case, mediation_case (먼저)
   - criteria, law (나중)

2. 배치 요청 (50개씩)
   POST http://localhost:5000/embedding
   {
     "texts": ["청크1 내용", "청크2 내용", ...]
   }

3. UPDATE chunks SET embedding = 벡터 값

4. REFRESH MATERIALIZED VIEW mv_searchable_chunks
```

**임베딩 API**:
- Docker 환경: `http://localhost:5000/embedding`
- 로컬 환경: `.env`의 `EMBEDDING_API_URL`

**특징**:
- 실패 시 3회 재시도
- 진행률 표시
- 배치 자동 갱신

---

### 3.3 load_all_test_data.py - 통합 데이터 로딩

**위치**: `backend/scripts/data_loading/load_all_test_data.py`

**역할**: 모든 데이터 소스 일괄 적재

**사용법**:
```bash
conda activate dsr

# 모든 데이터 적재
python backend/scripts/data_loading/load_all_test_data.py --all

# 특정 데이터만
python backend/scripts/data_loading/load_all_test_data.py --counsel
python backend/scripts/data_loading/load_all_test_data.py --dispute
python backend/scripts/data_loading/load_all_test_data.py --criteria

# 옵션
python backend/scripts/data_loading/load_all_test_data.py --all \
  --batch-size 500 \
  --skip-existing \
  --output-dir ./reports
```

**적재 순서**:
1. Counsel 데이터 (~18,000 문서 → ~62,851 청크)
2. Dispute 데이터 (~2,000 문서 → ~6,000 청크)
3. Criteria 데이터 (7 파일 → ~507 청크)

**출력 리포트**:
```json
{
  "timestamp": "2026-01-16T...",
  "duration_seconds": 45.23,
  "summary": {
    "total_documents": 20000,
    "total_chunks": 69000,
    "total_errors": 0
  },
  "performance": {
    "documents_per_second": 442.1
  }
}
```

---

### 3.4 hybrid_retriever.py - 하이브리드 검색

**위치**: `backend/rag/hybrid_retriever.py`

**역할**: Dense(벡터) + Lexical(FTS) + RRF 퓨전

**핵심 클래스**:
```python
class HybridRetriever:
    def search(
        self,
        query: str,
        top_k: int = 10,
        dense_weight: float = 0.6,
        lexical_weight: float = 0.4,
        doc_types: List[str] = None,
        rrf_k: int = 60
    ) -> List[SearchResult]
```

**RRF (Reciprocal Rank Fusion) 공식**:
```
RRF_score = Σ (1 / (k + rank_i))
```
- `k`: smoothing 파라미터 (기본값 60)
- `rank_i`: 각 검색 방식에서의 순위

**튜닝 포인트**:
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `dense_weight` | 0.6 | 벡터 검색 가중치 |
| `lexical_weight` | 0.4 | 텍스트 검색 가중치 |
| `rrf_k` | 60 | RRF smoothing |
| `top_k` | 10 | 최종 반환 개수 |

---

### 3.5 specialized_retrievers.py - 4섹션 검색기

**위치**: `backend/rag/specialized_retrievers.py`

**역할**: 4개 섹션별 전문 검색기

**클래스 구조**:
```python
class LawRetriever:
    """법령 2단계 검색 (stage1: 항/호/목, stage2: 상위 조)"""
    def search(self, query: str, top_k: int = 5) -> List[LawResult]

class CriteriaRetriever:
    """분쟁조정기준 2단계 검색"""
    def search(self, query: str, top_k: int = 5) -> List[CriteriaResult]

class CaseRetriever:
    """분쟁조정사례 & 상담사례 분리 검색"""
    def search_disputes(self, query: str, top_k: int = 5) -> List[DisputeResult]
    def search_counsels(self, query: str, top_k: int = 5) -> List[CounselResult]

class StructuredRetriever:
    """4개 섹션 통합 검색"""
    def search_all_sections(self, query: str) -> Dict[str, Any]
```

**StructuredRetriever.search_all_sections() 반환값**:
```python
{
    'agency': {
        'code': 'KCA',
        'name': '한국소비자원',
        'url': '...',
        'phone': '1372'
    },
    'disputes': [...],    # 분쟁조정사례 Top-5
    'counsels': [...],    # 상담사례 Top-5
    'laws': [...],        # 관련 법령 Top-5
    'criteria': [...]     # 관련 기준 Top-5
}
```

---

### 3.6 validate_hybrid_retrieval.py - 검색 검증

**위치**: `backend/scripts/testing/validate_hybrid_retrieval.py`

**역할**: 임베딩된 데이터의 검색 성능 테스트

**사용법**:
```bash
conda activate dsr
python backend/scripts/testing/validate_hybrid_retrieval.py
```

**테스트 항목**:
1. Lexical search (FTS) 동작 확인
2. Dense search (Vector) 동작 확인
3. Hybrid search (RRF 퓨전) 동작 확인
4. 각 검색 방식 결과 비교

---

## 4. 테스트 스크립트

### 4.1 하이브리드 검색 검증
```bash
conda activate dsr
python backend/scripts/testing/validate_hybrid_retrieval.py
```

### 4.2 동시성 테스트
```bash
# Note: test_api_concurrent.py was removed in test refactoring (branch refactor/47-test-refactor)
# Use the following E2E tests for validation instead:
cd backend
python -m pytest scripts/testing/e2e/test_merged_graph.py -v -p no:asyncio
```

**테스트 항목**:
- E2E 시스템 통합 테스트
- 검색 및 답변 생성 파이프라인 검증

### 4.3 전체 데이터 로딩 테스트
```bash
python backend/scripts/data_loading/load_all_test_data.py --all
```

### 4.4 사례 로딩 테스트
```bash
cd backend
python -m pytest scripts/evaluation/test_load_cases.py -v -p no:asyncio
```

---

## 5. 평가 스크립트

### 5.1 성능 벤치마크
```bash
conda activate dsr
cd backend
python -m scripts.evaluation.benchmark_performance \
  --url http://localhost:8000
```

**벤치마크 지표**:
| 지표 | 목표값 | 설명 |
|------|--------|------|
| p50 (중앙값) | < 0.3초 | 50번째 백분위수 응답 시간 |
| p95 | < 0.5초 | 95번째 백분위수 |
| p99 | < 1.0초 | 99번째 백분위수 |
| Throughput | > 20 req/sec | 초당 처리 요청 수 |

**출력 예시**:
```json
{
  "latency": {
    "p50_ms": 245.3,
    "p95_ms": 412.8,
    "p99_ms": 678.2
  },
  "throughput": {
    "requests_per_second": 28.5
  }
}
```

---

## 6. 완료 기준

| 지표 | 목표값 | 확인 방법 |
|------|--------|----------|
| 임베딩 완료 | ~74,858 청크 | DB 쿼리 확인 |
| embedding null | 0 | `SELECT COUNT(*) FROM chunks WHERE embedding IS NULL;` |
| API p50 | < 0.3초 | `benchmark_performance.py` 실행 |
| Throughput | > 20 req/sec | `benchmark_performance.py` 실행 |

---

## 7. 데이터 규모

| 도메인 | 원본 파일 | 예상 문서 | 예상 청크 |
|--------|----------|----------|----------|
| 상담 (Counsel) | `counsel/counsel.jsonl` | ~13,544건 | ~62,851 |
| 분쟁 (Dispute) | `dispute/*.jsonl` | ~2,015건 | ~6,045 |
| **합계** | | ~15,559건 | ~68,896 |

---

## 8. 주차별 작업

### 1주차
- [ ] 사례/상담 JSONL 분석
- [ ] `case_pipeline.py` 구현
- [ ] 임베딩 파이프라인 실행
- [ ] 데이터 검증

### 2주차
- [ ] 하이브리드 검색 튜닝
- [ ] 2단계 검색 최적화
- [ ] 검색 벤치마크
- [ ] 캐싱 적용

### 3주차
- [ ] 검색 최종 튜닝
- [ ] 캐싱/성능 최적화
- [ ] 문서화

---

## 9. 데이터 파이프라인 흐름도

```
JSONL (Counsel + Dispute)
    ↓
load_cases_to_db.py (정규화, 재인덱싱)
    ↓
┌─────────────────┬─────────────────┐
│   documents     │    chunks       │
│ (문서 메타)     │ (검색용 청크)   │
└─────────────────┴─────────────────┘
    ↓
embed_all_data.py (배치 임베딩)
    ↓
chunks.embedding (1024차원 벡터)
    ↓
┌─────────────────────────────────────┐
│  validate_hybrid_retrieval.py       │
│  (하이브리드 검색 검증)             │
└─────────────────────────────────────┘
    ↓
benchmark_performance.py (성능 측정)
```

---

## 10. 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 프로젝트 계획서 | `/plans/plans.md` | 전체 3주 계획 |
| 임베딩 가이드 | `/docs/guides/embedding_process_guide.md` | 임베딩 상세 |
| RAG 아키텍처 | `/docs/guides/system_architecture.md` | 시스템 구조 |
| 테스트 가이드 | `/docs/backend/scripts/TEST_README.md` | 테스트 방법 |

---

## 11. 자주 사용하는 명령어 모음

```bash
# 환경 활성화
conda activate dsr

# 전체 데이터 로딩
python backend/scripts/data_loading/load_all_test_data.py --all

# 개별 데이터 로딩
python backend/scripts/data_loading/load_all_test_data.py --counsel
python backend/scripts/data_loading/load_all_test_data.py --dispute

# Counsel 사례 로딩
python backend/scripts/data_loading/load_cases_to_db.py \
  --counsel backend/data/counsel/counsel.jsonl

# Dispute 사례 로딩 (각 기관별)
python backend/scripts/data_loading/load_cases_to_db.py \
  --dispute backend/data/dispute/kca.jsonl --agency kca

# 임베딩 생성
python backend/scripts/data_loading/embed_all_data.py

# 하이브리드 검색 검증
python backend/scripts/testing/validate_hybrid_retrieval.py

# 성능 벤치마크
python -m scripts.evaluation.benchmark_performance --url http://localhost:8000

# E2E 테스트 (backend 디렉토리에서)
# Note: test_api_concurrent.py was removed in test refactoring
cd backend
python -m pytest scripts/testing/e2e/test_merged_graph.py -v -p no:asyncio

# DB 확인 (임베딩 현황)
docker exec -it ddoksori_db psql -U postgres -d ddoksori -c \
  "SELECT doc_type, COUNT(*), COUNT(embedding) as with_embedding FROM chunks c JOIN documents d ON c.doc_id = d.doc_id GROUP BY doc_type;"

# 임베딩 null 개수 확인
docker exec -it ddoksori_db psql -U postgres -d ddoksori -c \
  "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL;"
```

---

## 12. 검색 튜닝 팁

### Dense vs Lexical 가중치 조정
```python
# hybrid_retriever.py에서 조정
retriever = HybridRetriever()
results = retriever.search(
    query="헬스장 환불",
    dense_weight=0.7,   # 의미 기반 검색 강화
    lexical_weight=0.3  # 키워드 매칭 약화
)
```

### 검색 결과 개수 조정
```python
# specialized_retrievers.py에서 조정
class StructuredRetriever:
    def search_all_sections(self, query: str):
        disputes = self.case_retriever.search_disputes(query, top_k=5)
        counsels = self.case_retriever.search_counsels(query, top_k=5)
        laws = self.law_retriever.search(query, top_k=5)
        criteria = self.criteria_retriever.search(query, top_k=3)
```

