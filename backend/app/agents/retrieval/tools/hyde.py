"""
HyDE (Hypothetical Document Embeddings) 모듈

쿼리에 대한 가상 법률 답변을 생성하여 검색 임베딩으로 사용합니다.
원본 쿼리 대신 가상 답변을 임베딩하면 실제 문서와의 의미적 유사도가 높아집니다.

참고: Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels" (2022)

사용법:
    hyde = HyDEGenerator()
    hypothetical_doc = await hyde.generate(query="노트북 환불 가능한가요?", domain="criteria")
    # 가상 답변의 임베딩을 벡터 검색에 사용
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 도메인별 HyDE 프롬프트 템플릿 (한국어 법률 용어 최적화)
HYDE_PROMPTS = {
    "law": """당신은 한국 소비자보호법 전문가입니다.
다음 소비자 질문에 대해 관련 법률 조문을 인용하여 답변해주세요.
실제 법률 조문처럼 구체적인 조항 번호와 내용을 포함하세요.

질문: {query}

답변:""",

    "criteria": """당신은 한국 소비자분쟁해결기준 전문가입니다.
다음 소비자 질문에 대해 분쟁해결기준 별표의 내용을 기반으로 답변해주세요.
품목별 보상 기준, 교환/환불 조건 등을 구체적으로 포함하세요.

질문: {query}

답변:""",

    "case": """당신은 한국소비자원 분쟁조정 전문가입니다.
다음 소비자 질문과 유사한 분쟁조정 사례의 결과를 작성해주세요.
사건 개요, 당사자 주장, 조정 결정 등을 포함하세요.

질문: {query}

답변:""",

    "counsel": """당신은 소비자상담 전문 상담사입니다.
다음 소비자 질문에 대해 실제 상담 사례처럼 답변해주세요.
관련 법률, 해결 절차, 주의사항 등을 포함하세요.

질문: {query}

답변:""",

    "default": """당신은 한국 소비자 분쟁 해결 전문가입니다.
다음 소비자 질문에 대해 관련 법률과 기준을 근거로 답변해주세요.

질문: {query}

답변:""",
}


class HyDEGenerator:
    """
    HyDE (Hypothetical Document Embeddings) 생성기.

    쿼리에 대한 가상 법률 답변을 생성하여 검색 품질을 향상시킵니다.
    도메인별 프롬프트로 한국어 법률 용어에 최적화된 가상 문서를 생성합니다.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
    ):
        """
        Args:
            model: 가상 답변 생성 모델 (기본: config.retrieval.hyde_model)
            max_tokens: 최대 토큰 수 (기본: config.retrieval.hyde_max_tokens)
            api_key: OpenAI API 키 (기본: OPENAI_API_KEY 환경변수)
        """
        from ....common.config import get_config
        config = get_config().retrieval

        self._model = model or config.hyde_model
        self._max_tokens = max_tokens or config.hyde_max_tokens
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._client = None

    def _get_client(self):
        """OpenAI 클라이언트를 지연 생성합니다."""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self._api_key, timeout=15.0)
        return self._client

    async def generate(
        self,
        query: str,
        domain: Optional[str] = None,
    ) -> Optional[str]:
        """
        쿼리에 대한 가상 답변을 생성합니다.

        Args:
            query: 사용자 쿼리
            domain: 도메인 (law, criteria, case, counsel)
                    None이면 default 프롬프트 사용

        Returns:
            가상 답변 텍스트. 실패 시 None 반환.
        """
        prompt_template = HYDE_PROMPTS.get(domain, HYDE_PROMPTS["default"])
        prompt = prompt_template.format(query=query)

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._max_tokens,
                temperature=0.7,  # 다양성을 위해 약간 높은 온도
            )
            hypothetical_doc = response.choices[0].message.content or ""

            logger.info(
                f"[HyDE] Generated hypothetical doc: "
                f"domain={domain}, model={self._model}, "
                f"length={len(hypothetical_doc)} chars"
            )
            return hypothetical_doc

        except Exception as e:
            logger.warning(f"[HyDE] Generation failed: {e}. Falling back to original query.")
            return None


__all__ = ["HyDEGenerator", "HYDE_PROMPTS"]
