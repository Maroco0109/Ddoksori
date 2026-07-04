"""M6-1: Prometheus scrape 엔드포인트.

이미 default registry에 등록된 Prometheus metric(common/metrics.py의 PROM_*,
legal_review/metrics.py 등)을 `generate_latest`로 내보내는 `GET /metrics` 라우트.
기존 `/metrics/*`(admin JSON, metrics.py)와는 별개의 exact-match 경로라 충돌하지 않는다.

- 노출 포맷: Prometheus text exposition (`text/plain; version=0.0.4`).
- 비인증: Prometheus 서버가 내부 네트워크에서 scrape하는 표준 엔드포인트.
- 단일 프로세스(dev) 기준 default REGISTRY. 다중 워커 운영은 multiprocess 모드 필요(범위 밖).
"""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """등록된 모든 Prometheus metric을 scrape 포맷으로 반환한다."""
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
