# 평가 스크립트 안내

이 문서는 아래 3개 파일만 다룹니다.
- `build_ragas_retrieval_log.py`
- `law_retrieval_eval.py`
- `ragas_retrieval_eval.py`

## build_ragas_retrieval_log.py
- 역할: golden JSONL의 `queries_llm`를 사용해 **retriever-only 로그(JSONL)** 생성
- 내부 검색: `hybrid_rrf_search` (RDS 기반)
- 출력: `retrieved_contexts`, `retrieved_ids`, `scores(rrf/bm25/vector)` 포함
- 주요 옵션
  - `--input` / `--output`
  - `--max-queries`, `--top-k`, `--rrf-k`
  - `--filter-document-type` (쉼표 구분 문자열)
  - `--shuffle`, `--seed`
  - `--continue-on-error`, `--dry-run`

## law_retrieval_eval.py
- 역할: **법령 골든셋** 기준의 정량 평가
- 평가 지표: ExactHit@K / ArticleHit@K / LawHit@K, recall@K
- 내부 검색: `hybrid_rrf_search` (RDS 기반)
- 입력: golden JSONL (`citations`, `article_ids`, `queries_llm` 필요)
- 주요 옵션
  - `--input`, `--law-map`, `--top-k`
  - `--start-line`, `--count`
  - `--output` (선택, JSONL 저장)
  - `--json` (요약 JSON 출력)

## ragas_retrieval_eval.py
- 역할: **RAGAS context_relevancy**로 retriever-only 로그 평가
- 입력: `ragas_retrieval_log_*.jsonl`
  - `user_input`, `retrieved_contexts` 필수
- LLM 필요: `OPENAI_API_KEY`
- 주요 옵션
  - `--input`, `--output`, `--model`
  - `--max-rows`, `--shuffle`, `--seed`

## 비고
- 세 스크립트 모두 `backend/.env`를 로드하도록 구성됨
- `hybrid_rrf_search`는 `backend/app/agents/retrieval/tools/rds_retriever.py`를 사용
