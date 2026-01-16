# 팀원 A 가이드 - 법령/기준 ETL + Retrieval + 평가 시스템

> **역할**: 법령/기준 데이터 ETL, Retrieval Node, 평가 시스템 구축
> **최종 수정**: 2026-01-16

---

## 1. 역할 개요

팀원 A는 ddoksori 시스템의 **데이터 기반**을 담당합니다.

### 주요 책임
- 법령 데이터 XML 파싱 및 DB 적재
- 분쟁조정기준(criteria) 데이터 적재
- Retrieval Node 개선
- 평가 시스템(Golden Set) 구축 및 지표 측정
- 데이터 품질 검증

---

## 2. 담당 파일 목록

### 2.1 법령 ETL 스크립트 (backend/data/law/scripts/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `law_xml_parser_v2.py` | XML 파싱, 계층 구조 보존 | ★★★ |
| `load_law_to_db_v2.py` | law_units + documents/chunks 동시 적재 | ★★★ |
| `load_law_jsonl_v2.py` | JSONL 형식 법령 적재 | ★★☆ |
| `law_chunking_strategy.py` | 청킹 전략 정의 (indexable 판단) | ★★☆ |
| `law_schema_v2.sql` | 스키마 정의 (laws, law_units) | ★☆☆ |

### 2.2 기준 ETL 스크립트 (backend/scripts/data_loading/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `load_criteria_to_db.py` | 분쟁조정기준 DB 적재 | ★★★ |

### 2.3 Retrieval 관련 (backend/app/orchestrator/nodes/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `retrieval.py` | Retrieval 노드 (4섹션 검색 호출) | ★★★ |

### 2.4 평가 스크립트 (backend/scripts/evaluation/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `run_evaluation.py` | Retrieval 품질 평가 (nDCG, MRR) | ★★★ |
| `evaluate_query_analysis.py` | Query Analysis 평가 | ★★☆ |
| `verify_loaded_data.py` | 데이터 로딩 검증 | ★★☆ |

---

## 3. 파일별 상세 설명

### 3.1 law_xml_parser_v2.py - XML 파싱

**위치**: `backend/data/law/scripts/law_xml_parser_v2.py`

**역할**: 법령 XML → 구조화된 노드 리스트 변환

**핵심 함수**:
```python
def parse_xml_to_nodes(xml_path: str, strategy: Optional[ChunkingStrategy] = None) -> List[Dict[str, Any]]
```

**출력 노드 구조**:
```python
{
    'law_id': 'E_Commerce_Consumer_Law',
    'doc_id': 'E_Commerce_Consumer_Law|A1',  # law_id|조항ID
    'parent_id': None,                        # 계층 참조
    'level': 'article',                       # article/paragraph/item/subitem
    'article_no': '제1조',
    'text': '이 법은...',
    'is_indexable': True,                     # 검색 대상 여부
    'path': '제1장 > 제1조',
    'section_path': ['제1장', '제1절'],
    'amendment_note': '신설 2020.1.1'
}
```

**계층 구조**:
```
법령 (Law)
├── 편 (Part)
│   ├── 장 (Chapter)
│   │   ├── 절 (Section)
│   │   │   ├── 조 (Article) ← level='article'
│   │   │   │   ├── 항 (Paragraph) ← level='paragraph'
│   │   │   │   │   ├── 호 (Item) ← level='item'
│   │   │   │   │   │   └── 목 (Subitem) ← level='subitem'
```

---

### 3.2 load_law_to_db_v2.py - 법령 DB 적재

**위치**: `backend/data/law/scripts/load_law_to_db_v2.py`

**사용법**:
```bash
conda activate dsr

# 단일 XML 파일 적재
python backend/data/law/scripts/load_law_to_db_v2.py /path/to/E_Commerce_Consumer_Law.xml

# 폴더 내 모든 XML 일괄 적재
python backend/data/law/scripts/load_law_to_db_v2.py --all backend/data/law/raw/law_rawdata
```

**적재 대상 테이블**:

| 테이블 | 역할 | 주요 컬럼 |
|--------|------|----------|
| `laws` | 법령 메타데이터 | law_id, law_name, ministry, enforcement_date |
| `law_units` | 조문 계층 구조 | doc_id, law_id, parent_id, level, text |
| `documents` | RAG 문서 (법령당 1개) | doc_id, doc_type='law' |
| `chunks` | 검색용 청크 | chunk_id, doc_id, content, embedding |
| `chunk_relations` | 계층 관계 | parent_chunk_id, child_chunk_id |

