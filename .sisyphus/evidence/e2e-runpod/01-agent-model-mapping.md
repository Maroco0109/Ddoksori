# 에이전트별 모델 할당 점검

## 1. 개요
현재 시스템(DDOKSORI MAS Supervisor)에서 각 에이전트가 사용하는 LLM 모델 및 클라이언트 매핑을 점검한 결과입니다. 시스템은 RunPod에서 호스팅되는 EXAONE 3.5 모델을 주력으로 사용하며, OpenAI(GPT-4o-mini)를 보조 및 검토용으로 활용하고 있습니다.

## 2. 에이전트-모델 매핑 테이블

| 에이전트 | 호출 경로 | 사용 모델/엔드포인트 | 주요 환경변수 | Fallback 체인 |
|---------|----------|-------------------|-------------|--------------|
| **Query Rewrite** | `query_analysis` -> `QueryRewriter` | EXAONE 3.5 (RunPod) | `QUERY_REWRITE_ENABLED`, `EXAONE_RUNPOD_URL` | LLM (EXAONE) → 규칙 기반 (사전 정의 매핑) |
| **Tool Calling** | `react_act` -> `ToolCallingClient` | EXAONE 3.5 (RunPod) | `USE_LLM_TOOLS`, `EXAONE_RUNPOD_URL` | LLM (EXAONE) → 규칙 기반 (ActionRegistry) |
| **Answer Generation** | `generation_node` -> `AnswerGenerationFallback` | GPT-4o-mini (OpenAI) | `LLM_MODEL` | GPT-4o-mini → Claude-3-Haiku → 규칙 기반 |
| **Legal Review** | `review_node` -> `HybridLegalReviewer` | GPT-4o-mini (OpenAI) | `ENABLE_LLM_REVIEW` | 규칙 기반 (Regex) → LLM (GPT-4o-mini) |
| **Ambiguity Check** | `query_analysis` -> `ExaoneLLMClient` | EXAONE 3.5 (RunPod) | `ENABLE_AMBIGUOUS_DETECTION` | LLM (EXAONE) → 보수적 RAG 진행 (False) |

## 3. 상세 매핑

### 3.1 Query Rewrite (질의 재작성)
- **호출 지점**: `backend/app/agents/query_analysis/agent.py` :: `_expand_query_by_type`
- **사용 env**: 
    1. `QUERY_REWRITE_ENABLED` (기본값: True)
    2. `QUERY_REWRITE_TIMEOUT` (기본값: 10000ms)
    3. `EXAONE_RUNPOD_URL` (RunPod 엔드포인트)
- **외부 엔드포인트**: `EXAONE_RUNPOD_URL` (vLLM OpenAI-compatible API)
- **성공 신호**: `[QueryRewriter] LLM rewrite in {elapsed}ms: ...`
- **실패/폴백 신호**: 
    - `[QueryRewriter] Timeout ({elapsed}ms > {timeout}ms), using rule-based`
    - `[QueryRewriter] LLM unavailable: {e}, using rule-based`
- **조건부 동작**: `is_complex_query` 함수를 통해 법률 용어 포함 여부, 길이(50자 초과), 격식체 여부를 판단하여 필요한 경우에만 LLM 호출.

### 3.2 Tool Calling (레거시 ReAct)
- **호출 지점**: `backend/app/agents/react/react_act.py` :: `HybridToolExecutor.execute`
- **사용 env**:
    1. `USE_LLM_TOOLS` (기본값: False)
    2. `LLM_TOOL_TIMEOUT_MS` (기본값: 5000ms)
    3. `EXAONE_RUNPOD_URL`
- **외부 엔드포인트**: `EXAONE_RUNPOD_URL`
- **성공 신호**: `[HybridToolExecutor] Tools bound successfully`
- **실패/폴백 신호**: `[HybridToolExecutor] LLM tool calling failed: {e}, falling back`
- **조건부 동작**: `USE_LLM_TOOLS`가 True이고 RunPod 서버가 가용할 때만 LLM 기반 도구 선택 시도.

### 3.3 Legal Review (법률 검토)
- **호출 지점**: `backend/app/agents/legal_review/llm_reviewer.py` :: `HybridLegalReviewer._llm_based_review`
- **사용 env**:
    1. `ENABLE_LLM_REVIEW` (기본값: False)
    2. `PROHIBITED_VIOLATION_THRESHOLD` (기본값: 3)
- **외부 엔드포인트**: OpenAI API (`gpt-4o-mini`)
- **성공 신호**: `[HybridLegalReviewer] initialized, enable_llm=True`
- **실패/폴백 신호**: `[llm_review] LLM review failed: {e}` (규칙 기반 결과만 사용)
- **조건부 동작**: 
    - `chat_type='general'`인 경우 검토 스킵 (Fast Path).
    - 규칙 기반 검토에서 심각한 위반(3건 이상) 발견 시 LLM 검토 스킵.

### 3.4 Answer Generation (답변 생성)
- **호출 지점**: `backend/app/agents/answer_generation/fallback.py` :: `AnswerGenerationFallback.generate_with_fallback`
- **사용 env**: `LLM_MODEL` (기본값: gpt-4o-mini)
- **외부 엔드포인트**: OpenAI API, Anthropic API
- **성공 신호**: `generation_model_used` 필드에 사용된 모델명 기록.
- **실패/폴백 신호**: `model_used`가 `rule_based` 또는 `safe_fallback`으로 설정됨.
- **조건부 동작**: `chat_type='general'`인 경우 규칙 기반 인사말 응답. 도메인 분류 결과 `is_restricted`인 경우 기관 안내 템플릿 응답.

## 4. 그래프 선택 및 조건부 동작
- **MAS_SUPERVISOR_ENABLED**: 현재 `graph_mas.py`가 기본 그래프로 사용됨 (Phase 7).
- **QUERY_REWRITE_ENABLED**: `query_analysis` 노드에서 LLM 재작성 사용 여부 결정.
- **USE_LLM_TOOLS**: ReAct 액션 노드에서 LLM 기반 도구 선택 사용 여부 결정.
- **chat_type**: 
    - `general`: 검색 및 검토 스킵 (Fast Path).
    - `dispute`: 전체 RAG 파이프라인 및 정밀 검토 수행.

## 5. Fallback 정책
1. **LLM 서버 장애 (RunPod)**: `ExaoneLLMClient` 및 `ToolCallingClient`에서 `health_check` 실패 시 즉시 규칙 기반(Rule-based) 로직으로 전환.
2. **LLM 타임아웃**: `QueryRewriter`는 10초(기본값) 타임아웃 적용 후 규칙 기반 폴백.
3. **답변 생성 장애**: OpenAI → Anthropic → 규칙 기반 템플릿 순으로 폴백 체인 가동.
4. **검토 장애**: LLM 검토 실패 시 규칙 기반(정규식) 검토 결과만 신뢰.

## 6. 참조 파일
- `backend/app/common/config.py`
- `backend/app/orchestrator/graph_mas.py`
- `backend/app/agents/query_analysis/agent.py`
- `backend/app/agents/answer_generation/agent.py`
- `backend/app/agents/legal_review/agent.py`
- `backend/app/llm/query_rewriter.py`
- `backend/app/llm/exaone_client.py`
- `backend/app/llm/tool_calling_client.py`
