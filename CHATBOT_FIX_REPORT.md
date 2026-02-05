# DDOKSORI 챗봇 답변 루프 이슈 해결 보고서
## Chatbot Self-Response Loop Fix Report

---

**보고 일자**: 2026년 2월 4일
**프로젝트**: DDOKSORI - 한국 소비자 분쟁 해결 챗봇
**기술 스택**: LangGraph, Python Backend
**해결 범위**: `input_guardrail_node` (입력 유효성 검사 및 메시지 처리)

---

## 요약 (Executive Summary)

본 보고서는 챗봇이 자신의 답변을 사용자의 입력으로 오인하여 무한 루프(Self-Response Loop)에 빠지는 치명적인 이슈에 대한 원인 분석 및 해결 결과를 기술합니다.

**이슈 개요**:
클라이언트가 대화 기록(Chat History)을 통째로 전송할 때, 백엔드가 마지막 메시지의 **화자(Speaker)**를 구분하지 않고 무조건 사용자의 최신 질문으로 처리하는 로직 결함이 있었습니다. 이로 인해 챗봇의 직전 답변이 다시 사용자의 질문으로 입력되어, 챗봇이 스스로에게 계속 대답하는 무한 루프가 발생했습니다.

**해결 결과**:
`backend/app/guardrail/nodes.py`의 입력 추출 로직을 수정하여 **엄격한 타입 체크(Strict Type Checking)**를 도입했습니다. 이제 시스템은 명시적으로 `HumanMessage` 타입이거나 `role="user"`인 메시지만 입력으로 받아들이며, AI의 메시지는 입력으로 처리하지 않습니다. 이를 통해 불필요한 중복 비교 로직 없이 근본적으로 루프를 차단했습니다.

---

## 상세 해결 내역 (Detailed Resolution)

### ISSUE-01: 챗봇 자기 답변 루프 (Self-Response Loop)

**ID**: FIX-20260204-01
**심각도**: **Critical** (서비스 거부 및 과도한 리소스 소모)
**상태**: ✅ **Resolved (해결됨)**

#### 1. 문제 원인 (Root Cause Analysis)

기술적 분석 결과, 다음 3단계 과정으로 문제가 발생했습니다:

1.  **클라이언트의 상태 전송**: 챗봇 답변 생성 직후, 클라이언트(또는 프론트엔드)가 새로운 사용자 입력 없이 현재까지의 대화 상태(`[Human, AI]`)를 백엔드로 재전송했습니다.
2.  **취약한 입력 추출 로직**: 백엔드의 `input_guardrail_node`는 메시지 리스트의 **마지막 요소**를 무조건 `user_query`로 추출했습니다. 마지막 메시지가 `AIMessage`(챗봇의 답변)임에도 불구하고 이를 사용자 질문으로 간주했습니다.
3.  **루프 발생**: 챗봇은 자신의 답변을 질문으로 인식하고 또 다른 답변을 생성했고, 이 과정이 반복되었습니다.

#### 2. 해결 방법 (Implemented Solution)

**수정 파일**: `backend/app/guardrail/nodes.py`

입력 추출 방식을 "위치 기반(마지막 메시지)"에서 "**속성 기반(사람 메시지인지 확인)**"으로 변경했습니다.

*   **엄격한 타입 체크 적용**:
    *   기존: `messages[-1].content` (타입 무관)
    *   변경: `isinstance(last_message, HumanMessage)` 또는 `last_message.type == "human"` 조건 확인.
*   **AI 메시지 무시**:
    *   마지막 메시지가 `AIMessage`인 경우, 유효한 사용자 입력이 없는 것으로 간주하여 처리를 중단하거나 빈 값으로 처리합니다.
*   **다양한 메시지 포맷 지원 (Hotfix 반영)**:
    *   LangChain 객체 (`HumanMessage`)
    *   Dictionary 포맷 (`{"type": "human", ...}`)
    *   OpenAI API 포맷 (`{"role": "user", ...}`)
    *   위 3가지 케이스를 모두 정상적으로 `user_query`로 식별하도록 정규화 로직 추가.

#### 3. 검증 결과 (Verification)

`verify_root_cause_fix.py` 검증 스크립트를 통해 다양한 시나리오에서 패치가 정상 작동함을 확인했습니다.

| 테스트 시나리오 | 입력 상태 (Messages) | 이전 동작 (Before) | 수정 후 동작 (After) | 판정 |
| :--- | :--- | :--- | :--- | :--- |
| **Ambiguous State** | `[Human, AI]` (마지막이 AI) | AI 답변을 질문으로 인식 (Loop 발생) | **입력 없음으로 간주 (Loop 차단)** | ✅ Pass |
| **Normal State** | `[AI, Human]` (마지막이 사람) | 정상 인식 | **정상 인식** (기존 기능 유지) | ✅ Pass |
| **Dict Format** | `{"type": "human", ...}` | 정상 인식 | **정상 인식** | ✅ Pass |
| **OpenAI Format** | `{"role": "user", ...}` | 인식 실패 가능성 있음 | **정상 인식** (호환성 확보) | ✅ Pass |

---

## 결론 (Conclusion)

본 패치를 통해 챗봇이 자신의 답변에 반응하는 무한 루프 문제를 근본적으로 해결했습니다. 단순한 내용 비교(유사도 검사)가 아닌, **메시지의 화자(Speaker)를 식별**하는 방식으로 로직을 개선하여 오탐(False Positive) 가능성을 없애고 처리 효율을 높였습니다. 또한 OpenAI 포맷 등 다양한 입력 형태에 대한 호환성도 확보되었습니다.
