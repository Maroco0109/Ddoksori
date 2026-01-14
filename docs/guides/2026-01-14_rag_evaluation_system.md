# 2026-01-14 RAG 정량 평가 시스템 구현

## 변경사항 요약

- **RAG 검색 품질 평가 시스템 구현**
- **평가 메트릭 모듈 추가** (nDCG, MRR, Precision, Recall)
- **CLI 평가 도구 및 데이터셋 생성 도구 추가**

---

## 1. 구현 배경

RAG 시스템의 성능 고도화를 위해 정량적 평가 기준이 필요했습니다.
- LLM 호출 없이 빠르고 저렴하게 실행
- 기존 RAG 로그에서 평가 데이터셋 자동 생성
- 섹션별(Domain, Cases, Laws, Criteria) 검색 품질 측정

---

## 2. 구현 내용

### 2.1 평가 메트릭

| 메트릭 | 설명 | 수식 |
|-------|------|------|
| **nDCG@K** | 상위 K개 결과의 순위 품질 | DCG / IDCG |
| **MRR** | 첫 번째 관련 문서의 역순위 | 1 / rank |
| **Precision@K** | 상위 K개 중 관련 문서 비율 | hits / K |
| **Recall** | 전체 관련 문서 중 검색된 비율 | hits / total_relevant |
| **Hit Rate@K** | K개 중 관련 문서 존재 여부 | 1 or 0 |
| **Domain Accuracy** | 기관 추천 정확도 | match or not |

### 2.2 섹션별 평가

```
┌─────────────────────────────────────────────────────────┐
│ Domain (기관추천)     → Accuracy                        │
├─────────────────────────────────────────────────────────┤
│ Cases (유사사례)      → nDCG@3, MRR, Precision@3, Recall│
├─────────────────────────────────────────────────────────┤
│ Laws (관련법령)       → nDCG@3, MRR, Precision@3, Recall│
├─────────────────────────────────────────────────────────┤
│ Criteria (분쟁기준)   → nDCG@3, MRR, Precision@3, Recall│
└─────────────────────────────────────────────────────────┘
```

---

## 3. 신규 파일

| 파일 | 설명 |
|------|------|
| `rag/evaluation/__init__.py` | 평가 모듈 초기화 |
| `rag/evaluation/retrieval_metrics.py` | 검색 메트릭 구현 |
| `scripts/evaluation/run_evaluation.py` | CLI 평가 실행 스크립트 |
| `scripts/evaluation/create_eval_dataset.py` | 데이터셋 생성 도구 |
| `data/evaluation/eval_dataset.jsonl` | 평가 데이터셋 (9개 항목) |

---

## 4. 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `rag/__init__.py` | evaluation 모듈 export 추가 |

---

## 5. 사용법

### 5.1 평가 데이터셋 생성

```bash
# RAG 로그에서 질문 추출 및 context 자동 매핑
python scripts/evaluation/create_eval_dataset.py \
  --log-dir logs/rag \
  --output data/evaluation/eval_dataset_draft.jsonl \
  --max-items 50

# 대화형 검토 모드 (relevance 레이블링)
python scripts/evaluation/create_eval_dataset.py \
  --interactive \
  --input data/evaluation/eval_dataset_draft.jsonl \
  --output data/evaluation/eval_dataset.jsonl
```

### 5.2 평가 실행

```bash
# JSON 출력
python scripts/evaluation/run_evaluation.py \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/eval_$(date +%Y%m%d).json

# CSV 출력
python scripts/evaluation/run_evaluation.py \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/eval.csv \
  --format csv

# 상세 로그 출력
python scripts/evaluation/run_evaluation.py \
  --dataset data/evaluation/eval_dataset.jsonl \
  --verbose

# 검색 없이 데이터셋만 검증
python scripts/evaluation/run_evaluation.py \
  --dataset data/evaluation/eval_dataset.jsonl \
  --dry-run
```

---

## 6. 테스트 결과

### 6.1 단위 테스트 (Retrieval Metrics)

```
=== Unit Test: Retrieval Metrics ===
nDCG@3: 0.2961
MRR: 0.5000
Precision@3: 0.3333
Recall: 0.6667
Hit Rate@3: 1.0000
Domain Accuracy (match): 1.0000
Domain Accuracy (no match): 0.0000

=== All unit tests passed! ===
```

### 6.2 통합 테스트 (RetrievalMetrics Class)

```
=== Integration Test: RetrievalMetrics Class ===
Item ID: test_001
Domain Accuracy: 1.0
Overall MRR: 1.0000
Overall Hit Rate: 1.0000
Cases nDCG: 0.6131
Cases MRR: 1.0000
Laws Precision@K: 0.3333

Aggregated mean domain_accuracy: 1.0

=== Integration test passed! ===
```

### 6.3 전체 평가 실행 (9개 샘플)

```
==================================================
=== RAG Evaluation Results ===
==================================================

Dataset: 9 samples
Time: 8.6s

Section         Metric                Score
---------------------------------------------
Domain          Accuracy              1.000
Cases           ndcg                  0.589
Cases           mrr                   0.750
Cases           precision@k           0.518
Cases           recall                0.600
---------------------------------------------
Overall         nDCG                  0.679
Overall         MRR                   0.750
Overall         Hit Rate              1.000
==================================================
```

---

## 7. 평가 데이터셋 스키마

```json
{
  "id": "eval_001",
  "question": "인터넷에서 구매한 에어컨을 설치 후 3일 만에 고장났는데...",
  "expected_contexts": [
    {"doc_type": "law", "doc_id": "...", "relevance": "essential"},
    {"doc_type": "criteria", "unit_id": "...", "relevance": "supporting"},
    {"doc_type": "case", "doc_id": "...", "relevance": "supporting"}
  ],
  "expected_agency": "KCA",
  "category": "전자상거래_환불"
}
```

### relevance 레벨

| 레벨 | 설명 |
|-----|------|
| `essential` | 답변에 반드시 필요한 context |
| `supporting` | 답변을 보강하는 context |

---

## 8. 결과 출력 형식

### 8.1 JSON 결과

```json
{
  "summary": {
    "run_id": "eval_20260114_000000",
    "dataset": "data/evaluation/eval_dataset.jsonl",
    "sample_count": 9,
    "total_time_seconds": 8.6,
    "domain_accuracy_mean": 1.0,
    "cases_ndcg_mean": 0.589,
    "cases_mrr_mean": 0.750,
    "overall_hit_rate_mean": 1.0
  },
  "detailed_results": [...]
}
```

### 8.2 터미널 출력

```
=== RAG Evaluation Results ===
Dataset: 9 samples
Time: 8.6s

Section         Metric          Score
─────────────────────────────────────
Domain          Accuracy        1.000
Cases           nDCG@3          0.589
...
```

---

## 9. 향후 개선 사항

- [ ] 평가 데이터셋 30개 이상 확보
- [ ] RAGAS 메트릭 추가 (Faithfulness, Answer Relevancy)
- [ ] 한국어 특화 메트릭 추가 (Citation Accuracy, Korean Semantic Sim)
- [ ] 평가 결과 DB 저장 기능
- [ ] HTML 리포트 생성기

---

## 관련 파일

- 계획: `/.claude/plans/foamy-seeking-shore.md`
- 4섹션 구조화 응답: `/docs/guides/2026-01-13_structured_response_implementation.md`
- 시스템 아키텍처: `/docs/guides/system_architecture.md`
