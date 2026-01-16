# ddoksori 프로젝트 3주 집중 계획서

> **프로젝트**: 한국 소비자 분쟁 조정을 위한 멀티 에이전트 RAG 챗봇
> **기간**: 3주 (2026년 1월 ~ 2월)
> **팀 규모**: 5명

---

## 1. 팀 구성 및 역할 배정

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         🟣 팀장                                             │
│              통합/오케스트레이션 + 질의분석 + 전체 조율                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  🟢 팀원 A          🟢 팀원 B          🔵 팀원 C          🔴 팀원 D          │
│  법령/기준 ETL      사례/상담 ETL       생성 Agent         검토 + 프론트     │
│  + Retrieval       + 임베딩 + 검색     + 프롬프트         + Review + UI     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 역할별 담당 영역

| 역할 | 담당 파일 | 주요 업무 |
|------|----------|----------|
| **🟣 팀장** | `graph.py`, `state.py`, `query_analysis.py`, `classifier.py` | 그래프 워크플로우, 상태 관리, 질의 분류, 전체 조율 |
| **🟢 팀원 A** | `load_law_*.py`, `load_criteria_*.py`, `retrieval.py`, `evaluate_*.py` | 법령/기준 ETL, Retrieval Node, 평가 시스템 |
| **🟢 팀원 B** | `load_cases_*.py`, `embed_*.py`, `hybrid_retriever.py`, `specialized_retrievers.py` | 사례/상담 ETL, 임베딩, 검색 최적화 |
| **🔵 팀원 C** | `generation.py`, `generator.py` | 답변 생성, 프롬프트 엔지니어링 |
| **🔴 팀원 D** | `review.py`, `ask_clarification.py`, `frontend/src/**` | 검토 로직, 프론트엔드 UI |

---

## 2. 3주 일정 개요

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1주차                    2주차                    3주차                    │
│  ════════                ════════                ════════                  │
│  데이터 파이프라인         Agent 고도화            통합 + 마무리             │
│  ──────────────          ──────────────          ──────────────            │
│  • ETL 자동화             • 노드별 개선            • E2E 테스트              │
│  • 임베딩 완료             • 평가 시스템            • 프론트엔드              │
│  • 품질 검증              • 검색 최적화            • 문서화/데모             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 1주차: 데이터 파이프라인 (병렬 집중)

### 목표
- 전체 데이터 로딩 및 임베딩 완료
- 데이터 품질 검증 통과
- 파이프라인 자동화

### 일정표

| 담당 | Day 1-2 | Day 3-4 | Day 5 |
|------|---------|---------|-------|
| **🟣 팀장** | 아키텍처 설계, 인터페이스 정의 | 통합 스크립트 작성 | 품질 리포트 통합 |
| **🟢 팀원 A** | 법령 XML 파싱 분석 | `law_pipeline.py` 구현 | `criteria_pipeline.py` 구현 |
| **🟢 팀원 B** | 사례/상담 JSONL 분석 | `case_pipeline.py` 구현 | 임베딩 파이프라인 실행 |
| **🔵 팀원 C** | 프로젝트 구조 학습 | Generation 코드 분석, 프롬프트 분석 | 프롬프트 개선안 초안 |
| **🔴 팀원 D** | 프로젝트 구조 학습 | Review 코드 분석, 프론트 구조 파악 | 개선 포인트 정리 |

### 실행 명령어

```bash
# 팀원 A: 법령/기준 데이터 로딩
cd backend
python data/law/scripts/load_law_to_db_v2.py
python scripts/data_loading/load_criteria_to_db.py

# 팀원 B: 사례/상담 데이터 로딩 + 임베딩
python scripts/data_loading/load_all_test_data.py --all
python scripts/data_loading/embed_all_data.py

# 데이터 검증
python scripts/evaluation/verify_loaded_data.py
```

### 완료 기준

- [ ] 전체 데이터 로딩 완료 (`python load_all_test_data.py --all` 성공)
- [ ] 임베딩 생성 완료 (null embedding = 0)
- [ ] 데이터 품질 리포트 JSON/CSV 생성

---

## 4. 2주차: Agent 고도화 (각자 담당 노드)

### 목표
- 각 Agent 노드 개선 및 테스트
- 평가 시스템 구축 및 지표 달성
- 검색 품질 최적화

### 일정표

