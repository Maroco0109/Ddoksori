from typing import Literal

ModerationCategory = Literal[
    'hate',
    'hate/threatening',
    'harassment',
    'harassment/threatening',
    'self-harm',
    'self-harm/intent',
    'self-harm/instructions',
    'sexual',
    'sexual/minors',
    'violence',
    'violence/graphic',
]

BLOCKED_CATEGORIES: set[ModerationCategory] = {
    'hate',
    'hate/threatening',
    'harassment/threatening',
    'self-harm',
    'self-harm/intent',
    'self-harm/instructions',
    'sexual/minors',
    'violence/graphic',
}

WARN_CATEGORIES: set[ModerationCategory] = {
    'harassment',
    'sexual',
    'violence',
}

FALLBACK_MESSAGES = {
    'blocked': (
        "요청하신 내용은 서비스 정책상 처리할 수 없습니다. "
        "소비자 분쟁 관련 질문을 입력해 주세요."
    ),
    'error': (
        "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    ),
    'timeout': (
        "요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
    ),
}


def should_block(flagged_categories: dict[str, bool]) -> bool:
    for category in BLOCKED_CATEGORIES:
        if flagged_categories.get(category, False):
            return True
    return False


def get_flagged_categories(category_flags: dict[str, bool]) -> list[str]:
    return [cat for cat, flagged in category_flags.items() if flagged]


def get_fallback_message(
    reason: Literal['blocked', 'error', 'timeout'] = 'blocked'
) -> str:
    return FALLBACK_MESSAGES.get(reason, FALLBACK_MESSAGES['error'])
