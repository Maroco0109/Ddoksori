# M3-1 Observability Inventory (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-1` 현재 trace/metric 구조 inventory
- 계획서: `docs/plans/modules/M3-1-observability-inventory-plan.md`
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (L109–122)
- 성격: **read-only 조사 결과.** A(MAS)·B(variant_b) 코드 무변경, pod 미사용.
- 검증 원칙: 모든 출처 필드는 실제 코드를 `파일:라인`으로 인용한다.

## 0. 한 줄 결론

`/chat` 한 번이 남기는 관측 표면은 **5개(S1–S5)** 이며, 이를 **두 계층(Layer 1 실시간 집계 / Layer 2 요청 단위 기록)** 으로 정리했다. M3가 채우는 갭은 **Layer 2**다. 요청 단위 기록의 가장 풍부한 source-of-truth는 **S3(RAG JSON 파일)** 이지만 **파일 저장이라 쿼리/회귀비교 불가**, 그리고 **B 경로(S5)는 아예 영속화되지 않고 응답에서도 버려진다**(가장 큰 갭). M3는 (a) S3의 필드를 DB로 옮기고 (b) A/B를 같은 스키마로 흡수하는 공통 식별자·공통 형태를 만드는 일이다.

---

## 1. 표면별 필드 목록 (S1–S5)

### S1 — Prometheus 공통 metric + in-memory `AgentMetrics`
`backend/app/common/metrics.py`

- **Prometheus 객체**(정의·증가만, 노출 없음):
  - `agent_execution_seconds` Histogram, label `agent_name` (`metrics.py:17`)
  - `agent_requests_total` Counter, label `agent_name,status` (`metrics.py:20`)
  - `llm_tokens_total` Counter, label `model,type` (`metrics.py:23`)
  - `agent_tool_usage_total` Counter, label `tool_name,mode` (`metrics.py:26`)
  - `cache_hits_total / cache_misses_total / cache_errors_total` (`metrics.py:31-33`)
  - `llm_cost_usd_total` label `model`, `embedding_cost_usd_total` (`metrics.py:36-39`)
- **in-memory `AgentMetrics`**(클래스 변수 `_metrics`, agent당 최대 1000건, `metrics.py:53-55`):
  - `MetricRecord`: `agent, operation, duration_ms, success, error, timestamp, metadata` (`metrics.py:42-50`)
  - 집계 `get_stats()`: `count, success_rate, avg/max/min_duration_ms, p50/p95/p99` (n<5면 percentile=None) (`metrics.py:139-179`)
- **식별자**: 없음. agent_name 단위로만 집계되고 **request_id가 없다** → 개별 쿼리 추적 불가.
- **노출**: Prometheus `generate_latest`/`make_asgi_app` 부재(전역 grep 0). 별도 REST API만 존재(아래).

### S1-REST — `AgentMetrics` JSON API
`backend/app/api/metrics.py` (`prefix=/metrics`, admin 전용)
- `GET /metrics/agents?agent_name=` → `AgentMetrics.get_stats` (`metrics.py:17-32`)
- `GET /metrics/agents/summary` → `get_summary` (`metrics.py:35-45`)
- `GET /metrics/agents/recent?limit=` → `get_recent_records` (`metrics.py:48-66`)
- 즉 `/metrics/*`는 **Prometheus 형식이 아니라 in-memory 집계를 JSON으로** 주는 REST(이원화). 프로세스 재시작 시 소실.

### S2 — legal_review metric
`backend/app/agents/legal_review/metrics.py`
- **Prometheus**(지연 초기화, `metrics.py:29-83`): `legal_review_violations_total{violation_type}`, `..._hallucination_detected_total`, `..._legal_judgment_detected_total`, `..._confidence_score`(Hist), `..._llm_calls_total{status}`, `..._processing_seconds`(Hist), `..._reviews_total{result}`, `..._relevance_score`(Hist). S1과 같은 노출 부재 문제 공유.
- **오프라인 평가용 dataclass**(라이브 경로 아님): `ReviewEvalResult`(precision/recall/f1/tp/fp/fn/tn, `metrics.py:193-228`), `aggregate_review_results`(`metrics.py:316-366`). 이는 goldenset 평가(Phase 4)용이지 `/chat` 라이브 기록이 아님 → M3 직접 대상 아님.

