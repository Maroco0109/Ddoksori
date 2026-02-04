"""
PII (개인 식별 정보) 마스킹 모듈 - SEC-08 보안 수정

로그에서 민감한 개인정보를 마스킹하여 GDPR/PIPA 규정을 준수합니다.

지원 패턴:
    - 한국 전화번호 (010-xxxx-xxxx, 02-xxx-xxxx 등)
    - 이메일 주소
    - 주민등록번호 (xxxxxx-xxxxxxx)
    - 신용카드 번호
    - 계좌번호 (숫자 10-14자리 연속)

Usage:
    from app.common.logging.pii_redactor import redact_pii

    # 로그 메시지에서 PII 마스킹
    safe_log = redact_pii("사용자 010-1234-5678 문의")
    # 결과: "사용자 [PHONE] 문의"

Feature Flag:
    ENABLE_PII_REDACTION=true (기본값)
"""

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Feature flag
ENABLE_PII_REDACTION = os.getenv("ENABLE_PII_REDACTION", "true").lower() == "true"

# PII 패턴 정의
PII_PATTERNS = [
    # 한국 전화번호
    # 휴대폰: 010-1234-5678, 01012345678, 010.1234.5678
    (
        r"\b(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})\b",
        "[PHONE]",
        "phone_mobile",
    ),
    # 일반전화: 02-1234-5678, 031-123-4567
    (
        r"\b(0\d{1,2})[-.\s]?(\d{3,4})[-.\s]?(\d{4})\b",
        "[PHONE]",
        "phone_landline",
    ),
    # 이메일 주소
    (
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        lambda m: f"{m.group(0)[:3]}***@{m.group(0).split('@')[1]}" if '@' in m.group(0) else "[EMAIL]",
        "email",
    ),
    # 주민등록번호 (6자리-7자리 또는 13자리 연속)
    (
        r"\b(\d{6})[-\s]?([1-4]\d{6})\b",
        "[SSN]",
        "ssn",
    ),
    # 신용카드 번호 (16자리, 다양한 구분자)
    (
        r"\b(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})\b",
        "[CARD]",
        "card",
    ),
    # 계좌번호 (10-14자리 연속 숫자, 하이픈 구분 가능)
    (
        r"\b(\d{3,4})[-\s]?(\d{2,4})[-\s]?(\d{4,6})\b",
        "[ACCOUNT]",
        "account",
    ),
]

# 컴파일된 패턴
COMPILED_PII_PATTERNS = [
    (re.compile(pattern), replacement, name)
    for pattern, replacement, name in PII_PATTERNS
]


def redact_pii(text: str, log_redactions: bool = False) -> str:
    """
    텍스트에서 PII를 마스킹합니다.

    Args:
        text: 원본 텍스트
        log_redactions: 마스킹 발생 시 로그 기록 여부 (기본: False)

    Returns:
        str: PII가 마스킹된 텍스트

    Examples:
        >>> redact_pii("연락처: 010-1234-5678")
        '연락처: [PHONE]'

        >>> redact_pii("이메일: test@example.com")
        '이메일: tes***@example.com'

        >>> redact_pii("주민번호: 901231-1234567")
        '주민번호: [SSN]'
    """
    if not text:
        return ""

    if not ENABLE_PII_REDACTION:
        return text

    redacted_text = text
    redactions_made = []

    for pattern, replacement, name in COMPILED_PII_PATTERNS:
        # replacement가 함수인 경우 (이메일 부분 마스킹용)
        if callable(replacement):
            new_text = pattern.sub(replacement, redacted_text)
        else:
            new_text = pattern.sub(replacement, redacted_text)

        if new_text != redacted_text:
            redactions_made.append(name)
            redacted_text = new_text

    if log_redactions and redactions_made:
        logger.debug(f"[PII Redactor] Masked patterns: {redactions_made}")

    return redacted_text


def redact_email_partial(email: str) -> str:
    """
    이메일 주소를 부분 마스킹합니다.
    예: test@example.com → tes***@example.com

    Args:
        email: 이메일 주소

    Returns:
        str: 부분 마스킹된 이메일
    """
    if not email or "@" not in email:
        return "[EMAIL]"

    local, domain = email.split("@", 1)
    if len(local) <= 3:
        masked_local = local[0] + "***"
    else:
        masked_local = local[:3] + "***"

    return f"{masked_local}@{domain}"


def redact_dict(data: dict, keys_to_redact: Optional[list] = None) -> dict:
    """
    딕셔너리의 값들에서 PII를 마스킹합니다.

    Args:
        data: 원본 딕셔너리
        keys_to_redact: 완전히 마스킹할 키 목록 (예: ["password", "token"])

    Returns:
        dict: PII가 마스킹된 딕셔너리
    """
    if not data:
        return data

    keys_to_redact = keys_to_redact or ["password", "token", "secret", "api_key"]

    redacted = {}
    for key, value in data.items():
        # 특정 키는 완전히 마스킹
        if any(k in key.lower() for k in keys_to_redact):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            redacted[key] = redact_pii(value)
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value, keys_to_redact)
        elif isinstance(value, list):
            redacted[key] = [
                redact_pii(v) if isinstance(v, str) else v for v in value
            ]
        else:
            redacted[key] = value

    return redacted


class PIIRedactingFilter(logging.Filter):
    """
    로그 레코드에서 자동으로 PII를 마스킹하는 필터.

    Usage:
        handler.addFilter(PIIRedactingFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = redact_pii(record.msg)

        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                record.args = redact_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_pii(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True


# Export
__all__ = [
    "redact_pii",
    "redact_email_partial",
    "redact_dict",
    "PIIRedactingFilter",
    "ENABLE_PII_REDACTION",
]