| 담당 | Day 1-2 | Day 3-4 | Day 5 |
|------|---------|---------|-------|
| **🟣 팀장** | 도메인 분류 고도화 | 라우팅 로직 강화, 상태 스키마 최적화 | 팀 코드 리뷰, 통합 테스트 |
| **🟢 팀원 A** | Retrieval Node 개선 | 평가 Golden Set 구축 | 평가 스크립트 실행 |
| **🟢 팀원 B** | 하이브리드 검색 튜닝 | 2단계 검색 최적화 | 검색 벤치마크 |
| **🔵 팀원 C** | 답변 포맷 개선 | 프롬프트 튜닝 | Faithfulness 분석 |
| **🔴 팀원 D** | Review 패턴 확장 | Ask Clarification 개선 | 위반 탐지 테스트 |

### 실행 명령어

```bash
# 각 담당자: 단위 테스트
pytest backend/scripts/testing/orchestrator/test_pr2_nodes.py -v

# 팀장: 그래프 테스트
pytest backend/scripts/testing/orchestrator/test_pr3_graph.py -v

# 팀원 A: 평가 실행
python -m scripts.evaluation.run_evaluation \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/retrieval_eval.json

# 팀원 A: Query Analysis 평가
python -m scripts.evaluation.evaluate_query_analysis \
  --golden-set ./data/golden_set/query_analysis.jsonl \
  --output ./results/qa_eval.json

# 팀원 D: Review 평가
python -m scripts.evaluation.evaluate_review \
  --golden-set ./data/golden_set/review.jsonl \
  --output ./results/review_eval.json
```

### 완료 기준

- [ ] 각 노드 단위 테스트 통과 (`pytest test_pr2_nodes.py` 100%)
- [ ] Retrieval nDCG@5 ≥ 0.65
- [ ] Query Type Accuracy ≥ 0.90
- [ ] Violation Detection Precision ≥ 0.85

---

## 5. 3주차: 통합 테스트 + 프론트엔드 + 마무리

### 목표
- E2E 시나리오 테스트 통과
- 프론트엔드 UI 개선 완료
- 문서화 및 데모 준비

### 일정표

| 담당 | Day 1-2 | Day 3-4 | Day 5 |
|------|---------|---------|-------|
| **🟣 팀장** | E2E 테스트 시나리오 실행 | 버그 수정 조율 | 최종 통합, 데모 준비 |
| **🟢 팀원 A** | 전체 평가 실행 | 성능 리포트 작성 | 문서화 |
| **🟢 팀원 B** | 검색 최종 튜닝 | 캐싱/성능 최적화 | 문서화 |
| **🔵 팀원 C** | 답변 품질 검증 | 예외 케이스 처리 | 문서화 |
| **🔴 팀원 D** | **프론트엔드 UI 개선** | **출처 모달, 안전 경고 UI** | UX 마무리, 반응형 |

### 실행 명령어

```bash
# 전체 테스트 실행
./backend/run_local_rag_tests.sh all

# 프론트엔드 개발 서버
cd frontend && npm run dev

# E2E 시나리오 테스트 (수동)
# http://localhost:5173 접속 후 시나리오 테스트
```

### E2E 테스트 시나리오

| # | 시나리오 | 확인 사항 |
|---|---------|----------|
| 1 | 분쟁 상담 + 스트리밍 | "헬스장 환불" 질의 → 실시간 타이핑, 면책 문구 표시 |
| 2 | 인라인 출처 확인 | `[1]`, `[2]` 클릭 → 출처 상세 모달 표시 |
| 3 | 안전 장치 | 모호한 질문 → 오렌지 경고 박스, 추가 질문 표시 |
| 4 | 일반 대화 | "안녕" → 스트리밍 응답, 출처 없음 |
| 5 | 에러 처리 | 백엔드 중지 후 질문 → 에러 메시지 표시 |

### 완료 기준

- [ ] E2E 시나리오 5개 모두 통과
- [ ] 프론트엔드 UI 개선 완료
- [ ] 데모 가능 상태

---

## 6. 기술 지식 요구 수준

### 분야별 요구 수준 비교

| 분야 | 팀장 | 팀원A | 팀원B | 팀원C | 팀원D |
|------|:----:|:-----:|:-----:|:-----:|:-----:|
| **LangGraph/Agent** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ |
| **SQL/데이터** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
| **검색/임베딩** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ |
| **LLM/프롬프트** | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **React/프론트** | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐ |

### 역할별 필요 지식 상세

#### 🟣 팀장: 통합/오케스트레이션 + 질의분석