### S3 — RAG JSON 구조화 로그 (가장 풍부)
`backend/app/common/logging/rag_logger.py`, 출력 `logs/rag/YYYY-MM-DD/HHMMSS_{request_id8}.json` (`rag_logger.py:667`)
- 루트 `RAGLogEntry`: `request_id, timestamp, query, input_data, retrieval, structured_retrieval, llm, response, total_time_ms, node_timings[], pipeline_trace` (`rag_logger.py:270-290`)
- `InputLog`: `message, session_id, chat_type, onboarding, top_k, chunk_types, agencies` (`rag_logger.py:248-262`)
- `RetrievalLog`: `mode, top_k, embedding_time_ms, search_time_ms, dense_candidates, lexical_candidates, chunks[]` (`rag_logger.py:65-79`)
- `ChunkLog`: `chunk_id, doc_id, doc_title, doc_type, chunk_type, source_org, similarity, content_preview` (`rag_logger.py:47-62`)
- `StructuredRetrievalLog`(4섹션): `domain, disputes[], counsels[], laws[], criteria[]` (`rag_logger.py:211-223`) — 각 dataclass에 `similarity`, 메타데이터(예: Dispute의 `mediation_result`, `dispute_amount`) 포함 (`rag_logger.py:140-208`)
- `LLMLog`: `model, system_prompt, user_prompt, prompt_tokens, completion_tokens, response_time_ms, has_sufficient_evidence, clarifying_questions[]` (`rag_logger.py:87-102`)
- `ResponseSummary`: `answer_length, chunks_used, sources_count, status(success|no_results|error), error_message` (`rag_logger.py:105-117`)
- `NodeTimingLog`: `node_name, duration_ms, start_time, end_time, input_snapshot, output_snapshot, state_changes[]` (`rag_logger.py:231-245`)
- `pipeline_trace`: `build_pipeline_summary()` 결과(아래 S4)
- **식별자**: `request_id`(uuid, `rag_logger.py:346`), `session_id`(InputLog). **A 경로 단위 식별자 보유.**
- **호출 경로**: `/chat` A 경로가 `create_entry`(`chat.py:91`) → `log_input/…/log_response`(`chat.py:96-301`) → `finalize`+`save`(`chat.py:308-309`). 활성화는 `is_rag_logging_enabled()` 게이트(`rag_logger.py:329`).

### S4 — supervisor trace state
`backend/app/supervisor/state/control.py` + `backend/app/supervisor/graph.py`
- `TraceEntry`(TypedDict): `node_name, timestamp, duration_ms, protocol_summary, metadata` (`control.py:26-46`)
- `_agent_trace_entries`: `Annotated[List[TraceEntry], operator.add]`(append-only, 병렬 fan-out 호환, `state/__init__.py:231`)
- `_node_timings`: `Dict[node→{start,end,duration_ms,input/output_snapshot,state_changes}]` (`graph.py:281-288`)
- `ControlState` 라우팅/가드레일 필드: `mode, low_similarity_mode, guardrail_blocked, guardrail_type, query_complexity, retry_count` (`control.py:96-102`)
- `build_pipeline_summary(trace_entries,total)` → `{total_duration_ms, node_count, node_sequence[], per_node[{seq,node,duration_ms,summary}]}` (`graph.py:215-238`)
- **호출 경로**: `_create_timed_node` 래퍼가 노드마다 timing+trace_entry 생성(`graph.py:281-299`). `/chat`이 `final_state["_agent_trace_entries"]`를 꺼내(`chat.py:288`) summary 빌드 후 S3 `pipeline_trace`로 저장. **즉 S4는 독립 저장이 아니라 S3에 흡수되어 영속화된다.**

### S5 — variant_b trace (B)
`backend/app/variant_b/agent.py`, in-memory `trace: List[Dict]`(`agent.py:49`)
- step별 평평한 dict: `guardrail_input{blocked,flagged}`(`agent.py:53`), `gate_retrieval{max_cosine,n_docs}`(`agent.py:67`), `clarify{reason}`(`agent.py:71`), `react{n_tool_calls,tool_calls[],n_retrieved}`(`agent.py:102`), `guardrail_output{blocked,flagged}`(`agent.py:111`)
- 반환 dict: `clarified, blocked, answer, max_cosine, tool_calls[], retrieved_chunk_ids[], trace[]` (`agent.py:116-124`)
- **식별자**: 없음(request_id/session_id 미부여).
- **호출 경로 / 치명적 갭**: `/chat`의 `variant=="B"` 분기가 `run_b`를 호출(`chat.py:111-116`)하지만 **`ChatResponse`를 곧바로 return(`chat.py:118-126`)** 하면서 `b_result["trace"]`·`tool_calls`·`max_cosine`·`retrieved_chunk_ids`를 **응답에도 넣지 않고 rag_logger로도 저장하지 않는다.** `model`은 실제 spec이 아닌 정적 문자열 `"variant-b"`(`chat.py:122`). **→ B의 관측치는 100% 휘발.**

