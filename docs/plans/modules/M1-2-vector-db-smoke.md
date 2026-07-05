# M1-2 Vector DB 점검 및 검색 연결 Smoke Test

- 작성일: 2026-05-18
- 모듈: `M1-2` 복원된 Docker vector DB 점검 및 compose 연결 smoke test
- 상위 계획: `docs/plans/modules/M1-1-rag-db-inventory.md`
- 목표: 이미 Docker에 복원된 `pgvector` DB가 현재 Ddoksori backend의 active RAG 검색 기준선으로 사용 가능한지 확인한다.
- 이번 모듈에서 하지 않는 일: DB schema 생성/수정, seed/restore 작성, 검색 품질 개선, local embedding 모델 교체, `search_hybrid_rrf_2()` 구현.

## 1. 결론

복원된 Docker DB는 `vector_chunks` 중심 active retrieval 기준선을 만족한다.

- PostgreSQL container: `data_collection_snippets-postgres-1`
- Image: `pgvector/pgvector:pg17`
- Database: `ddoksori`
- `vector` extension: 확인됨
- `vector_chunks`: 확인됨
- `embedding`: 전체 row에서 존재
- embedding dimension: 전체 row가 `1536`
- `text_tsv`: 전체 row에서 존재
- `search_similar_chunks()`: sample query 성공
- `search_hybrid_rrf()`: sample query 성공

M1-2에서 확인된 제한 사항은 다음 단계의 판단 대상으로 남긴다.

- `search_hybrid_rrf_2()`는 DB function으로 존재하지 않는다.
- `documents`, `chunks`, `law_units`, `mv_searchable_chunks`는 현재 DB에 없다.
- 현재 DB는 Ddoksori root compose가 생성한 service가 아니라 `/home/maroco/data_collection_snippets` compose의 `postgres` service이다.

## 2. 구현 변경

### Docker Compose 연결

`docker-compose.yml`의 backend service를 복원된 host-side DB에 연결할 수 있게 최소 수정했다.

- `.env` 파일은 optional로 변경했다.
- `.env`가 없을 때도 local smoke가 가능하도록 DB 기본값을 추가했다.
- Docker container에서 host의 `5432` DB에 접근할 수 있도록 `host.docker.internal:host-gateway`를 추가했다.
- PostgreSQL service를 새로 추가하지 않았다.

기본 local 연결값:

```env
DB_HOST=host.docker.internal
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=postgres
RETRIEVAL_MODE=hybrid
```

### 반복 가능한 DB 점검 스크립트

`backend/scripts/testing/check_vector_db_smoke.py`를 추가했다.

이 스크립트는 read-only query만 수행하며 다음을 확인한다. Host Python에서 실행하려면 `psycopg2`가 설치되어 있어야 하며, 의존성 설치 없이 검증하려면 backend container에서 실행한다.

- DB 버전과 현재 DB/user
- `vector` extension
- `vector_chunks` relation
- `search_similar_chunks()`, `search_hybrid_rrf()` function
- `vector_chunks` row count, embedding count, `text_tsv` count
- `vector_dims(embedding)=1536`
- dataset/category/document_type 분포
- dense/hybrid sample query 결과
- optional object 부재 목록

## 3. 점검 결과

현재 로컬 Docker DB 기준 결과:

| Check | Result |
| --- | --- |
| `vector` extension | OK, `0.8.2` |
| `vector_chunks` relation | OK |
| total rows | `40,285` |
| rows with embedding | `40,285` |
| rows with `text_tsv` | `40,285` |
| rows with 1536 dimensions | `40,285` |
| rows not 1536 dimensions | `0` |
| `search_similar_chunks()` | OK |
| `search_hybrid_rrf()` | OK |
| `search_hybrid_rrf_2()` | Missing, not M1-2 blocker |
| legacy relations | Missing, not M1-2 blocker |

Top distribution:

| dataset_type | category | document_type | rows |
| --- | --- | --- | ---: |
| case | 조정 |  | 20,992 |
| case | 상담 |  | 11,342 |
| law_guide |  | 법률 | 3,448 |
| case | 해결 |  | 1,874 |
| law_guide |  | 별표 | 1,692 |
| law_guide |  | 시행령 | 611 |
| law_guide |  | 행정규칙 | 326 |

## 4. 검증 명령

Host에서 DB 점검:

```bash
DB_HOST=127.0.0.1 \
DB_PORT=5432 \
DB_NAME=ddoksori \
DB_USER=postgres \
DB_PASSWORD=postgres \
python backend/scripts/testing/check_vector_db_smoke.py
```

Host Python에 backend dependency가 없으면 위 명령은 `psycopg2` import 단계에서 실패할 수 있다. 이 경우 아래 backend container 검증을 기준으로 삼는다.

Compose 설정 검증:

```bash
docker compose config
```

Backend container에서 DB 점검:

```bash
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

Backend container에서 스크립트 syntax 확인:

```bash
docker compose run --rm backend python -m py_compile scripts/testing/check_vector_db_smoke.py
```

Full `/search` API smoke test는 `OPENAI_API_KEY`가 필요하다. 현재 worktree에는 `.env`와 shell `OPENAI_API_KEY`가 없어 M1-2에서는 DB function 기반 검색 가능 여부와 backend container DB 연결까지만 검증했다.

## 5. 다음 단계

M1-2 완료 후 바로 M1-3으로 넘어가지 않는다. 먼저 사용자와 아래 내용을 검토한다.

- `search_hybrid_rrf_2()`를 DB function으로 복구할지, 현재 inline SQL 기반 구현을 기준으로 둘지
- `documents/chunks/law_units` legacy schema를 복구할지, active `vector_chunks` schema로 테스트/평가를 정리할지
- Ddoksori compose 안에 별도 PostgreSQL service를 둘지, 현재처럼 외부 복원 DB를 host 연결로 사용할지
