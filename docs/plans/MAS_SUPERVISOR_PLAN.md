# MAS Supervisor Architecture 전환 계획

**작성일**: 2026-01-26  
**목표**: 현재 State Machine + ReAct Loop 구조를 진정한 Multi-Agent System (Supervisor Pattern)으로 전환

---

## 1. 현재 vs 목표 아키텍처

### 1.1 현재 구조 (State Machine)

```
User Query
    ↓
[InputGuard] → [QueryAnalysis] → [Routing Function] → [ReAct Loop] → [Generation] → [Review] → [OutputGuard]
                                        ↓
                              규칙 기반 if/else 분기
                              (NO_RETRIEVAL / NEED_RAG / NEED_CLARIFY)
```

**문제점**:
- 중앙 관제자 없음 (라우팅이 함수로 분산)
- 에이전트 간 통신 없음 (State 공유만)
- 동적 재시도/수정 불가 (고정된 패턴)
- 단일 Retrieval 노드 (병렬 검색 불가)

### 1.2 목표 구조 (MAS Supervisor)

```
User Query
    ↓
[InputGuard]
    ↓
┌─────────────────────────────────────────────────────────────────┐
│                      [SUPERVISOR]                                │
│                      (Central Brain)                             │
│                                                                  │
│  "나는 중앙 관제자다. 에이전트들에게 태스크를 배분하고           │
│   결과를 종합하여 최종 판단한다."                                │
│                                                                  │
│  상태: 대기 → 분석요청 → 검색요청 → 초안요청 → 검토요청 → 완료   │
└─────────────────────────────────────────────────────────────────┘
         ↓               ↓               ↓               ↓
    [Query         [Retrieval      [Answer        [Legal
     Analyst]       Team]           Drafter]       Reviewer]
         ↑               ↑               ↑               ↑
         └───────────────┴───────────────┴───────────────┘
                              ↓
                    결과 보고 → Supervisor로 복귀
```

---

## 2. 시스템 구조 변경 개요

### 2.1 변경 범위

| 영역 | 현재 | 변경 후 | 변경 규모 |
|------|------|---------|----------|
| **Graph 구조** | Linear + ReAct Loop | Hub-Spoke (Supervisor 중심) | **Major** |
| **라우팅** | 규칙 함수 (`_route_*`) | Supervisor LLM 판단 | **Major** |
| **에이전트** | 노드 함수 | 독립 Agent 클래스 | **Major** |
| **통신** | State 공유 | Message 교환 | **Major** |
| **Retrieval** | 단일 노드 | 4개 Agent (병렬) | **Major** |
| **State** | ChatState | SupervisorState 확장 | **Medium** |

### 2.2 변경하지 않는 부분

| 컴포넌트 | 이유 |
|----------|------|
| Guardrail 노드 | 입출력 필터링은 그대로 유지 |
| Checkpointer | 세션 저장 로직 유지 |
| API 엔드포인트 | `/chat`, `/chat/stream` 인터페이스 유지 |
| 기존 Retriever 클래스 | Agent 내부에서 재사용 |

---

## 3. 단계별 구현 계획

### Phase 1: State 스키마 확장

**목표**: Supervisor ↔ Agent 통신을 위한 State 확장

#### 3.1.1 새로운 State 필드

```python
# backend/app/orchestrator/state/supervisor.py (신규)

class AgentMessage(TypedDict):
    """Supervisor ↔ Agent 간 메시지"""
    from_agent: str          # 발신자 (supervisor, query_analyst, ...)
    to_agent: str            # 수신자
    message_type: str        # request, response, error
    content: Dict[str, Any]  # 실제 페이로드
    timestamp: float

class SupervisorState(TypedDict):
    """Supervisor 전용 상태"""
    current_phase: str                    # analyzing, retrieving, drafting, reviewing, done
    agent_messages: List[AgentMessage]    # 통신 기록
    pending_tasks: List[str]              # 대기 중인 태스크
    completed_tasks: List[str]            # 완료된 태스크
    supervisor_reasoning: str             # Supervisor의 현재 판단 근거
    next_agent: Optional[str]             # 다음 호출할 Agent
```

#### 3.1.2 ChatState 확장

```python
# ChatState에 SupervisorState 필드 추가
class ChatState(MessagesState):
    # ... 기존 필드 ...
    
    # === Supervisor 확장 ===
    supervisor: Optional[SupervisorState]
```

#### 3.1.3 파일 구조

```
backend/app/orchestrator/state/
├── __init__.py          # SupervisorState export 추가
├── supervisor.py        # (신규) Supervisor 전용 상태
└── ... (기존 파일 유지)
```

