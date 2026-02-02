"""
LLMProviderFactory - 통합 LLM 클라이언트 팩토리

OpenAI, EXAONE (vLLM), Anthropic 클라이언트를 싱글톤으로 관리.
도메인별 EXAONE 인스턴스 지원 (Retrieval Agent용).

사용 예시:
    from app.llm.providers import get_openai_client, get_exaone_client

    # OpenAI 클라이언트 (싱글톤)
    openai = get_openai_client()

    # 도메인별 EXAONE 클라이언트
    exaone_law = get_exaone_client(domain="law")
"""

import logging
import os
from typing import Dict, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# 클라이언트 캐시 (싱글톤)
_openai_client: Optional[OpenAI] = None
_anthropic_client = None  # Optional[Anthropic]
_shared_exaone_client: Optional[OpenAI] = None
_domain_exaone_clients: Dict[str, OpenAI] = {}


class LLMProviderFactory:
    """
    통합 LLM 클라이언트 팩토리.

    모든 클라이언트는 싱글톤으로 관리되어 연결을 재사용합니다.
    """

    @classmethod
    def get_openai_client(cls, timeout: float = 30.0) -> Optional[OpenAI]:
        """
        OpenAI 클라이언트 반환 (싱글톤).

        환경변수:
        - OPENAI_API_KEY: API 키 (필수)

        Args:
            timeout: 요청 타임아웃 (초)

        Returns:
            OpenAI 클라이언트 또는 API 키 미설정 시 None
        """
        global _openai_client

        if _openai_client is not None:
            return _openai_client

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("[LLMProvider] OPENAI_API_KEY not set")
            return None

        _openai_client = OpenAI(
            api_key=api_key,
            timeout=timeout,
        )
        logger.info("[LLMProvider] OpenAI client initialized")
        return _openai_client

    @classmethod
    def get_exaone_client(
        cls,
        domain: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Optional[OpenAI]:
        """
        EXAONE vLLM 클라이언트 반환.

        도메인별 독립 인스턴스 또는 공유 인스턴스 반환.

        환경변수:
        - RETRIEVAL_LLM_{DOMAIN}_URL: 도메인별 URL (예: RETRIEVAL_LLM_LAW_URL)
        - EXAONE_RUNPOD_URL: 공유 URL (도메인별 URL 미설정 시 fallback)
        - EXAONE_RUNPOD_API_KEY: API 키

        Args:
            domain: 도메인 키 (law, criteria, case, counsel)
            timeout: 요청 타임아웃 (초)

        Returns:
            OpenAI 호환 클라이언트 (vLLM용) 또는 None
        """
        global _shared_exaone_client, _domain_exaone_clients

        api_key = os.getenv("EXAONE_RUNPOD_API_KEY", "dummy")

        # 도메인별 URL 확인
        if domain:
            domain_url = os.getenv(f"RETRIEVAL_LLM_{domain.upper()}_URL")
            if domain_url:
                if domain not in _domain_exaone_clients:
                    _domain_exaone_clients[domain] = OpenAI(
                        base_url=domain_url,
                        api_key=api_key,
                        timeout=timeout,
                    )
                    logger.info(
                        f"[LLMProvider] EXAONE client for domain '{domain}': {domain_url}"
                    )
                return _domain_exaone_clients[domain]

        # 공유 클라이언트 fallback
        if _shared_exaone_client is None:
            runpod_url = os.getenv("EXAONE_RUNPOD_URL")
            if runpod_url:
                _shared_exaone_client = OpenAI(
                    base_url=runpod_url,
                    api_key=api_key,
                    timeout=timeout,
                )
                logger.info(f"[LLMProvider] Shared EXAONE client: {runpod_url}")

        return _shared_exaone_client

    @classmethod
    def get_anthropic_client(cls, timeout: float = 60.0):
        """
        Anthropic 클라이언트 반환 (싱글톤).

        환경변수:
        - ANTHROPIC_API_KEY: API 키 (필수)

        Args:
            timeout: 요청 타임아웃 (초)

        Returns:
            Anthropic 클라이언트 또는 API 키 미설정/패키지 미설치 시 None
        """
        global _anthropic_client

        if _anthropic_client is not None:
            return _anthropic_client

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[LLMProvider] ANTHROPIC_API_KEY not set")
            return None

        try:
            from anthropic import Anthropic

            _anthropic_client = Anthropic(
                api_key=api_key,
                timeout=timeout,
            )
            logger.info("[LLMProvider] Anthropic client initialized")
            return _anthropic_client
        except ImportError:
            logger.warning("[LLMProvider] anthropic package not installed")
            return None

    @classmethod
    def reset_all(cls) -> None:
        """모든 클라이언트 리셋 (테스트용)."""
        global \
            _openai_client, \
            _anthropic_client, \
            _shared_exaone_client, \
            _domain_exaone_clients
        _openai_client = None
        _anthropic_client = None
        _shared_exaone_client = None
        _domain_exaone_clients = {}
        logger.debug("[LLMProvider] All clients reset")


# 편의 함수
def get_openai_client(timeout: float = 30.0) -> Optional[OpenAI]:
    """OpenAI 클라이언트 반환 (싱글톤)."""
    return LLMProviderFactory.get_openai_client(timeout)


def get_exaone_client(
    domain: Optional[str] = None,
    timeout: float = 30.0,
) -> Optional[OpenAI]:
    """EXAONE 클라이언트 반환."""
    return LLMProviderFactory.get_exaone_client(domain, timeout)


def get_anthropic_client(timeout: float = 60.0):
    """Anthropic 클라이언트 반환 (싱글톤)."""
    return LLMProviderFactory.get_anthropic_client(timeout)


def reset_all_clients() -> None:
    """모든 클라이언트 리셋 (테스트용)."""
    LLMProviderFactory.reset_all()
