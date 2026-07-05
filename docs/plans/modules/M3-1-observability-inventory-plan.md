# M3-1 Observability Inventory (계획서)

- 작성일: 2026-06-24
- 모듈: `M3` Agent/RAG workflow 모니터링 시스템 구축 — `M3-1` 현재 trace/metric 구조 inventory
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (L109–122, L200–201)
- 선행 결정: M2-7R(A/B 비교) 완료 후 **M3 먼저** 진행(모니터링 백본), 이후 M2-8R, M2-9R floating
- 성격: **계획서**(코드 없음). M3-1 산출물은 "observability inventory 문서"이며, 본 PR은 그 인벤토리를 **어떻게 작성할지**를 확정한다.
- 원칙: **A(MAS)·B(variant_b) 무변경.** M3-1은 read-only 조사. pod 불필요.

## 0. 한 줄 요약

`/chat` 한 번이 남기는 모든 관측 표면(Prometheus metric, RAG JSON 로그, supervisor trace state, variant_b trace)을 목록화하고, 각 표면을 M3 목표 테이블(`workflow_runs`/`workflow_steps`/`retrieval_events`/`llm_calls`/`guardrail_events`)에 **매핑**하여 **"재사용 vs 신규"를 한 표로 확정**한다. 핵심 설계 긴장(A trace와 B trace의 **shape 불일치**, 그리고 **파일 로그 → DB 영속화** 갭)을 명시적으로 드러내는 것이 목표.

## 1. 목표 / 비목표

### 목표
- 이미 존재하는 관측 자산을 빠짐없이 inventory하고, M3가 **재사용할 것 / 새로 만들 것**을 구분(roadmap M3-1 완료기준).
- M3-2(`workflow_runs` 최소 테이블 설계)가 추측 없이 시작되도록 **필드 출처 매핑**을 제공.

### 비목표
- 테이블/migration 설계·구현(M3-2~M3-7), 조회 API(M3-8).
- 대시보드·Grafana·trace 뷰어 등 시각화/디버깅 UX (M3 범위 밖, scope creep).
- A/B 코드 변경, 신규 계측 추가, 오프라인 eval 하니스(`ab_compare.py`) 변경.

## 2. 조사 대상 (1차 식별 완료, 본 모듈에서 정밀 인벤토리)

| # | 관측 표면 | 위치 | 형태 | 적용 경로 |
| --- | --- | --- | --- | --- |
| S1 | Prometheus 공통 metric | `backend/app/common/metrics.py` | Counter/Histogram + in-memory `AgentMetrics`(percentile) | A(에이전트 전반) |
| S1-note | **노출(scrape) 엔드포인트 부재** | backend 전역에 `generate_latest`/`make_asgi_app` 없음 | Prometheus 객체는 정의·증가만 됨, `/metrics` scrape 엔드포인트 없음. 별도 `api/metrics.py`의 `/metrics/*`는 Prometheus 형식이 아니라 **in-memory `AgentMetrics`를 JSON**으로 주는 REST API(이원화) | — |
| S2 | legal_review metric | `backend/app/agents/legal_review/metrics.py` | 별도 Prometheus(violations/hallucination/confidence/…) + dataclass | A(guardrail/legal) |
| S3 | RAG JSON 구조화 로그 | `backend/app/common/logging/rag_logger.py` | 요청당 JSON 파일 `logs/rag/YYYY-MM-DD/…json` (Retrieval/LLM/NodeTiming/Input/Domain… dataclass) | A |
| S4 | supervisor trace state | `backend/app/supervisor/state/control.py` | `_agent_trace_entries`(append-only), `_node_timings`(Dict) | A(MAS 내부) |
| S5 | variant_b trace | `backend/app/variant_b/agent.py` | in-memory `trace` 리스트(guardrail_input/gate_retrieval/clarify/tool/guardrail_output), 응답에 동봉 | B |

## 3. 산출물: inventory 문서가 답해야 할 질문

`M3-1-observability-inventory-results.md`가 다음을 확정한다.

1. **표면별 필드 목록**: S1–S5 각각이 실제로 담는 필드(예: S3 RetrievalLog의 top-k/similarity/chunk_id, S5 trace의 max_cosine/n_docs/blocked).
2. **M3 테이블 ↔ 출처 매핑표** (핵심 산출물):

   | M3 테이블 | A 출처 | B 출처 | 재사용/신규 | 비고 |
   | --- | --- | --- | --- | --- |
   | `workflow_runs` | S3 RAGLogEntry / S4 | S5 trace | ? | 요청 단위 row, A/B 공통 식별자 필요 |
   | `workflow_steps` | S3 NodeTimingLog / S4 `_node_timings` | S5 trace steps | ? | node duration |
   | `retrieval_events` | S3 Retrieval/ChunkLog | S5 gate_retrieval + tool | ? | top-k/result count/similarity |
   | `llm_calls` | S3 LLMLog + S1 토큰/비용 | S5(미계측?) | ? | provider/model/fallback/error |
   | `guardrail_events` | S2 + S3 Dispute류 | S5 guardrail_in/out | ? | block/pass + reason |

