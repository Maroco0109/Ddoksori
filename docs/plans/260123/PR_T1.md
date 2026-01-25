# PR-T1: Test DB Fixture + Minimal Seed (DDOKSORI)

**작성일**: 2026-01-23
**목표**: DB 의존 테스트(/search, /case, integration/concurrency)가 “DB 비어있음/스키마 누락” 상태에서도 예측 가능하게 동작하도록 정비하여 테스트 성공률을 끌어올린다.

## 배경 (우리 코드베이스 기준)
- 테스트 DB 연결 fixture는 `backend/scripts/testing/conftest.py`의 `db_connection`(psycopg v3)에서 제공한다.
- API 검색 로직(lexical)은 `mv_searchable_chunks`를 사용한다.
- `mv_searchable_chunks`는 migration 정의상 `WHERE c.drop = FALSE AND c.embedding IS NOT NULL` 조건을 가진다.
  - 즉, chunks에 embedding이 NULL이면 MV에 row가 들어가지 않고 FTS 결과는 항상 0이 된다.
  - 더 중요한 문제는 MV가 아예 없으면 `/search`가 500이 되어 concurrency/integration 류 테스트가 깨진다.

## 관찰된 위험/실패 모드
1. **Postgres는 켜져 있지만 스키마/migration을 안 돌린 상태**
   - `mv_searchable_chunks` / 함수 / 컬럼 부재로 `/search`가 500 에러를 반환.
2. **스키마는 있지만 데이터가 완전히 비어있음**
   - 많은 테스트는 0 results를 허용하지만, `/case` 상세 조회나 `data_quality` 등은 skip되거나 무의미한 검증(0==0)만 수행.
3. **Embedding 서버 부재**
   - Dense retrieval은 예외 처리로 빈 리스트를 반환할 수 있으나, Lexical 검색은 MV에 의존하므로 “스키마 부재” 시 보호되지 않음.

## PR-T1 구현 계획 (확정 정책)

### 1. “DB 준비 상태 점검 + 최소 시드” session autouse fixture 추가
- **위치**: `backend/scripts/testing/conftest.py`
- **형태**: `@pytest.fixture(scope="session", autouse=True)`
- **동작 흐름**:
  1. `db_connection` 성공 여부 확인.
  2. **필수 오브젝트 존재 확인**: `documents`, `chunks` 테이블 및 `mv_searchable_chunks` 뷰.
  3. **스키마 부재 시**: `pytest.skip("DB schema not initialized. Run migrations first.")`로 즉시 중단 (테스트가 DB를 오염시키는 것을 방지).
  4. **데이터 부재 시 (Empty check)**: `documents` 테이블이 비어있으면 **최소 시드 데이터 삽입**.
  5. **MV 갱신**: 시드 삽입 후 반드시 `REFRESH MATERIALIZED VIEW mv_searchable_chunks;` 실행.

### 2. 시드 데이터 전략
- **방식**: 대형 SQL 파일 대신 **Python 코드 내에서 생성**하여 fixture 내에서 실행.
- **벡터 처리**: `chunks.embedding` 컬럼(`vector(1024)`)에 Python list `[0.0, ...]`를 삽입 (psycopg 어댑터 활용 또는 `::vector` 캐스팅).
- **구성**:
  - **documents** (3건 이상):
    - `doc_type`: `counsel_case`, `mediation_case`, `law`
    - `source_org`: `KCA`, `statute` 등
  - **chunks** (6~12건):
    - `content`: 테스트 쿼리("환불", "배송지연", "분쟁조정" 등)가 포함된 텍스트.
    - `embedding`: **NOT NULL** (Dummy 1024-dim zero vector) → MV 포함 조건 충족.

### 3. `test_data_quality.py` 정책
- 시드 데이터가 보장되므로, 데이터 부재로 인한 `skip` 로직을 제거하거나, 최소 데이터가 있음을 전제로 assertion을 수행하도록 개선.
- 목표: `test_data_quality.py`가 무의미하게 통과하지 않고, 실제 시드 데이터를 검증하도록 함.

## 최소 시드 데이터 명세
| 테이블 | 컬럼 | 값 예시 | 비고 |
|---|---|---|---|
| `documents` | `doc_id` | `test_doc_counsel_01` | |
| | `doc_type` | `counsel_case` | 라우팅 테스트용 |
| `chunks` | `chunk_id` | `test_chunk_c01_01` | |
| | `content` | "전자상거래 환불 규정..." | FTS 검색용 |
| | `embedding` | `[0.0, 0.0, ...]` (1024개) | MV 조건 충족용 |

## 완료 기준
- **Postgres 스키마가 준비된 상태**에서:
  - `/search` 테스트가 항상 200 OK (결과가 있든 없든).
  - `/case/{uid}` 테스트가 시드 데이터를 찾아 200 OK 반환.
  - Concurrency/Integration 테스트가 500 에러 없이 통과.
- **스키마가 없는 상태**에서:
  - 명확한 메시지와 함께 테스트가 Skip됨.

## 실행 커맨드
```bash
# 관련 테스트 실행
conda run -n dsr pytest -c backend/pytest.ini backend/scripts/testing/api -k "search or concurrent or case"
conda run -n dsr pytest -c backend/pytest.ini backend/scripts/testing/data/test_data_quality.py -v
```
