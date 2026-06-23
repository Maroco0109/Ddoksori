# M2-4R A/B 검색평가 하니스 + A baseline (계획서)

- 작성일: 2026-06-23
- 모듈: `M2-4R` (재정의됨) 외부 A/B 검색평가 하니스 구축 + A baseline 측정
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §1.2, `docs/plans/2026-06-23-ab-architecture-simplification-proposal.md`, `docs/plans/modules/M2-3R-b-architecture-ab-harness.md`
- 성격: **계획서**. 본 문서는 코드를 바꾸지 않는다. 실제 하니스 코드/측정은 본 계획 수용 후 구현.
- 원칙: **A(MAS)는 동결 baseline — 런타임 코드 무변경.** 평가는 A의 retriever를 read-only로 호출하는 *외부* 하니스로 수행한다.

## 0. 한 줄 요약

기존 `evaluate_retrieval.py`(nDCG@k·HitRate@k, retriever 주입형)와 RAGAS 스크립트를 재사용하되, repo에 없는 **고정 eval셋(chunk/doc-id 라벨)**을 만들어 커밋하고, A의 검색을 그 위에서 측정해 baseline 숫자를 남긴다. B는 M2-7R에서 동일 하니스로 측정한다.

## 1. 목표 / 비목표

### 목표
- A·B를 동일 eval셋·동일 지표로 비교할 외부 하니스를 확정·구축한다.
- 재현 가능한 **고정 eval셋**을 git에 커밋한다.
- A retrieval baseline 수치를 산출·리포트로 남긴다.

### 비목표
- B 어댑터 구현/측정(M2-7R), DB 저장(M3), A 런타임 동작 변경, B 게이트 신호(M2-5R, B 내부).

## 2. reuse-first 점검 결과

| 자산 | 상태 | M2-4R에서 |
| --- | --- | --- |
| `scripts/evaluation/evaluate_retrieval.py` | nDCG@k·HitRate@k, `run_evaluation(retriever, samples, k)` **retriever 주입형**, relevance는 **doc_type 매칭** | 재사용 + relevance를 **id 매칭**으로 확장 |
| `scripts/evaluation/ragas_retrieval_eval.py` | RAGAS `context_relevancy`(LLM judge), `{user_input, retrieved_contexts}` JSONL | **선택적 secondary** |
| `create_eval_dataset.py` | 로그→질문 추출 + **대화형 context 라벨링** | eval셋 반자동 라벨링에 활용 |
| `backend/data/golden_set`, `data/evaluation` | **.gitignore + 추적 0** → 고정 eval셋 없음 | **신규 고정 eval셋 커밋(gitignore 예외)** |

## 3. 결정사항

### 3.1 지표 (primary = 결정형)
- **primary**: nDCG@5, nDCG@10, HitRate@5, HitRate@10 (LLM 없이, 저렴·재현). 
- **secondary(선택)**: RAGAS `context_relevancy`(의미 유사도, LLM judge — 비용/변동성 있어 bounded run).

### 3.2 eval셋 = 소규모 수제 큐레이션
- law/criteria/case 도메인을 균형 있게 덮는 **~30개 질의**(도메인당 ~10).
- 소비자분쟁 실제 시나리오 기반(환불/교환/배송/계약 등).
- **git 커밋**(재현성/포트폴리오). `data/golden_set`이 gitignore이므로 **해당 eval 파일만 gitignore 예외**로 추적.

### 3.3 relevance = chunk/doc-id 라벨 (doc_type 재사용 반려)
- **이유**: A의 각 retrieval agent는 `metadata_filter`로 doc_type을 강제하고(graph_mas `_create_retrieval_agent_node`), B도 `search_law/criteria/case` 분리 tool로 doc_type을 선택한다 → "기대 doc_type을 가져왔나"는 **거의 자동 충족**이라 실제 문서 랭킹 품질을 못 잰다.
- 따라서 relevance를 **질의별 실제 관련 문서 ID**로 라벨(**graded 0/1/2** 권장, nDCG 적합). doc_type hit_rate는 **보조 sanity**로만 유지.
- 효과: "그 특정 관련문서를 top-k에 잘 올렸나"를 **라우팅 무관**하게 A·B 동일 기준으로 측정.
- 라벨링: `create_eval_dataset.py` 대화형으로 **후보 자동 제안 → 사람 검증**(반자동, 비용 절감).

### 3.4 하니스 확장 (A 무변경)
- `evaluate_retrieval.py`의 `compute_relevances`/`hit_rate_at_k`를 **chunk_id/doc_id 매칭** 지원하도록 확장(graded relevance 포함). doc_type 경로는 유지.
- A retriever 어댑터: MAS가 쓰는 `UnifiedRetriever`를 read-only로 호출(= A 동작 불변). **A 런타임 코드는 손대지 않음**(eval 스크립트만 변경).

## 4. In scope / Out of scope

### In scope (구현 모듈에서)
- 신규 고정 eval셋 파일(질의 + id 라벨) + gitignore 예외.
- `evaluate_retrieval.py` id/graded relevance 확장.
- A baseline 측정 실행 + 결과 리포트(JSON/CSV/MD) 커밋.

### Out of scope
- B 어댑터/측정(M2-7R), DB 저장(M3), A 런타임 변경, RAGAS 대규모 런(선택·bounded만).

## 5. 작업 순서 (구현 시)
1. eval셋 스키마 확정(id-labeled, graded): `{id, query, category, expected_docs:[{chunk_id/doc_id, grade}], (보조)expected_doc_types}`.
2. ~30개 질의 큐레이션 + `create_eval_dataset.py` 반자동 라벨링 → 사람 검증 → 커밋.
3. `evaluate_retrieval.py` id/graded relevance 확장(+ doc_type 보조 유지).
4. A baseline 측정: `UnifiedRetriever` 주입, k=5/10, nDCG·HitRate 산출.
5. (선택) RAGAS `context_relevancy` bounded 보조 측정.
6. 리포트 커밋(`generate_report.py` 활용 가능).

## 6. 완료 기준 / 검증
- 고정 eval셋이 git에 커밋되어 누구나 같은 입력으로 재실행 가능.
- A baseline: nDCG@5/10·HitRate@5/10 수치가 산출·리포트로 남음(+선택 RAGAS).
- **A 런타임 무변경 증명**: eval은 `UnifiedRetriever` read-only 호출만, A 코드 diff 0.
- B는 M2-7R에서 동일 하니스·동일 eval셋으로 측정(본 모듈 범위 아님).

## 7. 가정 / 리스크
- **안정적 chunk_id**: M1 복원 DB의 chunk_id가 고정이어야 id 라벨이 유효(가정; eval셋에 corpus 버전 메모).
- 소규모 셋이라 통계력 제한 → "포트폴리오 비교 데모"용으로 충분, 추후 확장 백로그.
- RAGAS judge 비용/변동성 → secondary·bounded로 한정.
- 라벨 주관성 → graded 기준 문서화 + 사람 검증.

## 8. pod / 환경
- **pod 불필요**. 필요한 것: 로컬 pgvector DB(M1) + OpenAI 임베딩(검색), RAGAS 쓸 때만 OpenAI judge.

## 9. Next gate
본 계획 수용 후 구현(eval셋 → 하니스 확장 → A baseline). 그 전에는 B 어댑터/측정을 시작하지 않는다.
