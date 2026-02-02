"""
RAGConversationMemory 유틸리티 및 memory_save_node 단위 테스트

작성일: 2026-01-31

테스트 대상:
- backend/app/supervisor/state/memory.py
- backend/app/supervisor/nodes/memory_save.py
"""

from typing import Any, Dict, List

import pytest

# 전체 파일에 unit 마커 적용 (DB 의존성 없음)
pytestmark = pytest.mark.unit


# === Test Fixtures ===


@pytest.fixture
def sample_need_rag_state() -> Dict[str, Any]:
    """NEED_RAG 모드 샘플 상태"""
    return {
        "mode": "NEED_RAG",
        "user_query": "헬스장 환불이 안된다고 합니다",
        "final_answer": "소비자기본법 제17조에 따라 청약 철회가 가능합니다. 다만 서비스 이용을 시작한 경우 잔여 기간에 대한 환불만 가능합니다.",
        "rag_conversation_memory": [],
    }


@pytest.fixture
def sample_no_retrieval_state() -> Dict[str, Any]:
    """NO_RETRIEVAL 모드 샘플 상태 (인사/시스템 질문)"""
    return {
        "mode": "NO_RETRIEVAL",
        "user_query": "안녕하세요",
        "final_answer": "안녕하세요! 소비자 분쟁 해결을 도와드리겠습니다.",
        "rag_conversation_memory": [],
    }


@pytest.fixture
def sample_need_clarification_state() -> Dict[str, Any]:
    """NEED_CLARIFICATION 모드 샘플 상태"""
    return {
        "mode": "NEED_CLARIFICATION",
        "user_query": "환불",
        "final_answer": "어떤 품목에 대한 환불 문의인가요? 구체적으로 알려주시면 더 정확히 답변드리겠습니다.",
        "rag_conversation_memory": [],
    }


@pytest.fixture
def existing_memory_state() -> List[Dict[str, Any]]:
    """기존 메모리가 있는 상태 (3개 턴)"""
    return [
        {
            "user_query": "헬스장 환불 문의",
            "answer_summary": "청약철회 가능하나 이용 기간 제외...",
            "mode": "NEED_RAG",
        },
        {
            "user_query": "중고차 계약 취소",
            "answer_summary": "중고차는 소비자기본법 적용 대상...",
            "mode": "NEED_RAG",
        },
        {
            "user_query": "온라인 쇼핑몰 반품",
            "answer_summary": "전자상거래법 제17조 7일 청약철회...",
            "mode": "NEED_RAG",
        },
    ]


@pytest.fixture
def long_answer_text() -> str:
    """200자 초과 답변 텍스트"""
    return (
        "소비자기본법 제17조에 따라 청약 철회가 가능합니다. "
        "다만 서비스 이용을 시작한 경우 잔여 기간에 대한 환불만 가능하며, "
        "이미 이용한 기간에 대한 비용은 공제됩니다. "
        "헬스장 회원권의 경우 계약서에 명시된 환불 규정을 우선 확인해야 하며, "
        "소비자분쟁해결기준에 따라 환불 비율이 결정됩니다. "
        "추가로 계약 후 7일 이내라면 위약금 없이 환불이 가능할 수 있습니다. "
        "소비자상담센터 1372를 통해 추가 상담을 받으실 수 있습니다."
    )


# === Unit Tests ===