| 분야 | 수준 | 필요 지식 |
|------|------|----------|
| LangGraph | ⭐⭐⭐⭐⭐ | `StateGraph`, `add_node`, `add_conditional_edges`, checkpointer |
| 상태 관리 | ⭐⭐⭐⭐ | TypedDict, MessagesState, reducer 패턴 |
| Python | ⭐⭐⭐ | 타입 힌트, dataclass, 비동기 기초 |
| 도메인 지식 | ⭐⭐⭐⭐ | 소비자 분쟁 기관 (KCA/ECMC/KCDRC/FSS/K-MEDI) |

#### 🟢 팀원 A: 법령/기준 + Retrieval + 평가

| 분야 | 수준 | 필요 지식 |
|------|------|----------|
| SQL/PostgreSQL | ⭐⭐⭐⭐ | DDL, UPSERT, FK 관계, 인덱스 |
| 데이터 모델링 | ⭐⭐⭐⭐ | 계층 구조, 정규화 |
| Python | ⭐⭐⭐ | XML 파싱, JSONL 처리, pytest |
| 평가 지표 | ⭐⭐⭐⭐ | nDCG, MRR, Precision, Recall |

#### 🟢 팀원 B: 사례/상담 + 임베딩 + 검색 최적화

| 분야 | 수준 | 필요 지식 |
|------|------|----------|
| 임베딩/벡터 | ⭐⭐⭐⭐⭐ | 임베딩 API, pgvector, 벡터 인덱스 |
| 검색/IR | ⭐⭐⭐⭐ | Dense/Sparse 검색, RRF, 하이브리드 검색 |
| PostgreSQL | ⭐⭐⭐ | pgvector, SQL 쿼리 최적화 |
| Python | ⭐⭐⭐ | requests, 비동기 처리 |

#### 🔵 팀원 C: 생성 Agent + 프롬프트

| 분야 | 수준 | 필요 지식 |
|------|------|----------|
| LLM/프롬프트 | ⭐⭐⭐⭐⭐ | 시스템 프롬프트, Few-shot, Chain-of-Thought |
| LangChain | ⭐⭐⭐ | ChatOpenAI, AIMessage, 프롬프트 템플릿 |
| RAG 개념 | ⭐⭐⭐⭐ | Context Window, Hallucination, Faithfulness |
| 도메인 지식 | ⭐⭐⭐ | 법률 답변 포맷, 면책 문구, 출처 인용 |

#### 🔴 팀원 D: 검토 + 프론트엔드

| 분야 | 수준 | 필요 지식 |
|------|------|----------|
| 정규표현식 | ⭐⭐⭐⭐ | 금지 표현 패턴 매칭, 한국어 처리 |
| React/TypeScript | ⭐⭐⭐⭐ | React 컴포넌트, 상태 관리, TailwindCSS |
| UX/UI | ⭐⭐⭐ | 사용자 경험, 에러 메시지, 스트리밍 UI |
| Python | ⭐⭐⭐ | re 모듈, 문자열 처리 |

---

## 7. 협업 규칙

### 일일 체크인

```
매일 오전 9시 30분: 진행 상황 공유 (Slack/노션)
- 어제 완료한 것
- 오늘 할 것
- 블로커 있으면 공유

매일 오후 5시: 진행 상황 업데이트
```

### 주간 마일스톤 체크

| 주차 | 금요일 체크포인트 | 확인 방법 |
|------|-----------------|----------|
| **1주차** | 데이터 파이프라인 완료 | `--all` 실행 성공, 리포트 생성 |
| **2주차** | Agent 테스트 통과 | pytest 100%, 평가 지표 달성 |
| **3주차** | 데모 준비 완료 | E2E 시나리오 통과, UI 완성 |

### 코드 리뷰 규칙

| 변경 영역 | 필수 리뷰어 |
|----------|-----------|
| `graph.py`, `state.py` | 팀장 필수 |
| `nodes/*.py` | 팀장 + 해당 노드 담당자 |
| `rag/*.py` | 팀원 A 또는 B |
| `frontend/**` | 팀원 D + 팀장 |
| `scripts/data_loading/**` | 팀원 A ↔ 팀원 B 교차 리뷰 |

---

## 8. 핵심 성공 지표

