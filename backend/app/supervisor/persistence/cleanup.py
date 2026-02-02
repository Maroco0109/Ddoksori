"""
똑소리 프로젝트 - 대화 메모리 정리 서비스

작성일: 2026-01-28
최종 수정: 2026-01-28

[역할 및 책임]
만료된 게스트 세션을 주기적으로 정리하는 백그라운드 서비스입니다.
- 게스트 세션 만료 확인 및 삭제
- 비활성 대화 정리 (옵션)
- Cleanup 통계 로깅

[사용 예시]
    from app.supervisor.persistence.cleanup import ConversationCleanupService
    from app.common.config import get_config

    config = get_config()
    cleanup_service = ConversationCleanupService(config.database, config.memory)

    # FastAPI startup event에서
    await cleanup_service.start()

    # FastAPI shutdown event에서
    await cleanup_service.stop()
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.common.config import DatabaseConfig, MemoryConfig, get_config
from app.supervisor.persistence.db import ConversationDB

logger = logging.getLogger(__name__)


class ConversationCleanupService:
    """
    대화 메모리 정리 서비스.

    주기적으로 만료된 게스트 세션을 정리하는 백그라운드 태스크를 실행합니다.
    FastAPI의 lifespan 이벤트에서 시작/종료할 수 있습니다.
    """

    def __init__(
        self,
        db_config: Optional[DatabaseConfig] = None,
        memory_config: Optional[MemoryConfig] = None,
    ):
        """
        ConversationCleanupService를 초기화합니다.

        Args:
            db_config: 데이터베이스 설정 (None이면 get_config()에서 가져옴)
            memory_config: 메모리 설정 (None이면 get_config()에서 가져옴)
        """
        config = get_config()
        self.db_config = db_config or config.database
        self.memory_config = memory_config or config.memory

        self.db = ConversationDB(self.db_config)
        self.interval_hours = self.memory_config.cleanup_interval_hours
        self.interval_seconds = self.interval_hours * 3600

        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """
        정리 서비스를 시작합니다.

        백그라운드 태스크를 생성하여 주기적으로 cleanup을 실행합니다.
        """
        if self._running:
            logger.warning("[CleanupService] 이미 실행 중입니다.")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_cleanup_loop())
        logger.info(
            f"[CleanupService] 정리 서비스 시작 (간격: {self.interval_hours}시간)"
        )

    async def stop(self) -> None:
        """
        정리 서비스를 종료합니다.

        백그라운드 태스크를 취소하고 종료를 기다립니다.
        """
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("[CleanupService] 정리 서비스 종료")

    async def _run_cleanup_loop(self) -> None:
        """
        정리 루프를 실행합니다.

        주기적으로 cleanup_expired_sessions를 호출합니다.
        """
        while self._running:
            try:
                await self._perform_cleanup()
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                logger.info("[CleanupService] 정리 루프 취소됨")
                break
            except Exception as e:
                logger.error(f"[CleanupService] 정리 실패: {e}", exc_info=True)
                # 에러 발생 시 짧은 대기 후 재시도
                await asyncio.sleep(60)

    async def _perform_cleanup(self) -> None:
        """
        만료된 세션을 정리합니다.

        실제 cleanup 로직을 실행하고 통계를 로깅합니다.
        """
        try:
            start_time = datetime.now()
            deleted_count = await self.db.cleanup_expired_sessions()
            elapsed = (datetime.now() - start_time).total_seconds()

            if deleted_count > 0:
                logger.info(
                    f"[CleanupService] 정리 완료: {deleted_count}개 세션 삭제 "
                    f"(소요 시간: {elapsed:.2f}초)"
                )
            else:
                logger.debug("[CleanupService] 만료된 세션 없음")

        except Exception as e:
            logger.error(f"[CleanupService] 정리 중 오류 발생: {e}", exc_info=True)
            raise

    async def run_once(self) -> int:
        """
        정리를 한 번 실행합니다 (테스트 또는 수동 실행용).

        Returns:
            삭제된 세션 수
        """
        logger.info("[CleanupService] 수동 정리 실행")
        await self._perform_cleanup()
        return await self.db.cleanup_expired_sessions()


# ============================================================
# 싱글톤 인스턴스 관리
# ============================================================

_cleanup_service_instance: Optional[ConversationCleanupService] = None


def get_cleanup_service() -> ConversationCleanupService:
    """
    CleanupService 싱글톤 인스턴스를 반환합니다.

    Returns:
        ConversationCleanupService 인스턴스
    """
    global _cleanup_service_instance
    if _cleanup_service_instance is None:
        _cleanup_service_instance = ConversationCleanupService()
    return _cleanup_service_instance
