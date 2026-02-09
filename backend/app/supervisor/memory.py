"""
똑소리 프로젝트 - 메모리 관리 모듈
작성일: 2026-01-20
PR-3: 대화 메모리 정책 및 관리
최종 수정: 2026-01-28 (Track 3: DB 통합)

메모리 정책:
- general: 대화 기억 없음 (1질문-1답변)
- dispute: 30턴 기억 + Compact (구조화 필드 추출, 15턴 → 30턴으로 증가)

토큰 사용량 분석 기반 설정:
- 한국어 1글자 ≈ 1토큰 (영어 대비 2.36배)
- 턴당 평균 ~1,000 토큰
- EXAONE 3.5 2.4B: 32K 컨텍스트 제한
- 30턴 × 1000 = 30K (94% 사용) - DB 기반 메모리로 관리
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryPolicy:
    """메모리 정책 데이터클래스"""

    max_turns: int
    compact_enabled: bool
    sliding_window: int = 0  # Compact 후 유지할 턴 수


# 채팅 타입별 메모리 정책
MEMORY_POLICIES: Dict[str, MemoryPolicy] = {
    "general": MemoryPolicy(
        max_turns=10, compact_enabled=False, sliding_window=5
    ),  # ← 멀티 디바이스 동기화를 위해 메모리 활성화
    "dispute": MemoryPolicy(
        max_turns=30,  # 15 → 30 (DB 기반 메모리로 증가)
        compact_enabled=True,
        sliding_window=10,  # 5 → 10 (DB 기반 메모리로 증가)
    ),
}


@dataclass
class ConversationTurn:
    """대화 턴 데이터"""

    role: Literal["user", "assistant"]
    content: str
    turn_number: int
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None


@dataclass
class CompactSummary:
    """Compact 요약 데이터"""

    purchase_item: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_amount: Optional[str] = None
    purchase_place: Optional[str] = None
    dispute_type: Optional[str] = None
    dispute_details: Optional[str] = None
    desired_resolution: Optional[str] = None
    key_facts: Optional[List[str]] = None
    compacted_turn_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purchase_item": self.purchase_item,
            "purchase_date": self.purchase_date,
            "purchase_amount": self.purchase_amount,
            "purchase_place": self.purchase_place,
            "dispute_type": self.dispute_type,
            "dispute_details": self.dispute_details,
            "desired_resolution": self.desired_resolution,
            "key_facts": self.key_facts or [],
            "compacted_turn_count": self.compacted_turn_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompactSummary":
        return cls(
            purchase_item=data.get("purchase_item"),
            purchase_date=data.get("purchase_date"),
            purchase_amount=data.get("purchase_amount"),
            purchase_place=data.get("purchase_place"),
            dispute_type=data.get("dispute_type"),
            dispute_details=data.get("dispute_details"),
            desired_resolution=data.get("desired_resolution"),
            key_facts=data.get("key_facts"),
            compacted_turn_count=data.get("compacted_turn_count", 0),
        )


class ConversationMemory:
    """대화 메모리 관리 클래스"""

    def __init__(
        self,
        chat_type: Literal["general", "dispute"] = "dispute",
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        use_db: bool = False,
    ):
        self.chat_type = chat_type
        self.session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id
        self.use_db = use_db
        self.policy = MEMORY_POLICIES.get(chat_type, MEMORY_POLICIES["dispute"])
        self.turns: List[ConversationTurn] = []
        self.compact_summary: Optional[CompactSummary] = None
        self.total_turn_count: int = 0
        self.conversation_id: Optional[Any] = None

        # DB integration
        self.db = None
        if self.use_db:
            from .persistence.db import ConversationDB

            self.db = ConversationDB()
            # Load existing conversation will be done asynchronously
            self._db_loaded = False

    async def _load_from_db(self) -> None:
        """Load existing conversation from DB"""
        if not self.db or self._db_loaded:
            return

        try:
            # Get conversation by session_id
            conv = await self.db.get_conversation_by_session(self.session_id)

            if conv:
                self.conversation_id = conv["conversation_id"]
                self.total_turn_count = conv["turn_count"]

                # Load recent turns (sliding window)
                turns = await self.db.get_conversation_history(
                    self.conversation_id, limit=self.policy.sliding_window
                )

                # Convert DB turns to ConversationTurn objects (reverse order)
                self.turns = []
                for turn in reversed(turns):
                    self.turns.append(
                        ConversationTurn(
                            role=turn["role"],
                            content=turn["content"],
                            turn_number=turn["turn_number"],
                            metadata=turn.get("metadata", {}),
                            timestamp=turn.get("created_at"),
                        )
                    )

                # Load summary
                summary = await self.db.get_summary(self.conversation_id)
                if summary:
                    self.compact_summary = CompactSummary.from_dict(
                        {
                            "purchase_item": summary.get("purchase_item"),
                            "purchase_date": summary.get("purchase_date"),
                            "purchase_amount": summary.get("purchase_amount"),
                            "purchase_place": summary.get("purchase_place"),
                            "dispute_type": summary.get("dispute_type"),
                            "dispute_details": summary.get("dispute_details"),
                            "desired_resolution": summary.get("desired_resolution"),
                            "key_facts": summary.get("key_facts", {}),
                            "compacted_turn_count": summary.get(
                                "compacted_turn_count", 0
                            ),
                        }
                    )

                logger.info(
                    f"[Memory] Loaded from DB: session_id={self.session_id}, "
                    f"conv_id={self.conversation_id}, turns={len(self.turns)}"
                )
            else:
                # Create new conversation in DB
                self.conversation_id = await self.db.create_conversation(
                    session_id=self.session_id,
                    chat_type=self.chat_type,
                    user_id=self.user_id,
                )
                logger.info(
                    f"[Memory] Created new conversation: session_id={self.session_id}, "
                    f"conv_id={self.conversation_id}"
                )

            self._db_loaded = True
        except Exception as e:
            logger.error(
                f"[Memory] Failed to load from DB: {e}, "
                f"session_id={self.session_id}, user_id={self.user_id}, "
                f"chat_type={self.chat_type}",
                exc_info=True,
            )
            # Continue with in-memory mode
            self.use_db = False
            self.db = None

    async def add_turn(
        self,
        role: Literal["user", "assistant"],
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """새 대화 턴 추가 (with DB persistence)"""
        if self.policy.max_turns == 0:
            # general 타입: 메모리 없음
            return

        # Ensure DB is loaded
        if self.use_db and not self._db_loaded:
            await self._load_from_db()

        self.total_turn_count += 1
        turn = ConversationTurn(
            role=role,
            content=content,
            turn_number=self.total_turn_count,
            metadata=metadata,
            timestamp=datetime.now(),
        )
        self.turns.append(turn)

        logger.debug(
            f"[Memory] Added turn {self.total_turn_count}: {role}, len={len(content)}"
        )

        # Save to DB
        if self.use_db and self.db and self.conversation_id:
            try:
                await self.db.add_turn(
                    conversation_id=self.conversation_id,
                    role=role,
                    content=content,
                    metadata=metadata,
                )
            except Exception as e:
                logger.error(f"[Memory] Failed to save turn to DB: {e}", exc_info=True)
                # BUG-5 fix: user 메시지 저장 실패 시 예외 전파하여 API에서 500 반환
                # assistant 응답은 재생성 가능하므로 삼킴
                if role == "user":
                    raise

        # Compact 트리거 체크
        if self._should_compact():
            await self._trigger_compact()

    def _should_compact(self) -> bool:
        """Compact 필요 여부 확인"""
        if not self.policy.compact_enabled:
            return False
        return len(self.turns) >= self.policy.max_turns

    async def _trigger_compact(self) -> None:
        """Compact 실행 (with DB persistence)"""
        from .compact import compact_conversation

        logger.info(
            f"[Memory] Triggering Compact: {len(self.turns)} turns -> {self.policy.sliding_window} turns"
        )

        # 현재 요약과 모든 턴을 Compact 함수에 전달
        new_summary = compact_conversation(
            turns=self.turns,
            existing_summary=self.compact_summary,
        )

        # Save summary to DB
        if self.use_db and self.db and self.conversation_id:
            try:
                await self.db.save_summary(
                    conversation_id=self.conversation_id,
                    summary_data=new_summary.to_dict(),
                    compacted_turn_count=self.total_turn_count,
                )
            except Exception as e:
                logger.error(
                    f"[Memory] Failed to save summary to DB: {e}", exc_info=True
                )

        # 최근 N턴만 유지
        self.turns = self.turns[-self.policy.sliding_window :]
        self.compact_summary = new_summary

        logger.info(
            f"[Memory] Compact complete: kept {len(self.turns)} turns, summary updated"
        )

    def get_context_for_llm(self) -> Dict[str, Any]:
        """
        LLM에 전달할 컨텍스트 반환 (동기 버전, 하위 호환성)

        Note: DB 기반 메모리를 사용하려면 먼저 add_turn()을 호출하여 DB를 로드해야 합니다.
        """
        if self.policy.max_turns == 0:
            return {"conversation_history": [], "compact_summary": None}

        history = [
            {"role": t.role, "content": t.content, "turn": t.turn_number}
            for t in self.turns
        ]

        return {
            "conversation_history": history,
            "compact_summary": (
                self.compact_summary.to_dict() if self.compact_summary else None
            ),
        }

    async def get_context_for_llm_async(self) -> Dict[str, Any]:
        """LLM에 전달할 컨텍스트 반환 (비동기 버전, DB 로딩 포함)"""
        if self.policy.max_turns == 0:
            return {"conversation_history": [], "compact_summary": None}

        # Ensure DB is loaded
        if self.use_db and not self._db_loaded:
            await self._load_from_db()

        history = [
            {"role": t.role, "content": t.content, "turn": t.turn_number}
            for t in self.turns
        ]

        return {
            "conversation_history": history,
            "compact_summary": (
                self.compact_summary.to_dict() if self.compact_summary else None
            ),
        }

    def get_turn_count(self) -> int:
        """현재 저장된 턴 수"""
        return len(self.turns)

    def get_total_turn_count(self) -> int:
        """전체 대화 턴 수 (Compact로 삭제된 것 포함)"""
        return self.total_turn_count

    def save_metadata(self, key: str, value: Any) -> None:
        """Save metadata associated with the conversation session."""
        if not hasattr(self, "_metadata"):
            self._metadata = {}
        self._metadata[key] = value

    def get_metadata(self, key: str) -> Optional[Any]:
        """Retrieve metadata associated with the conversation session."""
        if not hasattr(self, "_metadata"):
            return None
        return self._metadata.get(key)

    def clear(self) -> None:
        """메모리 초기화"""
        self.turns = []
        self.compact_summary = None
        self.total_turn_count = 0

    def to_dict(self) -> Dict[str, Any]:
        """직렬화"""
        return {
            "chat_type": self.chat_type,
            "turns": [
                {
                    "role": t.role,
                    "content": t.content,
                    "turn_number": t.turn_number,
                    "metadata": t.metadata,
                }
                for t in self.turns
            ],
            "compact_summary": (
                self.compact_summary.to_dict() if self.compact_summary else None
            ),
            "total_turn_count": self.total_turn_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMemory":
        """역직렬화"""
        memory = cls(chat_type=data.get("chat_type", "dispute"))
        memory.total_turn_count = data.get("total_turn_count", 0)

        for turn_data in data.get("turns", []):
            turn = ConversationTurn(
                role=turn_data["role"],
                content=turn_data["content"],
                turn_number=turn_data["turn_number"],
                metadata=turn_data.get("metadata"),
            )
            memory.turns.append(turn)

        if data.get("compact_summary"):
            memory.compact_summary = CompactSummary.from_dict(data["compact_summary"])

        return memory


def get_memory_policy(chat_type: str) -> MemoryPolicy:
    """채팅 타입에 해당하는 메모리 정책 반환"""
    return MEMORY_POLICIES.get(chat_type, MEMORY_POLICIES["dispute"])


def should_use_memory(chat_type: str) -> bool:
    """메모리 사용 여부 확인"""
    policy = get_memory_policy(chat_type)
    return policy.max_turns > 0
