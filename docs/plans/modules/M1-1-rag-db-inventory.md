# M1-1 RAG DB 의존성 인벤토리

- 작성일: 2026-05-18
- 모듈: `M1-1` 현재 DB/RAG 의존성 목록화
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 목표: 다음 모듈에서 로컬 `pgvector` 복구를 시작하기 전에, 현재 코드가 요구하는 DB object / retrieval 경로 / 환경변수를 파일 근거와 함께 확정한다.
- 이번 모듈에서 하지 않는 일: Docker 수정, DB schema 작성/변경, seed/restore script 작성, app 코드 수정, 테스트 fixture 변경.

## 1. 결론 요약

현재 리포지토리는 RAG 기능이 이미 구현되어 있지만, 로컬에서 재현 가능한 DB 계층은 아직 없다.

핵심 판단은 다음과 같다.

1. **현재 active 검색 대상은 `vector_chunks`이다.**
   - `UnifiedRetriever`, `HybridRetriever`, `RAGRetriever`, `RDSInternalRetriever`, specialized retriever가 모두 `vector_chunks`를 직접 또는 함수 경유로 사용한다.
2. **`search_hybrid_rrf()`와 `search_hybrid_rrf_2()`가 retrieval 품질의 중심이다.**
   - case/counsel 계열은 `search_hybrid_rrf()` 호출을 전제로 한다.
   - law/criteria specialized 경로는 `search_hybrid_rrf_2()` 또는 그와 동등한 inline SQL을 사용한다.
3. **`documents` / `chunks`는 완전히 제거되지 않은 legacy/supporting schema이다.**
   - 일부 specialized 검색, 평가/검증 스크립트, 백업 복구 스크립트가 여전히 `documents JOIN chunks`를 요구한다.
4. **`law_units`는 법령 조문 계층 직접 조회에 필요하다.**
   - 법령 조/항/호/목 단위 검색과 criteria/law 검증에서 사용된다.
5. **`mv_searchable_chunks`는 현재 active retriever에는 없어야 하지만, 테스트/문서에는 남아 있다.**
   - M1-2/M1-3에서 “복구할 object인지, 테스트를 최신 schema로 수정할지” 결정해야 한다.
6. **로컬 compose에는 PostgreSQL/pgvector가 없다.**
   - 현재 `docker-compose.yml`은 backend, frontend, redis만 포함한다.
7. **tracked migration에는 RAG schema가 없다.**
   - `backend/app/database/migrations/004_conversation_memory.sql`은 user/conversation 계층이며 RAG DB schema가 아니다.

따라서 M1-2로 넘어가기 전 기준선은 “`vector_chunks` 중심 schema + RRF 함수 + legacy object 호환 범위”를 명시한 뒤, 외부 DB dump/다른 리포의 DDL을 이 목록과 대조하는 것이다.

## 2. 필수 DB object 후보