---

## 2. M3 테이블 ↔ 출처 매핑표 (핵심 산출물)

| M3 테이블 | A 출처 (라이브) | B 출처 (라이브) | 판정 | 비고 |
| --- | --- | --- | --- | --- |
| `workflow_runs` | S3 `RAGLogEntry`(`request_id,session_id,query,total_time_ms,response.status`) | **없음**(S5는 식별자 무·미저장) | **재사용+신규** | A 필드 매핑 가능. **B는 신규로 만들어야**: run_b에 run_id 부여 + 저장 훅. `variant`(A/B) 컬럼 신설 |
| `workflow_steps` | S3 `node_timings[]` ← S4 `_agent_trace_entries`/`_node_timings` (`graph.py:281`) | S5 `trace[]`(평평한 step 리스트) | **재사용(A)+변환(B)** | A는 LangGraph node 그래프, B는 5-step 선형. 공통 step 스키마(`run_id,seq,name,duration_ms`)로 정규화 필요. **B엔 step별 duration 없음**(추가 계측 or null 허용 결정은 M3-4) |
| `retrieval_events` | S3 `RetrievalLog`+`ChunkLog`+`StructuredRetrievalLog`(top_k, similarity, chunk_id, mode, dense/lexical_candidates) | S5 `gate_retrieval{max_cosine}` + `react.retrieved_chunk_ids` | **재사용(A)+신규(B)** | A가 압도적으로 풍부. B는 gate cosine과 tool 검색 chunk_id만 → 최소 매핑 |
| `llm_calls` | S3 `LLMLog`(model,prompt/completion_tokens,response_time_ms) + S1 `llm_tokens_total`/`llm_cost_usd_total` | **없음**(S5 미계측, `model`도 정적) | **재사용(A)+신규(B)** | fallback/error 필드는 A도 `ResponseSummary.status`/`error_message`로 간접 → M3-6에서 명시 컬럼화. B는 provider/model 캡처 자체가 신규 |
| `guardrail_events` | S2 Prometheus(violations/hallucination/confidence) + S3 `StructuredRetrievalLog`(Dispute류) + `ControlState.guardrail_blocked/guardrail_type` | S5 `guardrail_input`/`guardrail_output{blocked,flagged}` | **재사용 양쪽** | A는 두 출처(legal_review S2 + moderation 상태)로 분산, B는 공통 `check_input/check_output` trace. block/pass+reason 공통화 가능 |

판정 요약: **A는 거의 재사용**(S3가 source-of-truth), **B는 거의 신규**(저장 훅 + 식별자부터 신설). 5개 테이블 모두 **variant(A/B) 식별 컬럼**과 **공통 run_id**가 선행 요건.

---

## 3. 갭 / 설계 긴장 (명시)

1. **A↔B shape 불일치**: A = 파일 JSON + LangGraph node 그래프(`node_sequence`), B = 평평한 5-step trace 리스트. M3 스키마는 **둘 다 표현 가능한 공통 형태**(run 1 : step N, step.name 자유문자열, duration nullable)여야 한다.
2. **파일 → DB 갭(Layer 2 본체)**: S3는 이미 M3 필드 대부분을 담지만 **파일**(`logs/rag/.../*.json`)이라 SQL 쿼리·회귀비교 불가. M3-3~M3-7은 이 dataclass들을 **DB row로 옮기는 일**이며 스키마 설계 부담이 낮다(필드가 이미 정의돼 있음).
3. **B 경로 미영속(가장 큰 갭)**: `chat.py:118` early return으로 S5는 응답·저장 양쪽에서 버려진다. M3가 A/B 비교를 DB로 하려면 **B에 (a) run 식별자 부여, (b) 저장 훅, (c) 실제 model spec 캡처**를 추가해야 한다(코드 변경 필요 → M3-3+에서, 본 M3-1 범위 밖).
4. **식별자 부재 표면**: S1(AgentMetrics)·S2·S5는 request_id가 없어 개별 쿼리로 join 불가. M3 join 키는 **S3의 request_id를 표준**으로 삼는 것이 자연스럽다.
5. **라이브 vs 오프라인 측정면 분기**: M3 테이블은 **라이브 `/chat`** 을 기록한다. 오프라인 A/B retrieval eval(nDCG, `scripts/.../ab_compare.py`)과 S2의 `ReviewEvalResult`(goldenset precision/recall)는 **별개 측정면**이라 M3가 자동 흡수하지 않는다. M2-8R 실험을 영속화하려면 (a) 계측 서빙 경로 통과 또는 (b) `retrieval_events`가 오프라인 런도 수용하도록 M3-5에서 결정. **M3-1은 이 분기점을 기록만 한다.**

