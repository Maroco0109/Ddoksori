"""
라우팅 규칙 설정 관리 모듈

템플릿 라우터에서 사용되는 키워드 및 임계값을 외부화하여 관리합니다.
JSON 파일을 통해 런타임에 설정을 변경할 수 있으며, 파일이 없으면 기본값을 사용합니다.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 기본 라우팅 설정
_DEFAULT_CONFIG: Dict[str, Any] = {
    "criminal_keywords": [
        "사기",
        "잠적",
        "먹튀",
        "고소",
        "경찰",
        "벽돌",
        "고발",
        "야반도주",
        "신고",
    ],
    "intl_keywords": [
        "직구",
        "해외결제",
        "알리",
        "테무",
        "아마존",
        "배대지",
        "관세",
        "해외 사이트",
    ],
    "high_amount_threshold": 5_000_000,
}

# 설정 파일 경로
_CONFIG_FILE_NAME = "routing_rules.json"
_CONFIG_DIR = Path(__file__).parent

# 설정 캐시 (첫 로드 후 재사용)
_cached_config: Optional[Dict[str, Any]] = None


def load_routing_config() -> Dict[str, Any]:
    """
    라우팅 설정을 로드합니다.

    1. routing_rules.json 파일이 존재하면 로드하여 기본값과 병합
    2. 파일이 없으면 기본값 반환
    3. 첫 로드 후 결과를 캐시하여 재사용

    Returns:
        Dict[str, Any]: 라우팅 설정 딕셔너리
            - criminal_keywords: 범죄 관련 키워드 리스트
            - intl_keywords: 해외결제 관련 키워드 리스트
            - high_amount_threshold: 고액 거래 임계값 (원)
    """
    global _cached_config

    # 캐시된 설정이 있으면 반환
    if _cached_config is not None:
        return _cached_config

    config = _DEFAULT_CONFIG.copy()
    config_path = _CONFIG_DIR / _CONFIG_FILE_NAME

    # JSON 파일이 존재하면 로드하여 병합
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)

            # 기본값 위에 사용자 설정 오버라이드
            config.update(user_config)
            logger.info(f"라우팅 설정을 {config_path}에서 로드했습니다.")

        except json.JSONDecodeError as e:
            logger.error(
                f"라우팅 설정 파일 파싱 실패: {config_path} - {e}. 기본값을 사용합니다."
            )
        except Exception as e:
            logger.error(
                f"라우팅 설정 파일 로드 중 오류 발생: {config_path} - {e}. 기본값을 사용합니다."
            )
    else:
        logger.info(
            f"라우팅 설정 파일이 없습니다 ({config_path}). 기본값을 사용합니다."
        )

    # 결과 캐시
    _cached_config = config
    return config


def get_criminal_keywords() -> List[str]:
    """
    범죄 관련 키워드 리스트를 반환합니다.

    Returns:
        List[str]: 범죄 관련 키워드 리스트
            예: ["사기", "잠적", "먹튀", "고소", "경찰", ...]
    """
    config = load_routing_config()
    return config.get("criminal_keywords", _DEFAULT_CONFIG["criminal_keywords"])


def get_intl_keywords() -> List[str]:
    """
    해외결제 관련 키워드 리스트를 반환합니다.

    Returns:
        List[str]: 해외결제 관련 키워드 리스트
            예: ["직구", "해외결제", "알리", "테무", "아마존", ...]
    """
    config = load_routing_config()
    return config.get("intl_keywords", _DEFAULT_CONFIG["intl_keywords"])


def get_high_amount_threshold() -> int:
    """
    고액 거래 임계값을 반환합니다.

    Returns:
        int: 고액 거래 임계값 (원 단위)
            기본값: 5,000,000원
    """
    config = load_routing_config()
    return config.get("high_amount_threshold", _DEFAULT_CONFIG["high_amount_threshold"])


def reload_config() -> None:
    """
    설정 캐시를 무효화하고 다음 호출 시 재로드하도록 합니다.

    테스트나 런타임에 설정 파일이 변경된 경우 사용할 수 있습니다.
    """
    global _cached_config
    _cached_config = None
    logger.info("라우팅 설정 캐시가 무효화되었습니다. 다음 호출 시 재로드됩니다.")
