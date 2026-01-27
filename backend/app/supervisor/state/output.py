"""
똑소리 프로젝트 - 출력 상태 스키마

최종 출력과 근거 매핑을 관리합니다.
사용자에게 반환되는 응답 데이터입니다.
"""

from typing import List, Dict, Optional, Annotated
from typing_extensions import TypedDict
import operator


class ClaimEvidenceMapping(TypedDict):
    """
    주장-근거 매핑

    답변에 포함된 각 주장과 그 근거가 되는 문서 청크를 연결합니다.
    할루시네이션 방지 및 출처 추적에 사용됩니다.

    Attributes:
        claim: 답변에 포함된 주장/진술
        evidence_chunk_ids: 근거 문서 청크 ID 목록
        evidence_texts: 근거 텍스트 발췌
        grounded: 근거 기반 여부 (True: 출처 있음)

    Example:
        >>> mapping: ClaimEvidenceMapping = {
        ...     'claim': '헬스장 환불은 잔여 기간에 비례합니다',
        ...     'evidence_chunk_ids': ['chunk_123', 'chunk_456'],
        ...     'evidence_texts': ['소비자분쟁해결기준에 따르면...'],
        ...     'grounded': True
        ... }
    """
    claim: str
    evidence_chunk_ids: List[str]
    evidence_texts: List[str]
    grounded: bool


class OutputState(TypedDict, total=False):
    """
    최종 출력 상태

    사용자에게 반환되는 최종 응답 데이터입니다.

    Attributes:
        final_answer: 최종 확정 답변
            - review 통과 후 설정
            - 모든 검증을 마친 안전한 응답

        sources: 인용 출처 목록 (operator.add로 누적)
            - 각 출처는 Dict 형태: {type, title, url, ...}
            - 검색 노드에서 추가됨

        has_sufficient_evidence: 근거 충분 여부
            - True: 검색 결과가 질문에 적합
            - False: 근거 부족 (규칙 기반 폴백 사용됨)

        clarifying_questions: 명확화 질문 목록 (Track 2)
            - 정보 부족 시 사용자에게 되묻는 질문들
            - 예: ["구매 날짜를 알려주시겠어요?"]

        followup_questions: 후속 질문 목록 (Track 2)
            - 현재 답변 기반 추가 질문 제안
            - 예: ["환불 처리 기간은 얼마나 걸리나요?"]

        claim_evidence_map: 주장-근거 매핑 리스트
            - 답변의 각 주장과 근거 연결
            - 할루시네이션 검증에 사용

    Note:
        sources 필드는 operator.add를 사용하여
        여러 노드에서 추가된 출처가 누적됩니다.

    Track 2 변경사항 (2026-01-28):
        - followup_questions 필드 추가
        - clarifying_questions 의미 명확화
    """
    final_answer: Optional[str]
    sources: Annotated[List[Dict], operator.add]
    has_sufficient_evidence: bool
    clarifying_questions: List[str]
    followup_questions: List[str]
    claim_evidence_map: List[ClaimEvidenceMapping]


__all__ = [
    'ClaimEvidenceMapping',
    'OutputState',
]
