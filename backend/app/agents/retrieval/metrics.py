"""
똑소리 RAG - 검색 품질 평가 메트릭

섹션별 검색 품질 측정:
- Domain (기관추천): Accuracy
- Cases (유사사례): nDCG@K, MRR
- Laws (법령): Precision@K, Recall
- Criteria (기준): Precision@K, Recall

전체 메트릭:
- Overall nDCG@K
- Overall MRR
- Hit Rate@K
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Union


def calculate_ndcg(retrieved: List[str], relevant: Set[str], k: int = 3) -> float:
    """
    Normalized Discounted Cumulative Gain (nDCG@K)

    상위 K개 결과의 순위 품질을 측정합니다.
    관련 문서가 상위에 있을수록 점수가 높습니다.

    Args:
        retrieved: 검색된 문서 ID 리스트 (순서대로)
        relevant: 관련 문서 ID 집합
        k: 상위 K개만 평가

    Returns:
        nDCG 점수 (0.0 ~ 1.0)
    """
    if not relevant:
        return 0.0

    # DCG (Discounted Cumulative Gain)
    dcg = 0.0
    for i, doc_id in enumerate(retrieved[:k]):
        if doc_id in relevant:
            # relevance = 1 for binary relevance
            dcg += 1.0 / math.log2(i + 2)  # i+2 because log2(1) = 0

    # IDCG (Ideal DCG) - 모든 관련 문서가 상위에 있는 경우
    ideal_length = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_length))

    return dcg / idcg if idcg > 0 else 0.0


def calculate_mrr(retrieved: List[str], relevant: Set[str]) -> float:
    """
    Mean Reciprocal Rank (MRR)

    첫 번째 관련 문서의 역순위를 계산합니다.
    관련 문서가 빨리 나올수록 점수가 높습니다.

    Args:
        retrieved: 검색된 문서 ID 리스트 (순서대로)
        relevant: 관련 문서 ID 집합

    Returns:
        MRR 점수 (0.0 ~ 1.0)
    """
    for i, doc_id in enumerate(retrieved):
        if doc_id in relevant:
            return 1.0 / (i + 1)
    return 0.0


def calculate_precision_at_k(
    retrieved: List[str], relevant: Set[str], k: int = 3
) -> float:
    """
    Precision@K

    상위 K개 중 관련 문서의 비율을 계산합니다.

    Args:
        retrieved: 검색된 문서 ID 리스트
        relevant: 관련 문서 ID 집합
        k: 상위 K개만 평가

    Returns:
        Precision 점수 (0.0 ~ 1.0)
    """
    if k == 0:
        return 0.0

    retrieved_k = retrieved[:k]
    hits = len(set(retrieved_k) & relevant)
    return hits / k


def calculate_recall(retrieved: List[str], relevant: Set[str]) -> float:
    """
    Recall

    전체 관련 문서 중 검색된 비율을 계산합니다.

    Args:
        retrieved: 검색된 문서 ID 리스트
        relevant: 관련 문서 ID 집합

    Returns:
        Recall 점수 (0.0 ~ 1.0)
    """
    if not relevant:
        return 0.0

    hits = len(set(retrieved) & relevant)
    return hits / len(relevant)


def calculate_domain_accuracy(predicted: str, expected: str) -> float:
    """
    Domain (기관추천) 정확도

    Args:
        predicted: 예측된 기관 코드 (KCA, ECMC, KCDRC)
        expected: 기대 기관 코드

    Returns:
        1.0 if match, 0.0 otherwise
    """
    return 1.0 if predicted == expected else 0.0


def calculate_hit_rate(retrieved: List[str], relevant: Set[str], k: int = 3) -> float:
    """
    Hit Rate@K

    상위 K개 중 관련 문서가 하나라도 있으면 1, 없으면 0

    Args:
        retrieved: 검색된 문서 ID 리스트
        relevant: 관련 문서 ID 집합
        k: 상위 K개만 평가

    Returns:
        1.0 if hit, 0.0 otherwise
    """
    retrieved_k = set(retrieved[:k])
    return 1.0 if retrieved_k & relevant else 0.0


@dataclass
class SectionMetrics:
    """섹션별 평가 결과"""

    section: str
    ndcg: float = 0.0
    mrr: float = 0.0
    precision_at_k: float = 0.0
    recall: float = 0.0
    hit_rate: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            f"{self.section}_ndcg": self.ndcg,
            f"{self.section}_mrr": self.mrr,
            f"{self.section}_precision@k": self.precision_at_k,
            f"{self.section}_recall": self.recall,
            f"{self.section}_hit_rate": self.hit_rate,
        }


@dataclass
class EvaluationResult:
    """단일 평가 항목 결과"""

    item_id: str
    question: str
    category: str

    # 섹션별 메트릭
    domain_accuracy: float = 0.0
    cases_metrics: Optional[SectionMetrics] = None
    laws_metrics: Optional[SectionMetrics] = None
    criteria_metrics: Optional[SectionMetrics] = None

    # 전체 메트릭
    overall_ndcg: float = 0.0
    overall_mrr: float = 0.0
    overall_hit_rate: float = 0.0

    # 메타 정보
    predicted_agency: str = ""
    expected_agency: str = ""
    retrieval_time_ms: float = 0.0

    def to_dict(self) -> Dict:
        result = {
            "id": self.item_id,
            "question": self.question,
            "category": self.category,
            "domain_accuracy": self.domain_accuracy,
            "predicted_agency": self.predicted_agency,
            "expected_agency": self.expected_agency,
            "overall_ndcg": self.overall_ndcg,
            "overall_mrr": self.overall_mrr,
            "overall_hit_rate": self.overall_hit_rate,
            "retrieval_time_ms": self.retrieval_time_ms,
        }

        if self.cases_metrics:
            result.update(self.cases_metrics.to_dict())
        if self.laws_metrics:
            result.update(self.laws_metrics.to_dict())
        if self.criteria_metrics:
            result.update(self.criteria_metrics.to_dict())

        return result


class RetrievalMetrics:
    """
    RAG 검색 품질 평가기

    Usage:
        metrics = RetrievalMetrics(k=3)

        result = metrics.evaluate_item(
            item_id="eval_001",
            question="에어컨 환불",
            category="전자상거래_환불",
            retrieved_results=search_results,
            expected_contexts=ground_truth,
            expected_agency="KCA",
            predicted_agency="KCA"
        )
    """

    def __init__(self, k: int = 3):
        """
        Args:
            k: Precision@K, nDCG@K 등의 K 값
        """
        self.k = k

    def evaluate_section(
        self, section: str, retrieved_ids: List[str], relevant_ids: Set[str]
    ) -> SectionMetrics:
        """
        단일 섹션 평가

        Args:
            section: 섹션명 (cases, laws, criteria)
            retrieved_ids: 검색된 문서 ID 리스트
            relevant_ids: 관련 문서 ID 집합
        """
        return SectionMetrics(
            section=section,
            ndcg=calculate_ndcg(retrieved_ids, relevant_ids, self.k),
            mrr=calculate_mrr(retrieved_ids, relevant_ids),
            precision_at_k=calculate_precision_at_k(
                retrieved_ids, relevant_ids, self.k
            ),
            recall=calculate_recall(retrieved_ids, relevant_ids),
            hit_rate=calculate_hit_rate(retrieved_ids, relevant_ids, self.k),
        )

    def evaluate_item(
        self,
        item_id: str,
        question: str,
        category: str,
        retrieved_results: Dict[str, List[Dict]],
        expected_contexts: List[Dict],
        expected_agency: str,
        predicted_agency: str,
        retrieval_time_ms: float = 0.0,
    ) -> EvaluationResult:
        """
        단일 평가 항목 전체 평가

        Args:
            item_id: 평가 항목 ID
            question: 질문
            category: 카테고리
            retrieved_results: 섹션별 검색 결과
                {
                    'disputes': [...],
                    'counsels': [...],
                    'laws': [...],
                    'criteria': [...]
                }
            expected_contexts: 기대 context 리스트
                [
                    {"doc_type": "law", "doc_id": "...", "relevance": "essential"},
                    ...
                ]
            expected_agency: 기대 기관 코드
            predicted_agency: 예측 기관 코드
            retrieval_time_ms: 검색 소요 시간
        """
        result = EvaluationResult(
            item_id=item_id,
            question=question,
            category=category,
            predicted_agency=predicted_agency,
            expected_agency=expected_agency,
            retrieval_time_ms=retrieval_time_ms,
        )

        # Domain 정확도
        result.domain_accuracy = calculate_domain_accuracy(
            predicted_agency, expected_agency
        )

        # expected_contexts를 doc_type별로 분류
        expected_by_type = self._group_expected_by_type(expected_contexts)

        # Cases 섹션 평가 (disputes + counsels)
        cases_retrieved = []
        for d in retrieved_results.get("disputes", []):
            cases_retrieved.append(self._get_doc_id(d))
        for c in retrieved_results.get("counsels", []):
            cases_retrieved.append(self._get_doc_id(c))

        cases_relevant = (
            expected_by_type.get("mediation_case", set())
            | expected_by_type.get("counsel_case", set())
            | expected_by_type.get("case", set())
        )

        if cases_relevant:
            result.cases_metrics = self.evaluate_section(
                "cases", cases_retrieved, cases_relevant
            )

        # Laws 섹션 평가
        laws_retrieved = [
            self._get_doc_id(l) for l in retrieved_results.get("laws", [])
        ]
        laws_relevant = expected_by_type.get("law", set())

        if laws_relevant:
            result.laws_metrics = self.evaluate_section(
                "laws", laws_retrieved, laws_relevant
            )

        # Criteria 섹션 평가
        criteria_retrieved = [
            self._get_doc_id(c) for c in retrieved_results.get("criteria", [])
        ]
        criteria_relevant = expected_by_type.get("criteria", set())

        if criteria_relevant:
            result.criteria_metrics = self.evaluate_section(
                "criteria", criteria_retrieved, criteria_relevant
            )

        # 전체 메트릭 계산
        all_retrieved = cases_retrieved + laws_retrieved + criteria_retrieved
        all_relevant = set()
        for ids in expected_by_type.values():
            all_relevant.update(ids)

        # essential만 필터링
        essential_relevant = self._get_essential_ids(expected_contexts)

        result.overall_ndcg = calculate_ndcg(all_retrieved, all_relevant, self.k * 3)
        result.overall_mrr = calculate_mrr(
            all_retrieved, essential_relevant or all_relevant
        )
        result.overall_hit_rate = calculate_hit_rate(
            all_retrieved, essential_relevant or all_relevant, self.k * 3
        )

        return result

    def _group_expected_by_type(
        self, expected_contexts: List[Dict]
    ) -> Dict[str, Set[str]]:
        """expected_contexts를 doc_type별로 그룹화"""
        grouped = {}
        for ctx in expected_contexts:
            doc_type = ctx.get("doc_type", "")
            doc_id = ctx.get("doc_id") or ctx.get("unit_id", "")

            if doc_type not in grouped:
                grouped[doc_type] = set()
            if doc_id:
                grouped[doc_type].add(doc_id)

        return grouped

    def _get_essential_ids(self, expected_contexts: List[Dict]) -> Set[str]:
        """essential relevance를 가진 문서 ID만 추출"""
        return {
            ctx.get("doc_id") or ctx.get("unit_id", "")
            for ctx in expected_contexts
            if ctx.get("relevance") == "essential"
        }

    def _get_doc_id(self, doc: Dict) -> str:
        """검색 결과에서 문서 ID 추출"""
        return doc.get("doc_id") or doc.get("chunk_id") or doc.get("unit_id", "")


def aggregate_results(results: List[EvaluationResult]) -> Dict[str, float]:
    """
    여러 평가 결과를 집계하여 평균 메트릭 계산

    Args:
        results: EvaluationResult 리스트

    Returns:
        평균 메트릭 딕셔너리
    """
    if not results:
        return {}

    # 모든 메트릭 키 수집
    all_metrics = {}
    for r in results:
        r_dict = r.to_dict()
        for key, value in r_dict.items():
            if isinstance(value, (int, float)) and key not in ("retrieval_time_ms",):
                if key not in all_metrics:
                    all_metrics[key] = []
                all_metrics[key].append(value)

    # 평균 계산
    summary = {}
    for key, values in all_metrics.items():
        valid_values = [v for v in values if v is not None]
        if valid_values:
            mean = sum(valid_values) / len(valid_values)
            summary[f"{key}_mean"] = round(mean, 4)

            # 표준편차
            if len(valid_values) > 1:
                variance = sum((v - mean) ** 2 for v in valid_values) / len(
                    valid_values
                )
                summary[f"{key}_std"] = round(math.sqrt(variance), 4)

    return summary
