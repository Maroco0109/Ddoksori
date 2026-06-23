# M2-7R A/B 비교 런 (계획서)

- 작성일: 2026-06-24
- 모듈: `M2-7R` A(Advanced RAG/MAS) vs B(Agentic RAG) 측정·비교
- 상위 계획: `docs/plans/2026-05-18-...roadmap.md` §1.2, `docs/plans/modules/M2-4R-ab-retrieval-eval-results.md`, `M2-5R-b-skeleton-results.md`, `M2-6R-b-full-pipeline-results.md`
- 성격: **계획서**(코드 없음). frontier 측정은 pod 불필요; **EXAONE-B 열만 pod 필요**.
- 원칙: **A 무변경**(read-only 측정). 동일 eval셋·동일 라벨로 공정 비교.

## 0. 한 줄 요약

M2-4R 하니스(`ab_retrieval_baseline.py`)와 동일 eval셋(`ab_retrieval_eval.jsonl`)을 재사용해 **검색 품질(nDCG@5/10·HitRate·MRR)을 A vs B로** 측정한다. B는 `run_b`를 eval 쿼리마다 실행하고 **search tool이 반환한 chunk_id를 trace에 계측**해 채점한다. 컬럼은 **A · frontier-B · EXAONE-B** 3열. clarification_rate·검색 latency도 함께 산출. 답변품질 e2e는 후속.

## 1. 목표 / 비목표

### 목표
- A·frontier-B·EXAONE-B의 retrieval nDCG/HitRate/MRR을 같은 eval셋에서 비교한 리포트 산출(포트폴리오 숫자).
- B 고유 지표(clarification_rate, 검색 latency) 산출.

### 비목표
- 허위인용 차단율(적대적 eval셋 필요 → M4), 답변품질 end-to-end 비교(A 백엔드 구동 필요 → 후속), DB 영속화(M3), A 변경.

## 2. 결정사항 (토론 확정, 2026-06-24)

| 항목 | 결정 |
| --- | --- |
| B 검색 계측 | **에이전트 실행 계측** — `run_b`를 실제 실행하고 search tool이 반환한 chunk_id(순위 포함)를 기록. 모델의 질의재작성+domain 선택까지 포함한 "에이전틱 검색"을 측정 |
| 측정 범위 | retrieval nDCG/HitRate/MRR(A vs B) + clarification_rate + 검색 latency |
| 비교 컬럼 | **A · frontier-B · EXAONE-B** (3열). frontier-B는 pod 불필요, EXAONE-B는 pod 필요 |
| 재사용 | M2-4R `ab_retrieval_baseline.py` 채점 로직 + `ab_retrieval_eval.jsonl` 라벨 + A baseline(`ab_retrieval_baseline_A.json`) |

## 3. 측정 설계

### 3.1 B 검색 chunk_id 계측 (instrument)
- 현재 `run_b` trace는 chunk_id를 노출하지 않음. `variant_b/tools.py`에 **contextvar 기반 retrieval recorder** 추가:
  - `search()`(또는 `search_consumer_disputes`)가 호출 시 반환 chunk_id를 순위 순서로 recorder에 append.
  - `run_b`가 agent 실행 전 recorder를 reset, 실행 후 수집 → 결과에 `retrieved_chunk_ids`(다중 tool 호출은 호출 순서대로 concat, 첫 등장 유지 dedupe) 추가.
- 이 변경은 B 전용(`variant_b/`)이며 A 무변경.

### 3.2 비교 러너 `ab_compare.py` (신규)
- 입력: `--eval-set`, `--model {frontier,exaone}`, `--k 5 10`, `--tau`, `--out`, `--report`.
- 각 eval 쿼리: `t0=time` → `run_b(query, model)` → `latency=time-t0`; `retrieved_chunk_ids`로 graded relevance 배열 구성 → nDCG@k/HitRate@k/MRR(M2-4R 공식 재사용); `clarified` 기록.
- 집계: 모델별 평균 nDCG/HitRate/MRR + clarification_rate + 평균 latency.
- **clarified 쿼리는 retrieval 지표에서 제외**(B가 검색-답변 대신 되물음) → `clarification_rate`로 별도 보고. (우리 eval셋은 구체 쿼리라 clarify는 드물 것.)
- A 열: 기존 `ab_retrieval_baseline_A.json` 재사용(또는 baseline 스크립트 재실행).

### 3.3 리포트
- `ab_compare_report.{json,md}`: A / frontier-B / EXAONE-B를 한 표로(metric × column) + 도메인별 분해 + clarification_rate/latency. git 커밋(gitignore 예외).

## 4. 작업 순서

1. tools.py에 retrieval recorder 추가, `run_b`가 `retrieved_chunk_ids` 반환(계측). B 단위 smoke로 chunk_id 수집 확인.
2. `ab_compare.py` 작성(nDCG/HitRate/MRR + clarification_rate + latency).
3. **A + frontier-B 측정**(pod 불필요): A는 baseline 재사용, frontier-B 실행 → 2열 비교 리포트.
4. **EXAONE-B 측정**(pod): 사용자에게 H100 Resume + tool-calling 재기동 요청 → `--model exaone` 실행 → 3열 완성 → pod Stop 안내.
5. 결과 문서화.

## 5. 산출물

- `backend/app/variant_b/tools.py`(recorder) + `agent.py`(retrieved_chunk_ids) 변경.
- `backend/scripts/evaluation/ab_compare.py`(신규).
- `backend/data/golden_set/ab_compare_report.{json,md}`(gitignore 예외).
- `docs/plans/modules/M2-7R-ab-comparison-results.md`.

## 6. 완료 기준 / 검증

- 동일 eval셋에서 **A·frontier-B·EXAONE-B nDCG@5/10·HitRate·MRR** 비교 수치 산출·커밋.
- clarification_rate·검색 latency 산출.
- A 무변경(측정 read-only) 확인.
- (EXAONE-B 열은 pod 가동 시 완성 — 미가동 시 A·frontier-B 2열로 먼저 마감하고 EXAONE-B 후속 가능.)

## 7. pod 안내

- 1~3단계(계측·러너·A·frontier-B): **pod 불필요**.
- **4단계(EXAONE-B)에서만 pod**: H100 Resume + `--enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1` 재기동(M2-5R 절차), `EXAONE_MODEL` 4.5-33B override. 측정 후 **Stop**.

## 8. 한계

- 소규모 eval셋(12) + pooling 라벨(M2-4R): 절대 수치보다 **A/B 상대 비교**에 의미. HitRate/MRR은 A에서 pooling 탓 trivial했으나 B는 다른 chunk를 가져올 수 있어 비로소 변별.
- 검색 품질 한정(답변품질 e2e는 백엔드 구동 후 후속).
- clarified 쿼리 retrieval 지표 제외(별도 보고).

## 9. Next gate

M3(관측 DB: 이 지표들을 `retrieval_events`/`llm_calls` 등에 영속화) 또는 M2-8R(B multi-RAG 실험: rerank/Graph). M2-7R 결과로 A/B 비교 숫자가 확보된다.