| Object | 분류 | 현재 필요도 | 근거 파일 | 필요한 필드/동작 |
| --- | --- | --- | --- | --- |
| `vector` extension | PostgreSQL extension | 필수 | `docs/data/db/03_03_DB_n_API결과.md`, `backend/requirements.txt` | `embedding vector(1536)`, `<=>` cosine/distance 연산 지원 |
| `vector_chunks` | Active RAG table | 필수 | `backend/app/agents/retrieval/tools/unified_retriever.py`, `hybrid_retriever.py`, `retriever.py`, `rds_internal_retriever.py` | `chunk_id`, `dataset_type`, `text`, `embedding`, `text_tsv`, `law_name`, `chunk_type`, `category`, `document_type`, `source_url`, `source_file`, `printed_page`, `source_year`, `metadata` |
| `search_similar_chunks()` | Dense search function | 필요 | `backend/app/agents/retrieval/tools/rds_internal_retriever.py`, `backend/app/agents/retrieval/docs/rds_internal_function.md`, `cli_search_similar_chunks_existing_fn.py` | `query_embedding vector(1536)`, dataset/category/law/year filter, similarity 반환 |
| `search_hybrid_rrf()` | Hybrid RRF function | 필수 | `backend/app/agents/retrieval/tools/unified_retriever.py`, `case_agent.py`, `counsel_agent.py`, `backend/app/agents/retrieval/README.md` | `query_text`, `query_embedding`, dataset/category/document_type/year filter, `rrf_score`, `bm25_score`, `vector_similarity` 반환 |
| `search_hybrid_rrf_2()` | Enhanced Hybrid RRF | 필수 후보 | `backend/app/agents/retrieval/tools/specialized_retrievers.py`, `rds_internal_retriever.py`, `docs/law_criteria_retrieval_subagents.md` | document_type array, chunk_type array, year range, metadata field matching |
| `documents` | Legacy/supporting table | 호환 필요 | `backend/app/agents/retrieval/tools/specialized_retrievers.py`, `backend/scripts/evaluation/*.py`, `backend/scripts/backup/restore_from_s3.sh` | `doc_id`, `doc_type`, `title`, `source_org`, `url`, `metadata` 등 |
| `chunks` | Legacy/supporting table | 호환 필요 | `backend/app/agents/retrieval/tools/specialized_retrievers.py`, `backend/scripts/evaluation/*.py`, `backend/scripts/backup/restore_from_s3.sh` | `chunk_id`, `doc_id`, `chunk_type`, `chunk_index`, `content`, `embedding`, `drop`, chunk count 계산 |
| `law_units` | Law hierarchy table | 필요 | `backend/app/agents/retrieval/tools/specialized_retrievers.py`, `backend/scripts/evaluation/verify_loaded_data.py`, `backend/data/docs/law_data_usage_guide.md` | `doc_id`, `law_id`, `parent_id`, `level`, `article_no`, `paragraph_no`, `item_no`, `subitem_no`, `path`, `text`, indexable flag 계열 |
| `mv_searchable_chunks` | Legacy materialized view | 결정 필요 | `backend/scripts/testing/conftest.py`, `backend/scripts/testing/e2e/test_system_architecture.py`, `backend/README.md` | 테스트 fixture는 필요 object로 보지만 active retriever는 참조하지 않아야 한다는 테스트도 존재 |
| `users`, `conversations`, `conversation_turns`, `conversation_summaries`, `oauth_sessions` | Auth/conversation schema | RAG 복구와 별개 | `backend/app/database/migrations/004_conversation_memory.sql` | 현재 M1 범위에서는 중요하지 않음. 로컬에서는 최소 동작만 보장하면 됨 |

## 3. `vector_chunks` 최소 계약

문서화된 schema 기준으로 현재 코드가 기대하는 최소 column은 아래와 같다.

```sql
chunk_id        varchar primary key
dataset_type    varchar      -- 'law_guide' | 'case'
text            text
embedding       vector(1536)
text_tsv        tsvector     -- BM25/FTS 검색용. 문서 schema 예시에는 누락되어 있으나 RRF SQL에서 사용
law_name        varchar
chunk_type      varchar
category        varchar      -- 상담/해결/조정 등 case category
document_type  varchar      -- 법률/시행령/행정규칙/별표 등 law guide type
source_url      text
source_file     varchar
printed_page    integer
source_year     integer
metadata        jsonb
created_at      timestamp
updated_at      timestamp
```

추가로 필요한 index 후보는 다음과 같다.

- HNSW/IVFFlat 계열 vector index on `embedding`
- GIN index on `text_tsv`
- GIN index on `metadata`
- B-tree filter indexes: `dataset_type`, `category`, `document_type`, `source_year`, 필요 시 `law_name`, `chunk_type`

M1-2에서는 index까지 구현하지 말고, container와 extension 확인에 집중한다. Index/schema 적용은 M1-3 이후 별도 모듈로 분리한다.

## 4. Retrieval 경로 매트릭스

