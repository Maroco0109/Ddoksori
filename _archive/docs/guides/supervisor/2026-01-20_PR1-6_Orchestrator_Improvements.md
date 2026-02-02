# PR-1~6: 오케스트레이터 개선 사항

> 작성일: 2026-01-20
> 브랜치: feature/22-orchestrator
> 작성자: Claude Code

---

## 전체 진행 상태

| PR | 이름 | 상태 | 주요 변경 |
|----|------|------|----------|
| PR-1 | 버그 수정 | ✅ 완료 | `draft_answer` → `final_answer` |
| PR-2 | 통합 ReAct | ✅ 완료 | UnifiedGraph 단일 그래프 |
| PR-3 | 메모리/Compact | ✅ 완료 | 15턴 제한, 5턴 슬라이딩 윈도우 |
| PR-4 | Clarify | ✅ 완료 | 유사도 < 0.40 시 역질문 |
| PR-5 | SSE 실시간 상태 | ✅ 완료 | `graph.astream()` 기반 진행률 표시 |
| PR-6 | 답변 형식 개선 | ✅ 완료 | 3섹션 구조, 면책 문구 위치 변경 |

---

## PR-1: 버그 수정

### 문제
- 기존 코드에서 `draft_answer` 필드가 사용되었으나, 실제로는 `final_answer`를 사용해야 함

### 변경 사항
- 상태 필드명 통일: `draft_answer` → `final_answer`
- 관련 노드 및 라우팅 로직 수정

---

## PR-2: 통합 ReAct 그래프

### 목표
분쟁상담(`dispute`)과 일반채팅(`general`)을 단일 그래프로 처리

### 아키텍처
```
input_guardrail → query_analysis → [라우팅]
    ├─ NO_RETRIEVAL: generation → review → output_guardrail → END
    ├─ NEED_CLARIFICATION: ask_clarification → END
    └─ NEED_RAG: react_think ↔ react_act → generation → review → output_guardrail → END
```

### 주요 변경
| 파일 | 변경 내용 |
|------|----------|
| `orchestrator/graph.py` | `create_unified_chat_graph()` 함수 추가 |
| `orchestrator/state.py` | `UnifiedState` TypedDict 정의 |
| `orchestrator/routing.py` | `_route_unified_*` 라우팅 함수들 |

### 라우팅 모드
```python
class QueryMode(Enum):
    NO_RETRIEVAL = "no_retrieval"      # 일반 대화, RAG 불필요
    NEED_RAG = "need_rag"              # RAG 검색 필요
    NEED_CLARIFICATION = "clarify"     # 정보 부족, 역질문 필요
```

---

## PR-3: 메모리/Compact 시스템

### 목표
멀티턴 대화에서 컨텍스트 유지 및 토큰 효율화

### 핵심 메커니즘
1. **15턴 제한**: 최대 15턴까지 대화 유지
2. **5턴 슬라이딩 윈도우**: 최근 5턴만 전체 내용 유지
3. **Compact Summary**: 오래된 턴은 요약하여 저장

### 구현 파일
| 파일 | 내용 |
|------|------|
| `orchestrator/memory.py` | `ConversationMemory` 클래스 |
| `main.py` | `_session_memories` 세션별 메모리 저장소 |

### 메모리 구조
```python
class ConversationMemory:
    def __init__(self, chat_type: str, max_turns: int = 15, window_size: int = 5):
        self.chat_type = chat_type
        self.turns: List[ConversationTurn] = []
        self.compact_summary: Optional[str] = None
        self.max_turns = max_turns
        self.window_size = window_size
```

---

## PR-4: Clarify (역질문) 시스템

### 트리거 조건
1. **검색 유사도 < 0.40**: 관련 사례를 찾기 어려움
2. **품목명 불명확**: 브랜드/모델명만 있고 카테고리 없음 (예: "삼성" → "삼성 뭐요?")
3. **필수 정보 누락**: `purchase_item`, `dispute_details` 등

### 구현 파일
| 파일 | 내용 |
|------|------|
| `orchestrator/nodes/clarify.py` | `ask_clarification_node()` 함수 |
| `orchestrator/graph.py` | `ask_clarification` 노드 등록 |

### 역질문 예시
```python
CLARIFICATION_TEMPLATES = {
    'purchase_item': ["어떤 제품/서비스에 대한 문의인지 알려주시겠어요?"],
    'dispute_details': ["어떤 문제가 발생했는지 자세히 알려주시겠어요?"],
    'product_category': ["{item}은(는) 어떤 종류의 제품인가요?"],
    'low_similarity': ["질문을 좀 더 구체적으로 해주시면 더 정확한 답변을 드릴 수 있어요."],
}
```

---

## PR-5: SSE 실시간 상태 표시

### 목표
프론트엔드에서 "질의 분석중...", "정보 검색중..." 등 **실시간** 진행 상태 표시

### 구현 방식
LangGraph `graph.astream()` 네이티브 스트리밍 사용

### 백엔드 변경

#### NODE_LABELS (main.py)
```python
NODE_LABELS: Dict[str, tuple[str, int]] = {
    'input_guardrail': ('입력 검증중...', 5),
    'query_analysis': ('질의 분석중...', 15),
    'ask_clarification': ('추가 정보 요청중...', 20),
    'react_think': ('추론중...', 25),
    'react_act': ('정보 검색중...', 50),
    'generation': ('답변 생성중...', 80),
    'review': ('검토중...', 95),
    'output_guardrail': ('완료', 100),
}
```