class TestRAGConversationMemory:
    """RAGConversationMemory 유틸리티 클래스 테스트"""

    def test_add_need_rag_turn(self):
        """NEED_RAG 모드 턴 정상 저장"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory()
        saved = memory.add_turn(
            mode="NEED_RAG",
            query="헬스장 환불 문의",
            answer_summary="청약철회 가능합니다.",
        )

        assert saved is True
        assert len(memory) == 1
        recent = memory.get_recent_turns()
        assert len(recent) == 1
        assert recent[0].user_query == "헬스장 환불 문의"
        assert recent[0].answer_summary == "청약철회 가능합니다."
        assert recent[0].mode == "NEED_RAG"

    def test_skip_no_retrieval_turn(self):
        """NO_RETRIEVAL 모드 턴 스킵 (returns False)"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory()
        saved = memory.add_turn(
            mode="NO_RETRIEVAL",
            query="안녕하세요",
            answer_summary="안녕하세요! 무엇을 도와드릴까요?",
        )

        assert saved is False
        assert len(memory) == 0

    def test_skip_need_clarification_turn(self):
        """NEED_CLARIFICATION 모드 턴 스킵"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory()
        saved = memory.add_turn(
            mode="NEED_CLARIFICATION",
            query="환불",
            answer_summary="어떤 품목에 대한 환불인가요?",
        )

        assert saved is False
        assert len(memory) == 0

    def test_window_size_limit(self):
        """윈도우 크기(5) 초과 시 오래된 턴 제거"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory(window_size=5)

        # 6개 턴 추가
        for i in range(6):
            memory.add_turn(
                mode="NEED_RAG", query=f"질문 {i + 1}", answer_summary=f"답변 {i + 1}"
            )

        # 윈도우 크기만큼만 유지
        assert len(memory) == 5
        recent = memory.get_recent_turns()
        # 가장 오래된 턴(질문 1) 제거됨
        assert recent[0].user_query == "질문 2"
        assert recent[-1].user_query == "질문 6"

    def test_answer_summary_truncation(self, long_answer_text):
        """200자 초과 답변 자동 절단 + '...'"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory()
        memory.add_turn(
            mode="NEED_RAG", query="긴 답변 요청", answer_summary=long_answer_text
        )

        recent = memory.get_recent_turns()[0]

        # 200자 + '...' 형태
        assert len(recent.answer_summary) <= 203  # 200자 + '...'
        assert recent.answer_summary.endswith("...")
        # 원본 텍스트의 앞부분 포함
        assert "소비자기본법 제17조" in recent.answer_summary

    def test_from_state_and_to_state(self, existing_memory_state):
        """List[Dict] ↔ RAGConversationMemory 변환 왕복"""
        from app.supervisor.state.memory import RAGConversationMemory

        # List[Dict] → RAGConversationMemory
        memory = RAGConversationMemory.from_state(existing_memory_state)
        assert len(memory) == 3

        # 내용 확인
        recent = memory.get_recent_turns()
        assert recent[0].user_query == "헬스장 환불 문의"
        assert recent[1].user_query == "중고차 계약 취소"
        assert recent[2].user_query == "온라인 쇼핑몰 반품"

        # RAGConversationMemory → List[Dict]
        state_list = memory.to_state()
        assert len(state_list) == 3
        assert state_list[0]["user_query"] == "헬스장 환불 문의"
        assert state_list[0]["mode"] == "NEED_RAG"

    def test_get_context_for_rewriting(self, existing_memory_state):
        """Query Rewriter용 컨텍스트 문자열 생성"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory.from_state(existing_memory_state)
        context = memory.get_context_for_rewriting()

        # 포맷 검증
        assert "[이전 대화 이력]" in context
        assert "턴 1:" in context
        assert "턴 2:" in context
        assert "턴 3:" in context
        assert "질문: 헬스장 환불 문의" in context
        assert "답변 요약: 청약철회 가능하나 이용 기간 제외..." in context

    def test_empty_memory(self):
        """빈 메모리에서 get_recent_turns() → []"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory()
        recent = memory.get_recent_turns()

        assert len(recent) == 0
        assert recent == []

        # 빈 메모리의 컨텍스트
        context = memory.get_context_for_rewriting()
        assert context == ""

    def test_env_window_size_override(self, monkeypatch):
        """환경변수 CONVERSATION_MEMORY_WINDOW 오버라이드"""
        from app.supervisor.state.memory import RAGConversationMemory

        # 환경변수로 윈도우 크기 3으로 설정
        monkeypatch.setenv("CONVERSATION_MEMORY_WINDOW", "3")

        memory = RAGConversationMemory()

        # 4개 턴 추가
        for i in range(4):
            memory.add_turn(
                mode="NEED_RAG", query=f"질문 {i + 1}", answer_summary=f"답변 {i + 1}"
            )

        # 환경변수에서 설정한 3으로 제한
        assert len(memory) == 3
        recent = memory.get_recent_turns()
        assert recent[0].user_query == "질문 2"
        assert recent[-1].user_query == "질문 4"

    def test_get_recent_turns_with_limit(self, existing_memory_state):
        """get_recent_turns(n) 제한 반환"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory.from_state(existing_memory_state)

        # 최근 2턴만
        recent_2 = memory.get_recent_turns(2)
        assert len(recent_2) == 2
        assert recent_2[0].user_query == "중고차 계약 취소"
        assert recent_2[1].user_query == "온라인 쇼핑몰 반품"

        # 최근 1턴만
        recent_1 = memory.get_recent_turns(1)
        assert len(recent_1) == 1
        assert recent_1[0].user_query == "온라인 쇼핑몰 반품"