| 진입점 | 선택/노드 | 검색 구현 | DB 의존성 | 비고 |
| --- | --- | --- | --- | --- |
| MAS supervisor | `retrieval_law` | `LawRetrievalAgent` → `specialized_retrievers.py` | `vector_chunks`, `law_units`, `search_hybrid_rrf_2` 계열 | `graph_mas.py`는 v2 기준 counsel 제외 3개 retrieval agent 주석 존재 |
| MAS supervisor | `retrieval_criteria` | `CriteriaRetrievalAgent` → `specialized_retrievers.py` | `vector_chunks`, `documents/chunks` 일부 legacy, `search_hybrid_rrf_2` | criteria는 `case` dataset의 `해결` category와 law guide 모두 관련 |
| MAS supervisor | `retrieval_case` | `CaseRetrievalAgent` → base/unified retriever | `search_hybrid_rrf()`, `vector_chunks` | case/counsel 분류는 `dataset_type='case'`, `category`로 매핑 |
| standalone retrieval | `CounselRetrievalAgent` | `UnifiedRetriever` 계열 | `search_hybrid_rrf()`, `vector_chunks` | 현재 MAS graph에서는 제외 주석이 있지만 모듈은 존재 |
| API `/search` | `RETRIEVAL_MODE=hybrid` | `HybridRetriever` | `vector_chunks`, `text_tsv`, OpenAI embedding | `backend/app/api/dependencies.py`에서 선택 |
| API `/search` | `RETRIEVAL_MODE=dense` | `RAGRetriever` | `vector_chunks`, `embedding` | 기본값은 코드상 `dense`, `.env.example`은 `hybrid` |
| health/check scripts | DB/RAG smoke | `diagnose_chat.py`, E2E tests | `vector_chunks`, `documents/chunks`, `mv_searchable_chunks` 혼재 | 테스트 기대값 정리가 필요 |
| evaluation | RAGAS/retrieval eval | `backend/scripts/evaluation/*` | `documents/chunks`, `law_units`, `search_hybrid_rrf_2` | 포트폴리오 수치화 단계에서 재사용 가능 |

## 5. 환경변수 / 설정 인벤토리

| 영역 | 환경변수 | 현재 의미 | 근거 |
| --- | --- | --- | --- |
| DB connection | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL 연결. 기본값은 localhost/postgres/ddoksori 계열 | `backend/app/api/dependencies.py`, `backend/app/common/config.py`, `.env.example` |
| Retrieval mode | `RETRIEVAL_MODE` | `hybrid`면 `HybridRetriever`, 그 외는 `RAGRetriever` | `backend/app/api/dependencies.py` |
| OpenAI embedding | `OPENAI_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `USE_OPENAI_EMBEDDING` | 현재 active retriever 다수는 `text-embedding-3-large`, 1536차원을 전제 | `.env.example`, `unified_retriever.py`, `common/embedding/factory.py` |
| Local embedding server | `EMBEDDING_API_URL`, `EMBEDDING_MODEL_NAME`, `PORT` | `services/embedding_server.py`와 `LocalEmbeddingProvider`가 있으나 retrieval 전체에 일관 적용되지는 않음 | `backend/app/agents/retrieval/services/embedding_server.py`, `backend/app/common/embedding/local_provider.py` |
| Redis cache | `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | embedding/answer/cache 계층에서 사용. local compose에는 redis만 존재 | `docker-compose.yml`, `backend/app/common/cache/*`, `.env.example` |
| Conversation memory | `CONVERSATION_MEMORY_BACKEND` 등 | RAG 복구 핵심은 아님. 로컬 최소 동작이면 충분 | `backend/app/supervisor/checkpointer.py`, `004_conversation_memory.sql` |

## 6. 현재 로컬 재현성 gap

1. **PostgreSQL/pgvector container 없음**
   - `docker-compose.yml`에는 `backend`, `frontend`, `redis`만 있다.
2. **RAG schema migration 없음**
   - tracked migration은 `004_conversation_memory.sql`뿐이며, `vector_chunks`, RRF 함수, `documents/chunks`, `law_units`를 생성하지 않는다.
3. **RRF 함수 migration 파일 불일치**
   - `unified_retriever.py`/README는 `004_add_rrf_search_functions.sql`을 언급하지만 현재 tracked file로는 확인되지 않는다.
   - 대신 `backend/app/agents/retrieval/docs/rds_internal_function.md`에 함수 정의 문서가 있다.
