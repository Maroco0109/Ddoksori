"""
M2-2: RunPod/local vLLM health check (재현 가능한 가용성 측정)

EXAONE vLLM endpoint의 상태를 provider/model/url/latency_ms와 함께 JSON으로 출력한다.
앱 전체를 기동하지 않고 단독 실행 가능하며, RunPod이 꺼져 있어도 실패 원인(error_type)을
명확히 구분한다. M2-3 provider policy / M3 측정 시스템의 가용성 기준선으로 사용한다.

사용 예:
    python backend/scripts/testing/llm/check_vllm_health.py
    python backend/scripts/testing/llm/check_vllm_health.py --url http://localhost:19080/v1
    EXAONE_RUNPOD_URL=http://localhost:19080/v1 python backend/scripts/testing/llm/check_vllm_health.py

종료 코드: healthy=0, 그 외=1 (CI/스모크에서 활용 가능)
"""

import argparse
import json
import os
import sys
import time
from typing import Optional, Tuple

import requests

PROVIDER = "runpod_vllm"
DEFAULT_TIMEOUT = 5.0


def _normalize_base(url: str) -> Tuple[str, str]:
    """입력 URL에서 (models_base=.../v1, health_base=.../) 쌍을 만든다."""
    trimmed = url.rstrip("/")
    if trimmed.endswith("/v1"):
        v1_base = trimmed
        root_base = trimmed[: -len("/v1")]
    else:
        v1_base = trimmed + "/v1"
        root_base = trimmed
    return v1_base, root_base


def _classify_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection_error"
    return "request_error"


def check_vllm_health(url: Optional[str], timeout: float = DEFAULT_TIMEOUT) -> dict:
    """
    vLLM endpoint를 probe하고 측정 결과 dict를 반환한다.

    1차 probe: GET {base}/v1/models  -> 200이면 healthy + 모델 id 확보
    보조 probe: GET {root}/health    -> vLLM native liveness (참고용)
    """
    result = {
        "provider": PROVIDER,
        "url": url,
        "model": None,
        "status": "unhealthy",
        "http_status": None,
        "latency_ms": None,
        "vllm_health": None,
        "error_type": None,
    }

    if not url:
        result["error_type"] = "not_configured"
        return result

    v1_base, root_base = _normalize_base(url)
    result["url"] = v1_base

    # 1차: /v1/models (OpenAI 호환 API + 모델 id)
    start = time.perf_counter()
    try:
        resp = requests.get(f"{v1_base}/models", timeout=timeout)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["http_status"] = resp.status_code
        if resp.status_code == 200:
            try:
                data = resp.json().get("data", [])
                if data:
                    result["model"] = data[0].get("id")
            except ValueError:
                result["error_type"] = "bad_response"
                return result
            result["status"] = "healthy"
        else:
            result["error_type"] = "bad_response"
            return result
    except Exception as exc:  # noqa: BLE001 - 의도적으로 모든 probe 오류 분류
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["error_type"] = _classify_error(exc)
        return result

    # 보조: /health (vLLM native, 실패해도 status는 healthy 유지)
    try:
        h = requests.get(f"{root_base}/health", timeout=timeout)
        result["vllm_health"] = h.status_code == 200
    except Exception:  # noqa: BLE001 - 보조 probe는 결과에 치명적이지 않음
        result["vllm_health"] = False

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="RunPod/local vLLM health check")
    parser.add_argument(
        "--url",
        default=os.getenv("EXAONE_RUNPOD_URL"),
        help="vLLM endpoint URL (기본: 환경변수 EXAONE_RUNPOD_URL)",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="probe 타임아웃(초)"
    )
    args = parser.parse_args()

    result = check_vllm_health(args.url, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())
