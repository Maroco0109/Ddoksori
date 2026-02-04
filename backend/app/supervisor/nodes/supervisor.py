"""
똑소리 프로젝트 - SupervisorNode (MAS 중앙 관제자)

MAS(Multi-Agent System) 슈퍼바이저 아키텍처의 중앙 관제자 노드입니다.
LLM을 사용하여 다음 행동을 동적으로 결정하고, 에이전트 간 워크플로우를 조율합니다.

작성일: 2026-01-26
Phase: MAS Supervisor Architecture - Phase 8 (Progressive Disclosure)

[역할 및 책임]
1. 현재 상태 분석 (어떤 정보가 있고 무엇이 부족한가?)
2. 다음 행동 결정 (어떤 Agent를 호출할 것인가?)
3. Agent 결과 평가 (결과가 충분한가? 재시도가 필요한가?)
4. 최종 판단 (사용자에게 응답할 준비가 되었는가?)

[라우팅 전략 - 2-전략]
- NO_RETRIEVAL / RESTRICTED_DOMAIN → Fast Path (검색/검토 생략)
- NEED_RAG / CACHED_RAG → Full Pipeline (검토 항상 포함)

[오류 처리]
- LLM 타임아웃: 다음 fallback 모델로 전환
- JSON 파싱 실패: 재시도 1회 후 다음 fallback
- 무한 루프: 10회 초과 시 강제 종료 + 부분 결과 응답
- Agent 응답 실패: 해당 Agent 스킵, 다음 단계 진행

[Fallback 체인]
1. GPT-4o (config.models.supervisor) - Primary
2. Claude 3.5 Sonnet (MODEL_SUPERVISOR_FALLBACK) - Secondary
3. Rule-based - Final fallback

[보안]
- 사용자 입력 sanitize (Prompt Injection 방지)
- 입력 길이 제한 (500자)
- 위험 패턴 마스킹
"""

import asyncio
import json
import os
import re
import time
from typing import Any, Dict, Optional, Protocol

from ...agents.registry import get_agent_registry
from ...common.config import get_config
from ...common.logging import get_logger
from ..state import ChatState
from ..state.supervisor import AgentMessage, SupervisorState

logger = get_logger(__name__)


# ============================================================================
# LLM 클라이언트 생성 헬퍼
# ============================================================================


def _create_openai_llm(model: str, timeout: float) -> Optional["AsyncLLMWrapper"]:
    """OpenAI 모델용 LLM 클라이언트 생성"""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("[SupervisorNode] OPENAI_API_KEY not set")
            return None

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        return AsyncLLMWrapper(client, model, "openai")
    except Exception as e:
        logger.warning(f"[SupervisorNode] Failed to create OpenAI client: {e}")
        return None


def _create_anthropic_llm(model: str, timeout: float) -> Optional["AsyncLLMWrapper"]:
    """Anthropic 모델용 LLM 클라이언트 생성"""
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[SupervisorNode] ANTHROPIC_API_KEY not set")
            return None

        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key, timeout=timeout)
        return AsyncLLMWrapper(client, model, "anthropic")
    except Exception as e:
        logger.warning(f"[SupervisorNode] Failed to create Anthropic client: {e}")
        return None


class AsyncLLMWrapper:
    """비동기 LLM 클라이언트 래퍼 (OpenAI/Anthropic 통합)"""

    def __init__(self, client: Any, model: str, provider: str):
        self.client = client
        self.model = model
        self.provider = provider

    async def generate(self, prompt: str) -> str:
        if self.provider == "openai":
            # o1-*, o3-* 등 reasoning 모델은 max_completion_tokens 사용
            uses_new_api = self.model.startswith(("o1-", "o3-"))

            params = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            }
            if uses_new_api:
                params["max_completion_tokens"] = 512
            else:
                params["max_tokens"] = 512

            response = await self.client.chat.completions.create(**params)
            return response.choices[0].message.content or ""
        elif self.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text if response.content else ""
        else:
            raise ValueError(f"Unknown provider: {self.provider}")


# ============================================================================
# 상수 정의
# ============================================================================

MAX_SUPERVISOR_ITERATIONS = 10
"""최대 Supervisor 호출 횟수 (무한 루프 방지)"""

LLM_TIMEOUT_SECONDS = 30.0
"""LLM 호출 타임아웃 (초)"""

