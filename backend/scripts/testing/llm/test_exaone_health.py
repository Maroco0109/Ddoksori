"""
EXAONE LLM Health Check 테스트
S3-PR2: 7.8B 모델 업그레이드 검증

RunPod vLLM 서버의 상태를 확인하고 기본 추론 기능을 테스트합니다.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import logging

from app.llm.exaone_client import ExaoneLLMClient, LLMUnavailableError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_health_check():
    logger.info("=== EXAONE LLM Health Check ===")

    client = ExaoneLLMClient()

    logger.info(f"Model: {client.model}")
    logger.info(f"Model Size: {client.model_size}")
    logger.info(f"RunPod URL: {client.runpod_url}")
    logger.info(f"Temperature: {client.temperature}")
    logger.info(f"Max Tokens: {client.max_tokens}")

    if client.is_available():
        logger.info("✅ RunPod vLLM server is HEALTHY")
        return True
    else:
        logger.error("❌ RunPod vLLM server is UNAVAILABLE")
        return False


def test_simple_generation():
    logger.info("\n=== Simple Generation Test ===")

    client = ExaoneLLMClient()

    if not client.is_available():
        logger.error("Skipping generation test - server unavailable")
        return False

    try:
        response = client.generate(
            system_prompt="당신은 도움이 되는 AI 어시스턴트입니다.",
            user_prompt="안녕하세요. 자기소개를 한 문장으로 해주세요.",
        )

        logger.info(f"✅ Generation successful")
        logger.info(f"Response: {response[:200]}...")
        return True

    except LLMUnavailableError as e:
        logger.error(f"❌ Generation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


def test_korean_legal_generation():
    logger.info("\n=== Korean Legal Generation Test ===")

    client = ExaoneLLMClient()

    if not client.is_available():
        logger.error("Skipping legal test - server unavailable")
        return False

    try:
        response = client.generate(
            system_prompt="당신은 한국 법률 전문 AI 어시스턴트입니다.",
            user_prompt="소비자기본법의 주요 목적을 2-3문장으로 설명해주세요.",
        )

        logger.info(f"✅ Legal generation successful")
        logger.info(f"Response: {response}")

        if len(response) < 20:
            logger.warning("⚠️ Response seems too short")
            return False

        return True

    except LLMUnavailableError as e:
        logger.error(f"❌ Legal generation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


def main():
    logger.info("Starting EXAONE LLM Health Check Tests\n")

    results = {
        "health_check": test_health_check(),
        "simple_generation": test_simple_generation(),
        "korean_legal": test_korean_legal_generation(),
    }

    logger.info("\n=== Test Results Summary ===")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{test_name}: {status}")

    all_passed = all(results.values())

    if all_passed:
        logger.info("\n🎉 All tests PASSED")
        return 0
    else:
        logger.error("\n💥 Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
