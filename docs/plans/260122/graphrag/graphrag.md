아래는 **GraphRAG(=지식그래프 + 커뮤니티 요약 기반 RAG)** 를 너의 “법률 + 분쟁조정기준(구조화 데이터 포함)” 프로젝트에 붙이는 계획을 **PR 단위**로 쪼갠 로드맵이야. (Microsoft GraphRAG의 **indexing → query** 2단계 구조와, 엔티티/관계 추출→커뮤니티 탐지→커뮤니티 요약이라는 핵심 파이프라인을 전제로 설계했어. ([Microsoft][1]))

---

## 전제(현재 프로젝트에 대한 합리적 가정)

* 기존에 **Vector RAG(예: pgvector)** 가 있고, LangGraph 기반으로 `Query Analysis → Orchestrator → Retriever → Generator/Reviewer` 흐름을 운영 중
* 데이터는 “법령/고시/가이드/분쟁조정기준/사례집” 등 텍스트 코퍼스 + 일부 구조화(표/필드) 형태
* 목표는 **정확도(근거 일치) + 속도(저지연) + 글로벌 질의(전체 기준 요약/테마)** 대응

---

# PR 로드맵

## PR0 — 설계/스펙 고정(아키텍처 & 성공 기준)

**목표:** GraphRAG를 “어떤 질문에 쓰고(적용범위)”, “기존 Vector RAG와 어떻게 공존시키는지” 결정

**Deliverables**

* `docs/graphrag/ADR-0001.md`

  * GraphRAG 사용 케이스 정의

    * **Global 질문**: “해당 분쟁 유형에서 판단 기준의 핵심 요건은?”처럼 **코퍼스 전체를 요약/종합**해야 하는 질의 (GraphRAG가 특히 강한 영역) ([arXiv][2])
    * **Local 질문**: 특정 조문/요건/절차 등 **정확한 근거 조각**이 필요한 질의(기존 Vector RAG도 강함 → 혼합 전략)
  * Orchestrator 라우팅 규칙(초안)

    * `NEED_GLOBAL_GRAPHRAG` / `NEED_LOCAL_GRAPHRAG` / `NEED_VECTOR_RAG` / `NO_RETRIEVAL`
* 성공 지표(예)

  * **근거 정확도(Attribution Precision)**, **누락(Recall)**, **응답 지연(P50/P95)**, **“근거 없는 생성” 차단율**

---

## PR1 — 데이터/스키마 준비(법률·기준에 맞는 엔티티/관계 사전)

**목표:** GraphRAG의 “엔티티/관계 추출”이 법률 도메인에 맞게 나오도록 **스키마/프롬프트 커스터마이즈 기반** 마련
(GraphRAG는 LLM으로 엔티티/관계/클레임 등을 추출하는 파이프라인을 갖고 있고, 파이프라인/프롬프트를 구성 가능하게 설계되어 있어. ([Microsoft GitHub][3]))

**Deliverables**

* `graphrag/schema/legal_entity_types.yaml` (예: 조문, 법령명, 요건, 효과, 예외, 기간, 기관, 절차, 서류, 분쟁유형, 상품/서비스, 책임주체 등)
* `graphrag/schema/legal_relation_types.yaml` (예: `requires`, `exceptions`, `applies_to`, `defined_by`, `refers_to`, `procedure_of`, `deadline`, `evidence_required` 등)
* 프롬프트 템플릿(초안)

  * 엔티티/관계 추출 시 “조문 번호/항/호”, “기준 표의 항목명/조건/결론”을 **구조적으로** 뽑도록 유도

**Acceptance**

* 샘플 50개 문서 chunk에서:

  * 엔티티 중복(동일 조문/법령명) 병합률 OK
  * 조문 참조 관계(예: “제xx조에 따른”)가 일정 비율 이상 추출

---

## PR2 — GraphRAG 인덱싱 파이프라인(오프라인 배치) 구축

**목표:** 코퍼스를 GraphRAG 인덱스로 변환하는 “무거운 작업”을 **배치로 재현 가능**하게 만들기
(GraphRAG는 **지식그래프 생성 + 커뮤니티 계층 + 커뮤니티 요약**을 인덱싱 단계에서 만들고, 질의 시 이를 활용함. ([Microsoft GitHub][4]))

**Deliverables**

* `tools/graphrag_index/`

  * 입력 어댑터: 기존 chunk/jsonl/md → GraphRAG 입력 포맷으로 변환
  * 실행 스크립트: `make graphrag-index` or `python -m tools.graphrag_index.run`
* 인덱싱 산출물 저장 규약(예)

  * `artifacts/graphrag/{corpus_version}/entities.parquet`
  * `.../relationships.parquet`
  * `.../communities.parquet`
  * `.../community_summaries.parquet` (핵심: 커뮤니티 요약) ([Microsoft GitHub][4])

