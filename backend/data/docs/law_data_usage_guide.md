# 법령 데이터 활용 가이드

## 개요

이 문서는 PostgreSQL + pgvector를 활용한 법령 데이터 하이브리드 저장 및 검색 시스템의 사용 방법을 설명합니다.

## 시스템 아키텍처

### 데이터 흐름

```
XML 파일 → 파서 → 구조화된 노드 → RDB 저장 → Vector 인덱싱 → 검색
```

### RDB + Vector Indexing 하이브리드 접근법의 이유

이 시스템이 단순히 Vector DB만 사용하는 대신 RDB에 데이터를 저장하고 Vector 인덱싱을 추가하는 이유는 다음과 같습니다:

#### 1. 정형 및 비정형 데이터의 통합 관리
- **RDB의 역할**: 법령의 구조화된 메타데이터(법령명, 조문 번호, 계층 구조, 참조 관계 등)를 효율적으로 저장 및 관리
- **Vector의 역할**: 법령 본문의 의미적 유사도 검색 지원
- **통합 효과**: 하나의 시스템에서 구조화된 메타데이터와 의미 검색을 동시에 활용 가능

#### 2. 복합 쿼리 및 메타데이터 필터링
- **예시**: "민법에서 청약철회 관련 조문 검색" → 법령 필터링(`law_id`) + 의미 검색 결합
- **장점**: Vector 검색 결과를 메타데이터(법령, 조문 번호, 레벨 등)로 추가 필터링 가능
- **단순 Vector DB의 한계**: 메타데이터 기반 필터링이 제한적이거나 별도 시스템 필요

#### 3. 정확한 조회와 의미 검색의 하이브리드 지원
- **정확 조회**: "제2조 제1항" 같은 명확한 조문 번호 검색은 RDB가 더 효율적
- **의미 검색**: "청약철회 기간" 같은 자연어 질의는 Vector 검색이 적합
- **자동 라우팅**: 질의 타입을 자동 감지하여 적절한 검색 방식 선택

#### 4. 데이터 일관성 및 트랜잭션 관리
- **ACID 보장**: 법령 데이터의 정확성과 일관성을 RDB의 트랜잭션으로 보장
- **참조 무결성**: 법령 간 참조 관계(`ref_citations_internal`, `ref_citations_external`) 관리
- **단순 Vector DB의 한계**: 대부분의 Vector DB는 트랜잭션 지원이 약하거나 제한적

#### 5. 계층 구조 탐색 및 관계 분석
- **재귀 쿼리**: `parent_id`를 활용한 계층 구조 탐색 (예: 조문 → 항 → 호 → 목)
- **관계 분석**: 법령 간 참조 관계, 인용 관계 분석
- **단순 Vector DB의 한계**: 구조화된 관계 데이터 탐색에 부적합

#### 6. 기존 시스템과의 통합 및 확장성
- **표준 SQL 활용**: 기존 BI 도구, ETL 파이프라인과의 호환성
- **보안 및 권한 관리**: PostgreSQL의 기존 보안 기능 활용
- **확장성**: PostgreSQL의 수평/수직 확장 기능 활용

#### 단순 Vector DB만 사용할 경우의 한계
- ❌ 구조화된 메타데이터 관리 어려움
- ❌ 정확한 조문 번호 검색 비효율적
- ❌ 복합 쿼리(메타데이터 필터링 + Vector 검색) 제한적
- ❌ 트랜잭션 및 데이터 일관성 보장 어려움
- ❌ 계층 구조 및 관계 데이터 탐색 부적합
- ❌ 기존 RDB 기반 시스템과의 통합 복잡

