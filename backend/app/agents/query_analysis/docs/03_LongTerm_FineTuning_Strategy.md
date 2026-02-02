# PR 3: Long-Term Fine-Tuning Strategy & Data Collection

## 1. 개요 및 검토 의견
`docs/plans/manus/질의 분석 에이전트 고도화 전략 비교 분석 보고서.md`의 결론에 따라, 장기적으로는 **Fine-Tuned Small LLM (EXAONE 2.4B 등)** 을 도입하는 것이 비용과 성능(Latency) 면에서 가장 효율적입니다.

하지만 즉각적인 도입보다는 **데이터 기반의 점진적 전환(Phase-based Transition)** 이 리스크를 줄이는 길입니다. 따라서 본 PR은 모델 교체 자체가 아닌, **"학습 데이터 수집 파이프라인 구축"**을 목표로 합니다.

### 1.1. (추가) 코드베이스 기반 현실성 점검

현재 코드베이스는 "데이터 수집" 관점에서 다음 기반이 이미 갖춰져 있어 Phase 1(로그 기반 데이터셋 생성)은 실현 가능성이 높습니다.

- `backend/app/common/logger.py`: `RAGLogger`가 요청 단위 JSON 로그를 `backend/logs/rag/<YYYY-MM-DD>/...json` 형태로 저장
- `backend/app/orchestrator/graph.py`: 각 노드를 `_create_timed_node()`로 감싸 `input_snapshot`/`output_snapshot`을 `_node_timings`에 주입
  - `query_analysis` 노드에 대해 `user_query`, `onboarding`, `chat_type` (input)과 `query_analysis`, `mode`, `query_analysis_v2` (output) 스냅샷 수집
- `backend/app/main.py`: 그래프 실행 후 `final_state['_node_timings']`를 `RAGLogger.log_node_timings()`로 저장

단, Phase 2에서 언급한 "사용자 만족(Thumbs up)" 데이터는 현재 로그 스키마에 존재하지 않으므로, 해당 기준은 보완/대체가 필요합니다.

## 2. 데이터 수집 파이프라인 (Data Flywheel)

### 2.1. 로깅 시스템 활용 (`backend/app/common/logger.py`)
현재 구축된 `RAGLogger`는 매우 상세한 정보를 JSON으로 남기고 있습니다. 이를 활용하여 별도의 추가 개발 없이 데이터를 축적합니다.

- **수집 대상**:
  - `query` / `input_data.message`: 사용자 입력 (실제 저장 필드)
  - `node_timings.query_analysis.output_snapshot`: 질의분석 결과 스냅샷
    - `query_analysis_v2.query_type`, `keywords`, `rewritten_query`, `search_queries` 등 (구현/실행 경로에 따라 포함)
  - `response.status`: 처리 성공 여부
  - `llm.clarifying_questions`: (LLM 호출이 있는 경우) 모호성 여부 판단 지표

**주의사항(현실적 제약)**
- `node_timings.*.output_snapshot`은 직렬화/크기 제한이 있으며(대략 2KB 내), 값이 큰 경우 문자열로 축약될 수 있습니다.
- "사용자 만족" 신호(thumbs up/down, 별점 등)는 현재 로그에 없으므로 Phase 2의 선별 로직에서 사용 불가합니다.

### 2.2. 데이터셋 구축 자동화 계획
로그 데이터를 학습 데이터 포맷으로 변환하는 전처리 스크립트를 작성할 예정입니다.

추출 대상은 우선 "실제 런타임에서 생성된 시스템 출력"(Rule/Hybrid 결과)을 기본 라벨로 삼고,
추가적으로 별도의 오프라인 라벨링 단계에서 LLM Teacher(GPT-4o/Sonnet 등)를 통해 보강 라벨을 생성하는 방향이 안전합니다.

**데이터셋 포맷 예시 (Classification):**
```json
{
  "instruction": "Classify the user query into 'dispute', 'general', 'law', 'system'.",
  "input": "환불이 안 된다는데 법적으로 어떻게 되나요?",
  "output": "law"
}
```

**데이터셋 포맷 예시 (Query Rewriting):**
```json
{
  "instruction": "Rewrite the query for better search retrieval.",
  "input": "그거 샀는데 고장났어 돈 줘",
  "output": "제품 고장 환불 요청"
}
```

## 3. 실행 로드맵 (Roadmap)

### Phase 1: 하이브리드 운영 & 데이터 축적 (현재 ~ 1개월)
- PR 2 (Hybrid Analysis) 적용 후 실제 운영.
- **Goal**: 1,000건 이상의 실제 사용자 쿼리 및 시스템 처리 로그 확보.
- 이 기간 동안에는 "운영 로그 기반 데이터셋"을 확보하는 것이 우선이며,
  Teacher 라벨(정답 라벨)은 "운영 중 실시간 생성"이 아니라 "오프라인 재라벨링"(비용/안전/재현성 측면)으로 확보하는 방향을 권장.

**Phase 1 체크포인트(추가)**
- `session_id`가 로그에 안정적으로 포함되도록(프론트 → 백엔드 전달) 운영 환경에서 확인
- 개인정보/민감정보(연락처, 계좌, 주소 등) 제거/마스킹 정책 정의 후 데이터셋 생성

### Phase 2: 데이터 정제 및 실험 (1개월 ~ 2개월)
- 수집된 로그 중 `confidence`가 높거나, (가능한 경우) 동일 `session_id` 내 재질문/재시도 징후가 없는 케이스를 우선 선별.
  - NOTE: 현재 "Thumbs up" 필드는 없으므로, 만족도는 '간접 지표'로만 근사 가능합니다.
- 오픈 소스 SLM (EXAONE 2.4B, Llama-3-8B) 대상 LoRA Fine-Tuning 실험 진행.
- 기존 Rule-based 시스템과 성능 비교 (Offline Evaluation).

### Phase 3: 모델 교체 및 배포 (3개월 차)
- 검증된 Fine-Tuned 모델을 `query_analysis` 노드에 탑재.
- Latency 목표는 배포 환경(CPU/GPU, 양자화 수준)에 크게 의존하므로, 우선 "p50 50ms 내"(GPU 기준) 같은 현실적인 SLO로 조정 후 측정 기반으로 최적화.

## 4. Action Items (for this PR)
본 PR에서는 Phase 1을 위한 준비 작업을 수행합니다.
1. `backend/scripts/data/` 디렉토리 생성.
2. `collect_training_data.py`: `logs/rag/` 하위의 JSON 로그를 파싱하여 CSV/JSONL 데이터셋으로 변환하는 스크립트 작성.
3. 데이터 수집 가이드라인 문서 작성 (`docs/data_collection_guide.md`).

### 4.1. (추가) Action Items 보완 (권장)

운영 환경에서 바로 유용한 데이터셋을 만들기 위해 아래 항목을 계획에 포함하는 것을 권장합니다.

- (A) 데이터셋 생성 시 마스킹/필터링 규칙 포함 (PII 제거)
- (B) `query_analysis` 출력 스냅샷이 축약되지 않는지 샘플 로그로 검증
- (C) 만족도/정답 라벨 확보 전략 명시
  - 1차: 시스템 출력(현행 Rule/Hybrid) 기반
  - 2차: 오프라인 Teacher 라벨링(샘플링 + 비용 통제)
