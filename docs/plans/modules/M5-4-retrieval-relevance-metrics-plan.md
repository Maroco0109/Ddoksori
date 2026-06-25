# M5-4 retrieval relevance 지표 (계획서)

- 작성일: 2026-06-25
- 모듈: `M5-4` retrieval relevance 지표 (goldenset 대비 검색 품질 수치화)
- 선행: `M5-3`(`quality_eval_v1.jsonl` 확정), `M2-4R`/`M2-7R`(평가 하니스 + A/B baseline)
- 상위 계획: §M5 (품질 평가)
- 성격: **측정·문서화 + LLM 교차검증 secondary.** 신규 프레임워크 없음(기존 스크립트 재사용). 스키마 변경 없음.

## 0. 한 줄 요약

확정된 `quality_eval_v1.jsonl`(M5-3, `relevant[]` graded)을 **단일 기준 eval셋**으로 삼아 A/B 검색 품질(hit_rate@k·nDCG@k·MRR)을 **재현·문서화**하고, RAGAS `context_relevancy`(LLM judge)를 **secondary 교차검증**으로 추가해 "사람이 라벨한 relevant[]"와 "LLM judge"의 일치를 본다. 핵심 지표는 **nDCG**(graded relevance 활용, hit rate는 소량셋에서 포화).

## 1. 배경 (왜 단순 재실행이 아닌가)

- M2-4R/M2-7R가 이미 `ab_retrieval_eval_v2.jsonl`에 대해 A/B 지표를 산출함(A nDCG@5=0.81/hit@5=1.0/MRR=0.96; B-exaone 0.50/0.83/0.56; B-frontier 0.71/0.92/0.65).
- M5-3에서 그 `relevant[]`를 **canonical 품질 goldenset `quality_eval_v1.jsonl`로 이관**(답변 라벨까지 통합). 따라서 M5-4는:
  1. 측정 기준 파일을 canonical goldenset으로 **고정**하고 동일 수치 **재현**(회귀 기준점 확립).
  2. 지금까지 없던 **RAGAS LLM 교차검증(secondary)**을 추가 — 단순 지표를 넘어 judge vs human relevance 일치를 수치화.
  3. A/B retrieval 비교를 **M5-4 results로 문서화**(포트폴리오용 measurable numbers).

## 2. 범위

### 목표
- `quality_eval_v1.jsonl` 기준 A/B retrieval 지표(hit_rate@5/10, nDCG@5/10, MRR) 재현·표.
- RAGAS `context_relevancy`(LLM judge) secondary 실행 → human graded relevant[]와의 교차검증 수치.
- M5-4 results 문서(지표 정의 + A/B 표 + 교차검증 + caveat).

### 비목표
- 답변 품질(coverage/faithfulness/safety) = M5-5, judge-human 일치도(답변측) = M5-6.
- DB/스키마 변경, 라이브 모니터링 연동(별도), 쿼리셋 확장.
- retriever 알고리즘 개선(측정만; 개선은 후속).

## 3. 재사용 자산 (신규 프레임워크 금지)

| 스크립트 | 역할 | M5-4에서 |
| --- | --- | --- |
| `ab_retrieval_baseline.py` | A CORE retriever nDCG/hit/MRR (`--eval-set` 주입) | `--eval-set quality_eval_v1.jsonl`로 A 재현 |
| `ab_compare.py` | B(run_b) 검색 지표 + A baseline 합본 표 | 동일 eval셋으로 B 재현(frontier=OpenAI only / exaone=pod) |
| `build_ragas_retrieval_log.py` | retriever 로그→`{user_input,retrieved_contexts}` | RAGAS 입력 생성 |
| `ragas_retrieval_eval.py` | RAGAS `context_relevancy`(LLM judge) | secondary 교차검증 |

- 확인됨: `ab_retrieval_baseline.py`는 `id/domain/query/relevant`만 읽어 **추가 필드(key_points/must_not 등) 무시** → `quality_eval_v1.jsonl` drop-in 안전.

## 4. 작업 단계

1. **canonical 고정**: A baseline을 `quality_eval_v1.jsonl`로 재실행 → 수치가 v2 baseline과 일치함을 확인(회귀 기준점). 산출: `quality_retrieval_A.json/.md`.
2. **A/B 표**: `ab_compare.py`로 B(frontier; exaone는 기존 v2 결과 재사용 또는 pod 시 재실행) 합본 → A/B retrieval 비교표.
3. **RAGAS secondary**: 각 variant retriever의 top-k 컨텍스트로 `context_relevancy` 산출 → human relevant[] 기반 nDCG와 **나란히** 제시(일치/괴리 해석). bounded run(비용·변동성 한정).
4. **문서화**: `M5-4-retrieval-relevance-metrics-results.md` — 지표 정의, A/B 표, RAGAS 교차검증, caveat, 인계.

## 5. 산출물

- `backend/data/golden_set/quality_retrieval_A.json` + `.md` (canonical A baseline).
- `backend/data/golden_set/quality_retrieval_compare.md` (A/B 합본 표).
- `backend/data/golden_set/quality_ragas_*.json` (RAGAS secondary).
- `docs/plans/modules/M5-4-retrieval-relevance-metrics-results.md`.

## 6. 완료 기준 / 검증

- [ ] `quality_eval_v1.jsonl` 기준 A nDCG/hit/MRR 산출, **M2-4R v2 수치와 일치**(동일 relevant[] → 재현성 확인).
- [ ] A/B 비교표 산출(최소 A + B-frontier; exaone은 기존 수치 인용 또는 pod 재실행 명시).
- [ ] RAGAS `context_relevancy` secondary 수치 1회 산출 + human relevant[]와의 해석.
- [ ] results 문서에 지표 정의·A/B 표·교차검증·caveat 기록.
- [ ] 코드/스키마 변경 없음(스크립트 재사용·인자 주입만). `quality_eval_v1.jsonl` 불변.

## 7. caveat

- **hit_rate 포화**: 12쿼리 소량셋에서 hit@5가 쉽게 1.0 → 변별은 nDCG/MRR. hit rate는 sanity로만.
- **RAGAS 비용/변동성**: LLM judge라 bounded run·seed 고정. primary는 graded nDCG(LLM 불필요·재현).
- **재현성 전제**: corpus(벡터 DB) chunk_id 고정. eval셋에 corpus 버전 메모 유지.
- exaone 신규 검색 재실행만 pod 필요. A·frontier·RAGAS는 OpenAI 임베딩/judge만.

## 8. Next gate → M5-5

- M5-5: `workflow_runs.answer`(M5-1) + retrieval contexts vs `key_points`/`must_not` → coverage/faithfulness/safety LLM-judge.
- 선결 인지: 답변 채점은 **goldenset 12쿼리를 실제 실행해 answer를 적재**하는 단계가 필요(현재 모니터링 DB엔 goldenset 쿼리 answer 없음). M5-5 계획에서 "goldenset 실행 → 적재 → 채점" 구조로 설계.