class TestMemorySaveNode:
    """memory_save_node LangGraph 노드 테스트"""

    def test_save_need_rag_turn(self, sample_need_rag_state):
        """NEED_RAG 모드 state → rag_conversation_memory 업데이트 반환"""
        from app.supervisor.nodes.memory_save import memory_save_node

        result = memory_save_node(sample_need_rag_state)

        # 메모리 업데이트 반환
        assert "rag_conversation_memory" in result
        memory_list = result["rag_conversation_memory"]
        assert len(memory_list) == 1

        # 저장된 내용 확인
        turn = memory_list[0]
        assert turn["user_query"] == "헬스장 환불이 안된다고 합니다"
        assert "소비자기본법 제17조" in turn["answer_summary"]
        assert turn["mode"] == "NEED_RAG"

    def test_skip_no_retrieval_mode(self, sample_no_retrieval_state):
        """NO_RETRIEVAL 모드 → 빈 dict 반환"""
        from app.supervisor.nodes.memory_save import memory_save_node

        result = memory_save_node(sample_no_retrieval_state)

        # 빈 dict 반환 (메모리 업데이트 없음)
        assert result == {}

    def test_skip_need_clarification_mode(self, sample_need_clarification_state):
        """NEED_CLARIFICATION 모드 → 빈 dict 반환"""
        from app.supervisor.nodes.memory_save import memory_save_node

        result = memory_save_node(sample_need_clarification_state)

        assert result == {}

    def test_skip_empty_query(self):
        """user_query 빈 문자열 → 빈 dict 반환"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "mode": "NEED_RAG",
            "user_query": "",  # 빈 문자열
            "final_answer": "답변 내용",
            "rag_conversation_memory": [],
        }

        result = memory_save_node(state)
        assert result == {}

    def test_skip_empty_final_answer(self):
        """final_answer 빈 문자열 → 빈 dict 반환"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "mode": "NEED_RAG",
            "user_query": "질문 내용",
            "final_answer": "",  # 빈 문자열
            "rag_conversation_memory": [],
        }

        result = memory_save_node(state)
        assert result == {}

    def test_accumulate_turns(self, sample_need_rag_state, existing_memory_state):
        """여러 턴 누적 저장 확인"""
        from app.supervisor.nodes.memory_save import memory_save_node

        # 기존 메모리 3개 턴
        state_with_existing = sample_need_rag_state.copy()
        state_with_existing["rag_conversation_memory"] = existing_memory_state

        result = memory_save_node(state_with_existing)

        # 기존 3개 + 새로운 1개 = 4개
        memory_list = result["rag_conversation_memory"]
        assert len(memory_list) == 4

        # 마지막 턴이 새로 추가된 것
        last_turn = memory_list[-1]
        assert last_turn["user_query"] == "헬스장 환불이 안된다고 합니다"

    def test_window_overflow_in_node(self, existing_memory_state):
        """노드에서 윈도우 초과 처리"""
        from app.supervisor.nodes.memory_save import memory_save_node

        # 이미 5개 턴이 있는 메모리
        five_turns = existing_memory_state + [
            {"user_query": "Q4", "answer_summary": "A4", "mode": "NEED_RAG"},
            {"user_query": "Q5", "answer_summary": "A5", "mode": "NEED_RAG"},
        ]

        state = {
            "mode": "NEED_RAG",
            "user_query": "Q6",  # 6번째 턴
            "final_answer": "A6",
            "rag_conversation_memory": five_turns,
        }

        result = memory_save_node(state)

        # 윈도우 크기 5 유지
        memory_list = result["rag_conversation_memory"]
        assert len(memory_list) == 5

        # 가장 오래된 턴(헬스장 환불 문의) 제거됨
        assert memory_list[0]["user_query"] != "헬스장 환불 문의"
        # 최신 턴(Q6) 포함
        assert memory_list[-1]["user_query"] == "Q6"

    def test_long_answer_truncation_in_node(self, long_answer_text):
        """노드에서 긴 답변 자동 절단"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "mode": "NEED_RAG",
            "user_query": "긴 답변 요청",
            "final_answer": long_answer_text,
            "rag_conversation_memory": [],
        }

        result = memory_save_node(state)

        memory_list = result["rag_conversation_memory"]
        saved_answer = memory_list[0]["answer_summary"]

        # 200자 + '...' 제한
        assert len(saved_answer) <= 203
        assert saved_answer.endswith("...")


class TestEdgeCases:
    """Edge cases 테스트"""

    def test_from_state_with_none(self):
        """from_state(None) → 빈 메모리"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory.from_state(None)
        assert len(memory) == 0

    def test_from_state_with_empty_list(self):
        """from_state([]) → 빈 메모리"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory.from_state([])
        assert len(memory) == 0

    def test_node_missing_mode_field(self):
        """state에 mode 필드 없음 → 빈 dict 반환"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {
            "user_query": "질문",
            "final_answer": "답변",
            "rag_conversation_memory": [],
        }

        result = memory_save_node(state)
        assert result == {}

    def test_node_missing_rag_conversation_memory(self):
        """state에 rag_conversation_memory 필드 없음 → 새로 생성"""
        from app.supervisor.nodes.memory_save import memory_save_node

        state = {"mode": "NEED_RAG", "user_query": "질문", "final_answer": "답변"}

        result = memory_save_node(state)

        # 새로 생성됨
        assert "rag_conversation_memory" in result
        assert len(result["rag_conversation_memory"]) == 1

    def test_custom_window_size(self):
        """커스텀 윈도우 크기 설정"""
        from app.supervisor.state.memory import RAGConversationMemory

        memory = RAGConversationMemory(window_size=2)

        # 3개 추가
        for i in range(3):
            memory.add_turn(
                mode="NEED_RAG", query=f"Q{i + 1}", answer_summary=f"A{i + 1}"
            )

        # 윈도우 크기 2 유지
        assert len(memory) == 2
        recent = memory.get_recent_turns()
        assert recent[0].user_query == "Q2"
        assert recent[1].user_query == "Q3"

    def test_answer_summary_exactly_200_chars(self):
        """정확히 200자 답변 → 절단 없음"""
        from app.supervisor.state.memory import RAGConversationMemory

        answer_200 = "A" * 200
        memory = RAGConversationMemory()
        memory.add_turn(mode="NEED_RAG", query="Q", answer_summary=answer_200)

        recent = memory.get_recent_turns()[0]
        # 정확히 200자면 '...' 없음
        assert len(recent.answer_summary) == 200
        assert not recent.answer_summary.endswith("...")

    def test_answer_summary_201_chars(self):
        """201자 답변 → 200자 + '...'"""
        from app.supervisor.state.memory import RAGConversationMemory

        answer_201 = "A" * 201
        memory = RAGConversationMemory()
        memory.add_turn(mode="NEED_RAG", query="Q", answer_summary=answer_201)

        recent = memory.get_recent_turns()[0]
        # 200자 + '...'
        assert len(recent.answer_summary) == 203
        assert recent.answer_summary.endswith("...")
