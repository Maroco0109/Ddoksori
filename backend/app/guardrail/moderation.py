"""
OpenAI Moderation Guardrail
Sprint 1: 입력/출력 유해성 검사
"""

import logging
import os
from typing import Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI
from typing_extensions import TypedDict

load_dotenv()

logger = logging.getLogger(__name__)

MODERATION_ENABLED = os.getenv("MODERATION_ENABLED", "true").lower() == "true"
MODERATION_MODEL = os.getenv("MODERATION_MODEL", "omni-moderation-latest")

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        _client = OpenAI(api_key=api_key)
    return _client


class ModerationResult(TypedDict):
    flagged: bool
    categories: Dict[str, bool]
    category_scores: Dict[str, float]
    blocked: bool
    fallback_message: Optional[str]


FALLBACK_MESSAGE_INPUT = (
    "죄송합니다. 입력하신 내용이 서비스 정책에 위배되어 처리할 수 없습니다. "
    "다른 질문을 입력해 주세요."
)

FALLBACK_MESSAGE_OUTPUT = (
    "죄송합니다. 요청하신 내용에 대한 답변을 생성할 수 없습니다. "
    "다른 질문을 입력해 주세요."
)

BLOCKED_CATEGORIES = [
    "harassment",
    "harassment/threatening",
    "hate",
    "hate/threatening",
    "self-harm",
    "self-harm/intent",
    "self-harm/instructions",
    "sexual",
    "sexual/minors",
    "violence",
    "violence/graphic",
]


def _check_moderation(text: str, is_input: bool = True) -> ModerationResult:
    if not MODERATION_ENABLED:
        return ModerationResult(
            flagged=False,
            categories={},
            category_scores={},
            blocked=False,
            fallback_message=None,
        )

    try:
        client = _get_client()
        response = client.moderations.create(model=MODERATION_MODEL, input=text)

        result = response.results[0]

        categories = {}
        category_scores = {}

        if hasattr(result, "categories") and result.categories:
            for cat in BLOCKED_CATEGORIES:
                cat_key = cat.replace("/", "_")
                categories[cat] = getattr(result.categories, cat_key, False)

        if hasattr(result, "category_scores") and result.category_scores:
            for cat in BLOCKED_CATEGORIES:
                cat_key = cat.replace("/", "_")
                category_scores[cat] = getattr(result.category_scores, cat_key, 0.0)

        flagged = result.flagged
        blocked = flagged and any(
            categories.get(cat, False) for cat in BLOCKED_CATEGORIES
        )

        fallback_message = None
        if blocked:
            fallback_message = (
                FALLBACK_MESSAGE_INPUT if is_input else FALLBACK_MESSAGE_OUTPUT
            )
            logger.warning(
                f"[Moderation] Content blocked - is_input={is_input}, "
                f"flagged_categories={[c for c, v in categories.items() if v]}"
            )

        return ModerationResult(
            flagged=flagged,
            categories=categories,
            category_scores=category_scores,
            blocked=blocked,
            fallback_message=fallback_message,
        )

    except Exception as e:
        logger.error(f"[Moderation] API error: {e}")
        # SEC-17: fail-closed - API 오류 시 안전하게 차단
        return ModerationResult(
            flagged=True,
            categories={},
            category_scores={},
            blocked=True,
            fallback_message="보안 검증 중 일시적 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )


def check_input(text: str) -> ModerationResult:
    return _check_moderation(text, is_input=True)


def check_output(text: str) -> ModerationResult:
    return _check_moderation(text, is_input=False)
