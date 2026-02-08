#!/usr/bin/env python3
"""
CI/CD 배포 전 OAuth 환경변수 검증 스크립트.

배포 파이프라인에서 실행하여 OAuth client_id가 빈 문자열이 아닌지 확인합니다.
빈 문자열 환경변수는 Docker Compose가 호스트에 해당 변수가 없을 때 발생하며,
이 경우 AWS Secrets Manager 주입이 필요합니다.

사용법:
    python backend/scripts/check_oauth_env.py

종료 코드:
    0: 모든 OAuth 변수가 유효 (비어있지 않음)
    1: 하나 이상의 OAuth 변수가 비어있음 (경고)
"""

import os
import sys

OAUTH_VARS = [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
]

REQUIRED_VARS = [
    "GOOGLE_CLIENT_ID",
    "NAVER_CLIENT_ID",
]


def check_oauth_env() -> int:
    """OAuth 환경변수를 검증합니다."""
    warnings = []
    errors = []

    use_aws = os.getenv("USE_AWS_SECRETS", "false").lower() == "true"

    for var in OAUTH_VARS:
        value = os.environ.get(var)
        if value is None:
            if use_aws:
                print(
                    f"  INFO: {var} not set (will be injected from AWS Secrets Manager)"
                )
            elif var in REQUIRED_VARS:
                errors.append(
                    f"  ERROR: {var} is not set and USE_AWS_SECRETS is not enabled"
                )
        elif value == "":
            if use_aws:
                print(
                    f"  INFO: {var} is empty string (will be overridden by AWS Secrets Manager)"
                )
            else:
                warnings.append(
                    f"  WARNING: {var} is empty string - OAuth login will fail!"
                )

    if errors:
        print("\n=== OAuth Environment Check: FAILED ===")
        for e in errors:
            print(e)
        return 1

    if warnings:
        print("\n=== OAuth Environment Check: WARNINGS ===")
        for w in warnings:
            print(w)
        return 1

    print("=== OAuth Environment Check: PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(check_oauth_env())
