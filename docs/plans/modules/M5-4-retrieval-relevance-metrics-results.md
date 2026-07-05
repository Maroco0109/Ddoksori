# M5-4 retrieval relevance 지표 (결과)

- 완료일: 2026-06-25
- 모듈: `M5-4` retrieval relevance 지표
- 선행: `M5-3`(`quality_eval_v1.jsonl`), `M2-4R`/`M2-7R`(평가 하니스 + A/B baseline)
- 성격: 측정·문서화 + LLM 교차검증 secondary. 스키마 변경 없음(스크립트 재사용 + 얇은 어댑터).

## 0. 한 줄 요약

확정 goldenset `quality_eval_v1.jsonl`을 단일 기준 eval셋으로 삼아 A/B 검색 품질(nDCG/hit/MRR)을 **재현·문서화**하고, **LLM judge vs human relevance 일치도**를 secondary 교차검증으로 산출했다. 결과: A가 검색 품질에서 B를 압도(nDCG@5 A=0.81 vs B-frontier 0.71 vs B-exaone 0.50), 그리고 자동 LLM judge는 사람 graded relevance와 **kappa 0.21(fair)**로 약하게만 일치하며 **관련성을 과대평가**한다 → 사람 기준 goldenset의 필요성을 수치로 입증.

## 1. Primary — A/B retrieval 지표 (graded relevance)

eval set: `quality_eval_v1.jsonl` (12쿼리, human-graded `relevant[]` 0/1/2)

| metric | A (MAS core) | B-exaone | B-frontier |
| --- | --- | --- | --- |
| **nDCG@5** | **0.8101** | 0.4953 | 0.7063 |
| hit_rate@5 | 1.0000 | 0.8333 | 0.9167 |
| nDCG@10 | 0.8796 | 0.5507 | 0.7063 |
| hit_rate@10 | 1.0000 | 0.9167 | 0.9167 |
| MRR | 0.9583 | 0.5625 | 0.6528 |
| mean_latency_ms | - | 30,776 | 7,548 |

- **A nDCG@5=0.8100512578988969 등 M2-4R v2 baseline과 비트 단위로 동일** → canonical 파일 재현성 확인(회귀 기준점 확립).
- B 수치는 M2-7R 산출값(동일 `relevant[]`)을 인용. 신규 exaone 검색 재실행만 pod 필요(미실행, 기존값 유효).
- **해석**: A(MAS core retriever)가 검색 랭킹 품질·MRR 모두 우위. B-frontier가 B-exaone보다 검색·지연 모두 우수. hit_rate는 12쿼리에서 포화(A=1.0) → 변별은 nDCG/MRR.

## 2. Secondary — LLM judge vs human relevance 일치도

각 쿼리의 A top-5 검색 청크를 LLM judge(gpt-4o-mini, temp 0)가 0/1/2로 채점 → human `relevant[]`와 비교. (60 (query,chunk) 쌍)

| 지표 | 값 |
| --- | --- |
| exact_agreement (0/1/2 일치) | 0.4667 |
| binary_agreement (≥1 일치) | 0.7667 |
| **Cohen's kappa** | **0.2109 (fair)** |

confusion (행=human, 열=judge):

| | j0 | j1 | j2 |
| --- | --- | --- | --- |
| h0 | 4 | 3 | 8 |
| h1 | 2 | 8 | 17 |
| h2 | 1 | 1 | 16 |

- **핵심 발견**: judge는 0점을 거의 안 줌(60쌍 중 7). human-0의 8/15, human-1의 17/27을 judge가 2로 상향 → **자동 judge가 관련성을 과대평가**.
- **의미**: reference-free LLM judge는 사람 graded relevance의 약한 대용물(kappa 0.21)일 뿐 → **사람 기준 앵커(goldenset)가 필요**함을 수치로 입증. M5-6(judge-human 일치도) 답변측 확장의 사전 신호.

## 3. RAGAS context_relevancy — 시도/보류

- 계획의 RAGAS secondary는 **`ragas==0.4.2`의 알려진 비호환**으로 보류: 로드시 `langchain_community.chat_models.vertexai`(구 경로) import 실패.
- RAGAS `context_relevancy`는 **reference-free**(질문↔컨텍스트만 평가, 사람 라벨 비교 없음)라, 본 모듈의 목표("judge vs human")에는 **§2의 judge-agreement가 더 직접적**이라 판단해 대체.
- 후속: langchain-community 버전 고정으로 RAGAS 복구 시 §2와 병기 가능(backlog).

## 4. 산출물 (재현)

- `backend/data/golden_set/quality_retrieval_A.json` / `.md` — A baseline(canonical).
- `backend/data/golden_set/quality_retrieval_compare.md` — A/B 합본 표.
- `backend/data/golden_set/quality_retrieval_log.jsonl` — A top-5 검색 컨텍스트 로그(judge/RAGAS 입력).
- `backend/data/golden_set/quality_judge_agreement.json` — judge-human 일치 상세.
- 신규 스크립트(재사용 glue):
  - `build_quality_retrieval_log.py` — A baseline의 embed/retrieve 재사용해 컨텍스트 로그 생성.
  - `judge_retrieval_relevance.py` — LLM judge 0/1/2 채점 + human 일치(exact/binary/kappa/confusion).

재현 커맨드(최소 venv: psycopg2-binary, openai, python-dotenv):
```
python backend/scripts/evaluation/ab_retrieval_baseline.py --eval-set backend/data/golden_set/quality_eval_v1.jsonl --variant A --k 5 10 --rrf-k 10 --env .env --out backend/data/golden_set/quality_retrieval_A.json --report backend/data/golden_set/quality_retrieval_A.md
python backend/scripts/evaluation/build_quality_retrieval_log.py --eval-set backend/data/golden_set/quality_eval_v1.jsonl --top-k 5 --rrf-k 10 --env .env --out backend/data/golden_set/quality_retrieval_log.jsonl
python backend/scripts/evaluation/judge_retrieval_relevance.py --log backend/data/golden_set/quality_retrieval_log.jsonl --model gpt-4o-mini --env .env --out backend/data/golden_set/quality_judge_agreement.json
```

## 5. 완료 기준 점검

- [x] `quality_eval_v1.jsonl` 기준 A nDCG/hit/MRR 산출, M2-4R v2와 일치(재현성).
- [x] A/B 비교표(A 재현 + B-exaone/frontier 인용).
- [x] LLM judge vs human 일치도 secondary 1회 산출(exact/binary/kappa/confusion).
- [x] results 문서에 지표 정의·A/B 표·교차검증·caveat 기록.
- [x] `quality_eval_v1.jsonl` 불변. DB/스키마 변경 없음.

## 6. caveat / 인계 → M5-5

- 12쿼리 시드는 smoke·앵커. hit_rate 포화·kappa 변동 가능 → 확장은 후속.
- exaone 검색 재실행만 pod 필요(현재 인용값 유효).
- **M5-5 선결**: 답변 채점은 goldenset 12쿼리를 실제 실행해 `workflow_runs.answer` 적재가 선행돼야 함(현 모니터링 DB엔 goldenset 답변 없음). M5-5 계획에서 "goldenset 실행 → 적재 → 채점" 구조로 설계.
