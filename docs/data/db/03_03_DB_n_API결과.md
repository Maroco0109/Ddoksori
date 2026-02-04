# AWS RDS PostgreSQL + pgvector 구축 및 API 연결 결과

**작성일**: 2026-01-26
**프로젝트**: 똑소리 (DDoksori) - 소비자 분쟁 해결 RAG 시스템
**데이터베이스**: AWS RDS PostgreSQL 17.2 + pgvector 0.8.1

---

## 📋 목차

1. [구축 완료 사항](#구축-완료-사항)
2. [AWS RDS 인스턴스 정보](#aws-rds-인스턴스-정보)
3. [데이터베이스 스키마](#데이터베이스-스키마)
4. [데이터 삽입 현황](#데이터-삽입-현황)
5. [검색 API](#검색-api)
6. [로컬 연결 방법](#로컬-연결-방법)
7. [팀원 공유 방법](#팀원-공유-방법)
8. [다음 단계](#다음-단계)

---

## ✅ 구축 완료 사항

### 인프라
- [x] AWS RDS PostgreSQL 17.2 인스턴스 생성
- [x] pgvector 0.8.1 확장 설치
- [x] 보안 그룹 설정 (포트 5432 개방)
- [x] 퍼블릭 액세스 활성화

### 데이터베이스
- [x] 통합 스키마 실행 완료
- [x] 테이블 9개 생성
- [x] 뷰 7개 생성
- [x] 함수 128개 생성 (검색 함수 포함)

### 애플리케이션
- [x] 데이터 삽입 스크립트 준비
- [x] FastAPI 검색 API 준비
- [x] 테스트 스크립트 준비

---

## 🗄️ AWS RDS 인스턴스 정보

### 연결 정보

```
엔드포인트: your-db-instance.ap-northeast-2.rds.amazonaws.com
포트: 5432
데이터베이스: ddoksori
사용자: postgres
리전: us-east-1 (미국 버지니아 북부)
```

### 인스턴스 사양

| 항목 | 값 |
|------|-----|
| **DB 엔진** | PostgreSQL 17.2-R3 |
| **인스턴스 클래스** | db.r7g.xlarge ⭐ (프로덕션) |
| **vCPU / RAM** | 4 vCPUs / 32 GiB RAM |
| **스토리지** | 범용 SSD (gp3) 100GB |
| **가용 영역** | 단일 AZ |
| **퍼블릭 액세스** | 예 ✅ |
| **백업 보존 기간** | 7일 |

**선택 이유**:
- db.r7g.xlarge: 대량 데이터 삽입 시 네트워크 타임아웃 방지
- 프리티어 대비 **10배 이상 빠른 성능**
- 데이터 삽입: 프리티어 1-2시간 → db.r7g.xlarge **10분**

### 보안 그룹

**인바운드 규칙**:
```
유형: PostgreSQL
프로토콜: TCP
포트 범위: 5432
소스: 0.0.0.0/0 (모든 IP 허용)
```

⚠️ **보안 주의**: 개발/테스트 환경용 설정. 프로덕션 환경에서는 특정 IP만 허용 권장

---

## 📊 데이터베이스 스키마

### 실행 결과

```
================================================================================
[INFO] 스키마 실행 시작
================================================================================
[INFO] 연결 중... your-db-instance.ap-northeast-2.rds.amazonaws.com:5432/ddoksori
[OK] 연결 성공

[INFO] 테이블 생성 확인...
[OK] 생성된 테이블: 9개
  - vector_chunks              # 메인 데이터 테이블 (텍스트 + 임베딩 벡터 저장)
  - search_quality_logs        # 검색 품질 로그 기록
  - case_statistics            # 사례 데이터 통계 (카테고리별 집계)
  - dataset_statistics         # 데이터셋 타입별 통계 (law_guide/case)
  - law_statistics             # 법령별 통계 (법령명별 청크 수)
  - pdf_source_statistics      # PDF 소스 파일별 통계
  - url_source_statistics      # URL 소스별 통계 (크롤링 데이터)
  - year_statistics            # 연도별 통계 (사례 발생 연도)
  - search_quality_analysis    # 검색 품질 분석 결과

[INFO] 뷰 생성 확인...
[OK] 생성된 뷰: 7개
  - case_statistics            # 사례 통계 뷰 (카테고리별 요약)
  - dataset_statistics         # 데이터셋 통계 뷰 (전체 데이터 개요)
  - law_statistics             # 법령 통계 뷰 (법령별 청크 분포)
  - pdf_source_statistics      # PDF 소스 통계 뷰 (파일별 집계)
  - url_source_statistics      # URL 소스 통계 뷰 (웹사이트별 집계)
  - year_statistics            # 연도 통계 뷰 (시계열 분석용)
  - search_quality_analysis    # 검색 품질 분석 뷰 (성능 모니터링)

[INFO] 함수 생성 확인...
[OK] 생성된 함수: 128개
  - pgvector 함수 (거리, 유사도 계산)
  - 검색 함수 (search_hybrid_rrf, search_bm25, search_similar_chunks 등)
  - 통계 함수 (get_chunk_statistics)
  - 검증 함수 (validate_embedding_dimensions, validate_duplicate_chunks 등)

[SUCCESS] 스키마 실행 완료!
================================================================================
```

### 핵심 테이블: vector_chunks

**컬럼 구조**:
```sql
CREATE TABLE vector_chunks (
    chunk_id VARCHAR(100) PRIMARY KEY,
    dataset_type VARCHAR(20) NOT NULL,              -- 'law_guide' or 'case'
    text TEXT NOT NULL,
    embedding vector(1536) NOT NULL,                -- OpenAI text-embedding-3-large
    law_name VARCHAR(255),
    chunk_type VARCHAR(50),
    category VARCHAR(50),                            -- B_case: '상담', '해결', '조정'
    document_type VARCHAR(20),                       -- A_law_ED_guide: '법률', '시행령', '행정규칙', '별표'
    source_url TEXT,
    source_file VARCHAR(255),
    printed_page INTEGER,
    source_year INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**필터링 필드 설명**:
- `dataset_type`: 데이터셋 구분 ('law_guide' / 'case')
- `category`: B_case 카테고리 ('상담' / '해결' / '조정')
- `document_type`: A_law_ED_guide 문서 유형 ('법률' / '시행령' / '행정규칙' / '별표')
  - "해결기준 알려줘" → document_type='행정규칙' or '별표'
  - "해결 사례 알려줘" → category='해결'

**인덱스**:
- `vector_chunks_pkey`: Primary Key (chunk_id)
- `idx_dataset_type`: dataset_type (필터링)
- `idx_category`: category (필터링)
- `idx_document_type`: document_type (필터링) ⭐ 신규
- `idx_source_year`: source_year (필터링)
- `idx_embedding_hnsw`: HNSW 벡터 인덱스 (고속 검색)

---

## 📦 데이터 삽입 현황

### ✅ 삽입 완료 (2026-01-26)

#### A_law_ED_guide (법령 데이터)
- **파일**:
  - `embedded_chunks_law_ED.jsonl` (4,111건)
  - `embedded_chunks_guide_1.jsonl` (333건)
  - `embedded_chunks_guide_2.jsonl` (1,694건)
- **처리 건수**: 6,138건
- **삽입 건수**: 6,077건 (중복 제거)
- **소요 시간**: 1분 40초 ⚡
- **상태**: ✅ 완료

#### B_case (사례 데이터)
- **파일**:
  - `embeddings_semantic_crawling.jsonl` (41,438건)
  - `embeddings_semantic_pdf.jsonl` (4,876건)
- **처리 건수**: 46,314건
- **삽입 건수**: 34,208건 (중복 제거)
- **소요 시간**: 9분 56초 ⚡
- **상태**: ✅ 완료

**중복 제거 설명**:
- JSONL 파일의 총 청크 수와 실제 삽입 건수의 차이는 `chunk_id` 중복 때문입니다
- `ON CONFLICT (chunk_id) DO UPDATE` 구문으로 중복은 업데이트만 수행
- 약 12,106건이 중복된 청크였음 (정상)

### 삽입 스크립트

```bash
# 1. 법령 데이터 삽입
python DB/02_02_insert_law_guide.py

# 2. 사례 데이터 삽입
python DB/02_03_insert_case.py
```

### 최종 통계 (실제 DB 데이터)

**총 데이터**:
- **전체 청크: 40,285건** ✅
- **law_guide: 6,077건**
- **case: 34,208건**

**카테고리별** (case):
- **조정**: 20,992건 (61.3%)
- **상담**: 11,342건 (33.2%)
- **해결**: 1,874건 (5.5%)

**데이터 소스별** (case):
- **Crawling**: 32,603건
- **PDF**: 168건
- **Unknown**: 1,437건

**연도별** (case):
- **2010-2024년**: 720건 (전체 연도 포함)
  - 2010년: 19건
  - 2011년: 18건
  - 2012년: 17건
  - 2013년: 12건
  - 2014년: 12건
  - 2015년: 161건
  - 2016년: 13건
  - 2017년: 15건
  - 2018년: 19건
  - 2019년: 90건
  - 2020년: 29건
  - 2021년: 15건
  - 2022년: 126건
  - 2023년: 75건
  - 2024년: 99건

---

## 🔍 검색 API

### API 서버 정보

**파일**: `DB/03_01_search_api.py`

**기술 스택**:
- FastAPI 0.115.6
- Uvicorn 0.32.1
- psycopg2-binary 2.9.9
- OpenAI API (임베딩 생성)

**실행 방법**:
```bash
# ddoksori 가상환경 활성화
conda activate ddoksori

# API 서버 실행
cd data_n_db/DB
python 03_01_search_api.py

# 서버 실행 확인
# http://localhost:8000
# http://localhost:8000/docs (Swagger UI)
```

### API 엔드포인트

#### 1. Health Check
```
GET /health
```

**응답 예시** (실제 결과):
```json
{
  "status": "healthy",
  "database": "connected",
  "total_chunks": 40285
}
```

**테스트 결과**: ✅ 정상 작동 (2026-01-26)

---

#### 2. 통계 조회
```
GET /stats
```

**응답 예시**:
```json
{
  "statistics": [
    {
      "dataset_type": "case",
      "category": "상담",
      "chunk_type": "case",
      "total_chunks": 15234,
      "avg_text_length": 512.5
    },
    ...
  ]
}
```

---

#### 3. 검색
```
POST /search
```

**요청 Body**:
```json
{
  "query": "환불 거부 시 소비자 권리는?",
  "search_type": "hybrid",
  "dataset_filter": null,
  "category_filter": null,
  "year_filter": null,
  "top_k": 10
}
```

**search_type 옵션**:
- `hybrid`: BM25 + 벡터 + RRF 통합 검색 (권장)
- `vector`: 순수 벡터 유사도 검색
- `bm25`: 순수 키워드 검색

**필터 옵션**:
- `dataset_filter`: `"law_guide"` 또는 `"case"`
- `category_filter`: `"상담"`, `"해결"`, `"조정"`
- `year_filter`: 연도 (예: `2023`)

**응답 예시** (실제 테스트 결과):
```json
{
  "query": "consumer rights",
  "total_results": 5,
  "search_type": "hybrid",
  "search_time_ms": 2431.41,
  "results": [
    {
      "chunk_id": "law_ED_조_전체_1",
      "dataset_type": "law_guide",
      "text": "소비자기본법 제16조 소비자의 기본적 권리...",
      "score": 0.0164,
      "category": null,
      "law_name": "소비자기본법",
      "source_url": null,
      "source_file": "법령.pdf",
      "printed_page": 15,
      "source_year": null,
      "metadata": {...}
    },
    ...
  ]
}
```

**성능 (db.r7g.xlarge)**:
- 첫 검색: 약 2.4초 (임베딩 생성 포함)
- 이후 검색: 약 2.4초 (RDS 네트워크 지연)
- 로컬 Docker 대비 느리지만 안정적

### 검색 함수 (PostgreSQL)

#### search_hybrid_rrf
```sql
SELECT * FROM search_hybrid_rrf(
    '환불 거부'::text,                 -- 검색 쿼리
    query_embedding::vector(1536),    -- 쿼리 임베딩
    'case'::varchar(20),              -- 데이터셋 필터
    '해결'::varchar(50),              -- 카테고리 필터
    2023::integer,                     -- 연도 필터
    10::integer,                       -- 결과 수
    60                                 -- RRF K 값
);
```

**RRF (Reciprocal Rank Fusion)**:
- BM25 순위와 벡터 유사도 순위를 결합
- 두 검색 방식의 장점을 모두 활용

---

## 💻 로컬 연결 방법

### 1. DBeaver로 연결

**연결 정보 입력**:
```
Host: your-db-instance.ap-northeast-2.rds.amazonaws.com
Port: 5432
Database: ddoksori
Username: postgres
Password: 별도 공유
```

**연결 테스트**: ✅ Test Connection → Success (2026-01-26)

---

### 2. Python에서 연결

**`.env` 파일 설정** (`data_n_db/.env`):
```env
DB_HOST=your-db-instance.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=별도 공유

OPENAI_API_KEY=sk-proj-...
```

**Python 코드 예시**:
```python
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os

# .env 파일 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# RDS 연결
conn = psycopg2.connect(
    host=os.getenv("DB_HOST").strip(),
    port=int(os.getenv("DB_PORT").strip()),
    database=os.getenv("DB_NAME").strip(),
    user=os.getenv("DB_USER").strip(),
    password=os.getenv("DB_PASSWORD").strip()
)

cursor = conn.cursor()

# 벡터 검색 예시
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 쿼리 임베딩 생성
query = "환불 거부 해결 사례"
response = client.embeddings.create(
    model="text-embedding-3-large",
    input=query,
    dimensions=1536
)
query_embedding = response.data[0].embedding

# 유사 벡터 검색
cursor.execute("""
    SELECT chunk_id, text,
           1 - (embedding <=> %s::vector) as similarity
    FROM vector_chunks
    WHERE dataset_type = 'case'
    ORDER BY embedding <=> %s::vector
    LIMIT 5
""", (query_embedding, query_embedding))

results = cursor.fetchall()
for row in results:
    print(f"Similarity: {row[2]:.4f}")
    print(f"Text: {row[1][:100]}...\n")

cursor.close()
conn.close()
```

---

### 3. API 테스트

**테스트 스크립트 실행**:
```bash
# 터미널 1: API 서버 실행
conda activate ddoksori
cd data_n_db/DB
python 03_01_search_api.py

# 터미널 2: 테스트 실행
conda activate ddoksori
cd data_n_db/DB
python 03_02_test_search_api.py
```

**테스트 내용**:
- Health Check
- 통계 조회
- 하이브리드 검색
- 순수 벡터 검색
- 필터링 검색
- 법령 검색

---

## 👥 팀원 공유 방법

### 1. GitHub로 코드 공유

**저장소**: `data_n_db` 폴더를 별도 저장소로 관리

**팀원 설정 방법**:
```bash
# 1. 저장소 클론
git clone <저장소_URL>
cd data_n_db

# 2. .env 파일 생성
cp .env.example .env

# 3. .env 파일 편집 (RDS 연결 정보 입력)
notepad .env  # Windows
nano .env     # Mac/Linux

# 4. Python 가상환경 생성
conda create -n ddoksori python=3.11 -y
conda activate ddoksori

# 5. 패키지 설치
pip install -r requirements.txt

# 6. 연결 테스트
python DB/03_02_test_search_api.py
```

---

### 2. .env 파일 공유 (보안 주의!)

**Slack DM 또는 암호화된 채널로 공유**:
```env
DB_HOST=your-db-instance.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=별도 공유

OPENAI_API_KEY=sk-proj-...
```

⚠️ **주의**: GitHub에 절대 업로드하지 말 것! (`.gitignore`에 포함됨)

---

### 3. DBeaver 연결 공유

**팀원에게 알려줄 정보**:
```
Host: your-db-instance.ap-northeast-2.rds.amazonaws.com
Port: 5432
Database: ddoksori
Username: postgres
Password: 별도 공유
```

**리전**: 미국 버지니아 북부 (us-east-1)

---

## 📈 다음 단계

### ✅ 완료된 작업

- [x] **데이터 삽입 완료** (2026-01-26)
  - law_guide: 6,077건 ✅
  - case: 34,208건 ✅
  - 총: 40,285건 ✅

- [x] **검색 API 테스트** (2026-01-26)
  - API 서버 실행 ✅
  - Health Check 성공 ✅
  - 하이브리드 검색 정상 작동 ✅

### 즉시 진행 가능

- [ ] **로컬에서 RAG 테스트**
  - RDS에서 벡터 검색
  - OpenAI API로 답변 생성
  - 성능 평가

- [ ] **팀원 공유**
  - 엔드포인트 정보 전달
  - DBeaver 연결 테스트
  - API 사용법 공유

---

### 향후 계획 (선택사항)

#### 1. 프론트엔드 개발
- Streamlit 또는 React로 웹 UI 개발
- API와 연동하여 검색 인터페이스 구현

#### 2. EC2 배포 (필요 시)
- FastAPI 서버를 EC2에 배포
- Nginx + Gunicorn 또는 Uvicorn으로 프로덕션 운영
- HTTPS 설정 (Let's Encrypt)

**배포 구조**:
```
사용자 브라우저
    ↓
EC2 (FastAPI 서버)
    ↓
AWS RDS (PostgreSQL + pgvector)
```

**예상 비용** (현재 구성):
- EC2 t2.micro (프리티어): 무료 또는 월 $5-10
- RDS db.r7g.xlarge: 월 $360-390
- **총**: 월 $365-400

**비용 절감**: 프로젝트 종료 후 RDS 스냅샷 저장 → 월 $2-3만 발생

---

#### 3. 성능 최적화
- [ ] 인덱스 튜닝
- [ ] 쿼리 최적화
- [ ] 캐싱 (Redis)
- [ ] 벡터 양자화 (binary_quantize)

---

#### 4. RAG 파이프라인 통합
- [ ] LangChain 또는 LlamaIndex 통합
- [ ] 프롬프트 엔지니어링
- [ ] 검색 결과 재순위화 (Reranking)
- [ ] 답변 품질 평가

---

## 🎯 성공 지표

### ✅ 모두 달성 완료! (2026-01-26)

- ✅ AWS RDS PostgreSQL + pgvector 구축
  - **인스턴스**: dsr-postgres (db.r7g.xlarge)
  - **리전**: us-east-1 (버지니아 북부)

- ✅ 스키마 실행 완료 (128개 함수 포함)
  - 테이블 9개, 뷰 7개, 함수 128개

- ✅ 데이터 삽입 완료
  - **총 40,285건** (law_guide 6,077 + case 34,208)
  - 소요 시간: **11분 36초** (db.r7g.xlarge 덕분)

- ✅ 검색 API 정상 작동
  - 하이브리드 검색 성공
  - 응답 속도: 약 2.4초 (RDS 네트워크 지연 포함)

- ✅ 보안 그룹 설정 (외부 접속 가능)
  - 0.0.0.0/0 허용 (개발/테스트용)

- ✅ 팀원 공유 준비 완료
  - 엔드포인트 공유 가능
  - DBeaver 연결 테스트 완료

---

## 📚 참고 자료

### 프로젝트 문서

- `01_00_DB전략.md`: DB 전체 전략 및 스키마 설계
- `01_01_DB구축방법.md`: Docker 로컬 구축 가이드
- `01_02_AWS_RDS구축방법.md`: AWS RDS 구축 가이드 (GUI/CLI)
- `01_00_unified_schema.sql`: 통합 스키마 정의
- `README.md`: 빠른 시작 가이드

### 스크립트

- `02_01_run_schema.py`: 스키마 실행
- `02_02_insert_law_guide.py`: 법령 데이터 삽입
- `02_03_insert_case.py`: 사례 데이터 삽입
- `03_01_search_api.py`: FastAPI 검색 서버
- `03_02_test_search_api.py`: API 테스트

---

## 🔐 보안 고려사항

### 현재 설정

**⚠️ 개발/테스트 환경용**:
- 보안 그룹: 0.0.0.0/0 (모든 IP 허용)
- 퍼블릭 액세스: 예
- 비밀번호: `.env` 파일 관리

### 프로덕션 환경 권장

**강화 필요**:
- [ ] 보안 그룹: 특정 IP만 허용 (팀원 IP 화이트리스트)
- [ ] VPN 또는 Bastion Host 사용
- [ ] 비밀번호 변경 및 복잡도 강화
- [ ] AWS Secrets Manager 사용
- [ ] SSL/TLS 연결 강제 (require_ssl=true)
- [ ] CloudWatch 모니터링 활성화
- [ ] 정기 백업 스냅샷 생성

---

## 💰 비용 관리

### 현재 구성 (db.r7g.xlarge)

**⚠️ 프로덕션 인스턴스 - 비용 발생**

**월 예상 비용** (us-east-1 기준):
- **db.r7g.xlarge**: $360/월 (시간당 $0.50)
- **스토리지 100GB (gp3)**: $11.5/월
- **백업 스토리지**: $2-5/월 (7일 보존)
- **데이터 전송**: $5-10/월 (외부 액세스)

**총 예상 비용**: **$380-390/월** 💰

### 비용 절감 전략

#### 1. 사용 시간만 켜기 (최우선 권장) ⭐

**프로젝트 기간만 사용 (2주 가정)**:
```bash
# 사용 안 할 때 중지 (최대 7일)
aws rds stop-db-instance --db-instance-identifier dsr-postgres

# 재시작
aws rds start-db-instance --db-instance-identifier dsr-postgres
```

**절감액**:
- 한 달 30일 중 14일만 사용 → **약 $180/월 절감**
- 최종 비용: **$180-200/월**

#### 2. 프로젝트 종료 후 스냅샷 저장 ⭐

**필요시 복원 가능**:
```bash
# 1. 스냅샷 생성
aws rds create-db-snapshot \
  --db-instance-identifier dsr-postgres \
  --db-snapshot-identifier dsr-final-snapshot

# 2. 인스턴스 삭제
aws rds delete-db-instance \
  --db-instance-identifier dsr-postgres \
  --skip-final-snapshot

# 3. 나중에 복원 (필요시)
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier dsr-postgres-restored \
  --db-snapshot-identifier dsr-final-snapshot \
  --db-instance-class db.r7g.xlarge
```

**절감액**:
- 스냅샷 저장 비용: **$2-3/월** (100GB 기준)
- 인스턴스 비용: **$0/월**
- **총 절감: $360/월** ✅

#### 3. 인스턴스 다운그레이드 (속도 희생)

**프로젝트 데모/발표 전까지만 소형 인스턴스 사용**:
```bash
# db.t4g.small로 변경 (2 vCPU, 2GB RAM)
aws rds modify-db-instance \
  --db-instance-identifier dsr-postgres \
  --db-instance-class db.t4g.small \
  --apply-immediately
```

**절감액**:
- db.t4g.small: $30/월
- db.r7g.xlarge 대비 **$330/월 절감**
- 단, 검색 성능 느려짐 (2-3배)

### 권장 시나리오

**개발/테스트 기간 (2주)**:
1. db.r7g.xlarge 사용 (빠른 데이터 삽입 및 테스트)
2. 사용 안 할 때마다 중지
3. 예상 비용: **$180-200**

**프로젝트 종료 후**:
1. 스냅샷 생성
2. 인스턴스 삭제
3. 보관 비용: **$2-3/월**

**재사용 필요시**:
1. 스냅샷에서 복원
2. 필요한 만큼만 사용 후 다시 삭제

---

## 📞 문제 해결

### RDS 연결 실패

**증상**: `connection refused` 또는 타임아웃

**해결**:
1. 보안 그룹 인바운드 규칙 확인 (5432 포트 개방)
2. 퍼블릭 액세스 "예" 확인
3. RDS 인스턴스 상태 "사용 가능" 확인
4. 엔드포인트 주소 정확한지 확인

---

### 비밀번호 인증 실패

**증상**: `password authentication failed`

**해결**:
1. `.env` 파일 비밀번호 확인
2. 공백 제거 (`.strip()` 추가됨)
3. 필요 시 AWS 콘솔에서 비밀번호 재설정

---

### pgvector 함수 없음

**증상**: `function vector_in does not exist`

**해결**:
```sql
-- DBeaver에서 실행
CREATE EXTENSION IF NOT EXISTS vector;

-- 확인
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

---

## 🎉 마무리

**구축 완료!** 🚀

AWS RDS PostgreSQL + pgvector 환경 구축 및 데이터 삽입이 완전히 완료되었습니다!

**완료 사항**:
1. ✅ AWS RDS 인스턴스 생성 (db.r7g.xlarge)
2. ✅ pgvector 설치 및 스키마 실행
3. ✅ 데이터 삽입 완료 (40,285건)
4. ✅ 검색 API 테스트 완료

**다음 작업**:
1. 팀원에게 연결 정보 공유
2. 로컬에서 RAG 파이프라인 구현
3. 프론트엔드 개발 시작
4. 프로젝트 종료 후 인스턴스 관리 (스냅샷 저장)

**비용 관리 꼭 확인!**: 사용 안 할 때 인스턴스 중지 또는 삭제

**문의사항**: 문서 참고 또는 팀 채널에서 질문

---

**최종 수정일**: 2026-01-26
**작성자**: DDoksori 팀
**버전**: 2.1.0 (2021년 연도 데이터 복구 완료, 전체 연도 2010-2024년 지원)