**주의(성능/비용)**

* 커뮤니티 요약(community report)이 병목이 되는 사례가 있어, 배치 병렬화/캐싱/증분 인덱싱 전략을 초기에 넣는 게 좋아. ([GitHub][5])

---

## PR3 — 저장소 레이어 결정(Neo4j vs Postgres vs 파일+캐시)

**목표:** “정확하고 빠르게 가져오기”를 위해 **조회 레이어**를 확정

**권장 옵션(실무적으로)**

* MVP: **파일(Parquet) + 인메모리 캐시 + pgvector** 혼합
* 확장: 그래프 쿼리/탐색이 많아지면 Neo4j 같은 그래프 DB 검토 (법률 문서→KG가 유효하다는 실무 논의가 많음) ([Graph Database & Analytics][6])

**Deliverables**

* `backend/storage/graphrag_store.py`

  * `get_community_summaries(top_k, filters...)`
  * `get_entity_subgraph(entity_ids, depth...)`
* 캐시 정책(예: corpus_version 키드, hot community summary LRU)

---

## PR4 — Query 서비스(로컬/글로벌) + LangGraph Retriever 노드 통합

**목표:** Orchestrator가 **GraphRAG를 호출**할 수 있게 하고, Generator가 “근거로 쓸 컨텍스트”를 안정적으로 받게 만들기
(논문/블로그 기준 GraphRAG는 “커뮤니티 요약→부분 답변→최종 요약”의 계층적 합성을 사용. ([arXiv][2]))

**Deliverables**

* `backend/retrievers/graphrag_retriever.py`

  * `retrieve_global(question)`: 관련 커뮤니티 요약 다건 → partial response 생성(또는 요약들만 전달)
  * `retrieve_local(question)`: 엔티티 중심으로 서브그래프/근거 스니펫 구성
* LangGraph 노드 추가

  * `InfoRetrieverGraphRAGNode`
  * 라우팅: `NEED_GLOBAL_GRAPHRAG` / `NEED_LOCAL_GRAPHRAG`
* 출력 표준화

  * `context_items[]`에 `source_type=community_summary|entity|relationship|raw_chunk` + `source_id` + `corpus_version` + `confidence`

**Acceptance**

* Global 질문에서 “전체 기준 테마 요약” 품질이 기존 Vector RAG 대비 향상(정성+정량)

---

## PR5 — “근거 정확도” 중심 평가 하네스(회귀 테스트 포함)

**목표:** 배포 후에도 **근거 일치/누락/환각**을 지속 측정
(GraphRAG vs RAG 평가 연구/비교들도 있으니, 최소한 내부 벤치+회귀는 꼭 만드는 게 좋아. ([arXiv][7]))

**Deliverables**

* `eval/graphrag/`

  * 테스트 셋(질문-정답-필수근거 IDs)
  * 메트릭:

    * Citation precision/recall (필수 근거 포함 여부)
    * Answer faithfulness (근거 밖 주장 비율)
    * Latency (P50/P95)
* “Vector RAG vs GraphRAG vs Hybrid” A/B 스위치

---

## PR6 — 프로덕션 하드닝(증분 인덱싱, 옵저버빌리티, 안전장치)

**목표:** 운영 가능한 수준으로 안정화

**Deliverables**

* 증분 인덱싱(새 법령/개정/사례 추가 시)

  * 변경분만 재추출 → 커뮤니티 재계산 범위 최소화
* 모니터링

  * 인덱싱 비용/시간, 쿼리 지연, 실패율, 근거 누락률
* 안전장치

  * “근거 없으면 답변 거부/추가 질문” 정책(Reviewer/Guardrail 연동)

---

# 추천 운영 전략(너의 목표에 맞춘 현실적인 결론)

* **속도**: 실시간에는 “커뮤니티 요약(미리 생성)”을 1차로 쓰고, 필요한 경우에만 raw chunk/조문 원문으로 내려가는 2단 구조가 유리해. (GraphRAG가 인덱싱에서 요약을 만들어두는 이유) ([Microsoft][1])
* **정확도**: 법률/기준은 “관계(참조, 요건-효과)”가 중요하니, 엔티티/관계 스키마(PR1)가 성패를 좌우해. ([Microsoft GitHub][3])
* **현실적 혼합**: “정확한 조문 인용”은 여전히 Vector/키워드 기반 retrieval이 강한 경우가 많아서, GraphRAG는 **Global/종합형**에 강하게, Local은 **Hybrid**로 설계하는 게 안전해. ([meilisearch.com][8])

---

원하면 다음 단계로, 너 프로젝트의 현재 노드 구성(Orchestrator 라우팅 enum, Retriever 인터페이스, 저장소: pgvector/Postgres 등)을 기준으로 **PR별 폴더/파일 트리 + 함수 시그니처 + config 템플릿**까지 “바로 개발 들어갈 수 있게” 구체화해줄게.