| 지표 | 목표 | 담당 | 확인 방법 |
|------|------|------|----------|
| 데이터 로딩 완료 | 100% | 팀원 A, B | null embedding = 0 |
| Query Type Accuracy | ≥ 0.90 | 팀장 | `evaluate_query_analysis.py` |
| Retrieval nDCG@5 | ≥ 0.65 | 팀원 A, B | `run_evaluation.py` |
| Violation Detection Precision | ≥ 0.85 | 팀원 D | `evaluate_review.py` |
| E2E 시나리오 통과 | 5/5 | 전체 | 수동 테스트 |
| 프론트엔드 완성 | UI 개선 완료 | 팀원 D | 시각적 확인 |

---

## 9. 데이터 파이프라인 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        데이터 파이프라인 흐름                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Raw Data          ETL Scripts         PostgreSQL         Embedding        │
│  ──────────        ──────────────       ──────────        ──────────        │
│                                                                             │
│  📂 law/raw/   →   law_xml_parser    →  law_units     →  embed_law_units   │
│     (XML)          load_law_to_db       laws              (KURE-v1)         │
│                                                                             │
│  📂 criteria/  →   load_criteria     →  criteria_*    →  embed_all_data    │
│     (JSONL)        _to_db               documents                           │
│                                         chunks                              │
│                                                                             │
│  📂 dispute/   →   load_cases_to_db  →  documents     →  embed_all_data    │
│     (JSONL)        (kca/ecmc/kcdrc)     chunks                              │
│                                                                             │
│  📂 counsel/   →   load_counsel      →  documents     →  embed_all_data    │
│     (JSONL)        _jsonl               chunks                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 데이터 규모

| 도메인 | 원본 파일 | 예상 레코드 | 예상 청크 |
|--------|----------|------------|----------|
| 법령 (Law) | `law/raw/*.xml` | 11개 법령 | ~5,455 |
| 기준 (Criteria) | `criteria/jsonl/*.jsonl` | 7개 파일 | ~507 |
| 분쟁 (Dispute) | `dispute/*.jsonl` | ~2,015건 | ~6,045 |
| 상담 (Counsel) | `counsel/counsel.jsonl` | ~13,544건 | ~62,851 |
| **합계** | | | **~74,858** |

---

## 10. 참고 명령어 모음

### 환경 설정

```bash
# Conda 환경 활성화
conda activate dsr

# 환경 변수 설정
cp backend/.env.example backend/.env
# .env 파일에 API 키 설정
```

### 데이터 로딩

```bash
# 전체 데이터 로딩
python backend/scripts/data_loading/load_all_test_data.py --all

# 개별 데이터 로딩
python backend/scripts/data_loading/load_all_test_data.py --counsel
python backend/scripts/data_loading/load_all_test_data.py --dispute
python backend/scripts/data_loading/load_all_test_data.py --criteria

# 법령 데이터 로딩
python backend/data/law/scripts/load_law_to_db_v2.py

# 임베딩 생성
python backend/scripts/data_loading/embed_all_data.py
```

### 테스트 실행

```bash
# 전체 테스트
./backend/run_local_rag_tests.sh all

# 개별 테스트
./backend/run_local_rag_tests.sh api
./backend/run_local_rag_tests.sh integration
./backend/run_local_rag_tests.sh data

# 오케스트레이터 테스트
pytest backend/scripts/testing/orchestrator/ -v

# 도메인 분류 테스트
pytest backend/scripts/testing/domain/ -v
```

### 평가 실행

```bash
# Retrieval 평가
python -m scripts.evaluation.run_evaluation \
  --dataset data/evaluation/eval_dataset.jsonl \
  --output results/retrieval_eval.json

# Query Analysis 평가
python -m scripts.evaluation.evaluate_query_analysis \
  --golden-set ./data/golden_set/query_analysis.jsonl \
  --output ./results/qa_eval.json

# Review 평가
python -m scripts.evaluation.evaluate_review \
  --golden-set ./data/golden_set/review.jsonl \
  --output ./results/review_eval.json

# 인터랙티브 테스트
python backend/scripts/evaluation/interactive_rag_test.py
```

### 서비스 실행

```bash
# 백엔드
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 프론트엔드
cd frontend
npm install  # 최초 1회
npm run dev

# Docker 전체 실행
docker-compose up --build
```

---

## 11. 문서 링크

- [프로젝트 README](/README.md)
- [RAG 아키텍처 상세](/docs/guides/rag_architecture_expert_view.md)
- [임베딩 프로세스 가이드](/docs/guides/embedding_process_guide.md)
- [테스트 가이드](/docs/backend/scripts/TEST_README.md)
- [AGENTS.md](/AGENTS.md) - AI 코딩 에이전트 가이드

---

*최종 수정: 2026-01-16*
