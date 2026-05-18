# M1-3 RAG Schema Compatibility 결정 문서

- 작성일: 2026-05-18
- 모듈: `M1-3` Vector DB 스키마 복구 계획
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `docs/plans/modules/M1-1-rag-db-inventory.md`, `docs/plans/modules/M1-2-vector-db-smoke.md`
- 목표: M1-2에서 확인한 복원 DB 상태를 기준으로, 다음 구현 모듈에서 무엇을 복구/편입/제외할지 결정한다.
- 이번 모듈에서 하지 않는 일: SQL 실행, DB volume 변경, `docker-compose.yml` 수정, backend retrieval 코드 수정, 검색 품질 튜닝.

## 1. Clarified request

사용자의 현재 요청은 다음과 같이 해석한다.

1. `.env`는 secret이므로 git에 포함하지 않는다.
   - worktree를 삭제하면 그 worktree 안의 `.env`도 같이 사라진다.
   - local 실행이 필요하면 `cp .env.example .env` 후 `OPENAI_API_KEY` 등 개인 값을 채운다.
2. `search_hybrid_rrf_2()`는 legacy로 버리지 않는다.
   - 다음 구현 단계에서 DB schema에 복구해야 하는 함수로 확정한다.
   - 현재 repository 안에는 참고 가능한 DDL 문서가 있다: `backend/app/agents/retrieval/docs/rds_internal_function.md`.
3. PostgreSQL/pgvector는 최종적으로 Ddoksori `docker-compose.yml` 내부 service로 편입한다.
   - 현재는 외부 프로젝트의 Docker DB build를 로컬에서 활용하고 있다.
   - 이 외부 DB는 테스트와 dump/restore 기준선으로 최대한 활용한다.
   - 외부 hosted DB/RDS 같은 서비스는 local 재현성 검증이 끝난 뒤 고려한다.
4. 이번 M1-3은 구현이 아니라 **결정 문서 모듈**이다.
   - 한 번에 하나 이상의 작업을 하지 않기 위해, 실제 DB/compose 변경은 후속 모듈로 분리한다.

## 2. 현재 확인된 기준선

M1-2 기준 현재 복원 DB는 active RAG 검색의 최소 기준선을 만족한다.

| 항목 | 상태 | M1-3 판단 |
| --- | --- | --- |
| `vector` extension | 존재 | 유지 |
| `vector_chunks` | 존재 | active table로 확정 |
| embedding dimension | `1536` | `text-embedding-3-large` matryoshka 기본 차원으로 유지 |
| `text_tsv` | 존재 | hybrid/BM25 검색 필수 |
| `search_similar_chunks()` | 존재 | dense smoke 기준으로 유지 |
| `search_hybrid_rrf()` | 존재 | case/counsel 계열 active 함수로 유지 |
| `search_hybrid_rrf_2()` | 없음 | 후속 모듈에서 복구 |
| `documents`, `chunks`, `law_units`, `mv_searchable_chunks` | 없음 | 당장 전체 복구하지 않고 사용 경로별로 분리 판단 |
| compose DB service | 없음 | 후속 모듈에서 Ddoksori 내부 service로 편입 |

## 3. 결정 1: `search_hybrid_rrf_2()` 복구

### 결정

`search_hybrid_rrf_2()`는 후속 구현 모듈에서 DB schema에 복구한다.

### 이유

- `M1-1`에서 법령/기준 specialized retrieval 경로가 `search_hybrid_rrf_2()` 또는 동등한 inline SQL에 의존한다고 정리했다.
- `backend/app/agents/retrieval/tools/rds_internal_retriever.py`에는 `search_hybrid_rrf_2` 호출/호환 로직이 남아 있다.
- `backend/app/agents/retrieval/tools/specialized_retrievers.py`는 law/criteria 검색에서 `search_hybrid_rrf_2()` 계열 경로를 사용한다.
- `backend/app/agents/retrieval/docs/rds_internal_function.md`에는 `CREATE OR REPLACE FUNCTION search_hybrid_rrf_2(...)` DDL이 존재한다.
- 포트폴리오 목적상, specialized retrieval을 inline SQL fallback에만 의존시키기보다 DB function으로 고정하면 검색 기준선과 측정 지표를 안정화하기 쉽다.

### 후속 구현 범위

다음 구현 모듈에서는 아래만 수행한다.

1. `search_hybrid_rrf_2()` DDL을 repository-tracked SQL migration 또는 schema file로 이동/정리한다.
2. 현재 복원 DB에 적용 가능한지 local DB에서 검증한다.
3. `check_vector_db_smoke.py`에 `search_hybrid_rrf_2()` 존재 및 sample query 검증을 추가한다.
4. backend retrieval 코드의 대규모 수정은 하지 않는다.

### 완료 기준

- `SELECT proname FROM pg_proc WHERE proname = 'search_hybrid_rrf_2';` 로 존재 확인 가능
- sample query가 `vector_chunks`에서 결과를 반환하거나, 결과 0건이어도 함수 실행 에러가 없어야 함
- M1-2 smoke script가 `search_hybrid_rrf_2()`를 missing이 아닌 OK로 표시

## 4. 결정 2: legacy schema는 즉시 전체 복구하지 않음

### 결정

`documents`, `chunks`, `law_units`, `mv_searchable_chunks`는 M1-3 기준으로 즉시 전체 복구하지 않는다.

다만 완전히 버리는 것도 아니다. 다음처럼 나눈다.