MAX_JSON_PARSE_RETRIES = 1
"""JSON 파싱 실패 시 최대 재시도 횟수"""

MAX_USER_INPUT_LENGTH = 500
"""사용자 입력 최대 길이 (Prompt Injection 방지)"""


# ============================================================================
# LLM 프로토콜 (의존성 주입용)
# ============================================================================


class LLMProtocol(Protocol):
    """LLM 클라이언트 프로토콜 (의존성 주입용)"""

    async def generate(self, prompt: str) -> str:
        """프롬프트를 받아 응답 텍스트를 생성합니다."""
        ...


# ============================================================================
# SupervisorNode 클래스
# ============================================================================


class SupervisorNode:
    """
    MAS 중앙 관제자 노드

    LLM을 사용하여 다음 행동을 동적으로 결정합니다.
    LLM 호출 실패 시 규칙 기반 fallback으로 전환하여 안정성을 보장합니다.

    Attributes:
        llm: LLM 클라이언트 (generate 메서드 필요)
        available_agents: 사용 가능한 에이전트 목록 및 설명

    Example:
        >>> from app.llm import ExaoneLLMClient
        >>> supervisor = SupervisorNode(llm=AsyncLLMWrapper(ExaoneLLMClient()))
        >>> decision = await supervisor.decide_next_action(state)
        >>> print(decision["action"])  # "call_agent", "respond", "clarify"
    """

    # Fallback 모델 체인 (환경변수로 설정 가능)
    FALLBACK_MODEL = os.getenv(
        "MODEL_SUPERVISOR_FALLBACK", "claude-3-5-sonnet-20241022"
    )

    def __init__(self, llm: Optional[LLMProtocol] = None):
        """
        SupervisorNode 초기화

        Args:
            llm: LLM 클라이언트 (None이면 자동으로 config.models.supervisor 사용)
        """
        self._injected_llm = llm
        self._primary_llm: Optional[LLMProtocol] = None
        self._fallback_llm: Optional[LLMProtocol] = None
        self._current_model_name: str = "rule-based"

        # Agent Registry에서 동적으로 에이전트 목록 로드
        self._agent_registry = get_agent_registry()

        self._init_llm_chain()

    def _init_llm_chain(self) -> None:
        """LLM fallback 체인 초기화"""
        if self._injected_llm is not None:
            self._primary_llm = self._injected_llm
            self._current_model_name = "injected"
            logger.info("[SupervisorNode] 초기화 완료. 주입된 LLM 사용")
            return

        config = get_config()
        primary_model = config.models.supervisor

        self._primary_llm = _create_openai_llm(primary_model, LLM_TIMEOUT_SECONDS)
        if self._primary_llm:
            self._current_model_name = primary_model
            logger.info(f"[SupervisorNode] Primary LLM: {primary_model}")

        self._fallback_llm = _create_anthropic_llm(
            self.FALLBACK_MODEL, LLM_TIMEOUT_SECONDS
        )
        if self._fallback_llm:
            logger.info(f"[SupervisorNode] Fallback LLM: {self.FALLBACK_MODEL}")

        if not self._primary_llm and not self._fallback_llm:
            logger.warning("[SupervisorNode] No LLM available. Rule-based mode only.")
            self._current_model_name = "rule-based"

        logger.info(
            f"[SupervisorNode] 초기화 완료. "
            f"사용 가능 에이전트: {self._agent_registry.list_names()}"
        )

    @property
    def llm(self) -> Optional[LLMProtocol]:
        """현재 활성 LLM 반환 (하위 호환성)"""
        return self._primary_llm or self._fallback_llm

    @property
    def available_agents(self) -> Dict[str, str]:
        """사용 가능한 에이전트 목록 (Registry에서 동적 로드)"""
        return self._agent_registry.get_for_prompt()

    async def decide_next_action(self, state: ChatState) -> Dict[str, Any]:
        """
        현재 상태를 분석하고 다음 행동을 결정합니다.

        === 2-전략 라우팅 ===
        1. NO_RETRIEVAL → Fast Path (검색/검토 생략)
        2. NEED_RAG / CACHED_RAG → Full Pipeline (검토 항상 포함)

        Args:
            state: 현재 ChatState

        Returns:
            결정 딕셔너리:
                - action: "call_agent" | "respond" | "clarify"
                - target_agent: 다음 호출할 에이전트 (action이 call_agent인 경우)
                - request: 에이전트에게 보낼 요청 (action이 call_agent인 경우)
                - reasoning: 판단 근거
                - partial: True if max iterations reached
        """
        supervisor_state = state.get("supervisor") or {}
        iteration = (
            supervisor_state.get("iteration_count", 0) if supervisor_state else 0
        )

        # 무한 루프 방지
        if iteration >= MAX_SUPERVISOR_ITERATIONS:
            logger.warning(
                f"[SupervisorNode] 최대 반복 횟수({MAX_SUPERVISOR_ITERATIONS}) 도달. 강제 종료."
            )
            return self._fallback_respond(state)

        query_analysis = state.get("query_analysis")
        mode = state.get("mode", "NEED_RAG")

        logger.info(
            f"[SupervisorNode] decide_next_action: mode={mode}, "
            f"query_analysis={'present' if query_analysis else 'absent'}, "
            f"iteration={iteration}"
        )

        # Query Analysis가 없으면 먼저 수행
        supervisor_state = state.get("supervisor") or {}
        completed = supervisor_state.get("completed_tasks", [])

        if (
            not query_analysis
            and "query_analyst" not in completed
            and "query_analysis" not in completed
        ):
            logger.info("[SupervisorNode] Query Analysis 필요")
            return {
                "action": "call_agent",
                "target_agent": "query_analyst",
                "request": {},
                "reasoning": "Query Analysis 필요",
            }

        # === 2-전략 라우팅 ===

        # 1. NO_RETRIEVAL → Fast Path
        if mode == "NO_RETRIEVAL":
            return self._no_retrieval_decision(state)

        # 2. RESTRICTED_DOMAIN → 전문기관 안내 (기존 유지)
        if mode == "RESTRICTED_DOMAIN":
            return self._no_retrieval_decision(state)

        # 3. NEED_RAG / CACHED_RAG → Full Pipeline (항상 Review 포함)
        if mode in ("NEED_RAG", "CACHED_RAG"):
            return self._full_pipeline_decision(state)

        # Fallback → Full Pipeline
        logger.warning(
            f"[SupervisorNode] 알 수 없는 mode={mode}. Full Pipeline fallback."
        )
        return self._full_pipeline_decision(state)

    async def _try_llm_decision(
        self, llm: LLMProtocol, prompt: str, model_name: str
    ) -> Optional[Dict[str, Any]]:
        """단일 LLM으로 결정 시도. 실패 시 None 반환."""
        try:
            response = await asyncio.wait_for(
                llm.generate(prompt), timeout=LLM_TIMEOUT_SECONDS
            )
            decision = self._parse_decision_with_retry(response)

            if decision.get("action") == "rule_based_fallback":
                logger.info(
                    f"[SupervisorNode] {model_name}: JSON 파싱 실패, 다음 fallback 시도"
                )
                return None

            logger.info(
                f"[SupervisorNode] LLM 결정: model={model_name}, "
                f"action={decision.get('action')}, target={decision.get('target_agent')}"
            )
            return decision

        except asyncio.TimeoutError:
            logger.warning(
                f"[SupervisorNode] {model_name} 타임아웃 ({LLM_TIMEOUT_SECONDS}s)"
            )
            return None

        except Exception as e:
            logger.warning(f"[SupervisorNode] {model_name} 호출 실패: {e}")
            return None

    def _no_retrieval_decision(self, state: ChatState) -> Dict[str, Any]:
        """
        Fast Path: NO_RETRIEVAL / RESTRICTED_DOMAIN 쿼리 처리

        흐름: Query Analysis → Generation → END (검색/검토 생략)

        Args:
            state: 현재 ChatState

        Returns:
            결정 딕셔너리
        """
        supervisor_state = state.get("supervisor") or {}
        completed = supervisor_state.get("completed_tasks", [])
        draft_answer = state.get("draft_answer")

        if not draft_answer and "answer_drafter" not in completed:
            logger.info("[SupervisorNode] Fast Path → Generation")
            return {
                "action": "call_agent",
                "target_agent": "answer_drafter",
                "request": {},
                "reasoning": "Fast Path: NO_RETRIEVAL → Generation",
            }

        logger.info("[SupervisorNode] Fast Path 완료")
        return {"action": "respond", "reasoning": "Fast Path 완료"}

    def _full_pipeline_decision(self, state: ChatState) -> Dict[str, Any]:
        """
        Full Pipeline: NEED_RAG / CACHED_RAG 쿼리 처리

        흐름: Query Analysis → Retrieval → Generation → Review → END
        CACHED_RAG일 때는 Retrieval 단계를 생략합니다.

        Args:
            state: 현재 ChatState

        Returns:
            결정 딕셔너리
        """
        supervisor_state = state.get("supervisor") or {}
        completed = supervisor_state.get("completed_tasks", [])
        mode = state.get("mode", "NEED_RAG")
        retrieval = state.get("retrieval")
        draft_answer = state.get("draft_answer")
        review = state.get("review")

        # 1. Retrieval (NEED_RAG일 때만 실행, CACHED_RAG는 생략)
        if mode == "NEED_RAG" and not retrieval and "retrieval_team" not in completed:
            # Adaptive RAG: 쿼리 복잡도에 따라 검색 전략 결정
            query_complexity = state.get("query_complexity", "moderate")
            retrieval_config = get_config().retrieval

            use_hyde = retrieval_config.hyde_enabled
            if query_complexity == "simple" and retrieval_config.simple_skip_hyde:
                use_hyde = False

            strategy = "BM25-focused" if not use_hyde else "HyDE+RRF"
            logger.info(
                f"[SupervisorNode] Full Pipeline → Retrieval "
                f"(complexity={query_complexity}, strategy={strategy})"
            )
            return {
                "action": "call_agent",
                "target_agent": "retrieval_team",
                "request": {
                    "use_hyde": use_hyde,
                    "query_complexity": query_complexity,
                },
                "reasoning": f"Full Pipeline: Retrieval 필요 (complexity={query_complexity}, strategy={strategy})",
            }

        # 2. Generation
        if not draft_answer and "answer_drafter" not in completed:
            logger.info("[SupervisorNode] Full Pipeline → Generation")
            return {
                "action": "call_agent",
                "target_agent": "answer_drafter",
                "request": {},
                "reasoning": "Full Pipeline: Generation 필요",
            }

        # 3. Review (항상 실행)
        if not review and "legal_reviewer" not in completed:
            logger.info("[SupervisorNode] Full Pipeline → Review")
            return {
                "action": "call_agent",
                "target_agent": "legal_reviewer",
                "request": {},
                "reasoning": "Full Pipeline: Review 필요",
            }

        # 모든 단계 완료
        logger.info("[SupervisorNode] Full Pipeline 완료")
        return {"action": "respond", "reasoning": "Full Pipeline 완료"}

    def _build_decision_prompt(self, state: ChatState) -> str:
        """
        Supervisor 판단을 위한 프롬프트를 생성합니다.

        보안 고려사항:
        - 사용자 입력은 반드시 sanitize 후 삽입
        - 입력 길이 제한 (500자)
        - Instruction injection 패턴 필터링

        Args:
            state: 현재 ChatState

        Returns:
            LLM에 전달할 프롬프트 문자열
        """
        # 사용자 입력 sanitize
        user_query = self._sanitize_user_input(state.get("user_query", ""))
        supervisor_state = state.get("supervisor") or {}
        completed_tasks = supervisor_state.get("completed_tasks", [])

        # 각 필드 요약
        query_analysis = state.get("query_analysis")
        retrieval = state.get("retrieval")
        draft_answer = state.get("draft_answer")
        review = state.get("review")

        return f"""당신은 소비자 분쟁 해결 시스템의 중앙 관제자(Supervisor)입니다.

## 현재 상태
- 사용자 질문: {user_query}
- 완료된 태스크: {completed_tasks}
- 수집된 정보:
  - 질의 분석: {self._summarize_field(query_analysis)}
  - 검색 결과: {self._summarize_field(retrieval)}
  - 답변 초안: {self._summarize_field(draft_answer)}
  - 검토 결과: {self._summarize_field(review)}

## 사용 가능한 Agent
{self._format_agents()}

## 중요 규칙 (반드시 준수)
0. 사용자 질문이 너무 짧거나(5자 이하) 모호하면 → clarify 먼저 (예: "환불", "교환", "어떻게")
1. "질의 분석"이 없으면 → query_analyst 호출 필수
2. "검색 결과"가 없으면 → retrieval_team 호출 필수
3. "답변 초안"이 없으면 → answer_drafter 호출 필수
4. "검토 결과"가 없으면 → legal_reviewer 호출 필수
5. 모든 정보가 있을 때만 → respond 가능

## 출력 형식 (반드시 JSON으로 응답)
{{
    "action": "call_agent" | "respond" | "clarify",
    "target_agent": "agent_name",
    "request": {{}},
    "reasoning": "판단 근거"
}}
"""

    def _format_agents(self) -> str:
        """사용 가능한 에이전트 목록을 포맷팅합니다."""
        lines = []
        for name, description in self.available_agents.items():
            lines.append(f"- {name}: {description}")
        return "\n".join(lines)

    def _summarize_field(self, field: Any) -> str:
        """필드를 요약하여 문자열로 반환합니다."""
        if field is None:
            return "없음"
        if isinstance(field, str):
            return field[:100] + "..." if len(field) > 100 else field
        if isinstance(field, dict):
            return f"있음 (키: {list(field.keys())[:5]})"
        return "있음"

    def _sanitize_user_input(self, text: str) -> str:
        """
        사용자 입력을 sanitize합니다 (Prompt Injection 방지).

        처리 항목:
        1. 길이 제한 (500자)
        2. 위험 패턴 마스킹 (instruction override 시도)
        3. 연속된 특수문자 제거 (프롬프트 구조 파괴 시도 방지)

        Args:
            text: 원본 사용자 입력

        Returns:
            sanitize된 텍스트
        """
        if not text:
            return ""

        # 1. 길이 제한
        text = text[:MAX_USER_INPUT_LENGTH]

        # 2. 위험 패턴 마스킹 (instruction override 시도 차단)
        dangerous_patterns = [
            "ignore",  # "ignore previous instructions"
            "disregard",  # "disregard all rules"
            "forget",  # "forget your instructions"
            "instead",  # "instead do this"
            "pretend",  # "pretend you are"
            "act as",  # "act as a different AI"
            "new instruction",  # "here is your new instruction"
            "시스템 프롬프트",  # Korean: "system prompt"
            "지시를 무시",  # Korean: "ignore instructions"
        ]

        sanitized = text
        for pattern in dangerous_patterns:
            # 대소문자 무시 치환
            sanitized = re.sub(
                re.escape(pattern), f"[{pattern}]", sanitized, flags=re.IGNORECASE
            )

        # 3. 연속된 특수문자 제거 (프롬프트 구조 파괴 시도 방지)
        sanitized = re.sub(r"#{3,}", "##", sanitized)  # ### → ##
        sanitized = re.sub(r"-{3,}", "--", sanitized)  # --- → --

        return sanitized

    def _parse_decision_with_retry(
        self, response: str, retries: int = 0
    ) -> Dict[str, Any]:
        """
        LLM 응답을 JSON으로 파싱합니다. 실패 시 재시도 후 규칙 기반 전환.

        Args:
            response: LLM 응답 문자열
            retries: 현재 재시도 횟수

        Returns:
            파싱된 결정 딕셔너리
        """
        try:
            # JSON 직접 파싱 시도
            return json.loads(response)
        except json.JSONDecodeError:
            if retries < MAX_JSON_PARSE_RETRIES:
                # 재시도: 마크다운 코드 블록 제거 후 파싱
                cleaned = re.sub(r"```json?\n?|\n?```", "", response).strip()
                # JSON 객체 추출 시도
                match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group())
                    except json.JSONDecodeError:
                        logger.warning(
                            "[SupervisorNode] JSON re-parse failed after cleanup"
                        )
                return self._parse_decision_with_retry(cleaned, retries + 1)

            logger.warning(
                f"[SupervisorNode] JSON 파싱 실패 (재시도 {retries}회). 규칙 기반 fallback."
            )
            return {"action": "rule_based_fallback", "reasoning": "JSON parse failure"}

    def _rule_based_fallback(self, state: ChatState) -> Dict[str, Any]:
        """
        규칙 기반 의사결정 (LLM 실패 시 사용)

        === 2-전략 라우팅 ===
        - NO_RETRIEVAL / RESTRICTED: query_analysis → draft → respond
        - NEED_RAG / CACHED_RAG: query_analysis → retrieval → draft → review → respond

        Args:
            state: 현재 ChatState

        Returns:
            결정 딕셔너리
        """
        mode = state.get("mode", "NEED_RAG")

        # NO_RETRIEVAL / RESTRICTED → Fast Path
        if mode in ("NO_RETRIEVAL", "RESTRICTED_DOMAIN"):
            return self._no_retrieval_decision(state)

        # NEED_RAG / CACHED_RAG → Full Pipeline
        return self._full_pipeline_decision(state)

    def _fallback_respond(self, state: ChatState) -> Dict[str, Any]:
        """
        강제 종료 시 부분 결과 응답

        최대 반복 횟수에 도달했을 때 현재까지의 결과로 응답합니다.

        Args:
            state: 현재 ChatState

        Returns:
            부분 결과 응답 딕셔너리
        """
        return {
            "action": "respond",
            "reasoning": "최대 반복 횟수 도달 - 부분 결과 반환",
            "partial": True,
        }

    def create_supervisor_message(
        self, to_agent: str, message_type: str, content: Dict[str, Any]
    ) -> AgentMessage:
        """
        에이전트에게 보낼 메시지를 생성합니다.

        Args:
            to_agent: 수신 에이전트 이름
            message_type: 메시지 유형 ('request', 'response', 'error')
            content: 메시지 페이로드

        Returns:
            AgentMessage TypedDict
        """
        return AgentMessage(
            from_agent="supervisor",
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=time.time(),
        )

    def as_node(self):
        """
        이 Supervisor를 LangGraph 노드 함수로 변환합니다.

        Returns:
            LangGraph 노드로 사용할 수 있는 async 함수
        """
        supervisor = self

        async def supervisor_node(state: ChatState) -> Dict[str, Any]:
            """Supervisor 노드 함수"""
            supervisor_state = state.get("supervisor") or {}

            # 반복 횟수 증가
            iteration_count = supervisor_state.get("iteration_count", 0) + 1

            # 다음 행동 결정
            decision = await supervisor.decide_next_action(state)

            # 메시지 기록
            message = supervisor.create_supervisor_message(
                to_agent=decision.get("target_agent", "output"),
                message_type=(
                    "request" if decision["action"] == "call_agent" else "response"
                ),
                content={
                    "action": decision["action"],
                    "reasoning": decision.get("reasoning", ""),
                },
            )

            existing_messages = supervisor_state.get("agent_messages", [])
            updated_messages = existing_messages + [message]

            # 상태 업데이트
            return {
                "supervisor": {
                    **supervisor_state,
                    "agent_messages": updated_messages,
                    "next_agent": decision.get("target_agent"),
                    "supervisor_reasoning": decision.get("reasoning", ""),
                    "iteration_count": iteration_count,
                    "current_phase": _determine_phase(decision),
                }
            }

        return supervisor_node


