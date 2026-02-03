"""
똑소리 프로젝트 - Tool Calling LLM 클라이언트
작성일: 2026-01-21
S3-PR3: @tool 하이브리드 도입

LangChain의 ChatOpenAI를 사용하여 RunPod vLLM 서버에 Tool Calling을 지원하는 클라이언트.
vLLM의 OpenAI-compatible API를 활용하여 bind_tools()를 통한 도구 바인딩 지원.
"""

import logging
import os
from typing import Any, List, Optional

import requests

logger = logging.getLogger(__name__)


class ToolCallingUnavailableError(Exception):
    """Tool Calling LLM 서버 접근 불가 예외"""

    pass


class ToolCallingClient:
    """
    Tool Calling을 지원하는 LLM 클라이언트

    LangChain의 ChatOpenAI를 사용하여 vLLM 서버에 연결하고,
    bind_tools()를 통해 도구를 바인딩할 수 있습니다.
    """

    def __init__(
        self,
        runpod_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.runpod_url = runpod_url or os.getenv("EXAONE_RUNPOD_URL")
        self.api_key = api_key or os.getenv("EXAONE_RUNPOD_API_KEY", "dummy")
        self.model = model or os.getenv(
            "EXAONE_MODEL", "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"
        )
        self.timeout_ms = int(os.getenv("LLM_TOOL_TIMEOUT_MS", "5000"))
        self.timeout_sec = self.timeout_ms / 1000

        self._llm: Optional[Any] = None
        self._is_available: Optional[bool] = None

        logger.info(
            f"[ToolCallingClient] Initialized with model={self.model}, "
            f"timeout={self.timeout_ms}ms"
        )

    def health_check(self) -> bool:
        """
        RunPod vLLM 서버 헬스체크
        """
        if not self.runpod_url:
            logger.warning("[ToolCallingClient] EXAONE_RUNPOD_URL not configured")
            return False

        try:
            base_url = self.runpod_url.rstrip("/").replace("/v1", "")
            health_url = f"{base_url}/health"

            logger.debug(f"[ToolCallingClient] Health check: {health_url}")
            resp = requests.get(health_url, timeout=5)

            if resp.status_code == 200:
                logger.info("[ToolCallingClient] RunPod vLLM server is healthy")
                return True
            else:
                logger.warning(
                    f"[ToolCallingClient] Health check failed: {resp.status_code}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.warning("[ToolCallingClient] Health check timeout")
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("[ToolCallingClient] Health check connection error")
            return False
        except Exception as e:
            logger.warning(f"[ToolCallingClient] Health check error: {e}")
            return False

    def is_available(self) -> bool:
        """LLM 사용 가능 여부 (캐싱)"""
        if self._is_available is None:
            self._is_available = self.health_check()
        return self._is_available

    def reset_availability(self):
        """가용성 캐시 리셋"""
        self._is_available = None
        self._llm = None

    def _get_llm(self) -> Any:
        """
        LangChain ChatOpenAI 클라이언트 반환 (지연 초기화)
        """
        if not self._llm:
            if not self.runpod_url:
                raise ToolCallingUnavailableError("EXAONE_RUNPOD_URL not configured")

            try:
                from langchain_openai import ChatOpenAI

                self._llm = ChatOpenAI(
                    base_url=self.runpod_url,
                    api_key=self.api_key,
                    model=self.model,
                    temperature=0.1,
                    max_tokens=512,
                    timeout=self.timeout_sec,
                )
                logger.info(f"[ToolCallingClient] ChatOpenAI initialized: {self.model}")

            except ImportError:
                raise ToolCallingUnavailableError(
                    "langchain-openai not installed. Run: pip install langchain-openai"
                )
            except Exception as e:
                raise ToolCallingUnavailableError(
                    f"Failed to initialize ChatOpenAI: {e}"
                )

        return self._llm

    def bind_tools(self, tools: List[Any]) -> Any:
        """
        도구를 LLM에 바인딩
        """
        if not self.is_available():
            raise ToolCallingUnavailableError("RunPod LLM server unavailable")

        llm = self._get_llm()

        try:
            llm_with_tools = llm.bind_tools(tools)
            logger.info(f"[ToolCallingClient] Bound {len(tools)} tools to LLM")
            return llm_with_tools
        except Exception as e:
            logger.error(f"[ToolCallingClient] Failed to bind tools: {e}")
            raise ToolCallingUnavailableError(f"Failed to bind tools: {e}")
