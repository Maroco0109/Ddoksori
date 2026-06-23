# M2-7R A/B 비교 런 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M2-7R` A vs B 검색 품질 비교
- 상위 계획: `docs/plans/modules/M2-7R-ab-comparison-plan.md`
- 성격: 구현 결과 + **eval 방법론 편향 발견**. A 무변경(read-only 측정).

## 0. 한 줄 요약

비교 인프라(계측 + `ab_compare.py`)를 구축하고 **frontier-B**를 A와 같은 eval셋에서 측정했다. 표면 수치는 A nDCG@10=0.869 ≫ frontier-B 0.253이지만, per-query 분석 결과 **이는 B가 나빠서가 아니라 라벨이 A-pooled·case 지배라 B의 올바른 domain 라우팅을 깎아낸 편향** 때문이다. 측정 시스템은 정상 작동했고 이 편향을 드러낸 것이 핵심 성과. EXAONE-B 열은 편향 보정 후로 보류.

## 1. 산출물

| 파일 | 내용 |
| --- | --- |
| `backend/app/variant_b/tools.py` | contextvar **retrieval recorder**(search가 반환 chunk_id 기록) |
| `backend/app/variant_b/agent.py` | `run_b`가 agent tool 검색만 계측해 `retrieved_chunk_ids` 반환(게이트 제외) |
| `backend/scripts/evaluation/ab_compare.py` | 비교 러너: run_b 실행→nDCG/HitRate/MRR + clarification_rate + block_rate + latency, A baseline과 병합 리포트 |
| `backend/data/golden_set/ab_compare_frontier.json`, `ab_compare_report.md` | frontier-B 결과/리포트(gitignore 예외) |

## 2. 측정 결과 (frontier-B, 동일 eval셋 12쿼리)

| metric | A (MAS core retriever) | B-frontier |
| --- | --- | --- |
| nDCG@5 | 0.7244 | 0.2527 |
| nDCG@10 | 0.8693 | 0.2527 |
| HitRate@5/10 | 1.0000 | 0.3333 |
| MRR | 1.0000 | 0.2083 |
| clarification_rate | – | 0.0000 |
| block_rate | – | 0.0000 |
| mean_latency_ms | – | 8583.8 |

## 3. 핵심 발견 — 표면 수치는 eval 편향의 산물

per-query nDCG@10:

| query | domain | B nDCG@10 |
| --- | --- | --- |
| case-001 | case | 1.000 |
| case-004 | case | 0.712 |
| law-002 | law | 0.670 |
| law-004 | law | 0.651 |
| law-001, law-003, criteria-001~004, case-002, case-003 | – | 0.000 |

**원인**: M2-4R 라벨은 A의 `domain=all` top-15에서 pooling됐다. 코퍼스가 case(34,208) ≫ law(4,059)·criteria(2,018)라, law/criteria 쿼리조차 라벨이 대부분 **case(상담/조정) chunk**다(예: criteria-001 "세탁 손상 배상 기준" 라벨 = 세탁 *상담 사례*). 반면 B는 쿼리 유형대로 **domain 라우팅**(criteria 쿼리→별표/행정규칙)해 *질문에 맞는 문서 유형*을 가져오지만, case 편향 라벨과 겹치지 않아 0점이 된다. 라벨도 case인 case-001/004만 정상 점수.

→ **B의 낮은 점수는 검색 열위가 아니라 "A-pooled·case 지배 라벨"의 편향.** B의 agentic domain 라우팅은 의도대로 작동 중. 이는 M2-4R에서 명시한 pooling-circularity 한계의 구체적 발현이다.

## 4. 결론 / 시사점

1. **측정 인프라는 정상**: B의 에이전틱 검색(질의재작성+domain)을 계측·채점하고 A와 한 표로 비교 가능. clarification_rate/latency도 산출.
2. **비교가 방법론 결함을 드러냄**(포트폴리오 가치): "관련 문서 *유형*"을 보상하는 A-pooled 라벨은 도메인 라우팅을 하는 B를 부당하게 깎는다.
3. **다음 필수 작업 = 편향 보정 라벨**: 라벨 풀을 **A ∪ B(도메인별) 검색 합집합**으로 재구성하고 *토픽 관련성*(문서유형 무관)으로 재판정해야 공정. 이후 nDCG가 A/B 검색 *품질* 차이를 반영한다.
4. **EXAONE-B 보류**: 편향된 eval에서 EXAONE-B 열을 pod로 돌리는 건 가치가 낮다. 편향 보정 후 frontier-B·EXAONE-B를 함께 재측정 권장(pod 1회로 묶어 절약).

## 5. 완료 상태

- ✅ 계측(retrieved_chunk_ids) + `ab_compare.py` + frontier-B 측정 + 병합 리포트.
- ✅ A 무변경(read-only).
- ⏳ **편향 보정 eval(A∪B 재풀링·재판정)** → 후속(권장). 그 후 EXAONE-B(pod).
- M2-7R **인프라/1차 측정 완료**, 공정 수치는 편향 보정 후.

## 6. 재현

```bash
# (B venv ~/.venvs/ddoksori-b, OPENAI_API_KEY, 로컬 pgvector DB)
python backend/scripts/evaluation/ab_compare.py --model frontier --env <repo>/.env
# EXAONE-B(pod 가동 시): EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B python ... --model exaone
```

## 7. Next gate

(권장) 편향 보정 eval 라벨 재구성 → frontier-B·EXAONE-B 재측정 → 공정 A/B nDCG. 이후 M3(지표 영속화) 또는 M2-8R(multi-RAG).
