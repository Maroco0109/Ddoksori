"""
AWS Secrets Manager 통합 모듈.

프로덕션 환경에서 시크릿을 AWS Secrets Manager에서 로드하여
os.environ에 주입합니다. Pydantic Settings가 환경변수를 읽기 전에
호출되어야 합니다.

사용법:
    # config.py의 get_config() 내부에서 자동 호출됨
    from app.common.secrets import inject_aws_secrets
    inject_aws_secrets()

환경변수:
    USE_AWS_SECRETS: "true"이면 Secrets Manager에서 로드 (기본값: "false")
    SECRETS_ENV: 시크릿 환경 prefix (기본값: "staging")
    AWS_DEFAULT_REGION: AWS 리전 (기본값: "ap-northeast-2")

설계 문서: docs/plans/2026-01-29-aws-secrets-manager-design.md
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

SECRET_CATEGORIES = [
    "database",
    "llm",
    "oauth/google",
    "oauth/naver",
    "security",
    "infra",
]

_injected = False


def inject_aws_secrets() -> int:
    """
    AWS Secrets Manager에서 시크릿을 로드하여 os.environ에 주입합니다.

    USE_AWS_SECRETS=true일 때만 동작합니다.
    빈 문자열인 환경변수는 덮어씁니다 (실질적 값이 있는 환경변수만 우선).
    중복 호출 시 첫 번째 호출만 실행됩니다.

    Returns:
        주입된 시크릿 수
    """
    global _injected
    if _injected:
        return 0

    if os.getenv("USE_AWS_SECRETS", "false").lower() != "true":
        return 0

    try:
        import boto3
    except ImportError:
        logger.error("boto3 not installed. Run: pip install boto3")
        return 0

    _injected = True

    client = boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2"),
    )

    environment = os.getenv("SECRETS_ENV", "staging")
    prefix = f"ddoksori/{environment}/"
    injected = 0

    for category in SECRET_CATEGORIES:
        secret_name = prefix + category
        try:
            response = client.get_secret_value(SecretId=secret_name)
            data = json.loads(response["SecretString"])

            for env_key, env_value in data.items():
                if not os.environ.get(env_key):
                    os.environ[env_key] = str(env_value)
                    injected += 1

        except Exception as e:
            # ResourceNotFoundException 포함 모든 예외 처리
            error_type = type(e).__name__
            if "ResourceNotFoundException" in error_type:
                logger.warning("Secret not found: %s", secret_name)
            else:
                logger.error("Failed to load secret %s: %s", secret_name, e)

    logger.info(
        "Injected %d secrets from AWS Secrets Manager (%s)", injected, environment
    )
    return injected