def _determine_phase(decision: Dict[str, Any]) -> str:
    """결정에 따라 현재 phase를 결정합니다."""
    action = decision.get("action", "")
    target = decision.get("target_agent", "")

    if action == "respond":
        return "done"
    if action == "clarify":
        return "clarifying"
    if target == "query_analyst":
        return "analyzing"
    if target == "retrieval_team":
        return "retrieving"
    if target == "answer_drafter":
        return "drafting"
    if target == "legal_reviewer":
        return "reviewing"
    return "processing"


# ============================================================================
# 라우터 함수
# ============================================================================


def supervisor_router(state: ChatState) -> str:
    """
    Supervisor의 결정을 기반으로 다음 노드를 결정합니다.

    이 함수는 supervisor_node에서 설정한 next_agent를 읽어 라우팅합니다.

    Args:
        state: 현재 ChatState

    Returns:
        다음 노드 이름 (str)
    """
    supervisor_state = state.get("supervisor") or {}
    next_agent = supervisor_state.get("next_agent")

    if next_agent == "respond" or next_agent is None:
        return "output_guardrail"

    return next_agent


# ============================================================================
# 헬퍼 함수
# ============================================================================


def create_initial_supervisor_state() -> SupervisorState:
    """
    초기 SupervisorState를 생성합니다.

    Returns:
        초기화된 SupervisorState
    """
    return SupervisorState(
        current_phase="initial",
        agent_messages=[],
        pending_tasks=["query_analysis", "retrieval", "draft", "review"],
        completed_tasks=[],
        supervisor_reasoning="",
        next_agent=None,
        iteration_count=0,
    )


__all__ = [
    "SupervisorNode",
    "supervisor_router",
    "create_initial_supervisor_state",
    "MAX_SUPERVISOR_ITERATIONS",
    "LLM_TIMEOUT_SECONDS",
]
