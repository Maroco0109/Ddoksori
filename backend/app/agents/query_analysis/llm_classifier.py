"""
LLM Fallback Classifier for Query Type Classification.

Rule-based classifier의 confidence가 낮을 때 (< 0.7) 호출됩니다.
OpenAI structured output (JSON mode)을 사용하여 정확한 의도 분류를 수행합니다.

Issue #3: Hybrid Intent Classification (규칙 + LLM Fallback)
"""

import asyncio
import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Few-shot examples for intent classification
FEW_SHOT_EXAMPLES = [
    {
        "query": "안녕",
        "type": "general",
        "confidence": 0.95,
        "reasoning": "인사말 = 일반 대화",
    },
    {
        "query": "ㅎㅇ",
        "type": "general",
        "confidence": 0.95,
        "reasoning": "인사말 약어 = 일반 대화",
    },
    {
        "query": "뭐 알려줘",
        "type": "general",
        "confidence": 0.90,
        "reasoning": "구체적 정보 없는 메타 질문 = 일반 대화",
    },
    {
        "query": "노트북 파손되었는데 환불 가능해?",
        "type": "dispute",
        "confidence": 0.95,
        "reasoning": "제품 파손 + 환불 요청 = 소비자 분쟁",
    },
    {
        "query": "민법 756조에 대해서 알려줘",
        "type": "law",
        "confidence": 0.95,
        "reasoning": "특정 법조항 정보 요청",
    },
    {
        "query": "종묘에 관련된 분쟁이 생겼을 때, 어떻게 해결할 수 있는지 해결기준을 기반으로 알려줘",
        "type": "criteria",
        "confidence": 0.90,
        "reasoning": "종묘(구체적 품목) + 분쟁 + 해결기준 = 분쟁해결기준 검색",
    },
    {
        "query": "노트북 관련 기준 있어?",
        "type": "criteria",
        "confidence": 0.90,
        "reasoning": "제품 + 기준 요청 = 분쟁해결기준 검색",
    },
    {
        "query": "소비자보호법이 뭐야?",
        "type": "general",
        "confidence": 0.90,
        "reasoning": "정의형 질문, 구체적 분쟁 없음",
    },
    {
        "query": "오늘 날씨 어때?",
        "type": "general",
        "confidence": 0.95,
        "reasoning": "소비자 분쟁과 무관한 일반 대화",
    },
    {
        "query": "헬스장 3개월 등록했는데 환불해줘",
        "type": "dispute",
        "confidence": 0.95,
        "reasoning": "서비스 계약 + 환불 요청",
    },
    {
        "query": "청약철회 기간이 어떻게 되나요?",
        "type": "law",
        "confidence": 0.85,
        "reasoning": "법적 기간 정보 요청",
    },
    {
        "query": "전자상거래법 제17조가 뭐야?",
        "type": "law",
        "confidence": 0.95,
        "reasoning": "특정 법조항 정보 요청",
    },
    {
        "query": "분쟁해결기준에서 노트북 환불 기준 알려줘",
        "type": "criteria",
        "confidence": 0.90,
        "reasoning": "분쟁해결기준 참조",
    },
    {
        "query": "금융 분쟁 어떻게 해결하나요?",
        "type": "restricted",
        "confidence": 0.85,
        "reasoning": "금융 도메인 = 전문기관 필요",
    },
]

SYSTEM_PROMPT = """당신은 소비자 분쟁 상담 챗봇의 의도 분류기입니다.
사용자 질문을 다음 유형 중 하나로 분류하세요:

- dispute: 구체적인 소비자 분쟁 상담 (환불, 교환, 수리, 하자 등)
- general: 일반 대화, 인사, 정의형 질문, 메타 질문("뭐 알려줘")
- law: 법령/법조항 정보 요청 (예: "민법 756조 알려줘")
- criteria: 분쟁해결기준 정보 요청 (예: "노트북 환불 기준 알려줘")
- procedure: 절차/방법 질문
- restricted: 전문기관 도메인 (금융, 의료, 개인정보, 부동산, 건설)
- system_meta: 시스템/봇 관련 질문 (예: "네가 뭐야?", "어떤 AI야?")
- ambiguous: 분류 불가능

분류 지침:
1. "알려줘"가 있어도 구체적 품목/법령이 있으면 해당 카테고리로 분류
2. "뭐 알려줘", "도와줘" 같은 비구체적 요청은 general
3. "분쟁", "해결", "해결기준" 키워드가 있으면 dispute 또는 criteria

반드시 JSON 형식으로 응답하세요:
{"type": "dispute", "confidence": 0.95, "reasoning": "이유 설명"}
"""

# Valid query types for validation
_VALID_TYPES = {
    "dispute",
    "general",
    "law",
    "criteria",
    "procedure",
    "restricted",
    "system_meta",
    "meta_conversational",
    "ambiguous",
    "case",  # 사례 검색
}


async def llm_classify(
    query: str,
    timeout: float = 3.0,
) -> Optional[Tuple[str, float, str]]:
    """
    LLM을 사용하여 쿼리를 분류합니다.

    Rule-based classifier의 confidence가 낮을 때 호출되어
    gpt-4o-mini를 통해 더 정확한 의도 분류를 수행합니다.

    Args:
        query: 사용자 질문
        timeout: LLM 호출 타임아웃 (초)

    Returns:
        (query_type, confidence, reasoning) 또는 실패 시 None
    """
    try:
        import openai

        from ...common.config import get_config

        config = get_config()
        client = openai.AsyncOpenAI(api_key=config.llm.openai_api_key)

        # Few-shot 프롬프트 구성
        few_shot_text = "\n".join(
            [
                f"질문: {ex['query']}\n응답: {json.dumps(ex, ensure_ascii=False)}"
                for ex in FEW_SHOT_EXAMPLES
            ]
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"예시:\n{few_shot_text}\n\n질문: {query}\n응답:",
            },
        ]

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.models.query_classifier,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=100,
            ),
            timeout=timeout,
        )

        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)

        query_type = result.get("type", "dispute")
        confidence = float(result.get("confidence", 0.7))
        reasoning = result.get("reasoning", "")

        # Validate query_type
        if query_type not in _VALID_TYPES:
            query_type = "dispute"
            confidence = 0.5

        logger.info(
            f"[LLM Classifier] query='{query[:30]}' -> "
            f"type={query_type}, confidence={confidence:.2f}, reason={reasoning}"
        )

        return (query_type, confidence, reasoning)

    except asyncio.TimeoutError:
        logger.warning(f"[LLM Classifier] Timeout ({timeout}s) for: {query[:30]}")
        return None
    except Exception as e:
        logger.warning(f"[LLM Classifier] Error: {e}")
        return None


__all__ = ["llm_classify", "FEW_SHOT_EXAMPLES", "SYSTEM_PROMPT"]
