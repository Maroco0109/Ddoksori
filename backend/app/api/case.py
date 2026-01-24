"""
똑소리 프로젝트 - 사례 조회 라우터

특정 사례의 전체 정보를 조회하는 엔드포인트입니다.
"""

from fastapi import APIRouter, HTTPException, Depends

from .dependencies import get_retriever


router = APIRouter(tags=["Case"])


@router.get("/case/{case_uid}")
async def get_case(
    case_uid: str,
    retriever=Depends(get_retriever)
):
    """
    특정 사례의 전체 정보 조회

    Args:
        case_uid: 사례 고유 ID
        retriever: Retriever 인스턴스 (DI)

    Returns:
        case_uid: 요청된 사례 ID
        chunks_count: 청크 개수
        chunks: 청크 리스트

    Raises:
        404: 사례를 찾을 수 없는 경우
        500: 조회 중 오류 발생
    """
    try:
        chunks = retriever.get_case_chunks(case_uid)

        if not chunks:
            raise HTTPException(status_code=404, detail="사례를 찾을 수 없습니다.")

        return {
            "case_uid": case_uid,
            "chunks_count": len(chunks),
            "chunks": chunks
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사례 조회 중 오류 발생: {str(e)}")


__all__ = ['router']
