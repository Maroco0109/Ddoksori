"""
OpenAI Moderation Guardrail
Sprint 1: 입력/출력 유해성 검사
SEC-05: 프롬프트 인젝션 탐지 추가
"""

import logging
import os
import re
from typing import Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI
from typing_extensions import TypedDict

load_dotenv()

logger = logging.getLogger(__name__)

# 보안 로거 (인젝션 탐지 전용)
security_logger = logging.getLogger("security.injection")

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

# SEC-05: 프롬프트 인젝션 탐지 패턴
# sanitization.py와 동일한 패턴 사용하되, 보안 로깅 목적
INJECTION_PATTERNS = [
    # 영어 인젝션 패턴
    (
        r"\b(ignore|disregard|forget)\b.*\b(above|previous|instructions?|rules?)\b",
        "instruction_override",
    ),
    (r"\b(pretend|act\s+as|you\s+are\s+now)\b.*", "role_hijacking"),
    (r"\bnew\s+instructions?\b", "new_instruction"),
    (
        r"\b(override|bypass)\b.*\b(rules?|instructions?|restrictions?)\b",
        "bypass_attempt",
    ),
    (r"<\s*/?\s*system\s*>", "system_tag"),
    (r"\[\s*system\s*\]", "system_bracket"),
    # 한국어 인젝션 패턴
    (r"(시스템|시스템)\s*(프롬프트|지시|명령|규칙)", "ko_system_prompt"),
    (r"(지시|지침|명령|규칙)을?\s*(무시|잊|버려|취소)", "ko_ignore_instruction"),
    (r"(이전|위의?|앞의?)\s*(지시|명령|규칙|내용)을?\s*(무시|잊)", "ko_override"),
    (r"(새로운|다른)\s*(지시|명령|역할)을?\s*(따라|따르)", "ko_new_instruction"),
    (r"너는?\s*이제\s*(부터)?\s*", "ko_role_change"),
    # 구분자/탈출 시도
    (r"#{3,}", "delimiter_hash"),
    (r"-{3,}", "delimiter_dash"),
    (r"={3,}", "delimiter_equals"),
    (r"`{3,}", "code_block"),
    (r"\[/?INST\]", "llama_inst"),
    (r"<\|.*?\|>", "special_token"),
]

# 컴파일된 인젝션 패턴
COMPILED_INJECTION_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE), name)
    for pattern, name in INJECTION_PATTERNS
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
        return ModerationResult(
            flagged=False,
            categories={},
            category_scores={},
            blocked=False,
            fallback_message=None,
        )


def check_injection(text: str) -> Dict[str, bool]:
    """
    SEC-05: 프롬프트 인젝션 패턴 탐지

    OpenAI Moderation API 호출 전에 실행되어 추가적인 인젝션 탐지를 제공합니다.
    탐지된 패턴은 보안 로그에 기록됩니다.

    Args:
        text: 검사할 텍스트

    Returns:
        Dict[str, bool]: {
            "injection_detected": bool,
            "patterns": List[str] (탐지된 패턴 이름들)
        }
    """
    detected_patterns = []

    for pattern, name in COMPILED_INJECTION_PATTERNS:
        if pattern.search(text):
            detected_patterns.append(name)

    if detected_patterns:
        # 보안 로그 기록
        security_logger.warning(
            f"[SEC-05] Prompt injection detected - patterns={detected_patterns}, "
            f"text_preview={text[:100]}..."
        )

    return {
        "injection_detected": len(detected_patterns) > 0,
        "patterns": detected_patterns,
    }


def check_input(text: str) -> ModerationResult:
    """입력 텍스트에 대한 유해성 및 인젝션 검사"""
    # SEC-05: 인젝션 탐지 먼저 실행
    injection_result = check_injection(text)

    if injection_result["injection_detected"]:
        logger.warning(
            f"[Moderation] Injection patterns detected: {injection_result['patterns']}"
        )
        # 인젝션 탐지 시에도 OpenAI Moderation 계속 실행 (이중 검증)

    return _check_moderation(text, is_input=True)


def check_output(text: str) -> ModerationResult:
    return _check_moderation(text, is_input=False)