**핵심 동작**:
1. XML 파싱 → 노드 리스트 생성
2. `SET CONSTRAINTS ALL DEFERRED` (FK 지연)
3. laws 테이블 UPSERT
4. law_units 테이블 COPY 삽입
5. documents/chunks 동시 적재
6. orphaned nodes 검증

---

### 3.3 load_criteria_to_db.py - 기준 데이터 적재

**위치**: `backend/scripts/data_loading/load_criteria_to_db.py`

**입력 파일** (backend/data/criteria/jsonl/):
```
├── consumer_dispute_resolution_criteria_table1_items.jsonl
├── consumer_dispute_resolution_criteria_table2_resolutions.jsonl
├── consumer_dispute_resolution_criteria_table3_warranty.jsonl
├── consumer_dispute_resolution_criteria_table4_lifespan.jsonl
├── ecommerce_guideline.jsonl
└── content_guideline.jsonl
```

**사용법**:
```bash
conda activate dsr
python backend/scripts/data_loading/load_criteria_to_db.py
```

**적재 대상 테이블**:

| 테이블 | 역할 |
|--------|------|
| `criteria_units` | 구조화된 기준 정보 (unit_id, source_id, category) |
| `documents` | RAG 문서 (doc_type='criteria_*') |
| `chunks` | 검색용 청크 (search_stage 포함) |

**2-stage 검색 지원**:
- `stage1`: 별표1 (품목별 기본 기준) - 우선 검색
- `stage2`: 별표2~4, 가이드라인 - 상세 검색

---

### 3.4 retrieval.py - Retrieval 노드

**위치**: `backend/app/orchestrator/nodes/retrieval.py`

**핵심 함수**:
```python
def retrieval_node(state: ChatState) -> dict:
    """4섹션 검색 수행"""
    query = _build_search_query(state)

    retriever = StructuredRetriever()
    results = retriever.search_all_sections(query)

    return {
        'retrieval': RetrievalResult(
            agency=results['agency'],
            disputes=results['disputes'],
            counsels=results['counsels'],
            laws=results['laws'],
            criteria=results['criteria']
        ),
        'sources': _build_sources_from_retrieval(results)
    }
```

**수정 포인트**:
- `_build_search_query()`: 검색 쿼리 생성 로직
- 검색 파라미터 (top_k, threshold) 조정
- 2-stage 검색 순서 최적화

---

### 3.5 run_evaluation.py - Retrieval 평가

**위치**: `backend/scripts/evaluation/run_evaluation.py`

**사용법**:
```bash
conda activate dsr
cd backend
python -m scripts.evaluation.run_evaluation \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/retrieval_eval.json
```

**평가 지표**:
| 지표 | 목표값 | 설명 |
|------|--------|------|
| nDCG@5 | ≥ 0.65 | 순위 품질 (정규화 누적 이득) |
| MRR@3 | ≥ 0.60 | 첫 정답 순위 역수 |
| Precision@5 | ≥ 0.50 | 상위 5개 중 정답 비율 |
| Recall@5 | ≥ 0.55 | 전체 정답 중 검색된 비율 |

---

## 4. 테스트 스크립트

### 4.1 데이터 품질 테스트
```bash
conda activate dsr
pytest backend/scripts/testing/data/test_data_quality.py -v
```

**테스트 항목**:
- 각 테이블 레코드 수 확인
- embedding null 체크
- 필수 필드 검증

### 4.2 Retrieval 노드 테스트
```bash
pytest backend/scripts/testing/orchestrator/test_pr2_nodes.py::TestRetrievalNode -v
```

**테스트 항목**:
- 검색 결과 구조 검증
- 4섹션 모두 반환 확인
- 빈 결과 처리

### 4.3 법령 적재 자동 테스트
```bash
chmod +x backend/data/law/scripts/test_s1d2_loading_v2.sh
./backend/data/law/scripts/test_s1d2_loading_v2.sh
```

**단계별 실행**:
1. 환경 확인 (conda dsr)
2. Docker 컨테이너 확인
3. DB 연결 테스트
4. 스키마 적용
5. 법령 데이터 로딩
6. 데이터 검증

### 4.4 데이터 로딩 검증
```bash
python backend/scripts/evaluation/verify_loaded_data.py
```

**확인 사항**:
- 테이블별 레코드 수
- embedding null 비율
- 청크 총 개수

---

## 5. 평가 스크립트