| Object | 결정 | 이유 |
| --- | --- | --- |
| `documents` | 보류 | evaluation/backup script에 남아 있으나 active retrieval은 `vector_chunks` 중심 |
| `chunks` | 보류 | `documents`와 함께 legacy/evaluation 경로에 필요 |
| `law_units` | 별도 후보 | 법령 조문 계층 직접 조회에 유용하므로 specialized law module에서 별도 검토 |
| `mv_searchable_chunks` | 제외 후보 | active retriever에는 필요하지 않고 테스트/문서 잔재 가능성이 큼 |

### 이유

- 현재 복원 DB는 `vector_chunks`만으로 active 검색 smoke를 통과했다.
- legacy schema 전체를 한 번에 복구하면 M1-3의 범위가 schema migration, data migration, test fixture 정리까지 과대해진다.
- 현재 목표는 챗봇 성능 고도화 자체가 아니라, 현재 시스템과 개선 시스템의 차이를 측정할 수 있는 local baseline을 만드는 것이다.
- 따라서 먼저 `vector_chunks` 기반 검색 기준선을 고정하고, legacy object는 실제 측정/평가에 필요한 시점에 하나씩 복구한다.

### 후속 기준

- `law_units`가 필요한 작업은 별도 모듈로 분리한다.
- `documents/chunks`가 필요한 작업은 evaluation dataset 재현 모듈에서 분리한다.
- `mv_searchable_chunks`는 active code/test에서 반드시 필요한 증거가 나오기 전까지 복구하지 않는다.

## 5. 결정 3: PostgreSQL/pgvector를 compose 내부 service로 편입

### 결정

Ddoksori는 후속 모듈에서 자체 `postgres` 또는 `pgvector` compose service를 가진다.

현재 외부 프로젝트에서 로컬 Docker로 build/restore한 DB는 다음 역할로 활용한다.

1. schema/data 기준선 확인
2. dump 생성 원본
3. Ddoksori compose volume으로 restore할 seed source
4. migration/smoke test의 expected behavior 비교 대상

### 이유

- 현재 `docker-compose.yml`은 backend/frontend/redis만 포함하고 DB는 `host.docker.internal`을 통해 외부 DB에 연결한다.
- 이 방식은 M1-2 smoke에는 충분했지만, context 초기화 후 재현성이나 다른 환경에서 실행하기 어렵다.
- 포트폴리오 목적상 `docker compose up`으로 RAG 검색 baseline이 재현되는 것이 중요하다.
- 테스트 완료 전에는 외부 hosted DB보다 local DB volume을 우선한다.

### 후속 구현 원칙

- 기존 외부 DB container를 즉시 삭제하거나 대체하지 않는다.
- 먼저 외부 DB에서 dump를 만들고, Ddoksori compose 내부 service에 restore하는 경로를 문서화/검증한다.
- compose 편입은 DB service 추가와 backend 연결 전환을 한 모듈 안에 과도하게 묶지 않는다.

## 6. 후속 모듈 분리안

M1-3 이후에는 한 번에 하나만 진행한다.

| 후보 모듈 | 목표 | 범위 | 완료 기준 |
| --- | --- | --- | --- |
| `M1-4` | `search_hybrid_rrf_2()` schema 복구 | SQL file/migration 추가, local DB 적용, smoke script 확장 | 함수 존재 및 sample call 성공 |
| `M1-5` | 외부 DB dump/restore 경로 문서화 | 외부 Docker DB에서 schema/data dump 생성 방법 정리 | 재실행 가능한 dump 명령과 산출물 위치 확정 |
| `M1-6` | Ddoksori compose에 pgvector service 추가 | compose DB service, volume, env 연결값 추가 | `docker compose up postgres`와 extension 확인 |
| `M1-7` | Ddoksori volume에 dump restore | M1-5 dump를 M1-6 service에 restore | `vector_chunks` row count와 1536 dimension 재확인 |
| `M1-8` | backend `/search` smoke | OpenAI key 기반 API 검색 smoke | `/search`가 local compose DB로 검색 결과 반환 |

권장 순서는 `M1-4 -> M1-5 -> M1-6 -> M1-7 -> M1-8`이다.

## 7. M1-4 제안 범위

M1-4는 다음 하나만 수행하는 것이 좋다.

> 현재 복원 DB와 repository 문서에 있는 DDL을 기준으로 `search_hybrid_rrf_2()`를 reproducible schema file로 복구하고 smoke test에 포함한다.

M1-4에서 하지 않을 일:

- compose에 PostgreSQL service 추가
- dump/restore 자동화
- `documents/chunks/law_units` 생성
- 검색 품질 튜닝
- 로컬 embedding 모델 전환

## 8. `.env` 운용 메모

`.env`는 `.gitignore`에 의해 git에 포함되지 않는다. 따라서 worktree를 삭제하면 그 worktree 안의 `.env`도 삭제된다.

local에서 다시 만들려면 다음 방식이 맞다.

```bash
cp .env.example .env
```

그 다음 최소한 아래를 채운다.

```env
OPENAI_API_KEY=...
DB_HOST=host.docker.internal
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=postgres
RETRIEVAL_MODE=hybrid
```

Ddoksori compose 내부 DB service가 생긴 뒤에는 backend container 기준 기본값을 다음처럼 바꿀 가능성이 높다.

```env
DB_HOST=postgres
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=postgres
RETRIEVAL_MODE=hybrid
```

## 9. Verification plan

M1-3은 문서 모듈이므로 검증은 다음으로 제한한다.

```bash
git diff --check
git status --short
```

후속 M1-4부터는 DB 검증을 다시 수행한다.

```bash
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

## 10. Stop condition

이 문서가 merge되면 M1-3은 완료된다. 이후 바로 구현하지 않고 사용자와 다음 중 하나를 논의한다.

1. `M1-4`로 `search_hybrid_rrf_2()` 복구부터 진행
2. `M1-5`로 외부 DB dump/restore 경로부터 정리
3. M1-3 결정 내용 수정
