"""
똑소리 프로젝트 - EXAONE 3.5 2.4B LLM 클라이언트
작성일: 2026-01-17
S2-8: RunPod GPU Pod 배포 + vLLM OpenAI-compatible API

EXAONE 3.5 2.4B 모델을 RunPod에서 vLLM으로 서빙하고,
OpenAI SDK를 통해 호출하는 클라이언트.
RunPod 장애 시 규칙 기반 폴백을 위해 예외를 발생시킴.
"""

import logging
import os
from typing import Optional

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """LLM 서버 접근 불가 예외"""

    pass


class ExaoneLLMClient:
    """
    EXAONE 3.5 2.4B LLM 클라이언트 (RunPod GPU Pod)

    vLLM의 OpenAI-compatible API를 사용하여 EXAONE 모델 호출.
    RunPod 장애 시 LLMUnavailableError를 발생시켜 규칙 기반 폴백 유도.

    환경 변수:
        EXAONE_RUNPOD_URL: RunPod vLLM 서버 URL (예: https://<pod-id>-8000.proxy.runpod.net/v1)
        EXAONE_RUNPOD_API_KEY: RunPod API 키 (vLLM은 보통 필요 없음)
        EXAONE_MODEL: 모델 이름 (기본: LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct)
        EXAONE_TEMPERATURE: 생성 온도 (기본: 0.1)
        EXAONE_MAX_TOKENS: 최대 토큰 수 (기본: 512)
        EXAONE_TIMEOUT: 요청 타임아웃 초 (기본: 10)

    Example:
        >>> client = ExaoneLLMClient()
        >>> if client.is_available():
        ...     response = client.generate(
        ...         system_prompt="당신은 AI 어시스턴트입니다.",
        ...         user_prompt="안녕하세요"
        ...     )
        ...     print(response)
    """

    def __init__(self):
        self.runpod_url = os.getenv("EXAONE_RUNPOD_URL")
        self.api_key = os.getenv("EXAONE_RUNPOD_API_KEY", "dummy")
        self.model = os.getenv("EXAONE_MODEL", "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct")
        self.model_size = os.getenv("EXAONE_MODEL_SIZE", "7.8B")
        self.timeout = int(os.getenv("EXAONE_TIMEOUT", "10"))

        # 모델 크기에 따른 파라미터 자동 조정
        if self.model_size == "7.8B" or "7.8B" in self.model:
            self.temperature = float(os.getenv("EXAONE_TEMPERATURE", "0.3"))
            self.max_tokens = int(os.getenv("EXAONE_MAX_TOKENS", "1024"))
        elif self.model_size == "32B" or "32B" in self.model:
            self.temperature = float(os.getenv("EXAONE_TEMPERATURE", "0.3"))
            self.max_tokens = int(os.getenv("EXAONE_MAX_TOKENS", "2048"))
        else:  # 2.4B 또는 기본값
            self.temperature = float(os.getenv("EXAONE_TEMPERATURE", "0.1"))
            self.max_tokens = int(os.getenv("EXAONE_MAX_TOKENS", "512"))

        self._client: Optional[OpenAI] = None
        self._is_available: Optional[bool] = None

        logger.info(
            f"[ExaoneLLMClient] Initialized with model={self.model}, "
            f"size={self.model_size}, temp={self.temperature}, max_tokens={self.max_tokens}"
        )

    def health_check(self) -> bool:
        """
        RunPod vLLM 서버 헬스체크

        vLLM 서버의 /health 엔드포인트를 호출하여 서버 상태 확인.

        Returns:
            서버가 정상이면 True, 그렇지 않으면 False
        """
        if not self.runpod_url:
            logger.warning("[ExaoneLLMClient] EXAONE_RUNPOD_URL not configured")
            return False

        try:
            # /v1 제거하고 /health 호출
            base_url = self.runpod_url.rstrip("/").replace("/v1", "")
            health_url = f"{base_url}/health"

            logger.debug(f"[ExaoneLLMClient] Health check: {health_url}")
            resp = requests.get(health_url, timeout=5)

            if resp.status_code == 200:
                logger.info("[ExaoneLLMClient] RunPod vLLM server is healthy")
                return True
            else:
                logger.warning(
                    f"[ExaoneLLMClient] Health check failed: {resp.status_code}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.warning("[ExaoneLLMClient] Health check timeout")
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("[ExaoneLLMClient] Health check connection error")
            return False
        except Exception as e:
            logger.warning(f"[ExaoneLLMClient] Health check error: {e}")
            return False

    def is_available(self) -> bool:
        """
        LLM 사용 가능 여부 (캐싱)

        첫 호출 시 헬스체크를 수행하고 결과를 캐싱.
        인스턴스 생명주기 동안 재사용.

        Returns:
            LLM 서버 사용 가능 여부
        """
        if self._is_available is None:
            self._is_available = self.health_check()
        return self._is_available

    def reset_availability(self):
        """
        가용성 캐시 리셋

        다음 is_available() 호출 시 헬스체크를 다시 수행하도록 함.
        """
        self._is_available = None
        self._client = None

    def _get_client(self) -> OpenAI:
        """
        OpenAI 클라이언트 반환 (지연 초기화)

        Returns:
            OpenAI 클라이언트 인스턴스
        """
        if not self._client:
            self._client = OpenAI(
                base_url=self.runpod_url, api_key=self.api_key, timeout=self.timeout
            )
        return self._client

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        LLM 추론 실행

        Args:
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트

        Returns:
            LLM 생성 응답 텍스트

        Raises:
            LLMUnavailableError: 서버 접근 불가 시
        """
        if not self.is_available():
            raise LLMUnavailableError("RunPod LLM server unavailable")

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            content = response.choices[0].message.content
            if content is None:
                raise LLMUnavailableError("LLM returned empty response")

            logger.debug(f"[ExaoneLLMClient] Generated response: {content[:100]}...")

            if hasattr(response, "usage") and response.usage:
                logger.info(
                    f"[ExaoneLLMClient] Tokens - prompt: {response.usage.prompt_tokens}, "
                    f"completion: {response.usage.completion_tokens}"
                )

            return content

        except Exception as e:
            logger.error(f"[ExaoneLLMClient] Generation error: {e}")
            # 연결 오류 시 가용성 캐시 리셋
            self.reset_availability()
            raise LLMUnavailableError(f"LLM generation failed: {e}") from e
