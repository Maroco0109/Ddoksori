# 에이전트 레지스트리 모듈 (Agent Registry)

> **위치**: `backend/app/agents/registry/`
> **목적**: MAS 에이전트의 중앙 등록 및 생명주기 관리. Supervisor와 에이전트 구현체 간 결합도를 낮추는 레지스트리 패턴.

---

## 개요

Agent Registry는 Multi-Agent System(MAS)의 에이전트 메타데이터와 핸들러를 관리하는 **단일 진실 원천(SSOT)**입니다.

- **동적 에이전트 발견**: Supervisor가 런타임에 사용 가능한 에이전트를 조회
- **느슨한 결합**: Supervisor 코드 수정 없이 에이전트 추가/제거/비활성화 가능
- **프롬프트 생성**: LLM 의사결정을 위한 에이전트 설명 자동 생성

## 코드 구조

| 파일 | 설명 |
|------|------|
| `__init__.py` | 공개 API 내보내기 (`AgentRegistry`, `AgentInfo`, `AgentHandler`, `get_agent_registry`, `reset_agent_registry`) |
| `agent_registry.py` | 핵심 구현: 싱글톤 패턴, 기본 에이전트 등록 |

## 핵심 컴포넌트

### `AgentHandler` (Protocol)

```python
@runtime_checkable
class AgentHandler(Protocol):
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]: ...
```

구조적 서브타이핑 — `async def process()` 메서드만 있으면 상속 없이 에이전트 구현 가능.

### `AgentInfo` (Dataclass)

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `name` | `str` | 필수 | 고유 에이전트 식별자 |
| `description` | `str` | 필수 | Supervisor 프롬프트용 설명 |
| `handler` | `Optional[AgentHandler]` | `None` | 에이전트 구현체 |
| `category` | `str` | `"general"` | 분류 (analysis/retrieval/generation/review) |
| `required_inputs` | `List[str]` | `[]` | 필요한 ChatState 키 |
| `provided_outputs` | `List[str]` | `[]` | 생성하는 ChatState 키 |
| `priority` | `int` | `0` | 실행 우선순위 (높을수록 먼저) |
| `enabled` | `bool` | `True` | 활성화 여부 |

### `AgentRegistry` 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `register(...)` | 에이전트 등록 (이미 존재 시 덮어쓰기) |
| `unregister(name)` | 에이전트 제거 |
| `get(name)` | 메타데이터 조회 |
| `get_handler(name)` | 핸들러 인스턴스 반환 |
| `get_by_category(category)` | 카테고리별 조회 |
| `get_all(enabled_only)` | 전체 조회 (우선순위 정렬) |
| `get_for_prompt(enabled_only)` | Supervisor LLM 프롬프트용 `{name: description}` |
| `enable(name)` / `disable(name)` | 활성화/비활성화 토글 |

## 기본 등록 에이전트 (8개)

| 카테고리 | 이름 | 설명 | 우선순위 |
|----------|------|------|:--------:|
| analysis | `query_analyst` | 질문 분석 및 의도 파악 | 100 |
| retrieval | `retrieval_team` | 병렬 검색 (모든 소스) | 80 |
| retrieval | `retrieval_law` | 관련 법령 조항 검색 | 75 |
| retrieval | `retrieval_criteria` | 분쟁해결기준 검색 | 75 |
| retrieval | `retrieval_case` | 분쟁조정사례 검색 | 75 |
| retrieval | `retrieval_counsel` | 상담사례 검색 | 75 |
| generation | `answer_drafter` | 답변 초안 작성 | 60 |
| review | `legal_reviewer` | 법적 정확성 검토 | 40 |

## Supervisor 연동 흐름

```
Supervisor (gpt-4o)
    ↓
registry.get_for_prompt()  → {name: description} 딕셔너리
    ↓
LLM이 다음 에이전트 결정: "query_analyst"
    ↓
registry.get_handler("query_analyst")
    ↓
await handler.process(request)
```

## 설계 원칙

- **Protocol 기반**: ABC 상속 없이 `process()` 메서드만으로 에이전트 구현
- **메타데이터 우선**: 핸들러 인스턴스화 없이 에이전트 발견 가능
- **카테고리 인덱싱**: `_by_category` 딕셔너리로 O(1) 카테고리 조회
- **싱글톤**: `get_agent_registry()`로 전역 단일 인스턴스 보장

## 참조

- Supervisor 통합: `backend/app/supervisor/nodes/supervisor.py`
- ChatState 정의: `backend/app/supervisor/state/`
