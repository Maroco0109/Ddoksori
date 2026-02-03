# Backend 구조 및 설명

> **똑소리 프로젝트** - 한국 소비자 분쟁 조정 RAG 챗봇 백엔드

## 목차
1. [폴더 및 파일 구조도](#폴더-및-파일-구조도)
2. [핵심 아키텍처](#핵심-아키텍처)
3. [주요 특징](#주요-특징)
4. [기술 스택](#기술-스택)
5. [데이터베이스 테이블 상세](#데이터베이스-테이블-상세)
6. [API 엔드포인트](#api-엔드포인트)
7. [데이터 흐름](#데이터-흐름)

---

## 폴더 및 파일 구조도

```
backend/
│
├── 📄 환경 설정 파일
│   ├── .env                          # 실제 환경변수 설정 (DB 접속정보, API 키 등)
│   ├── .env.example                  # 환경변수 템플릿 (새 개발자용 참고 파일)
│   ├── .env.desktop                  # 데스크톱 전용 환경 설정
│   ├── .env.laptop                   # 노트북 전용 환경 설정
│   ├── .dockerignore                 # Docker 빌드 시 제외할 파일 목록
│   └── requirements.txt              # Python 패키지 의존성 목록
│                                     # (FastAPI, PostgreSQL, LLM, 임베딩 라이브러리 등)
│
├── 📄 배포/실행 파일
│   ├── Dockerfile                    # Docker 컨테이너 빌드 설정 (Python 3.11 기반)
│   └── run_local_rag_tests.sh        # 로컬 RAG 테스트 실행 쉘 스크립트
│
├── 🚀 app/ - 메인 애플리케이션 (FastAPI)
│   ├── __init__.py                   # 패키지 초기화 파일
│   └── main.py                       # ★ FastAPI 메인 서버 (v0.4.1)
│                                     # - 6개 API 엔드포인트 정의
│                                     # - CORS 미들웨어 설정
│                                     # - RAG 컴포넌트 초기화
│                                     # - Dependency Injection으로 DB 연결 관리
│
├── 🤖 rag/ - RAG 파이프라인 모듈
│   ├── __init__.py                   # 모듈 공개 API 정의
│   │                                 # (RAGRetriever, HybridRetriever, RAGGenerator, SearchResult 노출)
│   │
│   ├── retriever.py                  # ★ Dense Vector 검색기 (기본 검색)
│   │                                 # - embed_query(): 쿼리를 벡터로 변환
│   │                                 # - vector_search(): pgvector 코사인 유사도 검색
│   │                                 # - get_case_chunks(): 특정 사례의 모든 청크 조회
│   │                                 # - SearchResult 데이터클래스 정의
│   │
│   ├── hybrid_retriever.py           # ★ 하이브리드 검색기 (Dense + Lexical + RRF)
│   │                                 # - Dense: pgvector 벡터 검색
│   │                                 # - Lexical: PostgreSQL 전문검색(FTS)
│   │                                 # - RRF: Reciprocal Rank Fusion 알고리즘으로 결과 융합
│   │                                 # - search_prioritized(): 2단계 우선순위 검색
│   │                                 #   (분쟁조정사례 우선 → 상담사례 보조)
│   │
│   ├── specialized_retrievers.py     # ★ 전문 검색기 (법령/기준/사례 2단계 검색)
│   │                                 # - LawRetriever: 법령 2단계 검색기
│   │                                 # - CriteriaRetriever: 분쟁조정기준 검색기
│   │                                 # - CaseRetriever: 사례/판례 검색기
│   │                                 # - AgencyClassifier: 기관 분류기 (KCA/ECMC/KCDRC)
│   │                                 # - StructuredRetriever: 통합 검색기 오케스트레이션
│   │
│   ├── generator.py                  # ★ LLM 답변 생성기 (OpenAI GPT 기반)
│   │                                 # - 구조화된 답변 템플릿 적용:
│   │                                 #   1) 면책사항
│   │                                 #   2) 추천 기관 및 사유
│   │                                 #   3) 유사 사례
│   │                                 #   4) 관련 법적 근거
│   │                                 #   5) 다음 행동 체크리스트
│   │                                 # - Safety Guardrails: 근거 부족 시 추가 질문 유도
│   │
│   ├── logger.py                     # RAG 파이프라인 로거
│   │                                 # - JSON 형식 상세 로깅
│   │                                 # - 검색/LLM/응답 단계별 기록
│   │                                 # - 저장 경로: logs/rag/YYYY-MM-DD/
│   │
│   ├── splade_retriever.py           # SPLADE 희소 임베딩 (향후 구현 예정)
│   │                                 # - 희소 벡터 기반 검색 지원 계획
│   │
│   └── evaluation/                   # ★ 검색 품질 평가 모듈
│       ├── __init__.py               # 평가 모듈 초기화
│       └── retrieval_metrics.py      # ★ 검색 메트릭 함수 (nDCG, MRR, Precision@K)
│                                     # - Domain Accuracy: 기관추천 정확도
│                                     # - Cases: nDCG@K, MRR
│                                     # - Laws: Precision@K, Recall
│                                     # - Criteria: Precision@K, Recall
│                                     # - Overall: nDCG@K, MRR, Hit Rate@K
│
├── 🔌 외부 서버 (Embedding & SPLADE)
│   ├── embedding_server.py           # ★ 임베딩 서버 (포트 8001)
│   │                                 # - SentenceTransformer 기반
│   │                                 # - 기본 모델: KURE-v1 (한국어 특화, 1024차원)
│   │                                 # - Fallback: ko-sroberta-multitask
│   │                                 # - GPU/CPU 자동 감지 및 최적화
│   │                                 # - /embed: 임베딩 생성 엔드포인트
│   │                                 # - /health: 서버 상태 확인
│   │
│   └── splade_server.py              # SPLADE 서버 (포트 8002, 미구현)
│                                     # - 희소 벡터 생성 서버 (향후 구현)
│
├── 🛠️ utils/ - 유틸리티 모듈
│   ├── __init__.py                   # 패키지 초기화
│   └── embedding_connection.py       # ★ 임베딩 서버 연결 관리
│                                     # - 적응형 연결 전략:
│                                     #   1) Remote 서버 확인
│                                     #   2) Local 실행 중인 서버 확인
│                                     #   3) Local 서버 자동 시작
│                                     # - get_embedding_api_url(): 최적 API URL 결정
│
├── 💾 database/ - 데이터베이스 스키마 및 마이그레이션
│   ├── init.sql                      # 초기 데이터베이스 설정 스크립트
│   │
│   ├── schema_v2_final.sql           # ★ 최종 데이터베이스 스키마 (v2)
│   │                                 # - documents: 문서 메타데이터 테이블
│   │                                 # - chunks: 청크 + 벡터 임베딩 테이블
│   │                                 # - chunk_relations: 청크 간 관계 테이블
│   │                                 # - laws: 법령 메타데이터
│   │                                 # - law_units: 법령 계층 구조 (조/항/호/목)
│   │                                 # - law_version: 법령 버전 관리
│   │                                 # - law_citation_map: 사례-법령 연결
│   │                                 # - criteria: 분쟁조정기준 원천
│   │                                 # - criteria_units: 분쟁조정기준 단위 레코드
│   │                                 # - pgvector 확장 (벡터 검색)
│   │                                 # - 벡터 유사도 검색 함수
│   │                                 # - 통계 뷰
│   │
│   └── migrations/                   # DB 마이그레이션 스크립트
│       ├── 001_add_hybrid_search_support.sql
│       │                             # 하이브리드 검색용 인덱스 및 Materialized View 추가
│       │
│       ├── 002_add_splade_sparse_vector.sql
│       │                             # SPLADE 희소 벡터 컬럼 추가
│       │
│       └── 002_update_mv_searchable_chunks_citations.sql
│                                     # 전문검색(FTS) Materialized View 업데이트
│
├── 📚 data/ - 데이터 처리 문서 및 스크립트
│   ├── docs/                         # 데이터 처리 가이드 문서
│   │   ├── chunking_guide.md         # 청킹 전략 가이드
│   │   │                             # - 문서별 최적 청킹 방법
│   │   │                             # - 청크 크기 및 오버랩 설정
│   │   │
│   │   ├── criteria_hierarchical_search_guide.md
│   │   │                             # 분쟁조정기준 계층 검색 가이드
│   │   │                             # - 카테고리/업종/품목 기반 검색
│   │   │
│   │   └── law_data_usage_guide.md   # 법률 데이터 사용 가이드
│   │                                 # - 법령 데이터 구조 설명
│   │                                 # - 계층 검색 방법
│   │
│   └── law/                          # 법률 데이터 처리
│       └── scripts/                  # 법률 데이터 처리 스크립트
│           ├── law_chunking_strategy.py
│           │                         # 법률 문서 청킹 전략
│           │                         # - 조/항/호/목 단위 분할
│           │
│           ├── law_schema_v2.sql     # 법률 전용 스키마
│           │
│           ├── law_xml_parser_v2.py  # 법률 XML 파서
│           │                         # - 국가법령정보센터 XML 파싱
│           │                         # - 계층 구조 추출
│           │
│           ├── load_law_to_db_v2.py  # 법률 데이터 DB 로딩
│           │
│           ├── load_law_emb_jsonl.py # ★ 법령 임베딩 JSONL 로딩
│           │                         # - statute_chunk_vectors 테이블에 벡터 저장
│           │
│           ├── load_law_jsonl_v2.py  # ★ 법령 JSONL 로딩 v2
│           │                         # - law_units 테이블에 법령 구조 저장
│           │
│           └── test_s1d2_loading_v2.sh
│                                     # 법률 데이터 로딩 테스트 스크립트
│
├── 🔄 scripts/ - 데이터 로딩 및 테스트 스크립트
│   ├── data_loading/                 # 데이터 로딩 스크립트
│   │   ├── batch_loader.py           # 배치 데이터 로더
│   │   │                             # - 대용량 데이터 배치 처리
│   │   │
│   │   ├── embed_all_data.py         # 전체 데이터 임베딩
│   │   │                             # - 모든 청크에 벡터 임베딩 생성
│   │   │
│   │   ├── embed_law_units_v2.py     # 법률 단위별 임베딩
│   │   │
│   │   ├── load_all_test_data.py     # 테스트 데이터 전체 로딩
│   │   │
│   │   ├── load_cases_to_db.py       # ★ 분쟁/상담 사례 로딩 (ETL 파이프라인)
│   │   │                             # - 소비자원 데이터 파싱
│   │   │                             # - 문서 및 청크 생성
│   │   │
│   │   └── load_criteria_to_db.py    # 분쟁조정기준 로딩
│   │                                 # - 별표1~4 데이터 로딩
│   │                                 # - 품목/해결기준/보증기간 등
│   │
│   ├── evaluation/                   # 평가 및 벤치마크
│   │   ├── benchmark_performance.py  # 성능 벤치마킹
│   │   │                             # - 검색 속도 측정
│   │   │                             # - 응답 품질 평가
│   │   │
│   │   ├── create_eval_dataset.py    # ★ 평가 데이터셋 생성
│   │   │                             # - Ground Truth 데이터셋 구성
│   │   │
│   │   ├── run_evaluation.py         # ★ 평가 실행 스크립트
│   │   │                             # - 자동 평가 파이프라인 실행
│   │   │
│   │   ├── interactive_rag_test.py   # 대화형 RAG 테스트
│   │   │                             # - CLI 기반 실시간 테스트
│   │   │
│   │   ├── test_load_cases.py        # 사례 로딩 테스트
│   │   │
│   │   ├── verify_loaded_data.py     # 로딩된 데이터 검증
│   │   │
│   │   └── verify_s1d3_completion.py # S1-D3 완료 검증
│   │
│   ├── examples/                     # 예제 스크립트
│   │   └── query_criteria.py         # 분쟁조정기준 쿼리 예제
│   │
│   └── testing/                      # 테스트 스크립트
│       ├── conftest.py               # pytest 공통 Fixture
│       ├── test_mas_architecture.py  # MAS 아키텍처 통합 테스트
│       ├── README.md                 # 테스트 가이드
│       │
│       ├── agents/                   # 에이전트 기본 테스트
│       │   └── test_base_agent.py
│       ├── answer_generation/        # 답변 생성 테스트
│       │   ├── test_followup.py
│       │   ├── test_formats.py
│       │   └── test_specialist_agency.py
│       ├── auth/                     # 인증 테스트
│       │   └── test_jwt_dependencies.py
│       ├── data/                     # 데이터 수집 테스트
│       │   └── test_collect_training_data.py
│       ├── domain/                   # 도메인 분류 테스트
│       │   ├── golden_set.py
│       │   └── test_domain_classifier.py
│       ├── e2e/                      # E2E 통합 테스트
│       │   ├── test_merged_graph.py
│       │   ├── test_merged_retrieval.py
│       │   ├── test_mock_scenarios.py
│       │   ├── test_system_architecture.py
│       │   └── test_unified_retriever.py
│       ├── generation/               # 생성 노드 테스트
│       ├── legal_review/             # 법률 검토 테스트
│       │   ├── test_enhanced_review.py
│       │   └── test_review_logic.py
│       ├── llm/                      # LLM 호환성 검증
│       │   └── verify_compatibility.py
│       ├── persistence/              # 대화 영속화 테스트
│       │   └── test_conversation_db_unit.py
│       ├── query_analysis/           # 질의 분석 테스트
│       │   ├── test_ambiguous_queries.py
│       │   ├── test_classifier.py
│       │   ├── test_intent_cache.py
│       │   ├── test_new_query_types.py
│       │   └── test_pr2_hybrid.py
│       ├── retrieval/                # 검색 테스트
│       │   └── test_embedding_client.py
│       └── supervisor/               # MAS Supervisor 테스트 (20개)
│           ├── test_adaptive_rag.py
│           ├── test_agent_communication.py
│           ├── test_agent_metrics.py
│           ├── test_agent_trace.py
│           ├── test_answer_cache.py
│           ├── test_conversation_memory.py
│           ├── test_conversation_phase_manager.py
│           ├── test_e2e_queries.py
│           ├── test_fast_path.py
│           ├── test_followup_with_context.py
│           ├── test_mas_integration.py
│           ├── test_mas_supervisor_graph.py
│           ├── test_memory_db.py
│           ├── test_progressive_disclosure.py
│           ├── test_retrieval_merge.py
│           ├── test_retry_context.py
│           ├── test_selective_retrieval.py
│           ├── test_sufficiency.py
│           ├── test_supervisor.py
│           └── test_supervisor_state.py
│
└── 📋 logs/ - 로그 저장소
    └── rag/                          # RAG 파이프라인 로그
        └── YYYY-MM-DD/               # 날짜별 폴더
            └── HHMMSS_uuid.json      # JSON 형식 상세 로그
                                      # - 쿼리, 검색 결과, LLM 응답
                                      # - 토큰 사용량, 응답 시간 등
```

---

## 핵심 아키텍처

### RAG (Retrieval-Augmented Generation) 파이프라인

```
┌─────────────────────────────────────────────────────────────────────┐
│                        사용자 질문                                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    1. Embedding Server (8001)                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  KURE-v1 모델 (한국어 특화, 1024차원)                          │    │
│  │  - 질문 → 벡터 임베딩 변환                                     │    │
│  │  - GPU/CPU 자동 감지                                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    2. Hybrid Retriever                               │
│  ┌──────────────────────┐     ┌──────────────────────┐              │
│  │   Dense Search       │     │   Lexical Search     │              │
│  │   (pgvector)         │     │   (PostgreSQL FTS)   │              │
│  │   - 벡터 유사도 검색   │     │   - 키워드 전문검색   │              │
│  └──────────────────────┘     └──────────────────────┘              │
│              │                           │                          │
│              └───────────┬───────────────┘                          │
│                          ▼                                          │
│            ┌──────────────────────────┐                             │
│            │   RRF (Reciprocal Rank   │                             │
│            │   Fusion) 알고리즘        │                             │
│            │   - 두 검색 결과 융합      │                             │
│            │   - k=60 상수 사용        │                             │
│            └──────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    3. RAG Generator (OpenAI GPT)                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  구조화된 답변 생성 (S1-1 MVP 템플릿)                          │    │
│  │  - 면책사항                                                   │    │
│  │  - 추천 기관 및 사유                                          │    │
│  │  - 유사 사례 (출처 포함)                                       │    │
│  │  - 관련 법적 근거                                             │    │
│  │  - 다음 행동 체크리스트                                        │    │
│  │  + Safety Guardrails (근거 부족 시 추가 질문)                   │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        구조화된 응답                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 주요 특징

### 1. 하이브리드 검색 (Hybrid Retrieval)

- **Dense Search**: pgvector를 이용한 벡터 유사도 검색
- **Lexical Search**: PostgreSQL Full-Text Search (FTS)
- **RRF Fusion**: Reciprocal Rank Fusion 알고리즘으로 두 검색 결과 융합
  ```
  RRF Score = Σ(1 / (k + rank_i))  where k=60
  ```
- **2단계 우선순위 검색**: 분쟁조정사례 우선 검색 후, 부족분을 상담사례로 보충

### 2. 전문 검색기 (Specialized Retrievers)

- **LawRetriever**: 법령 2단계 검색 (항/호/목 → 조 매핑)
- **CriteriaRetriever**: 분쟁조정기준 검색
- **CaseRetriever**: 사례/판례 검색
- **AgencyClassifier**: 기관 분류 (KCA/ECMC/KCDRC)
- **StructuredRetriever**: 통합 검색기 오케스트레이션

### 3. 한국어 특화 임베딩 모델

- **KURE-v1**: 한국어 특화 임베딩 모델 (1024차원)
- **Fallback**: ko-sroberta-multitask (KURE-v1 로드 실패 시)
- **GPU/CPU 자동 감지**: CUDA 사용 가능 시 GPU 활용

### 4. 구조화된 LLM 답변 생성

```
[면책사항]
본 답변은 정보 제공 목적이며 법률 자문이 아닙니다...

1. 추천 기관 및 사유
   - 한국소비자원: ...

2. 유사 사례
   - [분쟁조정사례] 제목... (출처, 결정일)

3. 관련 법적 근거
   - 전자상거래법 제17조...

4. 다음 행동 체크리스트
   □ 관련 서류 준비
   □ 해당 기관 연락
```

### 5. Safety Guardrails

- 근거가 부족한 경우 추가 질문을 통해 정보 수집
- 단정적 표현 금지 (법률 판단 회피)
- 개인정보 요구 금지

### 6. 검색 품질 평가 시스템

- **섹션별 메트릭**:
  - Domain (기관추천): Accuracy
  - Cases (유사사례): nDCG@K, MRR
  - Laws (법령): Precision@K, Recall
  - Criteria (기준): Precision@K, Recall
- **전체 메트릭**: Overall nDCG@K, MRR, Hit Rate@K

### 7. 데이터베이스 설계

- **pgvector 확장**: 벡터 검색 지원
- **계층적 법령 구조**: 조/항/호/목 단위 저장
- **분쟁조정기준 정형화**: 별표1~4 (품목분류, 해결기준, 보증기간, 내용연수)
- **Materialized View**: 전문검색 최적화

### 8. Dependency Injection 패턴

```python
# 요청마다 독립적인 DB 연결 보장
def get_retriever() -> Generator[Any, None, None]:
    retriever = HybridRetriever(db_config, embed_api_url)
    try:
        retriever.connect()
        yield retriever
    finally:
        retriever.close()
```

### 9. 상세 로깅 시스템

- JSON 형식 로그
- 검색/LLM/응답 단계별 기록
- 토큰 사용량, 응답 시간 측정
- 날짜별 폴더 구조: `logs/rag/YYYY-MM-DD/`

---

## 기술 스택

| 분류 | 기술 |
|------|------|
| **웹 프레임워크** | FastAPI 0.115.6, Uvicorn 0.32.1 |
| **데이터베이스** | PostgreSQL + pgvector 0.3.6 |
| **임베딩** | SentenceTransformers 3.3.1 (KURE-v1, 1024차원) |
| **LLM** | OpenAI GPT-4o-mini |
| **딥러닝** | PyTorch 2.5.1 |
| **LLM 오케스트레이션** | LangChain, LangGraph |
| **평가** | RAGAS, 자체 메트릭 |
| **테스트** | pytest, pytest-asyncio, httpx |
| **컨테이너** | Docker |

---

## 데이터베이스 테이블 상세

> 총 10개 테이블로 구성된 PostgreSQL + pgvector 기반 데이터베이스

### 테이블 요약

| 테이블 | 건수 | 역할 |
|--------|------|------|
| **documents** | 16,395 | 문서 메타데이터 |
| **chunks** | 74,333 | 청크 + 임베딩 벡터 (검색 핵심) |
| **laws** | 20 | 법령 메타데이터 |
| **law_units** | 11,321 | 법령 조/항/호/목 계층 구조 |
| **statute_chunk_vectors** | 6,300 | 법령 벡터 임베딩 |
| **criteria** | 6 | 분쟁조정기준 원천 분류 |
| **criteria_units** | 0 | 분쟁조정기준 단위 (미적용) |
| **chunk_relations** | 5,494 | 청크 간 관계 |
| **law_version** | 0 | 법령 버전 (미적용) |
| **law_citation_map** | 0 | 사례-법령 연결 (미적용) |

---

### 1. documents (문서 메타데이터) - 16,395건

| doc_id | doc_type | title | source_org |
|--------|----------|-------|------------|
| 53321 | counsel_case | 가전제품 정액감가상각 계산법 문의 | consumer.go.kr |
| 50578 | counsel_case | 신용카드 결제 후 매출 취소 시 가맹점수수료 문의 | consumer.go.kr |
| 55497 | counsel_case | 자차사고 수리비 외에 부가세 지급에 관한 문의 | consumer.go.kr |
| 45532 | counsel_case | 진단서 발급을 거부하는 의료기관에 대한 처벌가능 여부 | consumer.go.kr |
| ECMC_04551_25 | mediation_case | 분쟁조정사례 04551 | ECMC |

**용도**: 모든 문서(상담사례, 분쟁조정사례, 법령)의 메타데이터 저장

**doc_type 종류**:
- `counsel_case`: 상담사례 (1372 소비자상담센터)
- `mediation_case`: 분쟁조정사례 (소비자원, ECMC 등)
- `law`: 법령

---

### 2. chunks (청크 + 임베딩) - 74,333건

| chunk_id | doc_id | chunk_type | content (일부) |
|----------|--------|------------|----------------|
| 49300:solution:0001 | 49300 | solution | 품질보증기간이내 정상적인 사용상태에서 발생한 하자는 무상수리... |
| 49301:full:0002 | 49301 | full | 중고차량 무상수리 기간 문의... |
| 49303:problem:0000 | 49303 | problem | 방문판매로 물품 구입 후 완불한 유아교재 반품 문의... |
| 49303:solution:0001 | 49303 | solution | 반품 및 환급이 불가능함. 방문판매로 물품을 구매한 경우... |

**용도**: 문서를 의미 단위로 분할 + **1024차원 임베딩 벡터** 저장 (검색용)

**chunk_type 종류**:
| chunk_type | 설명 |
|------------|------|
| `problem` | 질문/문제 상황 |
| `solution` | 답변/해결 방법 |
| `full` | 전체 내용 |
| `facts` | 사건 개요 |
| `claims` | 당사자 주장 |
| `reasoning` | 판단 근거 |
| `mediation_outcome` | 조정 결과 |

---

### 3. laws (법령 메타데이터) - 20건

| law_id | law_name | law_type | ministry |
|--------|----------|----------|----------|
| 000355 | 할부거래에 관한 법률 | 법률 | 공정거래위원회 |
| 001589 | 소비자기본법 | 법률 | 공정거래위원회 |
| 002011 | 표시·광고의 공정화에 관한 법률 | 법률 | 공정거래위원회 |
| 009280 | 콘텐츠산업 진흥법 | 법률 | 문화체육관광부 |
| 001706 | 민법 | 법률 | 법무부 |

**용도**: 소비자 관련 법령 메타데이터

---

### 4. law_units (법령 계층 구조) - 11,321건

| doc_id | law_id | level | article_no | text (일부) |
|--------|--------|-------|------------|-------------|
| 000355\|A1 | 000355 | article | 제1조 | 이 법은 할부계약 및 선불식 할부계약에 의한 거래를 공정하게... |
| 000355\|A2 | 000355 | article | 제2조 | 이 법에서 사용하는 용어의 뜻은 다음과 같다. |
| 000355\|A3 | 000355 | article | 제3조 | 이 법은 다음 각 호의 거래에는 적용하지 아니한다. |
| 000355\|A4 | 000355 | article | 제4조 | 다른 법률과의 관계... |
| 000355\|A5 | 000355 | article | 제5조 | 계약체결 전의 정보제공... |

**용도**: 법령을 조/항/호/목 단위로 계층 구조화

**level 종류**:
| level | 설명 |
|-------|------|
| `article` | 조 |
| `paragraph` | 항 |
| `item` | 호 |
| `subitem` | 목 |

**주요 컬럼**: doc_id, law_id, parent_id, level, search_stage, path, ref_citations_internal/external

---

### 5. statute_chunk_vectors (법령 벡터 임베딩) - 6,300건

| unit_id | embedding_model | law_id | unit_level | path | embedding |
|---------|-----------------|--------|------------|------|-----------|
| 000355\|A1 | KURE-v1 | 000355 | article | 제1조 | [1024차원 벡터] |

**용도**: 법령 조문의 1024차원 벡터 임베딩 저장 (2단계 검색용)

**주요 컬럼**: unit_id, embedding_model, law_id, unit_level, path, node_refs, index_text, embedding

---

### 6. criteria (분쟁조정기준 원천) - 6건

| source_id | source_label | description |
|-----------|--------------|-------------|
| table1 | 별표1 품목 분류 | 소비자분쟁해결기준 대상품목 분류 |
| table2 | 별표2 해결기준 | 소비자분쟁해결기준 품목별 해결기준 |
| table3 | 별표3 품질보증기간 | 품목별 품질보증기간 및 부품보유기간 |
| table4 | 별표4 내용연수 | 품목별 내용연수 |
| ecommerce_guideline | 전자상거래 소비자보호 지침 | 전자상거래 등에서의 소비자보호 지침 |
| content_guideline | 콘텐츠 소비자보호 지침 | 콘텐츠 소비자보호 지침 |

**용도**: 소비자분쟁해결기준 별표1~4, 지침 등 원천 데이터 분류

---

### 7. criteria_units (분쟁조정기준 단위) - 현재 0건

| 컬럼 | 설명 |
|------|------|
| unit_id | 단위 고유 식별자 |
| source_id | criteria 테이블 참조 |
| unit_text | 검색용 대표 텍스트 |
| embedding | 1024차원 벡터 임베딩 |

**용도**: 분쟁조정기준을 검색 가능한 단위로 분할 (임베딩 포함)

---

### 8. chunk_relations (청크 간 관계) - 5,494건

| source_chunk_id | target_chunk_id | relation_type | confidence |
|-----------------|-----------------|---------------|------------|
| 000355\|A2\|PX\|I1 | 000355\|A2\|PX\|I1\|M가 | child_subitem | 1 |
| 000355\|A2\|PX\|I1 | 000355\|A2\|PX\|I1\|M나 | child_subitem | 1 |
| 000355\|A2\|PX\|I2 | 000355\|A2\|PX\|I2\|M가 | child_subitem | 1 |

**용도**: 청크 간 관계 (상위-하위, 이전-다음 등) 저장

**relation_type 종류**:
| relation_type | 설명 |
|---------------|------|
| `next` | 다음 청크 |
| `prev` | 이전 청크 |
| `parent_article` | 상위 조문 |
| `child_paragraph` | 하위 항 |
| `child_item` | 하위 호 |
| `child_subitem` | 하위 목 |

---

### 9. law_version (법령 버전) - 현재 0건

| 컬럼 | 설명 |
|------|------|
| version_id | 버전 ID |
| law_id | 법령 ID |
| version_date | 시행일자 |
| version_type | 제정/개정/일부개정 등 |
| is_current | 현재 시행 버전 여부 |

**용도**: 법령 개정 이력 관리

---

### 10. law_citation_map (사례-법령 연결) - 현재 0건

| 컬럼 | 설명 |
|------|------|
| source_type | mediation_case, counsel_case, criteria_rule |
| source_id | 문서 또는 청크 ID |
| law_unit_id | 법령 조문 ID |
| citation_type | direct(직접 인용), related(연관), applied(적용) |

**용도**: 분쟁 사례에서 어떤 법령 조문이 적용되었는지 매핑

---

### 테이블 관계도 (ER Diagram 요약)

```
┌─────────────┐       ┌─────────────┐
│  documents  │───────│   chunks    │
│  (16,395)   │ 1 : N │  (74,333)   │
└─────────────┘       └──────┬──────┘
                             │
                             │ N : M
                             ▼
                      ┌─────────────────┐
                      │ chunk_relations │
                      │    (5,494)      │
                      └─────────────────┘

┌─────────────┐       ┌─────────────┐       ┌───────────────────────┐
│    laws     │───────│  law_units  │───────│ statute_chunk_vectors │
│    (20)     │ 1 : N │  (11,321)   │ 1 : 1 │       (6,300)         │
└─────────────┘       └──────┬──────┘       └───────────────────────┘
                             │
                             │ 1 : N
                             ▼
                      ┌─────────────────┐
                      │ law_citation_map│
                      │     (0건)       │
                      └─────────────────┘

┌─────────────┐       ┌─────────────────┐
│  criteria   │───────│ criteria_units  │
│    (6건)    │ 1 : N │     (0건)       │
└─────────────┘       └─────────────────┘
```

---

## API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/` | GET | 서버 상태 정보 (버전, 검색 모드) |
| `/health` | GET | 서버 헬스체크 (DB 연결 확인) |
| `/search` | POST | 벡터 검색만 수행 (LLM 없이) |
| `/chat` | POST | RAG 기반 답변 생성 |
| `/chat/stream` | POST | 스트리밍 답변 생성 |
| `/case/{uid}` | GET | 특정 사례의 전체 정보 조회 |

### 요청/응답 예시

**POST /chat**
```json
// Request
{
  "message": "인터넷 쇼핑몰에서 구매한 상품이 불량인데 환불이 안 돼요",
  "top_k": 5
}

// Response
{
  "answer": "본 답변은 정보 제공 목적이며...\n\n1. 추천 기관 및 사유\n...",
  "chunks_used": 5,
  "model": "gpt-4o-mini",
  "sources": [...],
  "has_sufficient_evidence": true,
  "clarifying_questions": []
}
```

---

## 데이터 흐름

### 1. 데이터 수집 및 저장
```
원본 데이터 (JSON/XML)
    │
    ▼
ETL 스크립트 (scripts/data_loading/)
    │
    ├── 분쟁조정사례, 상담사례 → documents + chunks 테이블
    ├── 법령 XML → laws + law_units 테이블
    └── 분쟁조정기준 → criteria + criteria_units 테이블
    │
    ▼
임베딩 생성 (embed_all_data.py)
    │
    ▼
PostgreSQL + pgvector (chunks.embedding 컬럼)
```

### 2. 검색 및 응답
```
사용자 질문
    │
    ▼
FastAPI 서버 (/chat 엔드포인트)
    │
    ▼
Embedding Server → 쿼리 벡터화
    │
    ▼
Hybrid Retriever
    ├── Dense Search (pgvector)
    └── Lexical Search (FTS)
    │
    ▼
RRF Fusion → 상위 K개 청크 선택
    │
    ▼
RAG Generator → 구조화된 답변 생성
    │
    ▼
JSON 응답 (답변 + 출처 + 메타데이터)
```

---

## 실행 방법

### 1. 환경 설정
```bash
# 환경변수 파일 복사
cp .env.example .env

# 필수 환경변수 설정
# - DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
# - OPENAI_API_KEY
# - EMBED_API_URL (선택)
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 임베딩 서버 실행
```bash
python embedding_server.py
# 포트 8001에서 실행
```

### 4. 메인 서버 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Docker 실행
```bash
docker build -t ddoksori-backend .
docker run -p 8000:8000 ddoksori-backend
```

---

## 참고 사항

- **버전**: v0.4.1 (Concurrency Safety 리팩토링 완료)
- **검색 모드**: `RETRIEVAL_MODE` 환경변수로 설정 (`hybrid` 또는 `dense`)
- **임베딩 차원**: 1024 (KURE-v1 모델)
- **RRF 상수**: k=60 (표준값)
- **법령 데이터**: 20개 법령, 11,321개 조문 단위
- **평가 메트릭**: nDCG@K, MRR, Precision@K, Recall, Hit Rate@K, Domain Accuracy
