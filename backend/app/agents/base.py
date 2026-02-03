"""
똑소리 프로젝트 - BaseAgent 추상 클래스

MAS(Multi-Agent System) 슈퍼바이저 아키텍처를 위한 에이전트 기본 클래스입니다.
모든 에이전트는 이 클래스를 상속받아 Supervisor와 통신합니다.

작성일: 2026-01-26
Phase: MAS Supervisor Architecture - Phase 2

[역할 및 책임]
1. 에이전트 메타데이터 정의 (이름, 설명, 입출력 필드)
2. Supervisor 요청 처리를 위한 표준 인터페이스 제공
3. Supervisor에게 결과 보고를 위한 표준 응답 형식 생성
4. LangGraph 노드로 변환하기 위한 래퍼 메서드 제공

[사용 예시]
    from app.agents.base import BaseAgent

    class QueryAnalystAgent(BaseAgent):
        agent_name = "query_analyst"
        agent_description = "사용자 질문을 분석하여 의도와 엔티티를 추출합니다."
        required_inputs = ["user_query"]
        provided_outputs = ["intent", "entities", "query_type"]

        async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
            user_query = request["context"]["user_query"]
            result = await self._analyze_query(user_query)
            return self.report_to_supervisor(
                status="success",
                result=result,
                message=f"분석 완료: {result['query_type']}"
            )
"""

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional

from ..supervisor.state import ChatState
from ..supervisor.state.supervisor import AgentMessage