---

## 4. 두 계층 구분 — Prometheus(운영 health) ≠ M3 DB(쿼리 분석)

| 계층 | 정체 | 표면 | 답하는 질문 | 한계 |
| --- | --- | --- | --- | --- |
| **Layer 1: 실시간 집계 지표** | Prometheus 시계열 | S1, S2 | "건강한가/추세는?" p95 지연·에러율·토큰율·가드레일 차단 수 (backend health) | 개별 쿼리 내용 소실(high-cardinality 라벨 불가). 게다가 **노출 엔드포인트 부재**(S1-note) — 현재는 S1-REST JSON으로만 부분 노출 |
| **Layer 2: 요청 단위 기록** | RAG JSON 파일(S3) + B trace(S5) → **M3 DB** | S3, S4(흡수), S5 | "이 쿼리에 무엇을 검색하고 왜 이렇게 답했나?" = 업그레이드·회귀분석 재료 | S3는 파일이라 쿼리 난, S5는 아예 미저장 → **M3가 DB로 옮기는 대상** |

**결론(M3 정당화)**: Layer 1(Prometheus)은 운영 health용이며 쿼리 단위 분석엔 구조상 부적합하다. 사용자 쿼리 수집·분석·개선의 본체는 **요청 단위 영속 기록(Layer 2 = M3 DB)** 이다. M2-7R 류 A/B 회귀비교를 재실행·SQL 집계 가능하게 만드는 것이 M3의 가치다. (Layer 1 scrape 엔드포인트 추가는 M3 범위 밖의 선택적 후속.)

> 주의: "A=Prometheus, B=trace"가 아니다. A·B **둘 다** 양쪽 계층에 들어와야 하며, 현재 B가 Layer 1·2 모두 비어 있는 것은 설계가 아니라 **미구현 상태**일 뿐이다.

---

## 5. 재사용 권고 초안 (확정은 M3-2+)

- **Source-of-truth = S3(RAGLogEntry)**. M3 테이블 컬럼은 S3 dataclass 필드를 1차 차용 → 설계 추측 최소화.
- **S4는 S3에 흡수된 채로 유지**(독립 테이블 불필요). `workflow_steps`는 `node_timings`/`pipeline_summary`를 평탄화해 채운다.
- **S1/S2(Prometheus)는 deprecate 아님 — 역할 분리**. Layer 1 운영지표로 존치하되 M3 DB와 이중 기록하지 않는다(M3는 Layer 2만 채움).
- **B(S5)는 신규 저장 경로 필수**. 최소 단위로 `run_b` 결과를 A와 같은 `workflow_runs` 행으로 흘리는 훅을 M3-3에서 추가(식별자·variant 컬럼 포함).
- **공통 식별자 표준 = `request_id`**(S3). B에도 동일 키를 부여해 A/B를 한 테이블에서 비교한다.

---

## 6. 완료 기준 점검 (계획서 §5 대비)

- [x] S1–S5 표면 전부 등재 + 각 필드를 `파일:라인`으로 인용.
- [x] 5개 M3 테이블 각각에 A 출처·B 출처·재사용/신규 판정 기입(§2).
- [x] A↔B shape 불일치 / 파일→DB 갭 / B 미영속 / 라이브 vs 오프라인 분기 명시(§3).
- [x] 두 계층 구분 + M3 정당화 결론(§4).
- [x] A/B 코드 diff 0(read-only). pod 미사용.

## 7. Next gate → M3-2

`workflow_runs` 단일 최소 테이블 설계(migration 초안). 입력으로 본 문서 §2의 `workflow_runs` 행을 사용:
`run_id(=request_id)`, `session_id`, `variant(A|B)`, `query`, `started_at`, `total_time_ms`, `status`. 처음부터 모든 테이블을 만들지 않고 `workflow_runs` 하나부터. **B 영속화 훅(§3-3)은 M3-3 구현 시점의 선결 과제로 인계.**