---

### Phase 2: Agent 프로토콜 정의

**목표**: 모든 Agent가 따르는 공통 인터페이스 정의

#### 3.2.1 Agent 기본 프로토콜

```python
# backend/app/agents/base.py (신규)

from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAgent(ABC):
    """모든 Agent의 기본 클래스"""
    
    agent_name: str           # 고유 식별자
    agent_description: str    # Supervisor가 참조할 설명
    required_inputs: list     # 필요한 입력 필드
    provided_outputs: list    # 제공하는 출력 필드
    
    @abstractmethod
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Supervisor로부터 요청을 받아 처리
        
        Args:
            request: Supervisor가 보낸 요청
                - task: 수행할 태스크
                - context: 필요한 컨텍스트
                
        Returns:
            response: Supervisor에게 보낼 응답
                - status: success / failure / need_more_info
                - result: 처리 결과
                - message: Supervisor에게 보고할 메시지
        """
        pass
    
    def report_to_supervisor(self, status: str, result: Any, message: str) -> Dict:
        """Supervisor에게 결과 보고 형식 생성"""
        return {
            "from_agent": self.agent_name,
            "status": status,
            "result": result,
            "message": message,
        }
```

#### 3.2.2 Agent 응답 표준

```python
# 성공 응답
{
    "from_agent": "query_analyst",
    "status": "success",
    "result": {
        "intent": "환불 가능 여부 문의",
        "entities": {"item": "노트북", "period": "2주"},
        "query_type": "dispute",
    },
    "message": "분석 완료. 노트북 환불 관련 분쟁 질의입니다."
}

# 실패 응답
{
    "from_agent": "retrieval_law",
    "status": "failure",
    "result": None,
    "message": "검색 결과 없음. 다른 키워드로 재시도 권장."
}

# 추가 정보 필요
{
    "from_agent": "query_analyst",
    "status": "need_more_info",
    "result": None,
    "message": "구매처 정보가 필요합니다. 사용자에게 질문해주세요."
}
```

---

### Phase 3: Supervisor 노드 구현

**목표**: 중앙 관제자 역할을 하는 Supervisor 노드 구현

#### 3.3.1 Supervisor 역할 정의

```
Supervisor는 다음을 수행한다:

1. 현재 상태 분석
   - 어떤 정보가 있는가?
   - 무엇이 부족한가?
   
2. 다음 행동 결정
   - 어떤 Agent를 호출할 것인가?
   - 무엇을 요청할 것인가?
   
3. Agent 결과 평가
   - 결과가 충분한가?
   - 재시도가 필요한가?
   
4. 최종 판단
   - 사용자에게 응답할 준비가 되었는가?
   - Clarification이 필요한가?
```

#### 3.3.2 Supervisor 노드 구조

