# M2-7R De-biased A/B Comparison (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M2-7R` 후속 — eval 편향 보정 후 A/B 재측정
- 선행: `docs/plans/modules/M2-7R-ab-comparison-results.md`(1차: 편향 발견)
- 성격: 구현 결과. A 무변경(read-only 측정).

## 0. 한 줄 요약

1차 비교에서 발견한 **eval 편향**(라벨이 A-pooled·case 지배 → B의 도메인 라우팅 부당 감점)을 **시스템 무관 per-domain 합집합 풀링 + 토픽 관련성 재판정**으로 보정(v2 라벨). 그 결과 **frontier-B nDCG가 0.25 → 0.71로 상승**, 편향이 산물이었음이 입증됐다. 보정 라벨에서 **3열(nDCG@10)** A=0.88 > frontier-B=0.71 > EXAONE-B=0.55로 공정 비교 완성(EXAONE-B는 ~30.8s로 frontier ~7.5s의 4배).

## 1. 편향 보정 절차 (3단계)

1. **풀링(`ab_pool_debiased.py`)**: 각 쿼리를 `all/law/criteria/case` 도메인으로 각각 검색 → **합집합**. 코퍼스가 case 지배여도 law/criteria 질문의 풀에 법령·별표 후보가 반드시 포함됨(특정 시스템 reformulation 비의존).
2. **재판정**: 합집합 후보를 **토픽 관련성**(grade 2=직접 답, 1=관련)으로 사람이 재판정. *문서유형·어느 시스템이 찾았는지 무관*. → `ab_retrieval_eval_v2.jsonl`(12쿼리, 단일 judge).
3. **재측정**: A baseline + frontier-B(+EXAONE-B)를 v2 라벨로 재실행.

## 2. 결과 (v2 = 편향 보정 라벨, 12쿼리)

| metric | A (MAS core) | B-frontier | B-EXAONE |
| --- | --- | --- | --- |
| nDCG@5 | 0.8101 | 0.7063 | 0.4953 |
| nDCG@10 | 0.8796 | 0.7063 | 0.5507 |
| HitRate@5 | 1.0000 | 0.9167 | 0.8333 |
| HitRate@10 | 1.0000 | 0.9167 | 0.9167 |
| MRR | 0.9583 | 0.6528 | 0.5625 |
| clarification_rate | – | 0.0000 | 0.0000 |
| mean_latency_ms | – | 7547.8 | 30776.1 |

**v1(편향) → v2(보정) frontier-B 변화**: nDCG 0.253 → **0.706**, HitRate 0.333 → **0.917**, MRR 0.208 → **0.653**.

## 3. 해석

- **편향 입증**: frontier-B가 보정만으로 0.25→0.71로 뛴 것은, 1차의 낮은 점수가 **검색 열위가 아니라 라벨 편향**이었음을 정량 확인. B의 도메인 라우팅이 가져온 법령·별표가 v2에서 정답으로 인정되며 점수 회복.
- **공정 비교**: 보정 라벨에서 **A(0.88) > frontier-B(0.71)**. A의 고정 hybrid(dense+BM25+RRF, domain=all) 파이프라인이 이 retrieval 지표에선 여전히 약간 앞선다. 단 A의 HitRate/MRR=1.0/0.96은 여전히 일부 self-pool 잔여 우위(v2도 A가 찾는 case chunk가 라벨에 포함)임에 유의 — nDCG가 가장 신뢰할 헤드라인.
- **3열 순위(nDCG@10)**: **A(0.88) > frontier-B(0.71) > EXAONE-B(0.55)**. 자체호스팅 EXAONE-B는 agentic 검색(질의재작성+domain 선택)이 frontier(gpt-4o-mini)보다 약해 검색 품질이 낮다. HitRate@10은 EXAONE-B도 0.92로 frontier와 동일(관련 문서를 *찾기는* 함) 하지만 nDCG/MRR이 낮음 → **관련 문서를 상위로 올리는 랭킹/도메인 선택이 약함**.
- **latency**: A core retriever(단일 검색)는 가장 빠름. frontier-B ~7.5s, **EXAONE-B ~30.8s(약 4배)** — 33B reasoning 모델 + ReAct 다단계. 자체호스팅의 비용/프라이버시 이점 ↔ 속도·agentic 품질 trade-off가 수치로 드러남(포트폴리오 가치).

## 4. EXAONE-B 측정 완료 (2026-06-24)

frontier-B 측정 직후 vLLM 엔드포인트가 한 번 무응답(`http_code=000`)이 됐는데, 원인은 **오래된 로컬 SSH 터널 세션이 죽은 것**(pod/vLLM는 정상)이었다. `ssh -N -L` 세션을 새로 띄워 복구 후 측정 완료. 재발 방지 keepalive는 `docs/infrastructure/runpod-vllm-setup.md` §2.1에 추가. 측정 명령:
```bash
EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B \
python backend/scripts/evaluation/ab_compare.py --model exaone \
  --eval-set backend/data/golden_set/ab_retrieval_eval_v2.jsonl \
  --a-baseline backend/data/golden_set/ab_retrieval_baseline_A_v2.json --tag v2 --env <repo>/.env
```
→ `ab_compare_exaone_v2.json` 생성 + `ab_compare_report_v2.md`에 3열 자동 병합.

## 5. 산출물

- `backend/scripts/evaluation/ab_pool_debiased.py` (per-domain 합집합 풀러)
- `ab_compare.py` 갱신(`--a-baseline`, `--tag`)
- `ab_retrieval_eval_v2.jsonl`, `ab_retrieval_baseline_A_v2.{json,md}`, `ab_compare_frontier_v2.json`, `ab_compare_report_v2.md` (gitignore 예외)

## 6. 한계

- 12쿼리·단일 judge(토픽 관련성). 절대값보다 **A/B 상대·v1→v2 변화**에 의미. 확장(쿼리 30+, 다중 judge)은 후속.
- A의 HitRate/MRR 잔여 self-pool 우위(nDCG 우선 해석).
- 검색 품질 한정(답변품질 e2e는 백엔드 구동 후속).

## 7. Next gate

3열 비교 완료. 이후 M3(지표 영속화) 또는 M2-8R(multi-RAG: rerank/Graph 등으로 B 검색품질 향상 후 A 추월 시도). EXAONE-B가 가장 낮으므로, 자체호스팅 B의 검색품질·속도 개선이 우선 후보.