[1]: https://www.microsoft.com/en-us/research/blog/graphrag-improving-global-search-via-dynamic-community-selection/?utm_source=chatgpt.com "GraphRAG: Improving global search via dynamic ..."
[2]: https://arxiv.org/abs/2404.16130?utm_source=chatgpt.com "From Local to Global: A Graph RAG Approach to Query-Focused Summarization"
[3]: https://microsoft.github.io/graphrag/index/overview/?utm_source=chatgpt.com "Overview - GraphRAG"
[4]: https://microsoft.github.io/graphrag/?utm_source=chatgpt.com "Welcome - GraphRAG"
[5]: https://github.com/microsoft/graphrag/issues/746?utm_source=chatgpt.com "Improve the indexing time (create_community_report part) ..."
[6]: https://neo4j.com/blog/developer/from-legal-documents-to-knowledge-graphs/?utm_source=chatgpt.com "From Legal Documents to Knowledge Graphs"
[7]: https://arxiv.org/html/2502.11371v1?utm_source=chatgpt.com "RAG vs. GraphRAG: A Systematic Evaluation and Key ..."
[8]: https://www.meilisearch.com/blog/graph-rag-vs-vector-rag?utm_source=chatgpt.com "GraphRAG vs. Vector RAG: Side-by-side comparison guide"

---

# 검토

## 1) 현재 코드베이스에 적용 가능성

**결론:** 적용 가능. 다만 **오프라인 인덱싱 파이프라인 + 저장 레이어**가 신규로 필요하며, 라우팅/리트리버 타입 확장이 핵심 작업.

**근거(코드베이스 매핑)**  
- **라우팅/플래닝 확장 여지 있음**: `backend/app/orchestrator/state.py`의 `SearchPlan.retrievers`와 `mode`가 이미 멀티 리트리버 전략을 전제함. `routing.py`도 모드 기반 분기라 GraphRAG용 모드 추가에 구조적 여유가 있음.  
- **리트리버 확장 구조 존재**: `backend/app/agents/retrieval/agent.py`의 `retrieval_node_v2`는 retriever type 리스트를 순차 실행하도록 되어 있어 GraphRAG를 새로운 retriever로 끼우기 쉬움.  
- **저장소/인프라 기본 재료 있음**: pgvector/Postgres 기반 RAG가 이미 있고, RDB 기반 검색도 존재. 다만 GraphRAG는 **그래프/커뮤니티 요약 산출물(Parquet/GraphDB)** 저장 계층이 없으므로 신규 설계 필요.  
- **평가 하네스 확장 가능**: `backend/scripts/evaluation/`에 평가 스크립트가 있어 GraphRAG 전용 지표를 추가해 A/B 평가로 확장 가능.  
- **그래프 DB 부재**: 현 구성에는 Neo4j 등 그래프 DB가 없으므로 MVP는 “파일(Parquet) + 캐시 + pgvector” 중심으로 시작하는 편이 현실적.

## 2) 적용 시 pros/cons 비교 분석

**Pros (GraphRAG 적용 시 기대 이점)**  
- **글로벌/종합 질문 정확도 개선**: 커뮤니티 요약 기반으로 “전체 기준/테마 요약”에 강점. 현 구조의 벡터 검색은 파편적 근거 수집에 유리하나, 전사적 요약에는 한계가 있음.  
- **법률/기준의 관계 정보 활용**: 조문-요건-효과/예외 같은 관계를 그래프로 묶어 의미 기반 근거 제공 가능.  
- **지연 분산**: 인덱싱 단계에서 요약을 사전 생성하면 실시간 응답 지연을 완화할 수 있음.  
- **현 구조와의 하이브리드 공존 용이**: `SearchPlan.retrievers` 기반으로 Vector/Hybrid와 병행 가능하므로 “Global=GraphRAG, Local=Vector” 전략을 쉽게 구현 가능.

**Cons (적용 리스크/비용)**  
- **인덱싱 비용과 운영 복잡도 증가**: 엔티티/관계 추출 + 커뮤니티 요약은 비용/시간이 크고, 증분 업데이트 전략이 필요함.  
- **한국어 법률 도메인 품질 리스크**: LLM 기반 엔티티/관계 추출의 품질이 불안정할 수 있어 스키마/프롬프트 튜닝이 필수.  
- **저장 레이어 추가 부담**: Parquet/캐시 또는 그래프 DB 도입은 운영/모니터링 체계가 추가됨.  
- **근거 인용/추적 난이도**: 커뮤니티 요약은 근거 원문과의 연결이 약해질 수 있어, 인용 메타데이터 설계가 중요.  
- **성능 튜닝 난이도**: Vector/Hybrid와 결합 시 라우팅 기준(글로벌 vs 로컬) 실패가 품질 변동을 야기할 수 있음.