4. **active schema와 legacy test schema가 혼재**
   - active retriever는 `vector_chunks` 중심이다.
   - 일부 fixture/evaluation/backup은 `documents`, `chunks`, `mv_searchable_chunks`를 요구한다.
5. **임베딩 차원 일관성 확인 필요**
   - `vector_chunks`와 RRF 함수는 `vector(1536)` / OpenAI `text-embedding-3-large` 기준이다.
   - local embedding provider와 `EMBEDDING_MODEL_NAME=nlpai-lab/KURE-v1` 경로는 차원이 1024일 수 있어, 로컬 모델 전환 시 schema/embedding 차원 변경 전략이 필요하다.
6. **외부 DB 복원 소스 필요**
   - 기존 RDS dump, 다른 repo의 DDL/seed, 또는 volume backup 중 무엇을 기준으로 복구할지 확정해야 한다.

## 7. M1-2 / M1-3 handoff

### M1-2에서 할 일

- `docker-compose.yml`에 PostgreSQL + pgvector service만 추가한다.
- volume 이름, port, local env 연결값을 확정한다.
- 검증은 `CREATE EXTENSION vector` 가능 여부와 `SELECT extversion FROM pg_extension WHERE extname='vector'` 수준으로 제한한다.
- `vector_chunks` schema나 seed data는 아직 만들지 않는다.

### M1-3에서 할 일

- 외부 참고 repo 또는 dump에서 실제 DDL을 가져와 이 문서의 object 목록과 비교한다.
- 최소 schema를 다음 순서로 분리한다.
  1. `vector` extension
  2. `vector_chunks` table
  3. `text_tsv` 생성 방식 / trigger 또는 generated column
  4. `search_similar_chunks()`
  5. `search_hybrid_rrf()`
  6. `search_hybrid_rrf_2()`
  7. `documents/chunks/law_units/mv_searchable_chunks` 호환 범위 결정
- local seed/restore는 schema 확정 이후 별도 모듈로 진행한다.

### 사용자 확인이 필요한 항목

- 참고할 “다른 리포” 또는 DB dump/backup 위치
- `vector_chunks`만 살릴지, `documents/chunks/law_units`도 local 개발에서 복구할지
- 로컬 모델 전환 시에도 `vector(1536)`을 유지할지, 모델 차원에 맞춰 별도 embedding table/schema를 만들지

## 8. 다음 단계 제한

M1-1 완료 후 바로 구현을 넓히지 않는다. 다음 대화에서는 이 인벤토리를 기준으로 다음 중 하나만 선택한다.

1. M1-2: `pgvector` local container 추가
2. M1-3: 외부 DDL/dump와 object 목록 비교
3. M1-1 보완: 누락된 retrieval path 또는 DB object 추가 조사

## 9. 검증 근거

이번 문서는 다음 repo-local 근거를 기준으로 작성했다.

- 상위 계획 확인: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- active retriever 검색: `backend/app/agents/retrieval/tools/unified_retriever.py`, `hybrid_retriever.py`, `retriever.py`, `rds_retriever.py`, `rds_internal_retriever.py`, `specialized_retrievers.py`
- retrieval agent / supervisor 확인: `backend/app/agents/retrieval/*.py`, `backend/app/supervisor/graph_mas.py`
- API dependency 확인: `backend/app/api/dependencies.py`, `backend/app/api/search.py`, `backend/app/api/health.py`
- DB/RRF 문서 확인: `docs/data/db/03_03_DB_n_API결과.md`, `backend/app/agents/retrieval/docs/rds_internal_function.md`, `docs/data/db/01_00_DB전략.md`
- local compose 확인: `docker-compose.yml`
- env/config 확인: `.env.example`, `backend/app/common/config.py`, `backend/app/common/embedding/*`, `backend/app/common/cache/*`
- migration 확인: `backend/app/database/migrations/004_conversation_memory.sql`
- legacy/test object 확인: `backend/scripts/testing/conftest.py`, `backend/scripts/testing/e2e/test_system_architecture.py`, `backend/scripts/evaluation/*`, `backend/scripts/backup/restore_from_s3.sh`