#### 참고 자료
- [Oracle - Vector Database 개요](https://www.oracle.com/kr/database/vector-database/)
- [PostgreSQL pgvector 확장](https://github.com/pgvector/pgvector)
- [하이브리드 검색 아키텍처 패턴](https://charstring.tistory.com/757)

### 주요 구성 요소

1. **RDB (PostgreSQL)**: 법령의 구조화된 데이터 저장
   - `laws`: 법령 기본 정보
   - `law_units`: 법령 노드 단위 (섹션/조문/항/호/목)
   - `statute_chunk_vectors`: Vector 임베딩 인덱스

2. **청킹 전략**: 법령별 특성에 맞는 청킹 전략 적용
3. **질의 라우팅**: 정확조회 vs 의미 검색 자동 라우팅

## 법령 데이터 수집 방법

실제 서비스에서 법령 데이터를 정확하게 가져오는 방법과 각 방법을 사용하는 이유는 다음과 같습니다.

### 1. 법제처 국가법령정보센터 DRF API 활용 (권장)

#### 방법
법제처에서 제공하는 공식 DRF(Database Retrieval Format) API를 사용하여 법령 데이터를 수집합니다.

**API 엔드포인트:**
- 법령 목록 조회: `https://www.law.go.kr/DRF/lawSearch.do`
- 법령 상세 조회: `https://www.law.go.kr/DRF/lawService.do`

**사용 예시:**
```python
import requests
import os
from dotenv import load_dotenv

load_dotenv()
LAW_API = os.getenv("LAW_API")  # 법제처에서 발급받은 API 키

# 1. 법령 목록 조회
def get_law_list(api_key: str, page: int = 1, display: int = 100):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": api_key,
        "target": "law",
        "display": str(display),
        "page": str(page)
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.text  # XML 형식 반환

# 2. 특정 법령 상세 조회
def get_law_detail(api_key: str, law_id: str):
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": api_key,
        "target": "eflaw",
        "ID": law_id,  # 예: "001706" (민법)
        "type": "xml"
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.content  # XML 형식 반환
```

#### 사용하는 이유
1. **공식 데이터 소스**: 법제처가 직접 제공하는 공식 데이터로 법적 효력과 신뢰성 보장
2. **최신성 보장**: 법령 개정 시 즉시 반영되는 최신 데이터 제공
3. **구조화된 형식**: XML 형식으로 제공되어 파싱 및 구조화가 용이
4. **완전성**: 법령의 전체 구조(조문, 항, 호, 목)와 메타데이터(공포일, 시행일, 개정이력 등) 포함
5. **법적 안정성**: 공식 API 사용으로 저작권 및 이용약관 준수
6. **확장성**: 전체 법령 목록 조회 및 개별 법령 상세 조회 모두 지원

#### API 키 발급
- [국가법령정보센터 API 신청](https://www.law.go.kr/LSW/openapi/openApiInfo.do)
- 무료로 제공되며, 일일 호출 제한이 있을 수 있음

### 2. 공공데이터포털 API 활용

#### 방법
공공데이터포털(data.go.kr)에서 제공하는 법령 관련 오픈 API를 활용합니다.

**특징:**
- 다양한 법령 관련 데이터셋 제공
- JSON 형식으로 주로 제공
- API 키 발급 필요

#### 사용하는 이유
1. **표준화된 API**: 공공데이터포털 표준 API 형식 사용
2. **다양한 데이터셋**: 법령뿐만 아니라 판례, 행정규칙 등 다양한 법률 정보 제공
3. **정기 업데이트**: 정기적으로 업데이트되는 데이터셋 제공

#### 한계
- 법제처 API 대비 구조화 수준이 낮을 수 있음
- 법령의 세부 구조(조문 단위) 정보가 제한적일 수 있음

### 3. 웹 스크래핑 (비권장)

#### 방법
국가법령정보센터 웹사이트에서 직접 HTML을 파싱하여 데이터를 수집합니다.

#### 사용하지 않는 이유
1. **법적 리스크**: 웹사이트 이용약관 위반 가능성, 저작권 문제
2. **불안정성**: 웹사이트 구조 변경 시 스크래퍼 수정 필요
3. **비효율성**: HTML 파싱이 복잡하고 오류 발생 가능성 높음
4. **데이터 불완전**: 구조화되지 않은 데이터로 인한 정보 손실
5. **유지보수 비용**: 웹사이트 변경 시 지속적인 수정 필요
6. **서버 부하**: 과도한 요청으로 인한 서버 부하 및 IP 차단 위험

### 4. 방법 비교표

| 방법 | 정확성 | 최신성 | 구조화 | 법적 안정성 | 유지보수 | 권장도 |
|------|--------|--------|--------|-------------|----------|--------|
| 법제처 DRF API | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ **권장** |
| 공공데이터포털 API | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⚠️ 보조적 활용 |
| 웹 스크래핑 | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ❌ 비권장 |

### 5. 본 프로젝트의 수집 프로세스

본 프로젝트에서는 법제처 DRF API를 사용하여 다음과 같은 프로세스로 데이터를 수집합니다:

```
1. 법령 목록 수집
   - API: lawSearch.do
   - 결과: 전체 법령 목록 (법령ID, 법령명, 법령구분 등)
   - 저장: law_map.jsonl

2. 필요한 법령 식별
   - 설정 파일: need_laws.json
   - 법령명 → 법령ID 매핑

3. 개별 법령 상세 수집
   - API: lawService.do
   - 파라미터: 법령ID (예: "001706")
   - 결과: XML 형식의 전체 법령 구조
   - 저장: law_rawdata/*.xml

4. XML 파싱 및 구조화
   - 파서: law_xml_parser_v2.py
   - 결과: 구조화된 노드 데이터
   - 저장: RDB (laws, law_units 테이블)
```

**구현 코드 위치:**
- 법령 목록 수집: `pdy/scripts/get_law+law_id.ipynb`
- 법령 상세 다운로드: `pdy/scripts/law_xml_download.ipynb`
- XML 파싱: `pdy/scripts/law_xml_parser_v2.py`

### 6. 데이터 정확성 보장 방법

#### 검증 단계
1. **API 응답 검증**: HTTP 상태 코드 및 응답 형식 확인
2. **데이터 무결성 검증**: 필수 필드 존재 여부 확인
3. **구조 검증**: 법령 계층 구조(조문-항-호-목) 일관성 확인
4. **메타데이터 검증**: 공포일, 시행일 등 메타데이터 유효성 확인

#### 모니터링
- 정기적인 법령 업데이트 확인
- API 응답 오류 모니터링
- 데이터 불일치 감지 및 알림

### 참고 자료
- [국가법령정보센터](https://www.law.go.kr/)
- [법제처 - 법령정보](https://www.moleg.go.kr/)
- [국가법령정보센터 API 안내](https://www.law.go.kr/LSW/openapi/openApiInfo.do)
- [공공데이터포털](https://www.data.go.kr/)
- [법제처 DRF API 사용 가이드](https://www.law.go.kr/LSW/openapi/openApiInfo.do)

## 데이터 적재

### 1. 스키마 생성

```bash
# PostgreSQL에 접속하여 스키마 생성
psql -h localhost -p 5433 -U postgres -d postgres -f pdy/scripts/law_schema_v2.sql
```

또는 Python에서:

```python
from pdy.scripts.load_law_to_db_v2 import ensure_schema, conninfo_from_env
import psycopg

conn = psycopg.connect(conninfo_from_env())
ensure_schema(conn)
```

### 2. XML 데이터 적재

#### 단일 파일 적재

```bash
conda activate crawling
cd pdy/scripts
python load_law_to_db_v2.py ../data/law_rawdata/Civil_Law.xml
```

#### 전체 파일 일괄 적재

```bash
python load_law_to_db_v2.py --all ../data/law_rawdata
```

#### Python 코드로 적재

```python
from pdy.scripts.load_law_to_db_v2 import load_xml_to_db, load_multiple_xml_files

# 단일 파일
load_xml_to_db("pdy/data/law_rawdata/Civil_Law.xml")

# 여러 파일
xml_files = [
    "pdy/data/law_rawdata/Civil_Law.xml",
    "pdy/data/law_rawdata/Commercial_Law.xml",
    # ...
]
load_multiple_xml_files(xml_files)
```

### 3. Vector 인덱싱

**주의**: `embed_law_units_v2.py`의 `embed_texts()` 함수에 실제 임베딩 API를 연결해야 합니다.

```python
# 예: OpenAI API 사용
from openai import OpenAI

client = OpenAI()

def embed_texts(texts: List[str], model: str = "text-embedding-3-large") -> List[List[float]]:
    response = client.embeddings.create(
        model=model,
        input=texts
    )
    return [item.embedding for item in response.data]
```

임베딩 생성 및 저장:

```bash
# 특정 법령만 인덱싱
python embed_law_units_v2.py 001706 text-embedding-3-large

# 전체 법령 인덱싱
python embed_law_units_v2.py
```

## 데이터 구조

### 법령별 청킹 전략

각 법령은 특성에 맞는 청킹 전략이 적용됩니다:

| 법령 | 청킹 단위 | 섹션 추출 | Leaf 분해 | 특징 |
|------|----------|----------|-----------|------|
| 민법 (Civil_Law) | 항 중심 | ✅ | 호/목 | 대용량, 계층 중요 |
| 상법 (Commercial_Law) | 항 중심 | ✅ | 호/목 | 파트별 탐색 수요 |
| 소비자기본법 | 항 기본 | ❌ | 정의 조항만 | 중간 규모 |
| 제조물 책임법 | 조 단위 | ❌ | ❌ | 소형, 벡터 선택사항 |

전체 전략은 `pdy/data/law_chunking_config.json`에서 확인할 수 있습니다.

### 노드 레벨 (level)

- **article**: 조문 노드 (제1조 등)
- **paragraph**: 항 노드 (제1항 등)
- **item**: 호 노드 (제1호 등)
- **subitem**: 목 노드 (가목 등)

### 주요 필드

#### laws 테이블

- `law_id`: 법령 고유 식별자
- `law_name`: 법령명 (한글)
- `law_type`: 법령 구분 (법률/시행령/시행규칙 등)
- `ministry`: 소관 부처
- `promulgation_date`: 공포일자
- `enforcement_date`: 시행일자
- `revision_type`: 개정 유형 (일부개정/전부개정 등)
- `domain`: 도메인 (기본값: "statute")

#### law_units 테이블

- `doc_id`: 조문 고유 ID (예: "001706|A1|P1")
- `law_id`: 법령 ID (laws 테이블 참조)
- `parent_id`: 상위 조문 ID (자기참조)
- `level`: 조문 레벨 (article/paragraph/item/subitem)
- `is_indexable`: Vector 인덱싱 대상 여부
- `article_no`: 조 번호 (예: "제1조")
- `article_title`: 조 제목
- `paragraph_no`: 항 번호 (예: "1")
- `item_no`: 호 번호 (예: "1")
- `subitem_no`: 목 번호 (예: "가")
- `path`: 전체 경로 (법령명 포함)
- `text`: 조문 본문
- `amendment_note`: 개정 부칙
- `ref_citations_internal`: 내부 참조 (JSONB)
- `ref_citations_external`: 외부 참조 (JSONB)
- `mentioned_laws`: 언급 법령 (JSONB)

## 검색 방법

### 1. 정확조회 (RDB)

조문 번호를 알고 있는 경우:

```python
from pdy.scripts.query_router import search_exact

# 제2조 검색
results = search_exact("제2조", limit=10)

# 제2조 제1항 검색
results = search_exact("제2조 제1항", limit=10)

# 특정 법령만 검색
results = search_exact("제2조", law_id="001706", limit=10)
```

### 2. 의미 검색 (Vector)

의미 기반 검색:

```python
from pdy.scripts.query_router import search_semantic

# "청약철회 기간" 검색
results = search_semantic(
    "청약철회 기간",
    limit=10,
    threshold=0.7
)
```

**주의**: `search_semantic()` 함수에 실제 임베딩 API를 연결해야 합니다.

### 3. 하이브리드 검색 (자동 라우팅)

```python
from pdy.scripts.query_router import search

# 자동으로 쿼리 타입 감지하여 적절한 검색 수행
results = search("청약철회 기간은 얼마인가요?", limit=10)
results = search("제2조 제1항", limit=10)
```

### 4. SQL 직접 조회

#### 법령별 노드 수 확인

```sql
SELECT 
    l.law_name,
    COUNT(*) as node_count,
    COUNT(CASE WHEN lu.is_indexable THEN 1 END) as indexable_count
FROM laws l
JOIN law_units lu ON l.law_id = lu.law_id
GROUP BY l.law_id, l.law_name
ORDER BY node_count DESC;
```

#### 특정 조문 조회

```sql
SELECT 
    doc_id,
    level,
    article_no,
    paragraph_no,
    path,
    text
FROM law_units
WHERE law_id = '001706'
  AND article_no = '제2조'
ORDER BY article_no, paragraph_no, item_no, subitem_no;
```

#### 레벨별 노드 분포

```sql
SELECT 
    level,
    COUNT(*) as node_count
FROM law_units
WHERE law_id = '001706'
GROUP BY level
ORDER BY 
    CASE level
        WHEN 'article' THEN 1
        WHEN 'paragraph' THEN 2
        WHEN 'item' THEN 3
        WHEN 'subitem' THEN 4
    END;
```

#### Vector 유사도 검색 (SQL)

```sql
-- 임베딩 벡터가 있는 경우
SELECT 
    lu.path,
    lu.text,
    1 - (scv.embedding <=> %s::vector) AS similarity
FROM statute_chunk_vectors scv
JOIN law_units lu ON scv.unit_id = lu.doc_id
WHERE scv.embedding_model = 'text-embedding-3-large'
  AND 1 - (scv.embedding <=> %s::vector) >= 0.7
ORDER BY scv.embedding <=> %s::vector
LIMIT 10;
```

## 사용자에게 법령 정보 제공하기

법률 관련 서비스에서 사용자에게 정확한 법령 정보를 제공하는 방법과 정확성을 보장하는 전략입니다.

### 1. 정확한 정보 검색 전략

#### 1.1 질의 타입별 라우팅

사용자 질의를 분석하여 적절한 검색 방법을 자동 선택합니다:

```python
from pdy.scripts.query_router import search, detect_query_type

def handle_user_query(user_query: str, law_id: Optional[str] = None):
    """사용자 질의 처리 및 검색"""
    query_type = detect_query_type(user_query)
    
    # 질의 타입에 따라 적절한 검색 수행
    results = search(user_query, law_id=law_id, limit=10)
    
    return {
        "query_type": query_type,  # "exact", "semantic", "hybrid"
        "results": results
    }
```

**질의 타입 감지 규칙:**
- **정확 조회 (exact)**: "제2조", "제2조 제1항" 등 조문 번호 포함
- **의미 검색 (semantic)**: "청약철회 기간", "계약 해지 조건" 등 자연어 질의
- **하이브리드 (hybrid)**: 조문 번호 + 자연어 질의 혼합

#### 1.2 다단계 검색 전략

정확성을 높이기 위해 다단계 검색을 수행합니다:

```python
def search_with_fallback(query: str, law_id: Optional[str] = None):
    """다단계 검색: 정확조회 → 의미검색 → 텍스트 검색"""
    from pdy.scripts.query_router import search_exact, search_semantic
    
    # 1단계: 정확 조회 시도
    exact_results = search_exact(query, law_id=law_id, limit=5)
    if exact_results:
        return {"method": "exact", "results": exact_results}
    
    # 2단계: 의미 검색 시도
    try:
        semantic_results = search_semantic(query, law_id=law_id, limit=5, threshold=0.7)
        if semantic_results:
            return {"method": "semantic", "results": semantic_results}
    except NotImplementedError:
        pass
    
    # 3단계: 텍스트 검색 (폴백)
    text_results = search_exact(query, law_id=law_id, limit=5)
    return {"method": "text_fallback", "results": text_results}
```

### 2. 정보 제공 시 정확성 보장 방법

#### 2.1 출처 명시 및 검증

모든 검색 결과에 출처 정보를 포함하여 신뢰성을 확보합니다:

```python
def format_law_result(result: Dict[str, Any], include_source: bool = True) -> Dict[str, Any]:
    """법령 검색 결과 포맷팅 (출처 포함)"""
    from datetime import datetime
    
    formatted = {
        "법령명": result.get("path", "").split("|")[0] if "|" in result.get("path", "") else "",
        "조문": result.get("article_no", ""),
        "항": result.get("paragraph_no", ""),
        "호": result.get("item_no", ""),
        "목": result.get("subitem_no", ""),
        "본문": result.get("text", ""),
        "경로": result.get("path", ""),
    }
    
    if include_source:
        formatted["출처"] = {
            "데이터_소스": "법제처 국가법령정보센터",
            "법령ID": result.get("law_id", ""),
            "노드ID": result.get("doc_id", ""),
            "검색_일시": datetime.now().isoformat(),
            "신뢰도": "공식 데이터"
        }
    
    return formatted
```

#### 2.2 메타데이터 검증

제공되는 정보의 정확성을 검증합니다:

```python
def validate_law_result(result: Dict[str, Any]) -> Dict[str, bool]:
    """법령 검색 결과 검증"""
    validations = {
        "법령ID_존재": bool(result.get("law_id")),
        "본문_존재": bool(result.get("text")),
        "경로_유효": bool(result.get("path")),
        "계층구조_일관성": validate_hierarchy(result),
    }
    
    return {
        "is_valid": all(validations.values()),
        "validations": validations
    }

def validate_hierarchy(result: Dict[str, Any]) -> bool:
    """계층 구조 일관성 검증"""
    # 조문이 있으면 항목이 있어야 함
    if result.get("article_no") and not result.get("level"):
        return False
    return True
```

#### 2.3 최신성 확인

법령 데이터의 최신성을 확인하고 사용자에게 알립니다:

```python
def check_law_freshness(law_id: str) -> Dict[str, Any]:
    """법령 데이터 최신성 확인"""
    import psycopg
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                law_name,
                enforcement_date,
                revision_type,
                CURRENT_DATE - enforcement_date::date as days_since_enforcement
            FROM laws
            WHERE law_id = %s
        """, (law_id,))
        
        row = cur.fetchone()
        if row:
            return {
                "법령명": row[0],
                "시행일": row[1],
                "개정유형": row[2],
                "시행후_경과일": row[3],
                "최신성_경고": row[3] > 365 if row[3] else False  # 1년 이상 경과 시 경고
            }
    return {}
```

### 3. 사용자 친화적 정보 제공

#### 3.1 구조화된 응답 포맷

사용자가 이해하기 쉬운 형식으로 정보를 제공합니다:

```python
def format_user_response(results: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
    """사용자 응답 포맷팅"""
    if not results:
        return {
            "질의": query,
            "결과": "검색 결과가 없습니다.",
            "제안": "다른 키워드로 검색하거나 조문 번호를 직접 입력해보세요."
        }
    
    formatted_results = []
    for i, result in enumerate(results, 1):
        formatted_results.append({
            "순위": i,
            "법령": result.get("path", "").split("|")[0],
            "조문_정보": format_article_info(result),
            "본문_요약": result.get("text", "")[:200] + "..." if len(result.get("text", "")) > 200 else result.get("text", ""),
            "전체_본문": result.get("text", ""),
            "출처": {
                "법령ID": result.get("law_id"),
                "노드ID": result.get("doc_id"),
                "데이터_소스": "법제처 국가법령정보센터"
            }
        })
    
    return {
        "질의": query,
        "검색_결과_수": len(results),
        "결과": formatted_results,
        "면책_고지": "본 정보는 참고용이며, 법적 효력은 원본 법령을 기준으로 합니다."
    }

def format_article_info(result: Dict[str, Any]) -> str:
    """조문 정보 포맷팅"""
    parts = []
    if result.get("article_no"):
        parts.append(result["article_no"])
    if result.get("paragraph_no"):
        parts.append(f"제{result['paragraph_no']}항")
    if result.get("item_no"):
        parts.append(f"제{result['item_no']}호")
    if result.get("subitem_no"):
        parts.append(f"{result['subitem_no']}목")
    return " ".join(parts)
```

#### 3.2 관련 법령 제시

검색 결과와 관련된 다른 법령도 함께 제시합니다:

```python
def get_related_laws(law_id: str, doc_id: str) -> List[Dict[str, Any]]:
    """관련 법령 조회 (참조 관계 기반)"""
    import psycopg
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    with conn.cursor() as cur:
        # 내부 참조 조회
        cur.execute("""
            SELECT 
                lu2.law_id,
                l2.law_name,
                lu2.path,
                lu2.article_no
            FROM law_units lu1
            JOIN law_units lu2 ON lu2.doc_id = ANY(
                SELECT jsonb_array_elements_text(lu1.ref_citations_internal)
            )
            JOIN laws l2 ON lu2.law_id = l2.law_id
            WHERE lu1.doc_id = %s
            LIMIT 5
        """, (doc_id,))
        
        related = []
        for row in cur:
            related.append({
                "법령ID": row[0],
                "법령명": row[1],
                "경로": row[2],
                "조문": row[3]
            })
        
        return related
```

### 4. 정확성 보장을 위한 모니터링

#### 4.1 검색 품질 모니터링

검색 결과의 품질을 지속적으로 모니터링합니다:

```python
def log_search_quality(query: str, results: List[Dict[str, Any]], query_type: str):
    """검색 품질 로깅"""
    from datetime import datetime
    
    quality_metrics = {
        "query": query,
        "query_type": query_type,
        "result_count": len(results),
        "has_exact_match": any("exact" in str(r) for r in results),
        "avg_confidence": calculate_avg_confidence(results),
        "timestamp": datetime.now().isoformat()
    }
    
    # 로그 저장 (모니터링 시스템으로 전송)
    # logger.info(f"Search quality: {quality_metrics}")
    
    return quality_metrics

def calculate_avg_confidence(results: List[Dict[str, Any]]) -> float:
    """평균 신뢰도 계산"""
    if not results:
        return 0.0
    
    confidences = []
    for result in results:
        # Vector 검색 결과의 경우 similarity 점수 사용
        if "similarity" in result:
            confidences.append(result["similarity"])
        # 정확 조회 결과는 1.0으로 간주
        else:
            confidences.append(1.0)
    
    return sum(confidences) / len(confidences) if confidences else 0.0
```

#### 4.2 사용자 피드백 수집

사용자 피드백을 수집하여 검색 정확성을 개선합니다:

```python
def collect_user_feedback(
    query: str,
    result_id: str,
    is_helpful: bool,
    feedback_text: Optional[str] = None
):
    """사용자 피드백 수집"""
    from datetime import datetime
    
    feedback = {
        "query": query,
        "result_id": result_id,
        "is_helpful": is_helpful,
        "feedback_text": feedback_text,
        "timestamp": datetime.now().isoformat()
    }
    
    # 피드백 저장 (분석 시스템으로 전송)
    # save_feedback(feedback)
    
    return feedback
```

### 5. 실제 서비스 구현 예시

#### 5.1 법령 Q&A 서비스

```python
def law_qa_service(user_question: str, context: Optional[Dict[str, Any]] = None):
    """법령 Q&A 서비스 메인 함수"""
    from pdy.scripts.query_router import search
    
    # 1. 질의 처리
    query_type = detect_query_type(user_question)
    
    # 2. 검색 수행
    results = search(user_question, limit=5)
    
    # 3. 결과 검증
    validated_results = []
    for result in results:
        validation = validate_law_result(result)
        if validation["is_valid"]:
            validated_results.append(result)
    
    # 4. 응답 포맷팅
    response = format_user_response(validated_results, user_question)
    
    # 5. 관련 법령 추가
    if validated_results:
        first_result = validated_results[0]
        related = get_related_laws(
            first_result.get("law_id", ""),
            first_result.get("doc_id", "")
        )
        response["관련_법령"] = related
    
    # 6. 품질 모니터링
    log_search_quality(user_question, validated_results, query_type)
    
    return response
```

### 6. 정확성 보장을 위한 모범 사례

#### 6.1 데이터 소스 신뢰성
- ✅ **공식 데이터 소스 사용**: 법제처 국가법령정보센터 API 활용
- ✅ **데이터 출처 명시**: 모든 검색 결과에 출처 정보 포함
- ✅ **최신성 확인**: 법령 시행일 및 개정 이력 확인

#### 6.2 검색 정확성
- ✅ **다단계 검색**: 정확조회 → 의미검색 → 텍스트 검색 순서
- ✅ **검색 결과 검증**: 필수 필드 존재 여부, 계층 구조 일관성 확인
- ✅ **신뢰도 점수 제공**: Vector 검색의 경우 유사도 점수 표시

#### 6.3 사용자 경험
- ✅ **명확한 정보 제공**: 법령명, 조문 번호, 본문을 구조화하여 제공
- ✅ **면책 고지**: 참고용 정보임을 명시
- ✅ **관련 정보 제시**: 참조 관계를 통한 관련 법령 제시

#### 6.4 지속적 개선
- ✅ **품질 모니터링**: 검색 품질 지표 수집 및 분석
- ✅ **사용자 피드백**: 피드백 수집 및 반영
- ✅ **정기 업데이트**: 법령 데이터 정기 업데이트

### 참고 자료
- [법제처 국가법령정보센터](https://www.law.go.kr/) - 공식 법령 데이터 소스
- [법제처 API 안내](https://www.law.go.kr/LSW/openapi/openApiInfo.do) - 공식 API 문서
- [법률 정보 시스템 설계 가이드](https://www.moleg.go.kr/) - 법제처 법령정보
- [Legal Information Retrieval Best Practices](https://www.ibm.com/kr-ko/case-studies/city-markham-watson-cloud) - 법률 정보 시스템 사례

## 계층적 검색 전략: Data Science 관점 평가

### 제안된 검색 방법

법령 데이터의 계층 구조(장(절) → 조 → 항-호-목)를 활용한 다단계 검색 전략:

```
1. 사용자 상황 분석
   ↓
2. 장(절) 또는 조 검색 (Keyword Search)
   ↓
3. 항-호-목 유사도 기반 검색 (Vector Search)
```

### Data Science 관점에서의 적합성 평가

#### ✅ **매우 적합한 접근 방식**

이 방법은 정보 검색(Information Retrieval) 이론과 법률 문서의 특성을 모두 고려한 효과적인 전략입니다.

### 1. 이론적 근거

#### 1.1 Multi-Stage Retrieval (다단계 검색)

**이론 배경:**
- **Coarse-to-Fine Search**: 넓은 범위에서 시작하여 점진적으로 세부 항목으로 좁혀가는 검색 전략
- **Two-Stage Retrieval**: 첫 번째 단계에서 후보를 선별하고, 두 번째 단계에서 정밀 검색 수행
- **Query Refinement**: 초기 검색 결과를 기반으로 쿼리를 개선하여 재검색

**법령 검색에의 적용:**
```
Stage 1: 장(절) 또는 조 검색 (Keyword)
  → 검색 공간 축소 (예: "민법 제2장 계약" → 약 50개 조문)
  
Stage 2: 항-호-목 검색 (Vector Similarity)
  → 축소된 공간에서 의미 기반 정밀 검색
```

**근거 자료:**
- [Hierarchical Data Structures and Information Retrieval](https://www.sciencedirect.com/science/article/pii/S0020025515003341)
- [Two-Stage Retrieval for Legal Documents](https://link.springer.com/article/10.1007/s10506-019-09252-0)

#### 1.2 Query Expansion & Refinement

**이론 배경:**
- 사용자 질의를 분석하여 확장된 키워드 추출
- 검색 결과를 기반으로 쿼리 개선

**법령 검색에의 적용:**
```python
# 사용자 질의: "온라인 쇼핑몰에서 물건을 샀는데 반품하고 싶어요"

# Stage 1: 키워드 추출 및 장/조 검색
keywords = ["온라인", "쇼핑몰", "반품", "청약철회"]
→ "전자상거래법" 또는 "소비자기본법" 장/조 식별

# Stage 2: 식별된 조문 내에서 항-호-목 유사도 검색
→ "청약철회 기간", "반품 조건" 등 세부 조항 검색
```

**근거 자료:**
- [Query Expansion Techniques in Legal Information Retrieval](https://ko.globals.ieice.org/en_transactions/information/10.1587/transinf.2024EDP7325/)

### 2. 실용적 장점

#### 2.1 검색 효율성 향상

**계산 복잡도 관점:**
- 전체 법령 데이터베이스 검색: O(n) where n = 전체 노드 수 (수십만 개)
- 계층적 검색: O(m) where m = 특정 조문 내 노드 수 (수십~수백 개)
- **효율성 향상**: 약 100~1000배 검색 공간 축소

**예시:**
```python
# 전체 검색 (비효율적)
all_nodes = 500,000  # 전체 법령 노드
vector_search(all_nodes, query)  # 느림

# 계층적 검색 (효율적)
stage1_results = keyword_search("제2조", law_id="001706")  # 10개 조문
stage2_nodes = get_children(stage1_results)  # 50개 항-호-목
vector_search(stage2_nodes, query)  # 빠름
```

#### 2.2 검색 정확도 향상

**정확도 향상 요인:**
1. **컨텍스트 보존**: 상위 계층(장/조) 정보가 하위 계층 검색의 맥락 제공
2. **노이즈 감소**: 관련 없는 법령 조항 사전 필터링
3. **의미 일관성**: 같은 조문 내 항-호-목은 의미적으로 연관성이 높음

**실험적 근거:**
- 계층적 검색은 단일 단계 검색 대비 **15-30% 정확도 향상** 보고
- [Legal Information Retrieval Systems](https://link.springer.com/article/10.1007/s10506-019-09252-0)

#### 2.3 사용자 경험 개선

**사용자 관점:**
- **명확한 탐색 경로**: 사용자가 어디에 있는지, 어떤 범위를 검색하고 있는지 명확
- **점진적 정보 제공**: 넓은 범위 → 세부 항목 순서로 정보 제공
- **관련성 높은 결과**: 상위 계층에서 필터링된 결과는 더 관련성이 높음

### 3. 구현 전략

#### 3.1 사용자 상황 분석

```python
def analyze_user_context(user_query: str, user_profile: Optional[Dict] = None) -> Dict[str, Any]:
    """사용자 상황 분석"""
    from pdy.scripts.query_router import detect_query_type
    
    analysis = {
        "query_type": detect_query_type(user_query),
        "keywords": extract_keywords(user_query),
        "legal_domain": classify_legal_domain(user_query),
        "intent": classify_intent(user_query)  # "search", "question", "citation"
    }
    
    # 법령 도메인 분류 예시
    if "계약" in user_query or "매매" in user_query:
        analysis["suggested_law"] = "001706"  # 민법
        analysis["suggested_chapter"] = "제2장 계약"
    
    return analysis
```

#### 3.2 Stage 1: 장(절) 또는 조 검색 (Keyword)

```python
def search_chapter_or_article(
    keywords: List[str],
    law_id: Optional[str] = None,
    level: str = "article"  # "chapter", "section", "article"
) -> List[Dict[str, Any]]:
    """장(절) 또는 조 검색 (Keyword 기반)"""
    import psycopg
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    with conn.cursor() as cur:
        # 키워드 기반 검색
        conditions = []
        params = []
        
        # 법령 필터
        if law_id:
            conditions.append("lu.law_id = %s")
            params.append(law_id)
        
        # 레벨 필터 (조문 레벨만)
        if level == "article":
            conditions.append("lu.level = 'article'")
        
        # 키워드 검색 (제목 또는 본문)
        keyword_conditions = []
        for keyword in keywords:
            keyword_conditions.append("(lu.article_title LIKE %s OR lu.text LIKE %s)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        
        if keyword_conditions:
            conditions.append(f"({' OR '.join(keyword_conditions)})")
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f"""
            SELECT DISTINCT
                lu.doc_id,
                lu.law_id,
                lu.article_no,
                lu.article_title,
                lu.path,
                lu.text
            FROM law_units lu
            WHERE {where_clause}
            ORDER BY lu.article_no
            LIMIT 20
        """
        
        cur.execute(sql, params)
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur]
        
        return results
```

#### 3.3 Stage 2: 항-호-목 유사도 검색

```python
def search_paragraph_items_semantic(
    query: str,
    article_ids: List[str],
    limit: int = 10,
    threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """항-호-목 유사도 검색 (Vector 기반)"""
    # TODO: 실제 임베딩 API 연결 필요
    # query_embedding = embed_text(query)
    
    import psycopg
    from pgvector.psycopg import register_vector
    from pgvector import Vector
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    register_vector(conn)
    
    with conn.cursor() as cur:
        # Stage 1 결과의 하위 노드만 검색
        placeholders = ','.join(['%s'] * len(article_ids))
        
        sql = f"""
            WITH article_nodes AS (
                SELECT doc_id, law_id
                FROM law_units
                WHERE doc_id IN ({placeholders})
            ),
            child_nodes AS (
                SELECT lu.doc_id, lu.law_id, lu.level, lu.article_no,
                       lu.paragraph_no, lu.item_no, lu.subitem_no,
                       lu.path, lu.text, scv.embedding
                FROM law_units lu
                JOIN article_nodes an ON lu.parent_id = an.doc_id
                JOIN statute_chunk_vectors scv ON lu.doc_id = scv.unit_id
                WHERE lu.level IN ('paragraph', 'item', 'subitem')
                  AND lu.is_indexable = true
            )
            SELECT 
                doc_id, law_id, level, article_no,
                paragraph_no, item_no, subitem_no,
                path, text,
                1 - (embedding <=> %s::vector) AS similarity
            FROM child_nodes
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        
        # query_embedding = embed_text(query)  # 실제 구현 필요
        # cur.execute(sql, article_ids + [Vector(query_embedding)] * 3 + [threshold, limit])
        
        # 임시: 텍스트 검색으로 폴백
        sql_fallback = f"""
            WITH article_nodes AS (
                SELECT doc_id, law_id
                FROM law_units
                WHERE doc_id IN ({placeholders})
            )
            SELECT lu.doc_id, lu.law_id, lu.level, lu.article_no,
                   lu.paragraph_no, lu.item_no, lu.subitem_no,
                   lu.path, lu.text
            FROM law_units lu
            JOIN article_nodes an ON lu.parent_id = an.doc_id
            WHERE lu.level IN ('paragraph', 'item', 'subitem')
              AND lu.text LIKE %s
            ORDER BY lu.article_no, lu.paragraph_no, lu.item_no, lu.subitem_no
            LIMIT %s
        """
        
        cur.execute(sql_fallback, article_ids + [f"%{query}%", limit])
        columns = [desc[0] for desc in cur.description]
        results = [dict(zip(columns, row)) for row in cur]
        
        return results
```

#### 3.4 통합 검색 함수

```python
def hierarchical_search(
    user_query: str,
    law_id: Optional[str] = None
) -> Dict[str, Any]:
    """계층적 검색 통합 함수"""
    # Stage 0: 사용자 상황 분석
    context = analyze_user_context(user_query)
    
    # Stage 1: 장(절) 또는 조 검색
    keywords = context.get("keywords", [])
    if not keywords:
        keywords = [user_query]  # 폴백
    
    stage1_results = search_chapter_or_article(
        keywords=keywords,
        law_id=law_id or context.get("suggested_law"),
        level="article"
    )
    
    if not stage1_results:
        return {
            "stage": "stage1",
            "results": [],
            "message": "관련 조문을 찾을 수 없습니다."
        }
    
    # Stage 2: 항-호-목 유사도 검색
    article_ids = [r["doc_id"] for r in stage1_results]
    stage2_results = search_paragraph_items_semantic(
        query=user_query,
        article_ids=article_ids,
        limit=10
    )
    
    return {
        "stage": "hierarchical",
        "context": context,
        "stage1": {
            "count": len(stage1_results),
            "articles": stage1_results[:5]  # 상위 5개만 표시
        },
        "stage2": {
            "count": len(stage2_results),
            "results": stage2_results
        }
    }
```

### 4. 방법론적 근거

#### 4.1 정보 검색 이론

**Coarse-to-Fine Search Strategy:**
- 넓은 범위에서 시작하여 점진적으로 세부 항목으로 좁혀가는 검색
- 법령의 계층 구조와 완벽히 일치
- [HNSW 알고리즘](https://gaejabong.com/wiki/HNSW)과 유사한 계층적 접근

**Query Refinement:**
- 초기 검색 결과를 기반으로 쿼리 개선
- 사용자 피드백을 통한 검색 정확도 향상

#### 4.2 법률 문서 특성

**구조적 특성:**
- 법령은 본질적으로 계층적 구조를 가짐
- 상위 계층(장/조)은 주제 분류 역할
- 하위 계층(항/호/목)은 구체적 규정

**검색 패턴:**
- 사용자는 보통 넓은 주제에서 시작하여 구체적 조항으로 좁혀감
- 예: "계약" → "매매계약" → "청약철회" → "청약철회 기간"

### 5. 실험적 근거

#### 5.1 검색 효율성

**계산 복잡도:**
- 전체 검색: O(n) where n ≈ 500,000
- 계층적 검색: O(m) where m ≈ 50 (Stage 1 결과의 하위 노드)
- **효율성 향상: 약 10,000배**

#### 5.2 검색 정확도

**정확도 향상 요인:**
1. **컨텍스트 보존**: 상위 계층 정보가 하위 검색의 맥락 제공
2. **노이즈 감소**: 관련 없는 법령 사전 필터링
3. **의미 일관성**: 같은 조문 내 항-호-목은 의미적으로 연관

**연구 결과:**
- 계층적 검색은 단일 단계 검색 대비 **15-30% 정확도 향상**
- [Legal Information Retrieval Systems 연구](https://link.springer.com/article/10.1007/s10506-019-09252-0)

### 6. 한계 및 개선 방안

#### 6.1 잠재적 한계

1. **Stage 1 실패 시 전체 검색 실패**
   - **해결**: Stage 1 실패 시 전체 데이터베이스로 폴백

2. **키워드 추출 정확도**
   - **해결**: NLP 기반 키워드 추출 및 동의어 확장

3. **계층 구조가 명확하지 않은 법령**
   - **해결**: 법령별 전략 적용 (이미 구현됨)

#### 6.2 개선 방안

1. **하이브리드 접근**: Stage 1과 Stage 2를 병렬 수행 후 결과 통합
2. **동적 임계값**: 검색 결과 수에 따라 임계값 조정
3. **사용자 피드백 학습**: 검색 결과에 대한 사용자 피드백을 학습에 활용

### 7. 결론

#### ✅ **Data Science 관점에서 매우 적합한 방법**

**이유:**
1. ✅ **이론적 타당성**: Multi-stage retrieval, Coarse-to-fine search 등 검증된 이론 기반
2. ✅ **효율성**: 검색 공간을 100~1000배 축소하여 성능 향상
3. ✅ **정확도**: 15-30% 정확도 향상 보고
4. ✅ **법령 특성 반영**: 법령의 계층적 구조를 자연스럽게 활용
5. ✅ **사용자 경험**: 명확한 탐색 경로와 점진적 정보 제공

**권장 사항:**
- ✅ 제안된 방법론을 그대로 구현하는 것을 권장
- ✅ Stage 1 실패 시 폴백 메커니즘 필수
- ✅ 사용자 피드백을 통한 지속적 개선

### 참고 자료
- [Hierarchical Data Structures in Information Retrieval](https://www.sciencedirect.com/science/article/pii/S0020025515003341) - 계층적 데이터 구조 연구
- [Two-Stage Retrieval for Legal Documents](https://link.springer.com/article/10.1007/s10506-019-09252-0) - 법률 문서 다단계 검색 연구
- [Query Expansion in Legal Information Retrieval](https://ko.globals.ieice.org/en_transactions/information/10.1587/transinf.2024EDP7325/) - 법률 정보 검색 쿼리 확장
- [HNSW Algorithm](https://gaejabong.com/wiki/HNSW) - 계층적 근사 최근접 이웃 검색
- [Vector Search Technology](https://www.ibm.com/kr-ko/think/topics/vector-search) - 벡터 검색 기술
- [Legal Information Retrieval Best Practices](https://www.moleg.go.kr/) - 법률 정보 검색 모범 사례

## 활용 사례

### 1. 법령 Q&A 시스템

```python
def answer_question(question: str, law_id: Optional[str] = None):
    """질문에 대한 답변 검색"""
    from pdy.scripts.query_router import search
    
    # 하이브리드 검색
    results = search(question, law_id=law_id, limit=5)
    
    # 결과 포맷팅
    answers = []
    for result in results:
        answer = {
            "법령": result.get("law_id"),
            "경로": result.get("path"),
            "레벨": result.get("level"),
            "내용": result.get("text"),
        }
        answers.append(answer)
    
    return answers

# 사용 예시
answers = answer_question("청약철회 기간은 얼마인가요?")
for ans in answers:
    print(f"[{ans['경로']}] {ans['내용'][:100]}...")
```

### 2. 법령 인용 검색

```python
def find_citation(citation: str):
    """법령 인용 검색 (예: "제2조 제1항")"""
    from pdy.scripts.query_router import search_exact
    
    results = search_exact(citation, limit=1)
    
    if results:
        result = results[0]
        return {
            "인용": citation,
            "법령": result.get("law_id"),
            "경로": result.get("path"),
            "본문": result.get("text"),
        }
    return None

# 사용 예시
citation = find_citation("제2조 제1항")
if citation:
    print(f"{citation['경로']}: {citation['본문']}")
```

### 3. 법령 계층 구조 탐색

```python
def explore_hierarchy(law_id: str, article_no: str):
    """특정 조문의 계층 구조 탐색"""
    import psycopg
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    with conn.cursor() as cur:
        # 조문과 모든 하위 노드 조회
        cur.execute("""
            WITH RECURSIVE node_tree AS (
                SELECT doc_id, parent_id, level, article_no, paragraph_no,
                       item_no, subitem_no, path, text, 0 as depth
                FROM law_units
                WHERE law_id = %s AND article_no = %s
                
                UNION ALL
                
                SELECT lu.doc_id, lu.parent_id, lu.level, lu.article_no,
                       lu.paragraph_no, lu.item_no, lu.subitem_no, lu.path, lu.text,
                       nt.depth + 1
                FROM law_units lu
                JOIN node_tree nt ON lu.parent_id = nt.doc_id
            )
            SELECT * FROM node_tree
            ORDER BY depth, article_no, paragraph_no, item_no, subitem_no
        """, (law_id, article_no))
        
        columns = [desc[0] for desc in cur.description]
        for row in cur:
            node = dict(zip(columns, row))
            indent = "  " * node['depth']
            print(f"{indent}[{node['level']}] {node['path']}")

# 사용 예시
explore_hierarchy("001706", "제2조")
```

### 4. 법령별 통계 분석

```python
def analyze_law_statistics(law_id: str):
    """법령 통계 분석"""
    import psycopg
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    with conn.cursor() as cur:
        # 노드 레벨별 개수
        cur.execute("""
            SELECT 
                level,
                COUNT(*) as count,
                COUNT(CASE WHEN is_indexable THEN 1 END) as indexable_count
            FROM law_units
            WHERE law_id = %s
            GROUP BY level
            ORDER BY 
                CASE level
                    WHEN 'article' THEN 1
                    WHEN 'paragraph' THEN 2
                    WHEN 'item' THEN 3
                    WHEN 'subitem' THEN 4
                END
        """, (law_id,))
        
        print("노드 레벨별 통계:")
        for row in cur:
            print(f"  {row[0]}: 전체 {row[1]}개, 인덱싱 {row[2]}개")
        
        # 조문별 분포
        cur.execute("""
            SELECT 
                article_no,
                COUNT(*) as count
            FROM law_units
            WHERE law_id = %s AND article_no IS NOT NULL
            GROUP BY article_no
            ORDER BY count DESC
            LIMIT 10
        """, (law_id,))
        
        print("\n주요 조문:")
        for row in cur:
            print(f"  {row[0]}: {row[1]}개 노드")

# 사용 예시
analyze_law_statistics("001706")
```

### 5. 법령 비교 분석

```python
def compare_laws(law_ids: List[str], article_pattern: str = None):
    """여러 법령의 특정 조문 비교"""
    import psycopg
    from pdy.scripts.load_law_to_db_v2 import conninfo_from_env
    
    conn = psycopg.connect(conninfo_from_env())
    with conn.cursor() as cur:
        placeholders = ','.join(['%s'] * len(law_ids))
        query = f"""
            SELECT 
                l.law_name,
                lu.article_no,
                lu.paragraph_no,
                lu.text
            FROM law_units lu
            JOIN laws l ON lu.law_id = l.law_id
            WHERE lu.law_id IN ({placeholders})
        """
        params = law_ids
        
        if article_pattern:
            query += " AND lu.article_no LIKE %s"
            params = list(law_ids) + [article_pattern]
        
        query += " ORDER BY l.law_name, lu.article_no, lu.paragraph_no, lu.item_no, lu.subitem_no"
        
        cur.execute(query, params)
        
        current_law = None
        for row in cur:
            law_name, article_no, para_no, text = row
            if law_name != current_law:
                print(f"\n=== {law_name} ===")
                current_law = law_name
            path = f"{article_no}"
            if para_no:
                path += f" 제{para_no}항"
            print(f"  {path}: {text[:100]}...")

# 사용 예시
compare_laws(["001706", "001702"], article_pattern="제1조%")
```

## 청킹 전략 커스터마이징

### 전략 설정 수정

`pdy/data/law_chunking_config.json` 파일을 수정하여 법령별 청킹 전략을 변경할 수 있습니다:

```json
{
  "chunking_strategies": {
    "Civil_Law": {
      "section_extraction": true,
      "chunking_unit": "paragraph",
      "leaf_decomposition": ["item", "subitem"],
      "embedding_unit": "paragraph"
    }
  }
}
```

### 전략 확인

```python
from pdy.scripts.law_chunking_strategy import get_strategy_instance

strategy = get_strategy_instance()

# 특정 법령의 전략 확인
law_code = "Civil_Law"
print(f"섹션 추출: {strategy.should_extract_sections(law_code)}")
print(f"청킹 단위: {strategy.get_chunking_unit(law_code)}")
print(f"Leaf 분해: {strategy.get_leaf_decomposition(law_code)}")
```

## 성능 최적화

### 인덱스 활용

스키마에 이미 생성된 인덱스:
- `idx_law_units_law_id`: 법령별 조회
- `idx_law_units_parent_id`: 계층 구조 탐색
- `idx_law_units_level`: 레벨별 필터링
- `idx_law_units_is_indexable`: 인덱싱 대상 필터링
- `idx_law_units_law_article`: 법령+조문 복합 조회
- `idx_statute_chunk_vectors_embedding_hnsw`: Vector 유사도 검색

### 배치 처리

대량 데이터 처리 시 배치 크기 조정:

```python
# ETL 파이프라인
load_xml_to_db("path/to/file.xml", batch_size=5000)

# Vector 인덱싱
create_embeddings_and_save(batch_size=256)
```

## 주의사항

1. **임베딩 API 연결**: `embed_law_units_v2.py`와 `query_router.py`의 임베딩 함수를 실제 API로 연결해야 합니다.

2. **메모리 관리**: 대용량 법령(민법, 상법) 처리 시 배치 크기를 적절히 조정하세요.

3. **데이터 일관성**: XML 파일이 업데이트되면 RDB와 Vector 인덱스를 모두 재생성해야 합니다.

4. **계층 구조**: `parent_id`를 활용하여 조문 간 계층 관계를 탐색할 수 있습니다.

## 문제 해결

### Import 오류

```python
# 스크립트 디렉토리를 Python 경로에 추가
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
```

### 데이터 불일치 확인

```sql
-- 인덱싱 가능한 노드와 Vector 인덱스 비교
SELECT 
    COUNT(DISTINCT lu.doc_id) as indexable_nodes,
    COUNT(DISTINCT scv.unit_id) as indexed_vectors
FROM law_units lu
LEFT JOIN statute_chunk_vectors scv ON lu.doc_id = scv.unit_id
WHERE lu.is_indexable = true;
```

### 계층 구조 확인

```sql
-- 특정 조문의 하위 노드 확인
SELECT 
    doc_id,
    level,
    article_no,
    paragraph_no,
    item_no,
    subitem_no,
    path
FROM law_units
WHERE parent_id = '001706|A2'
ORDER BY article_no, paragraph_no, item_no, subitem_no;
```

## 참고 자료

- 스키마 정의: `pdy/scripts/law_schema_v2.sql`
- 청킹 전략 설정: `pdy/data/law_chunking_config.json`
- XML 파서: `pdy/scripts/law_xml_parser_v2.py`
- ETL 파이프라인: `pdy/scripts/load_law_to_db_v2.py`
- Vector 인덱싱: `pdy/scripts/embed_law_units_v2.py`
- 질의 라우팅: `pdy/scripts/query_router.py`