class BaseAgent(ABC):
    """
    MAS 슈퍼바이저 아키텍처의 에이전트 기본 클래스

    모든 에이전트는 이 클래스를 상속받아 구현합니다.
    Supervisor가 에이전트를 호출할 때 process() 메서드가 실행되고,
    결과는 report_to_supervisor()를 통해 표준 형식으로 반환됩니다.

    Attributes:
        agent_name: 에이전트 고유 식별자 (예: 'query_analyst', 'retrieval_law')
        agent_description: Supervisor가 참조할 에이전트 설명
        required_inputs: 이 에이전트가 필요로 하는 입력 필드 목록
        provided_outputs: 이 에이전트가 제공하는 출력 필드 목록

    Class Variables (서브클래스에서 오버라이드):
        agent_name (ClassVar[str]): 에이전트 이름
        agent_description (ClassVar[str]): 에이전트 설명
        required_inputs (ClassVar[List[str]]): 필수 입력 필드
        provided_outputs (ClassVar[List[str]]): 출력 필드
    """

    agent_name: ClassVar[str] = ""
    agent_description: ClassVar[str] = ""
    required_inputs: ClassVar[List[str]] = []
    provided_outputs: ClassVar[List[str]] = []

    def __init__(self) -> None:
        """에이전트 초기화"""
        if not self.agent_name:
            raise ValueError(
                f"{self.__class__.__name__}은 agent_name을 정의해야 합니다."
            )

    @abstractmethod
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Supervisor로부터 요청을 받아 처리합니다.

        이 메서드는 서브클래스에서 반드시 구현해야 합니다.
        처리가 완료되면 report_to_supervisor()를 사용하여 결과를 반환합니다.

        Args:
            request: Supervisor가 보낸 요청
                - task: 수행할 태스크 이름 (str)
                - params: 태스크 파라미터 (Dict[str, Any])
                - context: 현재 상태 컨텍스트 (Dict[str, Any])
                    - user_query: 사용자 질문
                    - query_analysis: 질의 분석 결과 (있는 경우)
                    - retrieval: 검색 결과 (있는 경우)
                    - 기타 ChatState 필드

        Returns:
            Supervisor에게 보낼 응답 (report_to_supervisor() 형식)
                - from_agent: 발신 에이전트 이름
                - status: 'success' | 'failure' | 'need_more_info'
                - result: 처리 결과 데이터
                - message: Supervisor에게 보고할 메시지

        Example:
            >>> async def process(self, request):
            ...     query = request["context"]["user_query"]
            ...     result = await self._do_work(query)
            ...     return self.report_to_supervisor(
            ...         status="success",
            ...         result=result,
            ...         message="작업 완료"
            ...     )
        """
        pass

    def report_to_supervisor(
        self,
        status: str,
        result: Any,
        message: str,
    ) -> Dict[str, Any]:
        """
        Supervisor에게 결과를 보고하는 표준 응답 형식을 생성합니다.

        Args:
            status: 처리 상태
                - 'success': 성공적으로 완료
                - 'failure': 처리 실패 (재시도 또는 다른 접근 필요)
                - 'need_more_info': 추가 정보 필요 (사용자 질문 요청)
            result: 처리 결과 데이터 (Any 타입, 상태에 따라 다름)
                - success: 실제 처리 결과 딕셔너리
                - failure: None 또는 부분 결과
                - need_more_info: 필요한 정보 설명
            message: Supervisor에게 보고할 사람이 읽을 수 있는 메시지
                예: "분석 완료. 유형: dispute, 의도: 환불 문의"

        Returns:
            표준화된 응답 딕셔너리

        Example:
            >>> self.report_to_supervisor(
            ...     status="success",
            ...     result={"intent": "환불", "entities": {"item": "노트북"}},
            ...     message="분석 완료. 노트북 환불 관련 분쟁 질의입니다."
            ... )
            {
                "from_agent": "query_analyst",
                "status": "success",
                "result": {"intent": "환불", "entities": {"item": "노트북"}},
                "message": "분석 완료. 노트북 환불 관련 분쟁 질의입니다."
            }
        """
        return {
            "from_agent": self.agent_name,
            "status": status,
            "result": result,
            "message": message,
        }

    def create_agent_message(
        self,
        to_agent: str,
        message_type: str,
        content: Dict[str, Any],
    ) -> AgentMessage:
        """
        다른 에이전트 또는 Supervisor에게 보낼 메시지를 생성합니다.

        Args:
            to_agent: 수신 에이전트 이름 (예: 'supervisor', 'retrieval_law')
            message_type: 메시지 유형
                - 'request': 작업 요청
                - 'response': 작업 결과 응답
                - 'error': 오류 보고
            content: 메시지 페이로드

        Returns:
            AgentMessage TypedDict

        Example:
            >>> msg = agent.create_agent_message(
            ...     to_agent="supervisor",
            ...     message_type="response",
            ...     content={"result": analysis_result, "status": "success"}
            ... )
        """
        return AgentMessage(
            from_agent=self.agent_name,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            timestamp=time.time(),
        )

    def validate_request(self, request: Dict[str, Any]) -> Optional[str]:
        """
        요청이 필수 입력 필드를 포함하는지 검증합니다.

        Args:
            request: 검증할 요청 딕셔너리

        Returns:
            None if valid, error message string if invalid

        Example:
            >>> error = agent.validate_request(request)
            >>> if error:
            ...     return self.report_to_supervisor("failure", None, error)
        """
        context = request.get("context", {})

        missing_fields = []
        for field in self.required_inputs:
            if field not in context or context[field] is None:
                missing_fields.append(field)

        if missing_fields:
            return f"필수 입력 필드 누락: {', '.join(missing_fields)}"

        return None

    def as_node(self):
        """
        이 에이전트를 LangGraph 노드 함수로 변환합니다.

        LangGraph의 add_node()에 전달할 수 있는 callable을 반환합니다.
        노드 함수는 ChatState를 받아 처리하고 상태 업데이트를 반환합니다.

        Returns:
            LangGraph 노드로 사용할 수 있는 async 함수

        Example:
            >>> graph.add_node("query_analyst", query_analyst_agent.as_node())
        """
        agent = self

        async def node_function(state: ChatState) -> Dict[str, Any]:
            supervisor_state = state.get("supervisor", {})

            request = {
                "task": f"process_{agent.agent_name}",
                "params": {},
                "context": {
                    "user_query": state.get("user_query", ""),
                    "chat_type": state.get("chat_type", "general"),
                    "onboarding": state.get("onboarding"),
                    "query_analysis": state.get("query_analysis"),
                    "retrieval": state.get("retrieval"),
                    "draft_answer": state.get("draft_answer"),
                    "review": state.get("review"),
                },
            }

            response = await agent.process(request)

            agent_message = agent.create_agent_message(
                to_agent="supervisor",
                message_type="response",
                content=response,
            )

            existing_messages = supervisor_state.get("agent_messages", [])
            updated_messages = existing_messages + [agent_message]

            completed_tasks = supervisor_state.get("completed_tasks", [])
            if agent.agent_name not in completed_tasks:
                completed_tasks = completed_tasks + [agent.agent_name]

            return {
                "supervisor": {
                    **supervisor_state,
                    "agent_messages": updated_messages,
                    "completed_tasks": completed_tasks,
                }
            }

        return node_function

    def get_info(self) -> Dict[str, Any]:
        """
        에이전트 메타데이터를 반환합니다.

        Supervisor가 에이전트 선택 시 참조할 정보입니다.

        Returns:
            에이전트 정보 딕셔너리

        Example:
            >>> info = agent.get_info()
            >>> print(info["description"])
            "사용자 질문을 분석하여 의도와 엔티티를 추출합니다."
        """
        return {
            "name": self.agent_name,
            "description": self.agent_description,
            "required_inputs": self.required_inputs,
            "provided_outputs": self.provided_outputs,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.agent_name})>"


__all__ = [
    "BaseAgent",
]