```python
# backend/app/orchestrator/nodes/supervisor.py (신규)

class SupervisorNode:
    """
    MAS 중앙 관제자
    
    LLM을 사용하여 다음 행동을 동적으로 결정
    """
    
    def __init__(self, llm):
        self.llm = llm  # 30B 모델
        self.available_agents = {
            "query_analyst": "질문 분석 및 의도 파악",
            "retrieval_law": "법령 검색",
            "retrieval_criteria": "분쟁조정기준 검색",
            "retrieval_case": "분쟁사례 검색",
            "retrieval_counsel": "상담사례 검색",
            "answer_drafter": "답변 초안 작성",
            "legal_reviewer": "법적 정확성 검토",
        }
    
    async def decide_next_action(self, state: ChatState) -> Dict:
        """
        현재 상태를 분석하고 다음 행동 결정
        
        Returns:
            {
                "action": "call_agent" | "respond" | "clarify",
                "target_agent": "agent_name" (if call_agent),
                "request": {...} (if call_agent),
                "response": "..." (if respond or clarify),
                "reasoning": "판단 근거",
            }
        """
        prompt = self._build_decision_prompt(state)
        response = await self.llm.generate(prompt)
        return self._parse_decision(response)
    
    def _build_decision_prompt(self, state: ChatState) -> str:
        """
        Supervisor 판단을 위한 프롬프트 생성.
        
        보안 고려사항:
        - 사용자 입력은 반드시 sanitize 후 삽입
        - 입력 길이 제한 (500자)
        - Instruction injection 패턴 필터링
        """
        # 사용자 입력 sanitize
        user_query = self._sanitize_user_input(state.get('user_query', ''))
        
        return f"""당신은 소비자 분쟁 해결 시스템의 중앙 관제자(Supervisor)입니다.

## 현재 상태
- 사용자 질문: {user_query}
- 완료된 태스크: {state.get('supervisor', {}).get('completed_tasks', [])}
- 수집된 정보:
  - 질의 분석: {state.get('query_analysis')}
  - 검색 결과: {state.get('retrieval')}
  - 답변 초안: {state.get('draft_answer')}
  - 검토 결과: {state.get('review')}

## 사용 가능한 Agent
{self._format_agents()}

## 지시사항
현재 상태를 분석하고, 다음 중 하나를 선택하세요:

1. Agent 호출: 추가 정보가 필요한 경우
2. 사용자 응답: 충분한 정보로 답변 가능한 경우
3. Clarification: 사용자에게 추가 질문이 필요한 경우

## 출력 형식 (JSON)
{{
    "action": "call_agent" | "respond" | "clarify",
    "target_agent": "agent_name",  // action이 call_agent인 경우
    "request": {{}},               // agent에게 보낼 요청
    "reasoning": "판단 근거"
}}
"""
    
    def _sanitize_user_input(self, text: str) -> str:
        """
        사용자 입력 sanitize (Prompt Injection 방지).
        
        처리 항목:
        1. 길이 제한 (500자)
        2. 위험 패턴 마스킹 (instruction override 시도)
        3. 특수 문자 이스케이프
        
        Returns:
            sanitized text
        """
        if not text:
            return ""
        
        # 1. 길이 제한
        text = text[:500]
        
        # 2. 위험 패턴 마스킹 (instruction override 시도 차단)
        dangerous_patterns = [
            'ignore',           # "ignore previous instructions"
            'disregard',        # "disregard all rules"
            'forget',           # "forget your instructions"
            'instead',          # "instead do this"
            'pretend',          # "pretend you are"
            'act as',           # "act as a different AI"
            'new instruction',  # "here is your new instruction"
            '시스템 프롬프트',    # Korean: "system prompt"
            '지시를 무시',       # Korean: "ignore instructions"
        ]
        
        sanitized = text
        for pattern in dangerous_patterns:
            # 대소문자 무시 치환
            sanitized = re.sub(
                re.escape(pattern),
                f'[{pattern}]',
                sanitized,
                flags=re.IGNORECASE
            )
        
        # 3. 연속된 특수문자 제거 (프롬프트 구조 파괴 시도 방지)
        sanitized = re.sub(r'#{3,}', '##', sanitized)  # ### → ##
        sanitized = re.sub(r'-{3,}', '--', sanitized)  # --- → --
        
        return sanitized
```

#### 3.3.3 Supervisor 의사결정 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                    Supervisor Decision Flow                      │
└─────────────────────────────────────────────────────────────────┘

상태 진입
    │
    ▼
┌─────────────────┐
│ 현재 상태 분석   │ ← query_analysis? retrieval? draft? review?
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 질의 분석 없음?  │────▶│ Query Analyst   │
└────────┬────────┘ Yes  │ 호출            │
         │ No            └─────────────────┘
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 검색 필요?       │────▶│ Retrieval Team  │
└────────┬────────┘ Yes  │ 호출 (병렬)     │
         │ No            └─────────────────┘
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 검색 품질 충분?  │────▶│ 재검색 요청     │
└────────┬────────┘ No   │ (다른 쿼리로)   │
         │ Yes           └─────────────────┘
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 초안 없음?       │────▶│ Answer Drafter  │
└────────┬────────┘ Yes  │ 호출            │
         │ No            └─────────────────┘
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 검토 없음?       │────▶│ Legal Reviewer  │
└────────┬────────┘ Yes  │ 호출            │
         │ No            └─────────────────┘
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 검토 통과?       │────▶│ 수정 요청       │
└────────┬────────┘ No   │ → Answer Drafter│
         │ Yes           └─────────────────┘
         ▼
┌─────────────────┐
│ 사용자에게 응답  │
└─────────────────┘
```

#### 3.3.4 오류 처리 및 Fallback

Supervisor는 LLM 기반이므로 다양한 실패 모드에 대한 완화 방안이 필수입니다.

| 실패 모드 | 완화 방안 | 구현 위치 |
|----------|----------|----------|
| LLM 호출 타임아웃 (>5s) | 규칙 기반 fallback 즉시 전환 | `decide_next_action()` |
| LLM JSON 파싱 실패 | 재시도 1회 후 규칙 기반 fallback | `_parse_decision()` |
| 무한 루프 (>10회 Supervisor 호출) | 강제 종료 + 부분 결과 응답 | `decide_next_action()` |
| Agent 응답 실패 | 해당 Agent 스킵, 다음 단계 진행 | `supervisor_router()` |
| 모든 Retrieval 실패 | clarify 응답으로 전환 | `decide_next_action()` |

```python
# backend/app/orchestrator/nodes/supervisor.py