#### SSE 이벤트 포맷
```typescript
type SSEEvent = {
  type: 'status' | 'complete' | 'error';
  data: {
    node?: string;       // "query_analysis"
    status?: string;     // "질의 분석중..."
    progress?: number;   // 0-100
    session_id?: string;
    answer?: string;
    sources?: Array<{type, title, similarity}>;
  };
}
```

#### /chat/stream 엔드포인트
```python
@app.post("/chat/stream")
async def chat_stream_sse(request: ChatRequest):
    async def event_generator():
        async for event in graph.astream(initial_state, config):
            node_name = list(event.keys())[0]
            label, progress = NODE_LABELS.get(node_name, ('처리중...', 0))
            yield f"data: {json.dumps({'type': 'status', 'data': {...}})}\n\n"

        yield f"data: {json.dumps({'type': 'complete', 'data': {...}})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 프론트엔드 변경

| 파일 | 내용 |
|------|------|
| `shared/types/chat.types.ts` | SSE 타입 정의 (`SSEEvent`, `StreamingState`) |
| `features/chat/hooks/useStreamingChat.ts` | SSE 스트리밍 훅 |
| `features/chat/components/StatusIndicator.tsx` | 진행 상태 UI 컴포넌트 |

#### useStreamingChat 훅 사용 예시
```typescript
const { streamingState, startStream, cancelStream } = useStreamingChat({
  onStatusUpdate: (status, progress, node) => {
    console.log(`${status}: ${progress}%`);
  },
  onComplete: (data) => {
    addMessage(data.answer);
  },
  onError: (error) => {
    showError(error);
  },
});

// 스트리밍 시작
await startStream({ message: '노트북 환불 문의' });
```

---

## PR-6: 답변 형식 개선

### 목표
답변 구조 변경: **유사 사례 → 법령/기준 → 추가 안내** (3섹션)

### 변경 전/후 비교

| 순서 | 변경 전 | 변경 후 |
|------|---------|---------|
| 1 | 추천 기관 | **유사 사례 분석** |
| 2 | 유사 사례 | **관련 법령 및 기준** |
| 3 | 관련 법령 | **추가 안내** (기관 정보) |
| 4 | 관련 기준 | _(제거, 섹션 2에 병합)_ |
| 면책문 | **맨 위** | **맨 아래** |

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `generator.py:26-31` | `STRUCTURED_SECTIONS` 상수 수정 |
| `generator.py:493-532` | `_get_structured_system_prompt()` |
| `generator.py:534-624` | `_build_structured_prompt()` |
| `generator.py:687-776` | `_generate_structured_stub()` |

### 새 STRUCTURED_SECTIONS
```python
STRUCTURED_SECTIONS = [
    "1. 유사 사례 분석",
    "2. 관련 법령 및 기준",
    "3. 추가 안내"
]
```

### 최종 답변 구조
```markdown
## 1. 유사 사례 분석
### 분쟁조정사례 (법적 효력 있음)
- [사례 제목] (출처: KCA, 2024-01-15)

### 상담사례 (참고용)
- [상담 제목]

## 2. 관련 법령 및 기준
### 관련 법령
- 소비자기본법 제XX조: ...

### 분쟁해결기준
- [품목] 기준: ...

## 3. 추가 안내
- 담당 기관: 한국소비자원
- 웹사이트: https://www.kca.go.kr

---
*본 답변은 정보 제공 목적이며 법률 자문이 아닙니다.*
```

---

## 핵심 파일 요약

### 백엔드
| 파일 | 라인 | 내용 |
|------|------|------|
| `main.py` | 38-49 | `NODE_LABELS` SSE 노드 라벨 |
| `main.py` | 479-605 | `/chat/stream` SSE 엔드포인트 |
| `orchestrator/graph.py` | 663-749 | `create_unified_chat_graph()` |
| `orchestrator/nodes/clarify.py` | 전체 | Clarify 노드 |
| `orchestrator/memory.py` | 전체 | 대화 메모리 시스템 |
| `generator.py` | 26-31 | `STRUCTURED_SECTIONS` |
| `generator.py` | 493-776 | 구조화 프롬프트 함수들 |

### 프론트엔드
| 파일 | 내용 |
|------|------|
| `shared/types/chat.types.ts` | SSE 타입 정의 |
| `features/chat/hooks/useStreamingChat.ts` | SSE 스트리밍 훅 |
| `features/chat/components/StatusIndicator.tsx` | 진행 상태 UI |

---

## 의존성 관계

```
PR-1 (버그수정)
    ↓
PR-2 (통합 ReAct)
    ↓
PR-3 (메모리) ─┬─ PR-4 (Clarify)
              │
              ↓
          PR-5 (SSE) ─→ PR-6 (답변형식)
```

---

## 테스트 검증

- ✅ 백엔드 Python syntax valid
- ✅ `NODE_LABELS` 정상 import
- ✅ PR-6 Stub 모드 응답 3섹션 구조 확인
- ✅ 면책 문구 답변 후반부 위치 확인
- ✅ 프론트엔드 TypeScript 빌드 성공