### 5.1 Retrieval 품질 평가
```bash
cd backend
python -m scripts.evaluation.run_evaluation \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/retrieval_eval.json \
  --verbose
```

**출력 예시**:
```json
{
  "metrics": {
    "ndcg@5": 0.72,
    "mrr@3": 0.65,
    "precision@5": 0.58,
    "recall@5": 0.61
  },
  "per_query_results": [...]
}
```

### 5.2 Query Analysis 평가 (팀장과 협업)
```bash
python -m scripts.evaluation.evaluate_query_analysis \
  --golden-set ./data/golden_set/query_analysis.jsonl \
  --output ./results/qa_eval.json
```

---

## 6. 완료 기준

| 지표 | 목표값 | 확인 방법 |
|------|--------|----------|
| 데이터 로딩 | 100% | `verify_loaded_data.py` 실행 |
| embedding null | 0 | DB 쿼리 확인 |
| Retrieval nDCG@5 | ≥ 0.65 | `run_evaluation.py` 실행 |
| MRR@3 | ≥ 0.60 | `run_evaluation.py` 실행 |
| Precision@5 | ≥ 0.50 | `run_evaluation.py` 실행 |

---

## 7. 데이터 규모

| 도메인 | 원본 파일 | 예상 레코드 | 예상 청크 |
|--------|----------|------------|----------|
| 법령 (Law) | `law/raw/*.xml` | 11개 법령 | ~5,455 |
| 기준 (Criteria) | `criteria/jsonl/*.jsonl` | 7개 파일 | ~507 |

---

## 8. 주차별 작업

### 1주차
- [ ] 법령 XML 파싱 분석
- [ ] `law_pipeline.py` 구현 (load_law_to_db_v2.py 개선)
- [ ] `criteria_pipeline.py` 구현
- [ ] 데이터 품질 검증

### 2주차
- [ ] Retrieval Node 개선
- [ ] 평가 Golden Set 구축
- [ ] 평가 스크립트 실행
- [ ] nDCG@5 ≥ 0.65 달성

### 3주차
- [ ] 전체 평가 실행
- [ ] 성능 리포트 작성
- [ ] 문서화

---

## 9. 데이터 파이프라인 흐름도

```
법령 (XML)
    ↓
law_xml_parser_v2.py (파싱, 계층 보존)
    ↓
load_law_to_db_v2.py
    ↓
┌─────────────────┬─────────────────┐
│   law_units     │   documents     │
│ (조문 구조)     │   chunks        │
│                 │ (RAG 검색용)    │
└─────────────────┴─────────────────┘
    ↓
embed_law_units_v2.py (팀원 B 협업)
    ↓
chunks.embedding (1024차원 벡터)
    ↓
run_evaluation.py (품질 측정)
```

---

## 10. 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 프로젝트 계획서 | `/plans/plans.md` | 전체 3주 계획 |
| 임베딩 가이드 | `/docs/guides/embedding_process_guide.md` | 임베딩 프로세스 |
| 스키마 설계 | `/docs/guides/스키마_설계_근거.md` | DB 스키마 설계 이유 |
| 테스트 가이드 | `/docs/backend/scripts/TEST_README.md` | 테스트 실행 방법 |

---

## 11. 자주 사용하는 명령어 모음

```bash
# 환경 활성화
conda activate dsr

# 법령 데이터 로딩 (단일)
python backend/data/law/scripts/load_law_to_db_v2.py backend/data/law/raw/law_rawdata/E_Commerce_Consumer_Law.xml

# 법령 데이터 로딩 (전체)
python backend/data/law/scripts/load_law_to_db_v2.py --all backend/data/law/raw/law_rawdata

# 기준 데이터 로딩
python backend/scripts/data_loading/load_criteria_to_db.py

# 데이터 검증
python backend/scripts/evaluation/verify_loaded_data.py

# Retrieval 평가
python -m scripts.evaluation.run_evaluation \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/retrieval_eval.json

# 테스트 실행
pytest backend/scripts/testing/data/test_data_quality.py -v
pytest backend/scripts/testing/orchestrator/test_pr2_nodes.py::TestRetrievalNode -v

# DB 확인 (Docker)
docker exec -it ddoksori_db psql -U postgres -d ddoksori -c "SELECT COUNT(*) FROM law_units;"
docker exec -it ddoksori_db psql -U postgres -d ddoksori -c "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL;"
```

---

*이 문서는 팀원 A가 독립적으로 작업할 수 있도록 구성되었습니다.*
