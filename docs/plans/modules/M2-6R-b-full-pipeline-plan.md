# M2-6R B 풀 파이프라인 (계획서)

- 작성일: 2026-06-24
- 모듈: `M2-6R` B(Agentic RAG) 확장 — 도메인 retrieval + verify_citation + lookup tools + guardrail pre/post + `/chat?variant=B`
- 상위 계획: `docs/plans/2026-05-18-...roadmap.md` §1.2, `docs/plans/modules/M2-3R-b-architecture-ab-harness.md`, `docs/plans/modules/M2-5R-b-skeleton-results.md`
- 성격: **계획서**(코드 없음). frontier 개발은 pod 불필요; EXAONE 재검증은 선택(pod).
- 원칙: **A(MAS) 무변경.** B는 격리 모듈 `backend/app/variant_b/` 확장.

## 0. 한 줄 요약

M2-5R 골격(단일 generic search + cosine 게이트 + ReAct) 위에, **domain 인자 search** + **verify_citation**(허위인용 차단) + **get_law_article/get_case_detail**(원문 조회) + **guardrail pre/post**(A 모듈 재사용) + **`/chat?variant=B` 최소 엔드포인트**를 더해 B v1 풀 파이프라인을 완성한다. **서브 PR 3개**로 분할 진행.

## 1. 목표 / 비목표

### 목표
- M2-3R v1 카탈로그의 나머지 tool과 guardrail, B 엔드포인트를 구현해 B를 "측정 가능한 풀 파이프라인"으로 만든다.

### 비목표
- A 변경, A/B 정량 비교 런(M2-7R), DB 저장(M3), streaming/memory parity, MCP, multi-RAG 실험(M2-8R).

## 2. 결정사항 (토론 확정, 2026-06-24)

| 항목 | 결정 |
| --- | --- |
| retrieval tool 입자 | **단일 `search_consumer_disputes(query, domain, top_k)`** + `domain ∈ {law, criteria, case, all}`. 3 도메인이 같은 `vector_chunks`·동일 검색·균일 결과형태라 한 tool로 커버. domain은 WHERE 필터로 환산 |
| 다중 document_type 처리 | law(법률+시행령)/criteria(별표+행정규칙)는 `search_hybrid_rrf(...) ⋈ vector_chunks ON chunk_id` 조인 후 `document_type = ANY(...)` 후필터(함수 변경 없음). case는 `filter_dataset=case` |
| 진행 단위 | **서브 PR 3개**: ① tools ② guardrail ③ endpoint |
| 엔드포인트 깊이 | **최소 non-streaming** `/chat?variant=B` → `run_b` → answer+trace |
| verify_citation | 모델 인용(법령 `law_name`+`article_number` 또는 `chunk_id`/case)을 코퍼스에서 매칭 → 존재여부+원문. 보안(허위인용 차단) |
| guardrail | A의 `guardrail/moderation.py` `check_input()`/`check_output()` **read-only 재사용**(B 입력 전 / 답변 후) |

## 3. 도메인 필터 매핑 (근거: 라이브 DB)

| domain | 필터 | 코퍼스 규모 |
| --- | --- | --- |
| law | dataset_type=law_guide ∧ document_type ∈ {법률, 시행령} | 4,059 |
| criteria | dataset_type=law_guide ∧ document_type ∈ {별표, 행정규칙} | 2,018 |
| case | dataset_type=case (category 조정/상담/해결) | 34,208 |
| all | 필터 없음(M2-5R generic = A core retriever parity) | 40,285 |

## 4. Tool/guardrail 상세

- `search_consumer_disputes(query, domain="all", top_k=5)` — M2-5R 시그니처에 `domain` 추가(기본 all=기존 동작 유지). domain별 §3 필터. `max_cosine` 계속 반환(게이트용).
- `verify_citation(reference: str)` — `law_name`+`article_number` 또는 `chunk_id`/case uid 매칭 → `{exists, matched_chunk_id, snippet}`. lexical/exact 매칭.
- `get_law_article(law_name, article_number)` — 법령 조문 원문 정확 조회.
- `get_case_detail(chunk_id 또는 case uid)` — 사례 상세 조회.
- guardrail: `run_b` 진입 시 `check_input(query)` → blocked면 차단 응답; 답변 후 `check_output(answer)` → blocked면 마스킹/차단. trace에 guardrail 결과 기록.

## 5. 서브 PR 분할

| 서브 | 범위 | 완료 기준 |
| --- | --- | --- |
| **M2-6R-①** | `search_consumer_disputes`에 domain 추가 + `verify_citation` + `get_law_article` + `get_case_detail` 구현, agent에 tool 등록 | frontier smoke: 모델이 domain 지정 검색 + verify_citation 호출, trace 기록 |
| **M2-6R-②** | guardrail pre/post 통합(A 모듈 재사용) | 위험 입력/출력 케이스에서 block/pass + trace 기록 smoke |
| **M2-6R-③** | `/chat?variant=B` 최소 엔드포인트(run_b 라우팅, answer+trace 응답) | `variant=B`로 단발 응답 e2e(서버 또는 TestClient), A(variant 미지정) 무변경 |

각 서브는 별도 feature 브랜치/worktree/PR(branch-worktree-pr-flow), develop 대상.

## 6. 엔드포인트 설계 (최소)

- `backend/app/api/chat.py`: 요청에 `variant`(기본 None/"A") 추가. `variant=="B"`면 MAS 그래프 대신 `variant_b.agent.run_b` 호출, 결과(answer)를 기존 ChatResponse 형태로 매핑(+trace는 디버그 필드/로그). **variant 미지정 시 기존 A 경로 그대로**(무변경 보장).
- non-streaming `/chat`만. `/chat/stream`의 variant=B는 후속.

## 7. 완료 기준 / 검증

- 서브 ①②③ 각 frontier smoke 통과(pod 불필요).
- B가 domain 검색 + verify_citation + lookup + guardrail를 trace에 남기며 단발 응답 생성.
- `/chat?variant=B` 최소 e2e 통과, **A 무변경**(variant 미지정 경로 diff 0).
- (선택) EXAONE 재검증 1회(pod) — 필요 시 분리.

## 8. 환경 / pod

- frontier 개발/검증: **pod 불필요**(venv `~/.venvs/ddoksori-b`, 로컬 pgvector DB).
- EXAONE 재검증을 원하면 pod Resume + tool-calling 재기동(M2-5R 절차) — 선택.

## 9. Next gate

M2-7R: A/B 비교 런 — A(Advanced RAG) vs B(Agentic RAG)를 M2-4R 하니스+동일 eval셋으로 측정(retrieval nDCG/HitRate) + latency/clarification_rate/허위인용 차단율/trace 완전성 종합.
