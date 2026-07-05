"""똑소리 프로젝트 - 관측(observability) 조회 라우터 (M3-8, read-only).

M3 저장 계층(workflow_runs/steps/retrieval_events/llm_calls/guardrail_events)을
조회한다. /metrics와 동일하게 admin 전용.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.admin.dependencies import get_current_admin
from app.admin.models import Admin
from app.observability.query import get_run_detail, list_runs

router = APIRouter(prefix="/observability", tags=["Observability"])


@router.get("/runs")
async def get_runs(
    variant: Optional[str] = Query(None, description="A | B"),
    status: Optional[str] = Query(None, description="success | no_results | error"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: Admin = Depends(get_current_admin),
):
    """최근 workflow run 목록 (최신순). variant/status 필터."""
    runs = await list_runs(limit=limit, offset=offset, variant=variant, status=status)
    return {"count": len(runs), "runs": runs}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    admin: Admin = Depends(get_current_admin),
):
    """run 1건 + 자식(steps/retrieval_events/llm_calls/guardrail_events) detail."""
    detail = await get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run을 찾을 수 없습니다.")
    return detail


__all__ = ["router"]
