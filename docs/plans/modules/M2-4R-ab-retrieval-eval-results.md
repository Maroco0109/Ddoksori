# M2-4R A/B 검색평가 하니스 + A baseline (결과 문서)

- 작성일: 2026-06-23
- 모듈: `M2-4R` 외부 A/B 검색평가 하니스 구축 + A baseline 측정
- 상위 계획: `docs/plans/modules/M2-4R-ab-retrieval-eval-harness-plan.md`
- 성격: **구현/측정 결과**. A(MAS) 런타임 코드 무변경 — A가 쓰는 동일 SQL `search_hybrid_rrf()`를 read-only로 호출.

## 0. 한 줄 요약

A의 core retriever(`search_hybrid_rrf`, 단일쿼리·필터없음)를 고정 eval셋(12개 질의, chunk-id graded 라벨) 위에서 측정한 baseline: **nDCG@10 = 0.869, nDCG@5 = 0.724**. B는 M2-7R에서 동일 하니스·동일 eval셋으로 측정한다.

## 1. 산출물

| 파일 | 내용 |
| --- | --- |
| `backend/scripts/evaluation/ab_retrieval_baseline.py` | 독립 측정 러너. query 임베딩(OpenAI text-embedding-3-large 1536d) → `search_hybrid_rrf()` 직접 호출 → nDCG@k / HitRate@k / MRR. 최소 deps(psycopg2·openai·dotenv), app 스택 미import |
| `backend/scripts/evaluation/ab_pool_candidates.py` | 라벨링용 후보 풀러(IR pooling). 질의별 top-k 후보 + 스니펫 출력 |
| `backend/data/golden_set/ab_eval_queries.jsonl` | 고정 seed 질의 12개(law/criteria/case 각 4) |
| `backend/data/golden_set/ab_retrieval_eval.jsonl` | chunk-id graded 라벨 eval셋(grade 2=직접 답, 1=관련) |
| `backend/data/golden_set/ab_retrieval_baseline_A.{json,md}` | A baseline 결과/리포트 |

> `data/golden_set`은 `.gitignore` 대상이라, 위 eval/리포트 파일만 `.gitignore` 예외(`!`)로 추적해 재현성을 확보했다.

## 2. 측정 방법

- **변형 A = core retriever**: A가 운영에서 쓰는 동일 SQL 함수 `search_hybrid_rrf(query, embedding, ...top_k, rrf_k)`를 필터 없이 단일쿼리로 호출(=query expansion 제외). A 코드는 import/수정하지 않음.
- **지표**: nDCG@5/10(graded), HitRate@5/10, MRR. rrf_k=10, embed=text-embedding-3-large(1536d).
- **eval셋**: 소비자분쟁 시나리오 12질의. 라벨은 **pooling 방식** — `search_hybrid_rrf` top-15 후보를 스니펫으로 읽고 graded relevance(0/1/2)를 사람이 부여.

## 3. A baseline 결과

| metric | value |
| --- | --- |
| nDCG@5 | 0.7244 |
| nDCG@10 | 0.8693 |
| HitRate@5 | 1.0000 |
| HitRate@10 | 1.0000 |
| MRR | 1.0000 |

(도메인별 nDCG@10은 `ab_retrieval_baseline_A.md` 참조.)

## 4. 한계 / caveat (정직 고지)

- **Pooling circularity**: 라벨을 A의 top-15에서 pooling했기 때문에, A는 top-1이 항상 라벨된 관련문서 → **HitRate@k·MRR이 trivial하게 1.0**. 이 두 지표는 A 단독으로는 변별력이 없고, **B 측정 시(B가 다른 문서를 가져오면) 비로소 의미**를 가진다. **A 단독으로 의미 있는 지표는 nDCG**(grade-2를 grade-1보다 위에 올리는 랭킹 품질).
- **단일 judge·소규모(12)**: 통계력 제한. 포트폴리오 비교 데모용 v1. 확장(질의 30+, multi-judge, A 외 retriever로 pool 확장해 recall 편향 완화)은 백로그.
- **core retriever 한정**: query expansion(llm_expander)·search_multi 융합은 제외한 retriever-core 측정. full-pipeline 측정은 별도 축(백로그).
- **corpus 버전 의존**: chunk-id 라벨은 현재 복원 DB(vector_chunks 40,285행, 1536d) 기준. corpus 재적재 시 재라벨 필요.

## 5. 재현 방법

```bash
# (최소 venv: psycopg2-binary openai python-dotenv, OPENAI_API_KEY 필요, 로컬 pgvector DB 가동)
python backend/scripts/evaluation/ab_retrieval_baseline.py \
  --eval-set backend/data/golden_set/ab_retrieval_eval.jsonl \
  --variant A --k 5 10 --rrf-k 10 \
  --out backend/data/golden_set/ab_retrieval_baseline_A.json \
  --report backend/data/golden_set/ab_retrieval_baseline_A.md \
  --env .env --db-host localhost
```
라벨 재생성(후보 풀): `ab_pool_candidates.py --queries ab_eval_queries.jsonl --out <pool>` 후 graded 라벨 부여.

## 6. Next gate

B(Agentic RAG) 구현(M2-5R~) 후, **M2-7R**에서 동일 하니스에 B retriever 어댑터를 끼워 같은 eval셋으로 측정 → A/B nDCG/HitRate 델타 산출. (pod는 M2-5R부터 필요.)