MAX_SUPERVISOR_ITERATIONS = 10
LLM_TIMEOUT_SECONDS = 5.0
MAX_JSON_PARSE_RETRIES = 1

class SupervisorNode:
    async def decide_next_action(self, state: ChatState) -> Dict:
        """
        현재 상태를 분석하고 다음 행동 결정.
        
        Fallback 체인:
        1. LLM 판단 시도
        2. 타임아웃/파싱 실패 시 규칙 기반 fallback
        3. 무한 루프 감지 시 강제 종료
        """
        # 무한 루프 방지
        iteration = state.get("supervisor", {}).get("iteration_count", 0)
        if iteration >= MAX_SUPERVISOR_ITERATIONS:
            logger.warning(f"Max iterations ({MAX_SUPERVISOR_ITERATIONS}) reached, forcing respond")
            return self._fallback_respond(state)
        
        # LLM 판단 시도 (타임아웃 적용)
        try:
            prompt = self._build_decision_prompt(state)
            response = await asyncio.wait_for(
                self.llm.generate(prompt),
                timeout=LLM_TIMEOUT_SECONDS
            )
            return self._parse_decision_with_retry(response)
        except asyncio.TimeoutError:
            logger.warning("LLM timeout, falling back to rule-based")
            return self._rule_based_fallback(state)
        except Exception as e:
            logger.error(f"Supervisor decision failed: {e}")
            return self._rule_based_fallback(state)
    
    def _parse_decision_with_retry(self, response: str, retries: int = 0) -> Dict:
        """JSON 파싱 실패 시 재시도 후 규칙 기반 전환"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            if retries < MAX_JSON_PARSE_RETRIES:
                # 재시도: 마크다운 코드 블록 제거 후 파싱
                cleaned = re.sub(r'```json?\n?|\n?```', '', response).strip()
                return self._parse_decision_with_retry(cleaned, retries + 1)
            logger.warning("JSON parse failed after retry, using rule-based")
            return {"action": "rule_based_fallback", "reasoning": "JSON parse failure"}
    
    def _rule_based_fallback(self, state: ChatState) -> Dict:
        """규칙 기반 의사결정 (LLM 실패 시 사용)"""
        supervisor = state.get("supervisor", {})
        completed = supervisor.get("completed_tasks", [])
        
        if "query_analysis" not in completed:
            return {"action": "call_agent", "target_agent": "query_analyst", "reasoning": "Rule-based: need query analysis"}
        if "retrieval" not in completed:
            return {"action": "call_agent", "target_agent": "retrieval_team", "reasoning": "Rule-based: need retrieval"}
        if "draft" not in completed:
            return {"action": "call_agent", "target_agent": "answer_drafter", "reasoning": "Rule-based: need draft"}
        if "review" not in completed:
            return {"action": "call_agent", "target_agent": "legal_reviewer", "reasoning": "Rule-based: need review"}
        return {"action": "respond", "reasoning": "Rule-based: all tasks complete"}
    
    def _fallback_respond(self, state: ChatState) -> Dict:
        """강제 종료 시 부분 결과 응답"""
        return {
            "action": "respond",
            "reasoning": "Max iterations reached - returning partial result",
            "partial": True
        }
```

---

### Phase 4: Agent 구현

**목표**: 기존 노드 함수를 독립 Agent 클래스로 전환
**Retrieval Agent 전략**: 데이터 성격이 상이하므로 4개의 독립된 Retrieval Agent로 분리하여 각 데이터셋(법령, 기준, 사례, 상담)에 최적화된 RAG 전략을 수립합니다.

#### 3.4.1 Agent 목록

| Agent | 기반 코드 | LLM | 역할 |
|-------|----------|-----|------|
| QueryAnalystAgent | `query_analysis_node` | 7B | 질문 분석, 의도 파악 |
| LawRetrievalAgent | `retrieval_node` 일부 | 2.4B | 법령 검색 + 쿼리 재작성 |
| CriteriaRetrievalAgent | `retrieval_node` 일부 | 2.4B | 기준 검색 + 쿼리 재작성 |
| CaseRetrievalAgent | `retrieval_node` 일부 | 2.4B | 사례 검색 + 쿼리 재작성 |
| CounselRetrievalAgent | `retrieval_node` 일부 | 2.4B | 상담 검색 + 쿼리 재작성 |
| AnswerDrafterAgent | `generation_node` | 30B | 답변 초안 생성 |
| LegalReviewerAgent | `review_node` | 32B | 법적 정확성 검토 |

#### 3.4.2 파일 구조

```
backend/app/agents/
├── base.py                    # (신규) BaseAgent 정의
├── query_analyst/
│   ├── __init__.py
│   └── agent.py               # (수정) QueryAnalystAgent 클래스
├── retrieval/
│   ├── __init__.py
│   ├── law_agent.py           # (신규) LawRetrievalAgent
│   ├── criteria_agent.py      # (신규) CriteriaRetrievalAgent
│   ├── case_agent.py          # (신규) CaseRetrievalAgent
│   ├── counsel_agent.py       # (신규) CounselRetrievalAgent
│   └── tools/                 # (유지) 기존 Retriever 클래스들
├── answer_drafter/
│   ├── __init__.py
│   └── agent.py               # (수정) AnswerDrafterAgent 클래스
├── legal_reviewer/
│   ├── __init__.py
│   └── agent.py               # (수정) LegalReviewerAgent 클래스
└── protocols.py               # (수정) Agent 프로토콜 추가
```

#### 3.4.3 Agent 구현 예시 (QueryAnalystAgent)

```python
# backend/app/agents/query_analyst/agent.py

class QueryAnalystAgent(BaseAgent):
    agent_name = "query_analyst"
    agent_description = "사용자 질문을 분석하여 의도, 엔티티, 쿼리 유형을 파악합니다."
    required_inputs = ["user_query"]
    provided_outputs = ["intent", "entities", "query_type", "confidence"]
    
    def __init__(self, llm):
        self.llm = llm  # 7B 모델
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        user_query = request["context"]["user_query"]
        
        # 기존 query_analysis_node 로직 재사용
        result = await self._analyze_query(user_query)
        
        return self.report_to_supervisor(
            status="success",
            result=result,
            message=f"분석 완료. 유형: {result['query_type']}, 의도: {result['intent']}"
        )
    
    async def _analyze_query(self, query: str) -> Dict:
        # 기존 로직 재사용
        ...
```

---

### Phase 5: Graph 재설계

**목표**: Supervisor 중심 Hub-Spoke 구조로 Graph 재설계

#### 3.5.1 새로운 Graph 구조

```python
# backend/app/orchestrator/graph.py (전면 수정)

def create_mas_supervisor_graph() -> StateGraph:
    """
    MAS Supervisor Pattern Graph
    
    Hub-Spoke 구조:
    - Supervisor가 중앙 Hub
    - 각 Agent가 Spoke
    - 모든 Agent는 Supervisor로 복귀
    """
    graph = StateGraph(ChatState)
    
    # 노드 등록
    graph.add_node("input_guardrail", input_guardrail_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("query_analyst", query_analyst_agent.as_node())
    graph.add_node("retrieval_team", retrieval_team_node)  # Fan-out 처리
    graph.add_node("answer_drafter", answer_drafter_agent.as_node())
    graph.add_node("legal_reviewer", legal_reviewer_agent.as_node())
    graph.add_node("output_guardrail", output_guardrail_node)
    
    # 진입점
    graph.set_entry_point("input_guardrail")
    
    # input_guardrail → supervisor
    graph.add_conditional_edges(
        "input_guardrail",
        lambda s: END if s.get("guardrail_blocked") else "supervisor"
    )
    
    # supervisor → 동적 라우팅 (LLM 판단)
    graph.add_conditional_edges(
        "supervisor",
        supervisor_router,  # LLM이 결정
        {
            "query_analyst": "query_analyst",
            "retrieval_team": "retrieval_team",
            "answer_drafter": "answer_drafter",
            "legal_reviewer": "legal_reviewer",
            "output_guardrail": "output_guardrail",  # 완료
        }
    )
    
    # 모든 Agent → supervisor로 복귀
    for agent in ["query_analyst", "retrieval_team", "answer_drafter", "legal_reviewer"]:
        graph.add_edge(agent, "supervisor")
    
    # output_guardrail → END
    graph.add_edge("output_guardrail", END)
    
    return graph


def supervisor_router(state: ChatState) -> str:
    """
    Supervisor의 결정을 기반으로 다음 노드 결정
    
    Note: 이 함수는 supervisor_node에서 설정한 next_agent를 읽음
    """
    supervisor = state.get("supervisor", {})
    next_agent = supervisor.get("next_agent")
    
    if next_agent == "respond":
        return "output_guardrail"
    
    return next_agent or "output_guardrail"
```

#### 3.5.2 Retrieval Team (Fan-out 처리)

```python
# backend/app/orchestrator/nodes/retrieval_team.py (신규)

async def retrieval_team_node(state: ChatState) -> Dict:
    """
    4개 Retrieval Agent 병렬 실행
    
    Supervisor 요청에 따라 필요한 Agent만 호출
    """
    request = state["supervisor"]["current_request"]
    sources_to_search = request.get("sources", ["law", "criteria", "case", "counsel"])
    
    # 병렬 실행
    tasks = []
    if "law" in sources_to_search:
        tasks.append(law_agent.process(request))
    if "criteria" in sources_to_search:
        tasks.append(criteria_agent.process(request))
    if "case" in sources_to_search:
        tasks.append(case_agent.process(request))
    if "counsel" in sources_to_search:
        tasks.append(counsel_agent.process(request))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 결과 병합
    merged = merge_retrieval_results(results)
    
    # Supervisor에게 보고
    return {
        "retrieval": merged,
        "supervisor": {
            **state.get("supervisor", {}),
            "completed_tasks": state["supervisor"]["completed_tasks"] + ["retrieval"],
        }
    }
```

#### 3.5.3 Graph 시각화

```
                                    ┌─────────────┐
                                    │   START     │
                                    └──────┬──────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │ InputGuard  │
                                    └──────┬──────┘
                                           │
                                           ▼
                              ┌────────────────────────┐
                              │                        │
                              │      SUPERVISOR        │◄─────────────────┐
                              │                        │                  │
                              └───────────┬────────────┘                  │
                                          │                               │
                    ┌─────────────────────┼─────────────────────┐        │
                    │                     │                     │        │
                    ▼                     ▼                     ▼        │
             ┌────────────┐       ┌────────────┐       ┌────────────┐   │
             │  Query     │       │ Retrieval  │       │  Answer    │   │
             │  Analyst   │       │   Team     │       │  Drafter   │   │
             └─────┬──────┘       └─────┬──────┘       └─────┬──────┘   │
                   │                    │                    │          │
                   │              ┌─────┴─────┐              │          │
                   │              │           │              │          │
                   │           ┌──┴──┐     ┌──┴──┐           │          │
                   │           │Law  │     │Case │           │          │
                   │           │Agent│     │Agent│           │          │
                   │           └──┬──┘     └──┬──┘           │          │
                   │              │           │              │          │
                   └──────────────┴─────┬─────┴──────────────┘          │
                                        │                               │
                                        └───────────────────────────────┘
                                                      │
                                                      ▼
                                               ┌────────────┐
                                               │   Legal    │
                                               │  Reviewer  │
                                               └─────┬──────┘
                                                     │
                                                     ▼
                                               ┌────────────┐
                                               │OutputGuard │
                                               └─────┬──────┘
                                                     │
                                                     ▼
                                               ┌─────────────┐
                                               │     END     │
                                               └─────────────┘
```

---

### Phase 6: 통합 및 테스트

**목표**: 새로운 MAS 구조 통합 및 검증

#### 3.6.1 테스트 전략

| 테스트 유형 | 검증 대상 | 파일 |
|------------|----------|------|
| Unit | 각 Agent 독립 동작 | `test_agents/*.py` |
| Unit | Supervisor 의사결정 | `test_supervisor.py` |
| Integration | Agent 간 통신 | `test_agent_communication.py` |
| Integration | 전체 Graph 흐름 | `test_mas_graph.py` |
| E2E | 실제 질의 처리 | `test_e2e_queries.py` |

##### Supervisor 상세 테스트 케이스

| 테스트 함수 | 검증 항목 | 마커 |
|------------|----------|------|
| `test_supervisor_timeout_fallback` | LLM 타임아웃 시 규칙 기반 fallback 전환 | `unit` |
| `test_supervisor_json_parse_fallback` | JSON 파싱 실패 시 재시도 후 fallback | `unit` |
| `test_supervisor_max_iteration_limit` | 10회 초과 시 강제 종료 및 부분 결과 반환 | `unit` |
| `test_supervisor_handles_agent_failure` | Agent 실패 시 스킵 후 다음 단계 진행 | `unit` |
| `test_supervisor_rule_based_order` | 규칙 기반 fallback 순서 검증 (분석→검색→초안→검토) | `unit` |
| `test_supervisor_llm_decision_call_agent` | LLM이 "call_agent" 반환 시 올바른 Agent 호출 | `unit`, `llm` |
| `test_supervisor_llm_decision_respond` | LLM이 "respond" 반환 시 output_guardrail로 이동 | `unit`, `llm` |
| `test_supervisor_llm_decision_clarify` | LLM이 "clarify" 반환 시 사용자 질문 생성 | `unit`, `llm` |
| `test_supervisor_input_sanitization` | 사용자 입력 sanitize 동작 검증 | `unit` |
| `test_supervisor_agent_message_logging` | Agent 응답이 agent_messages에 기록 | `integration` |
| `test_supervisor_retrieval_team_parallel` | 4개 Retrieval Agent 병렬 호출 확인 | `integration` |
| `test_supervisor_hub_spoke_graph_structure` | Hub-Spoke 그래프 구조 검증 | `integration` |

```python
# backend/scripts/testing/orchestrator/test_supervisor.py 예시

class TestSupervisorFallback:
    """Supervisor 실패 모드 테스트"""
    
    @pytest.mark.unit
    async def test_supervisor_timeout_fallback(self, mock_llm_timeout):
        """LLM 타임아웃 시 규칙 기반 fallback 전환"""
        supervisor = SupervisorNode(llm=mock_llm_timeout)
        state = {"user_query": "환불 가능한가요?", "supervisor": {"completed_tasks": []}}
        
        result = await supervisor.decide_next_action(state)
        
        assert result["action"] == "call_agent"
        assert result["target_agent"] == "query_analyst"
        assert "Rule-based" in result["reasoning"]
    
    @pytest.mark.unit
    async def test_supervisor_max_iteration_limit(self):
        """10회 초과 시 강제 종료"""
        supervisor = SupervisorNode(llm=Mock())
        state = {"supervisor": {"iteration_count": 10}}
        
        result = await supervisor.decide_next_action(state)
        
        assert result["action"] == "respond"
        assert result.get("partial") is True
    
    @pytest.mark.unit
    def test_supervisor_json_parse_fallback(self, mock_llm_invalid_json):
        """JSON 파싱 실패 시 재시도 후 fallback"""
        supervisor = SupervisorNode(llm=mock_llm_invalid_json)
        
        result = supervisor._parse_decision_with_retry("not valid json")
        
        assert result["action"] == "rule_based_fallback"
```

#### 3.6.2 마이그레이션 및 롤백 전략

##### Feature Flag 기반 점진적 전환

```python
# Feature Flag로 점진적 전환
# backend/.env

MAS_SUPERVISOR_ENABLED=false  # 초기값 (기존 그래프 사용)
MAS_SUPERVISOR_CANARY_PERCENT=0  # Canary 배포 비율 (0-100)

# graph.py에서 분기
def get_graph_for_chat_type(chat_type: str, session_id: str = None):
    if os.getenv("MAS_SUPERVISOR_ENABLED") == "true":
        return get_mas_supervisor_graph()
    
    # Canary 배포: 일부 트래픽만 새 그래프로 라우팅
    canary_percent = int(os.getenv("MAS_SUPERVISOR_CANARY_PERCENT", "0"))
    if canary_percent > 0 and session_id:
        # 세션 ID 해시 기반 일관된 라우팅
        if hash(session_id) % 100 < canary_percent:
            return get_mas_supervisor_graph()
    
    return get_unified_graph()  # 기존 그래프
```

##### 롤백 절차

| 단계 | 조건 | 조치 | 복구 시간 |
|------|------|------|----------|
| 1. 즉시 롤백 | 배포 직후 심각한 오류 | `MAS_SUPERVISOR_ENABLED=false` → 서버 재시작 | < 2분 |
| 2. Canary 중단 | Canary 모니터링 중 오류율 상승 | `MAS_SUPERVISOR_CANARY_PERCENT=0` | < 1분 |
| 3. 자동 롤백 | 5분간 오류율 > 5% | 모니터링 알림 → 자동 Canary 중단 | 자동 |

##### 롤백 명령어

```bash
# 즉시 롤백 (운영 환경)
export MAS_SUPERVISOR_ENABLED=false
docker compose restart backend

# Canary 중단
export MAS_SUPERVISOR_CANARY_PERCENT=0
# 재시작 불필요 (환경변수 실시간 읽기)

# 로그 확인
docker logs backend --tail 100 | grep -E "supervisor|fallback|error"
```

##### 배포 순서 (권장)

1. **Local 검증**: 모든 Unit/Integration 테스트 통과
2. **Staging 배포**: `MAS_SUPERVISOR_ENABLED=true` 전체 테스트
3. **Canary 배포**: `MAS_SUPERVISOR_CANARY_PERCENT=10` (10% 트래픽)
4. **모니터링**: 24시간 오류율/지연 시간 관찰
5. **점진적 확대**: 10% → 25% → 50% → 100%
6. **전체 전환**: `MAS_SUPERVISOR_ENABLED=true`

##### 자동 롤백 조건

```python
# backend/app/monitoring/supervisor_health.py

ROLLBACK_CONDITIONS = {
    "error_rate_threshold": 0.05,      # 5% 오류율 초과 시
    "latency_p99_threshold": 10.0,     # P99 지연 10초 초과 시
    "supervisor_loop_threshold": 5,    # 평균 Supervisor 호출 5회 초과 시
    "evaluation_window": 300,          # 5분 윈도우
}
```

---

## 4. 구현 우선순위

| 순서 | Phase | 작업 | 예상 공수 | 의존성 |
|------|-------|------|----------|--------|
| 1 | Phase 1 | State 스키마 확장 | 4h | 없음 |
| 2 | Phase 2 | Agent 프로토콜 정의 | 4h | Phase 1 |
| 3 | Phase 3 | Supervisor 노드 구현 | 8h | Phase 2 |
| 4 | Phase 4 | QueryAnalystAgent | 4h | Phase 2 |
| 5 | Phase 4 | 4x RetrievalAgent | 8h | Phase 2 |
| 6 | Phase 4 | AnswerDrafterAgent | 4h | Phase 2 |
| 7 | Phase 4 | LegalReviewerAgent | 4h | Phase 2 |
| 8 | Phase 5 | Graph 재설계 | 8h | Phase 3, 4 |
| 9 | Phase 6 | 통합 테스트 | 8h | Phase 5 |
| **총합** | | | **52h (~7일)** | |

---

## 5. LLM 배치

| Agent | 모델 | 역할 | 호출 빈도 |
|-------|------|------|----------|
| Supervisor | **30B** (Kanana) | 중앙 판단 | 매 턴 2-4회 |
| QueryAnalyst | **7B** (A.X Light) | 질문 분석 | 1회/요청 |
| LawRetrieval | **2.4B** (EXAONE) | 법령 쿼리 재작성 | 조건부 |
| CriteriaRetrieval | **2.4B** (EXAONE) | 기준 쿼리 재작성 | 조건부 |
| CaseRetrieval | **2.4B** (EXAONE) | 사례 쿼리 재작성 | 조건부 |
| CounselRetrieval | **2.4B** (EXAONE) | 상담 쿼리 재작성 | 조건부 |
| AnswerDrafter | **30B** (Kanana) | 답변 생성 | 1회/요청 |
| LegalReviewer | **32B** (EXAONE) | 법적 검토 | 조건부 |

---

## 6. 리스크 및 완화

| 리스크 | 영향 | 완화 방안 |
|--------|------|----------|
| Supervisor 판단 오류 | 잘못된 Agent 호출 | 규칙 기반 fallback + 최대 루프 제한 |
| Agent 응답 지연 | 전체 지연 증가 | 타임아웃 + 부분 결과 허용 |
| 병렬 실행 복잡도 | 디버깅 어려움 | 상세 로깅 + 분산 트레이싱 |
| 기존 코드 호환성 | 기존 테스트 실패 | Feature Flag + 점진적 전환 |

---

## 7. 성공 기준

| 기준 | 측정 방법 |
|------|----------|
| Supervisor가 동적으로 Agent 선택 | 로그에서 LLM 판단 근거 확인 |
| Agent 간 메시지 교환 | `agent_messages` 필드에 기록 |
| 재시도/수정 요청 동작 | 검색 부족 시 재검색, 검토 실패 시 수정 확인 |
| 병렬 검색 동작 | 4개 Agent 동시 호출 확인 |
| 기존 기능 유지 | E2E 테스트 통과 |

---

## 8. 다음 단계

1. **Phase 1 시작**: State 스키마 확장 (`supervisor.py` 작성)
2. **Phase 2 시작**: BaseAgent 클래스 정의 (`base.py` 작성)
3. 이후 Phase 순차 진행

---

## Appendix: 용어 정의

| 용어 | 정의 |
|------|------|
| **Supervisor** | 중앙 관제자. LLM을 사용하여 다음 행동을 동적으로 결정 |
| **Agent** | 특정 태스크를 수행하는 독립 모듈. Supervisor의 요청을 받아 처리 |
| **Hub-Spoke** | 중앙(Hub)에서 주변(Spoke)으로 연결되는 구조 |
| **Fan-out** | 하나의 요청이 여러 Agent로 분산되는 패턴 |
| **Fan-in** | 여러 Agent의 결과가 하나로 수렴되는 패턴 |
