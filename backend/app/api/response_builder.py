"""
똑소리 프로젝트 - 공통 응답 빌더

/chat 과 /chat/stream 양쪽 엔드포인트에서 사용하는 응답 구성 로직을 통일합니다.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 각 섹션별 소스 최대 표시 건수
_MAX_SOURCES_PER_SECTION = 3


def build_chat_response_data(
    session_id: str,
    final_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    그래프 출력(final_state)에서 프론트엔드 호환 응답 dict를 생성.

    /chat 엔드포인트: ChatResponse(**result, chunks_used=..., model=...) 로 래핑
    /chat/stream 엔드포인트: {'type': 'complete', 'data': result} 로 SSE 전송

    Args:
        session_id: 세션 ID
        final_state: MAS 그래프의 최종 state dict

    Returns:
        프론트엔드 SSECompleteData 호환 dict
    """
    retrieval = final_state.get("retrieval") or {}
    agency_info = retrieval.get("agency", {})
    disputes = retrieval.get("disputes", [])
    counsels = retrieval.get("counsels", [])
    laws = retrieval.get("laws", [])
    criteria = retrieval.get("criteria", [])

    answer = final_state.get("final_answer") or ""

    return {
        "session_id": session_id,
        "answer": answer,
        "sources": _build_sources(disputes, counsels, laws, criteria),
        "clarifying_questions": [],  # PR-41: 추천 질문 제거
        "followup_questions": [],  # PR-41: 추천 질문 제거
        "has_sufficient_evidence": final_state.get("has_sufficient_evidence", True),
        "domain": _build_domain(agency_info),
        "similar_cases": _build_similar_cases(disputes, counsels),
        "related_laws": _build_related_laws(laws),
        "related_criteria": _build_related_criteria(criteria),
    }


def _build_sources(
    disputes: List[Dict],
    counsels: List[Dict],
    laws: List[Dict],
    criteria: List[Dict],
) -> List[Dict[str, Any]]:
    """4개 섹션에서 프론트엔드 SSESourceInfo 호환 sources 리스트를 생성."""
    sources: List[Dict[str, Any]] = []

    for d in disputes[:_MAX_SOURCES_PER_SECTION]:
        sources.append(
            {
                "type": "dispute",
                "title": d.get("doc_title", ""),
                "source_org": d.get("source_org", ""),
                "similarity": d.get("similarity", 0),
                "content": d.get("content", ""),
                "case_uid": d.get("case_uid"),
                "product_name": d.get("product_name"),
                "url": d.get("url", ""),  # URL 추가
                "source_file": d.get("source_file", ""),  # PDF 파일명
                "printed_page": d.get("printed_page"),  # 페이지 번호
            }
        )

    for c in counsels[:_MAX_SOURCES_PER_SECTION]:
        sources.append(
            {
                "type": "counsel",
                "title": c.get("doc_title", ""),
                "source_org": c.get("source_org", ""),
                "similarity": c.get("similarity", 0),
                "content": c.get("content", ""),
                "url": c.get("url", ""),  # URL 추가
                "source_file": c.get("source_file", ""),  # PDF 파일명
                "printed_page": c.get("printed_page"),  # 페이지 번호
            }
        )

    for law in laws[:_MAX_SOURCES_PER_SECTION]:
        sources.append(
            {
                "type": "law",
                "title": f"{law.get('law_name', '')} {law.get('full_path', '')}".strip(),
                "similarity": law.get("similarity", 0),
                "content": law.get("content", ""),
                "law_name": law.get("law_name"),
                "article": law.get("article"),
            }
        )

    for c in criteria[:_MAX_SOURCES_PER_SECTION]:
        sources.append(
            {
                "type": "criteria",
                "title": c.get("title", c.get("source_label", "")),
                "similarity": c.get("similarity", 0),
                "content": c.get("content", ""),
            }
        )

    return sources


def _build_domain(agency_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """agency dict를 프론트엔드 AgencyRecommendation 호환 dict로 변환.

    retrieval_merge에서 전달되는 agency dict 구조:
        {'domain': 'finance', 'name': '금융분쟁조정위원회',
         'organization': '금융감독원', 'url': '...', 'phone': '1332',
         'is_restricted': True}
    """
    if not agency_info:
        return None

    return {
        "agency": agency_info.get("domain", agency_info.get("agency", "")),
        "agency_info": {
            "name": agency_info.get("name", ""),
            "organization": agency_info.get("organization", ""),
            "url": agency_info.get("url", ""),
            "phone": agency_info.get("phone", ""),
        },
        "dispute_type": agency_info.get("dispute_type", ""),
        "reason": agency_info.get("reason", ""),
        "confidence": agency_info.get("confidence", 0.7),
        "is_restricted": agency_info.get("is_restricted", False),
        "full_name": agency_info.get("name", ""),
        "description": agency_info.get("organization", ""),
        "url": agency_info.get("url", ""),
        "agency_code": agency_info.get("domain", agency_info.get("agency", "")),
        "restriction_reason": agency_info.get("restriction_reason", ""),
    }


def _build_similar_cases(
    disputes: List[Dict],
    counsels: List[Dict],
) -> Optional[Dict[str, Any]]:
    """유사 사례 구성 (프론트엔드 SimilarCases 호환)."""
    if not disputes and not counsels:
        return None

    return {
        "disputes": [
            {
                "doc_title": d.get("doc_title"),
                "source_org": d.get("source_org"),
                "similarity": d.get("similarity", 0),
                "url": d.get("url", ""),  # URL 추가
                "source_file": d.get("source_file", ""),
                "printed_page": d.get("printed_page"),
            }
            for d in disputes
        ],
        "counsels": [
            {
                "doc_title": c.get("doc_title"),
                "source_org": c.get("source_org"),
                "similarity": c.get("similarity", 0),
                "url": c.get("url", ""),  # URL 추가
                "source_file": c.get("source_file", ""),
                "printed_page": c.get("printed_page"),
            }
            for c in counsels
        ],
    }


def _build_related_laws(laws: List[Dict]) -> Optional[List[Dict[str, Any]]]:
    """관련 법령 구성 (프론트엔드 LawReference 호환)."""
    if not laws:
        return None

    return [
        {
            "law_name": law.get("law_name"),
            "article": law.get("article"),
            "full_path": law.get("full_path"),
            "similarity": law.get("similarity", 0),
        }
        for law in laws
    ]


def _build_related_criteria(criteria: List[Dict]) -> Optional[List[Dict[str, Any]]]:
    """관련 분쟁해결기준 구성 (프론트엔드 CriteriaReference 호환)."""
    if not criteria:
        return None

    return [
        {
            "title": c.get("title", c.get("source_label", "")),
            "category": c.get("category"),
            "similarity": c.get("similarity", 0),
        }
        for c in criteria
    ]
