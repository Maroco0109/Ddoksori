"""
HTTP 클라이언트 - 백엔드 /chat 엔드포인트 호출
"""

import httpx
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class NodeTiming:
    """에이전트 노드 실행 시간"""
    node_name: str
    duration_ms: float
    start_time: str
    end_time: str


@dataclass
class ChatResponse:
    """채팅 응답"""
    session_id: str
    answer: str
    chunks_used: int
    model: str
    sources: List[dict]
    has_sufficient_evidence: bool = True
    clarifying_questions: List[str] = field(default_factory=list)
    domain: Optional[Dict[str, Any]] = None
    similar_cases: Optional[Dict[str, Any]] = None
    related_laws: Optional[List[Dict[str, Any]]] = None
    related_criteria: Optional[List[Dict[str, Any]]] = None
    node_timings: Optional[List[Dict[str, Any]]] = None
    request_id: Optional[str] = None
    total_time_ms: Optional[float] = None


class ChatClient:
    """백엔드 채팅 API 클라이언트"""

    def __init__(self, server_url: str = "http://localhost:8000", timeout: int = 120):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout

    def send_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        chat_type: str = "general",
        onboarding: Optional[Dict[str, str]] = None,
        top_k: int = 5,
        debug: bool = True
    ) -> ChatResponse:
        """
        메시지 전송 및 응답 수신

        Args:
            message: 사용자 질문
            session_id: 세션 ID (멀티턴 대화용)
            chat_type: 상담 유형 ('dispute' 또는 'general')
            onboarding: 온보딩 폼 데이터
            top_k: 검색 결과 수
            debug: 디버그 모드 (타이밍 정보 포함)

        Returns:
            ChatResponse 객체
        """
        payload = {
            "message": message,
            "chat_type": chat_type,
            "top_k": top_k,
            "debug": debug
        }

        if session_id:
            payload["session_id"] = session_id

        if onboarding:
            payload["onboarding"] = onboarding

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.server_url}/chat", json=payload)
            response.raise_for_status()
            data = response.json()

            return ChatResponse(
                session_id=data.get("session_id", ""),
                answer=data.get("answer", ""),
                chunks_used=data.get("chunks_used", 0),
                model=data.get("model", ""),
                sources=data.get("sources", []),
                has_sufficient_evidence=data.get("has_sufficient_evidence", True),
                clarifying_questions=data.get("clarifying_questions", []),
                domain=data.get("domain"),
                similar_cases=data.get("similar_cases"),
                related_laws=data.get("related_laws"),
                related_criteria=data.get("related_criteria"),
                node_timings=data.get("node_timings"),
                request_id=data.get("request_id"),
                total_time_ms=data.get("total_time_ms")
            )

    def health_check(self) -> bool:
        """
        서버 상태 확인

        Returns:
            True if 서버 정상, False otherwise
        """
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.server_url}/health")
                return response.status_code == 200
        except Exception:
            return False