3. **갭/긴장 명시**:
   - **A↔B shape 불일치**: A는 파일 JSON + MAS node 그래프, B는 평평한 trace 리스트. M3 스키마는 **둘 다 쓸 수 있는 공통 형태**여야 함.
   - **파일 → DB 갭**: S3는 이미 M3 필드의 대부분을 담지만 **파일**에 저장 → 쿼리/회귀비교 불가. M3는 이를 DB로 옮기는 일.
   - **측정면 구분(중요)**: M3 테이블은 **라이브 `/chat` 경로**를 기록. 오프라인 A/B retrieval eval(nDCG, `ab_compare.py`)은 별개 측정면 → M3가 자동 흡수하지 않음. M2-8R 실험을 영속화하려면 (a) 계측 서빙 경로 통과 또는 (b) `retrieval_events`가 오프라인 런도 수용하도록 M3-5에서 결정. M3-1은 이 분기점을 **기록만** 한다.
4. **재사용 권고 초안**: 어떤 표면을 source-of-truth로 삼고(예: S3가 가장 풍부), 어떤 것을 deprecate/유지할지 1차 의견(확정은 M3-2+).

## 3.5. 두 계층 구분 — Prometheus(운영 health) ≠ M3 DB(쿼리 분석)

inventory 문서는 관측을 **변종(A/B)이 아니라 두 계층(layer)** 으로 나눠 정리하고, **M3가 채우는 갭이 Layer 2임**을 결론으로 박는다. (A·B 둘 다 양쪽 계층에 들어와야 함 — "A=Prometheus, B=trace"가 아니라 우연한 현 상태일 뿐.)

| 계층 | 정체 | 대상 | 답하는 질문 | 한계 |
| --- | --- | --- | --- | --- |
| **Layer 1: 실시간 집계 지표** | Prometheus 시계열(S1/S2). 포트로 노출→Grafana 등에서 관측 | A·B(`variant` 라벨) | "건강한가/추세는?"(p95 지연, 에러율, 토큰율, 가드레일 차단 수) = backend health check 성격 | **개별 쿼리 내용 소실**. 쿼리 텍스트·요청 ID·검색 chunk는 high-cardinality라 라벨 불가 → 집계 숫자만 남음. 게다가 현재 **노출 엔드포인트도 없음**(§2 S1-note) |
| **Layer 2: 요청 단위 기록** | RAG JSON 파일(S3) → **M3 DB** | A·B 공통 | "이 쿼리에 무엇을 검색하고 왜 이렇게 답했나?" = 업그레이드·수정·회귀분석의 재료 | 현재 S3는 **파일** 저장이라 쿼리/집계 사실상 불가 → **M3가 DB로 옮겨 SQL 조회 가능하게 하는 대상** |

**결론(M3 정당화)**: Prometheus(Layer 1)는 운영 health 대시보드이며 쿼리 단위 분석엔 구조상 부적합하다. 사용자 쿼리 수집·분석·개선의 본체는 **요청 단위 영속 기록(Layer 2 = M3 DB)** 이다. M3-2 이후 "왜 파일/Prometheus가 아니라 DB여야 하는가"의 근거가 이 구분이다. (Layer 1 노출 엔드포인트 추가는 M3 범위 밖의 선택적 후속.)

## 4. 작업 절차

1. S1–S5 각 파일을 정독해 실제 필드·생성 시점·식별자(request_id 등) 추출.
2. `/chat` 1회가 어떤 표면을 어떤 순서로 남기는지 호출경로 추적(A 경로 / B 경로 각각).
3. §3.2 매핑표를 채우고 재사용/신규 판정.
4. 갭·긴장(§3.3) 서술 + 재사용 권고 초안(§3.4).
5. `M3-1-observability-inventory-results.md`로 작성.

## 5. 완료 기준 / 검증

- inventory 문서에 S1–S5 표면이 모두 등재되고, 각 M3 테이블에 대해 **출처 + 재사용/신규 판정 + A/B 양쪽 출처**가 기입됨.
- A↔B shape 불일치, 파일→DB 갭, 라이브 vs 오프라인 측정면 분기가 명시됨.
- A/B 코드 diff 0(read-only 조사). pod 미사용.
- 검증: 매핑표의 각 출처 필드가 실제 코드에 존재함을 인용(파일:라인)으로 뒷받침.

## 6. 환경 / pod

- read-only 코드 조사만. **pod 불필요**, 서버 구동 불필요.

## 7. Next gate

M3-2: `workflow_runs` 단일 최소 테이블 설계(migration 초안). M3-1 매핑표의 `workflow_runs` 행(요청 단위 식별자·시작/종료·variant A/B·status)을 입력으로 사용. 처음부터 모든 테이블을 만들지 않고 `workflow_runs` 하나부터.
