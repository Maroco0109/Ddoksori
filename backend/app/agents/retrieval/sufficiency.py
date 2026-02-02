"""
똑소리 프로젝트 - 검색 결과 충분성 검사기
작성일: 2026-01-31
PR-A: 검색 결과 충분성을 정량적으로 평가하여 답변 생성 전 조기 차단

충분성 공식:
  confidence = 0.4 * sim_score + 0.3 * doc_score + 0.3 * type_score

  sim_score = min(max_similarity / SUFFICIENCY_MIN_SIMILARITY, 1.0)
  doc_score = min(relevant_doc_count / SUFFICIENCY_MIN_DOCUMENTS, 1.0)
  type_score = 1.0 if (has_laws or has_criteria) else 0.0
"""

import os
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class SufficiencyResult:
    """검색 결과 충분성 평가 결과"""
    confidence: float  # 0.0 ~ 1.0
    is_sufficient: bool  # confidence >= MEDIUM_THRESHOLD (0.6)
    level: str  # 'sufficient' | 'partial' | 'insufficient'
    reason: str  # Human readable explanation (Korean)
    clarifying_questions: List[str]  # Questions when insufficient


class RetrievalSufficiencyChecker:
    """검색 결과의 충분성을 평가하여 답변 생성 전 조기 차단을 지원"""

    def __init__(self):
        """환경변수에서 임계값 로드"""
        self.min_similarity = float(os.getenv("SUFFICIENCY_MIN_SIMILARITY", "0.5"))
        self.min_documents = int(os.getenv("SUFFICIENCY_MIN_DOCUMENTS", "2"))
        self.low_threshold = float(os.getenv("SUFFICIENCY_LOW_THRESHOLD", "0.3"))
        self.medium_threshold = float(os.getenv("SUFFICIENCY_MEDIUM_THRESHOLD", "0.6"))

    def evaluate(self, retrieval_result: Dict[str, Any]) -> SufficiencyResult:
        """
        검색 결과의 충분성을 평가합니다.

        RRF top-k 방식에서는 임계치 없이 결과가 있으면 항상 sufficient로 처리합니다.
        결과가 0건일 때만 insufficient로 판정합니다.

        PR-D: max_similarity가 매우 낮으면 marginal로 경고합니다.
        """
        from ...common.config import get_config

        # Count total documents across all sections
        total_doc_count = 0
        for section in ["disputes", "counsels", "laws", "criteria"]:
            total_doc_count += len(retrieval_result.get(section, []))

        max_similarity = retrieval_result.get("max_similarity", 0.0)

        # Get minimum quality threshold from config
        min_quality = get_config().retrieval.sufficiency_min_score

        # 결과가 1건 이상이지만 품질이 매우 낮은 경우 → marginal
        if total_doc_count > 0 and max_similarity < min_quality:
            return SufficiencyResult(
                confidence=0.5,
                is_sufficient=True,
                level="marginal",
                reason=f"검색 결과 {total_doc_count}건 있으나 유사도가 낮음 (max={max_similarity:.4f})",
                clarifying_questions=[
                    "더 구체적인 제품명이나 상황을 알려주시면 더 정확한 정보를 찾을 수 있습니다.",
                ],
            )

        # 결과가 1건 이상이면 sufficient
        if total_doc_count > 0:
            return SufficiencyResult(
                confidence=1.0,
                is_sufficient=True,
                level="sufficient",
                reason=f"검색된 문서 {total_doc_count}건으로 답변 생성이 가능합니다.",
                clarifying_questions=[],
            )

        # 결과가 0건일 때만 insufficient
        return SufficiencyResult(
            confidence=0.0,
            is_sufficient=False,
            level="insufficient",
            reason="검색 결과가 없습니다. 질문을 더 구체적으로 해주세요.",
            clarifying_questions=[
                "분쟁 발생 날짜가 언제인가요?",
                "구입한 제품/서비스의 구체적인 명칭은 무엇인가요?",
                "어떤 문제가 발생했는지 자세히 설명해 주시겠어요?",
            ],
        )

    def _generate_reason(
        self,
        level: str,
        max_similarity: float,
        relevant_doc_count: int,
        has_laws: bool,
        has_criteria: bool,
    ) -> str:
        """충분성 판단 이유를 한국어로 생성"""
        if level == "sufficient":
            return (
                f"검색된 문서의 유사도(최대 {max_similarity:.2f})가 충분하고, "
                f"관련 문서 {relevant_doc_count}개가 발견되었으며, "
                f"법령 또는 기준이 포함되어 답변 생성이 가능합니다."
            )
        elif level == "partial":
            issues = []
            if max_similarity < self.min_similarity:
                issues.append(f"유사도(최대 {max_similarity:.2f})가 기준({self.min_similarity})보다 낮음")
            if relevant_doc_count < self.min_documents:
                issues.append(f"관련 문서 수({relevant_doc_count}개)가 부족함")
            if not has_laws and not has_criteria:
                issues.append("법령 및 기준 문서 없음")

            return f"일부 정보만 발견되었습니다: {', '.join(issues)}"
        else:  # insufficient
            issues = []
            if max_similarity < self.low_threshold:
                issues.append("유사도가 매우 낮음")
            if relevant_doc_count == 0:
                issues.append("관련 문서를 찾지 못함")
            if not has_laws and not has_criteria:
                issues.append("법적 근거 없음")

            return f"검색 결과가 불충분합니다: {', '.join(issues)}. 질문을 더 구체적으로 해주세요."
