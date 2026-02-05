"""
똑소리 프로젝트 - 하이브리드 법률 검토기
작성일: 2026-01-21
S2-PR2: 법률 검토 하이브리드 (규칙 + LLM)

배경:
- 현재 규칙 기반 검토만 사용
- 복잡한 문맥 이해 불가, 미묘한 위반 탐지 어려움

해결:
- 규칙 기반 검토 (빠름, 명확한 패턴) + LLM 기반 검토 (문맥 이해)
- LLM 실패 시 graceful degradation
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ...common.config import get_config

if TYPE_CHECKING:
    from ...supervisor.state import ChatState, ReviewResult

logger = logging.getLogger(__name__)

# LLM 재시도 설정
MAX_LLM_RETRIES = 2
RETRY_DELAY_SEC = 1.0

# 출처 본문 최대 문자 수 (한국어 기준 ~700-1000 토큰)
MAX_SOURCE_CONTENT_CHARS = 350


def _get_agent_functions():
    from .agent import (
        _build_violation_messages,
        _check_citation_presence,
        _check_evidence_sufficiency,
        _check_prohibited_expressions,
        _filter_prohibited_expressions,
    )

    return (
        _check_prohibited_expressions,
        _check_citation_presence,
        _check_evidence_sufficiency,
        _filter_prohibited_expressions,
        _build_violation_messages,
    )


# =============================================================================
# LLM Review 프롬프트 (Enhanced - Phase 1)
# =============================================================================

LLM_REVIEW_SYSTEM_PROMPT = """당신은 소비자 분쟁 해결 가이드 '똑소리'의 최종 품질 감사관입니다. 
제시된 [입력 데이터]와 [생성된 답변]을 비교하되, 아래의 **[품질 검토 기준]**을 최우선으로 적용하십시오.

### [품질 검토 기준 (v2.4.1 업데이트)]
1. **수치 할루시네이션 완화**: 
   - 데이터에 구체적인 숫자(%, 원)가 없는데 모델이 **숫자를 지어낸 경우만 반려**하십시오.
   - **[PASS 허용]**: "일정 비율", "관련 기준에 따른 위약금", "정당한 보상" 등 추상적인 표현은 할루시네이션이 아닌 '안전한 가이드'로 간주하여 무조건 통과시키십시오.

2. **용어 교정 정당성 인정**:
   - 답변의 '해지/해제' 선택이 JSON 데이터 원문과 다르더라도, **업종 성격(계속거래 vs 일회성)**에 맞춰 모델이 합리적으로 교정했다면 반려하지 마십시오. 
   - 예: 데이터 원문에 '해제'라고 되어 있어도 피부과/헬스장 케이스에서 모델이 '해지'라고 썼다면 이는 올바른 교정으로 간주합니다.

3. **데이터 활용 위계 및 Fallback**:
   - 데이터가 하나라도 존재함에도 데이터를 설명하지 않고 곧바로 『1372 소비자상담센터』로 안내했다면 '데이터 활용 미흡'으로 반려하십시오.
   - **모든 데이터**가 '데이터 없음'일 때 『1372 소비자상담센터』를 안내하는 것은 정상적인 대응(Fallback)이므로 반려하지 마십시오.

4. **완벽한 데이터 고립**: 
   - 데이터가 '데이터 없음'인 섹션에 대해 내용을 지어냈다면 반려하십시오. (단, 화이트리스트 용어 및 일반적 위로는 허용)

5. **중복 검사 (예외 규정)**: 
   - 동일 문장이 의미 없이 반복되는 경우만 반려하십시오.
   - **[허용 사항]**: 아래의 경우는 중복으로 간주하지 말고 무조건 통과시키십시오.
     1) 용어 병기 규칙(`단어(풀이)`)에 의한 반복적 노출.
     2) 본문에 적힌 '역질문 리스트'와 하단의 '버튼형 역질문' 내용이 동일한 경우.

6. **법적 판단/결론 탐지 (Critical)**:
   - "이것은 위법입니다", "불법입니다", "승소할 수 있습니다" 등 단정적 표현은 반려하십시오.
   - "위법 소지가 있습니다", "승소 가능성이 있습니다" 등 완화된 표현은 허용하십시오.

## 응답 형식 (JSON만 반환)

```json
{
  "passed": true | false,
  "issues": [
    {
      "type": "용어 병기|데이터 고립|법적 판단|전문가 사칭|근거 없는 주장|확정적 표현|형식 위반",
      "text": "발견된 텍스트",
      "severity": "low|medium|high",
      "suggestion": "수정 제안"
    }
  ],
  "legal_judgment_detected": true | false,
  "hedging_level": "safe|caution|dangerous",
  "overall_severity": "low|medium|high",
  "overall_comment": "전체 평가 요약"
}
```"""


LLM_REVIEW_USER_PROMPT_TEMPLATE = """## 사용자 질문
{query}

## 검색된 출처 (신뢰할 수 있는 정보)
{sources}

## 생성된 답변 (검토 대상)
{answer}

---
위 정보를 바탕으로 다음을 검증하세요:
1. 답변에 법적 판단/결론이 포함되어 있는가? (변호사법 위반 가능성)
2. 답변이 출처에 기반한 정보만 포함하는가? (Hallucination 여부)
3. 확정적/단정적 표현이 사용되었는가? (Hedging level)
4. 전문가 사칭이나 부적절한 조언이 있는가?

JSON 형식으로만 응답하세요."""


# =============================================================================
# LLM Review 결과 데이터 클래스
# =============================================================================


@dataclass
class LLMReviewResult:
    """LLM 기반 검토 결과 (Enhanced)"""

    passed: bool = True
    issues: List[Dict[str, str]] = field(default_factory=list)
    severity: str = "low"  # low, medium, high
    overall_comment: str = ""
    error: Optional[str] = None
    latency_ms: float = 0.0
    # Enhanced fields
    legal_judgment_detected: bool = False
    hedging_level: str = "safe"  # safe, caution, dangerous
    overall_severity: str = "low"


# =============================================================================
# 하이브리드 법률 검토기
# =============================================================================


class HybridLegalReviewer:
    """
    하이브리드 법률 검토기 (규칙 + LLM)

    2단계 검토:
    1단계: 규칙 기반 검토 (빠름, 명확한 패턴)
    2단계: LLM 기반 검토 (문맥 이해, 미묘한 위반) - 선택적

    Usage:
        reviewer = HybridLegalReviewer()
        result = reviewer.review(state)
    """

    def __init__(self, enable_llm: Optional[bool] = None):
        """
        Args:
            enable_llm: LLM 검토 활성화 여부.
                       None이면 환경 변수(ENABLE_LLM_REVIEW) 참조.
        """
        if enable_llm is not None:
            self.enable_llm = enable_llm
        else:
            self.enable_llm = os.getenv("ENABLE_LLM_REVIEW", "false").lower() == "true"

        self._llm_call_count = 0
        self._total_llm_latency_ms = 0.0

        logger.info(f"[HybridLegalReviewer] initialized, enable_llm={self.enable_llm}")

    # =========================================================================
    # 공개 API
    # =========================================================================

    def review(self, state: "ChatState") -> Dict:
        """
        2단계 하이브리드 검토 (조건부 LLM)

        1단계: 규칙 기반 검토 (빠름, 명확한 패턴)
        2단계: LLM 기반 검토 - 위반 감지 시에만 실행 (비용 최적화)

        Args:
            state: 현재 ChatState

        Returns:
            부분 상태 업데이트 dict (review, final_answer, retry_count 등)
        """
        draft_answer = state.get("draft_answer", "") or ""
        query_analysis = state.get("query_analysis")
        sources = state.get("sources", [])
        retry_count = state.get("retry_count", 0) or 0
        user_query = state.get("query", "") or state.get("user_query", "") or ""

        # 일반 대화는 검토 스킵
        if query_analysis and query_analysis.get("query_type") == "general":
            review_result: "ReviewResult" = {
                "passed": True,
                "violations": [],
                "filtered_answer": None,
            }
            return {
                "review": review_result,
                "final_answer": draft_answer,
            }

        # 1단계: 규칙 기반 검토
        rule_result = self._rule_based_review(state)

        from ...common.config import AgentConfig

        rule_violation_count = len(rule_result.get("violations", []))
        has_violations = rule_violation_count > 0 or not rule_result["passed"]

        # 2단계: LLM 기반 검토 - 위반 감지 시에만 실행 (비용 최적화)
        if self.enable_llm and has_violations:
            logger.info(
                f"[HybridLegalReviewer] rule violations detected ({rule_violation_count}), "
                "triggering LLM secondary review"
            )
            # 컨텍스트 주입: query, sources 포함
            llm_result = self._llm_based_review_with_context(
                draft_answer=draft_answer, query=user_query, sources=sources
            )
            merged_result = self._merge_results(rule_result, llm_result)
            return self._format_final_result(merged_result, state, retry_count)

        # 규칙 기반에서 심각한 위반 발견 시 즉시 반환
        if (
            not rule_result["passed"]
            and rule_violation_count >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD
        ):
            logger.info(
                f"[HybridLegalReviewer] severe rule violations ({rule_violation_count})"
            )
            return self._format_final_result(rule_result, state, retry_count)

        return self._format_final_result(rule_result, state, retry_count)

    def get_metrics(self) -> Dict[str, Any]:
        """
        비용 모니터링용 메트릭 반환

        Returns:
            {
                'llm_call_count': int,
                'total_llm_latency_ms': float,
                'avg_llm_latency_ms': float,
                'enable_llm': bool,
            }
        """
        avg_latency = (
            self._total_llm_latency_ms / self._llm_call_count
            if self._llm_call_count > 0
            else 0.0
        )
        return {
            "llm_call_count": self._llm_call_count,
            "total_llm_latency_ms": round(self._total_llm_latency_ms, 2),
            "avg_llm_latency_ms": round(avg_latency, 2),
            "enable_llm": self.enable_llm,
        }

    def reset_metrics(self) -> None:
        """메트릭 초기화 (테스트용)"""
        self._llm_call_count = 0
        self._total_llm_latency_ms = 0.0

    # =========================================================================
    # 내부 메서드
    # =========================================================================

    def _rule_based_review(self, state: "ChatState") -> Dict:
        (
            _check_prohibited_expressions,
            _check_citation_presence,
            _check_evidence_sufficiency,
            _filter_prohibited_expressions,
            _build_violation_messages,
        ) = _get_agent_functions()

        draft_answer = state.get("draft_answer", "") or ""
        sources = state.get("sources", [])

        prohibited_violations = _check_prohibited_expressions(draft_answer)

        has_sources = len(sources) > 0
        has_citation = _check_citation_presence(draft_answer, has_sources)

        has_evidence = _check_evidence_sufficiency(state)

        violation_messages = _build_violation_messages(
            prohibited_violations, has_citation, has_evidence
        )

        passed = len(prohibited_violations) == 0 and (has_citation or not has_sources)

        from ...common.config import AgentConfig

        needs_retry = (
            len(prohibited_violations) >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD
        )

        if prohibited_violations and not needs_retry:
            filtered = _filter_prohibited_expressions(
                draft_answer, prohibited_violations
            )
        else:
            filtered = None

        return {
            "passed": passed,
            "violations": violation_messages,
            "filtered_answer": filtered,
            "prohibited_violations": prohibited_violations,
        }

    def _llm_based_review(self, draft_answer: str) -> LLMReviewResult:
        """
        LLM 기반 검토 (기본 - 컨텍스트 없음)

        Args:
            draft_answer: 검토할 답변 텍스트

        Returns:
            LLMReviewResult
        """
        return self._llm_based_review_with_context(draft_answer, query="", sources=[])

    def _llm_based_review_with_context(
        self, draft_answer: str, query: str = "", sources: List[Dict] = None
    ) -> LLMReviewResult:
        """
        LLM 기반 검토 (컨텍스트 주입)

        Query와 Sources를 함께 제공하여 더 정확한 검토를 수행합니다.
        - Hallucination 탐지: 출처에 없는 정보 인용 여부
        - Query 관련성: 질문에 적절히 답변하는지
        - 법적 판단: 출처를 벗어난 법적 결론 여부

        Args:
            draft_answer: 검토할 답변 텍스트
            query: 사용자 질문 (컨텍스트)
            sources: 검색된 출처 문서 리스트 (컨텍스트)

        Returns:
            LLMReviewResult
        """
        if sources is None:
            sources = []

        start_time = time.time()

        try:
            import openai as openai_module
            from openai import OpenAI

            client = OpenAI()
            config = get_config()
            review_model = config.models.review_agent

            # 출처 텍스트 포맷팅
            sources_text = self._format_sources_for_prompt(sources)

            # 컨텍스트 주입 프롬프트 생성
            user_prompt = LLM_REVIEW_USER_PROMPT_TEMPLATE.format(
                query=query if query else "(질문 없음)",
                sources=sources_text if sources_text else "(출처 없음)",
                answer=draft_answer,
            )

            # 재시도 로직이 포함된 API 호출
            response = None
            last_error = None
            for attempt in range(MAX_LLM_RETRIES + 1):
                try:
                    response = client.chat.completions.create(
                        model=review_model,
                        messages=[
                            {"role": "system", "content": LLM_REVIEW_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format={"type": "json_object"},
                        timeout=15,
                    )
                    break
                except (
                    openai_module.RateLimitError,
                    openai_module.APIStatusError,
                ) as e:
                    last_error = e
                    if attempt < MAX_LLM_RETRIES:
                        logger.warning(
                            f"[llm_review] API call failed (attempt {attempt + 1}/{MAX_LLM_RETRIES + 1}): {e}"
                        )
                        time.sleep(RETRY_DELAY_SEC * (attempt + 1))
                        continue
                    logger.warning(
                        f"[llm_review] API call failed after {MAX_LLM_RETRIES + 1} attempts: {e}"
                    )

            if response is None:
                latency_ms = (time.time() - start_time) * 1000
                self._llm_call_count += 1
                self._total_llm_latency_ms += latency_ms
                logger.warning(
                    "[llm_review] All retries exhausted, degrading to rule-based review only"
                )
                return LLMReviewResult(
                    passed=True,
                    error=f"api_retry_exhausted: {str(last_error)}",
                    latency_ms=latency_ms,
                    overall_comment="LLM review skipped due to API failure; rule-based review only",
                )

            # 메트릭 업데이트
            latency_ms = (time.time() - start_time) * 1000
            self._llm_call_count += 1
            self._total_llm_latency_ms += latency_ms

            # JSON 파싱
            content = response.choices[0].message.content
            result_dict = json.loads(content)

            return LLMReviewResult(
                passed=result_dict.get("passed", True),
                issues=result_dict.get("issues", []),
                severity=result_dict.get("severity", "low"),
                overall_comment=result_dict.get("overall_comment", ""),
                latency_ms=latency_ms,
                legal_judgment_detected=result_dict.get(
                    "legal_judgment_detected", False
                ),
                hedging_level=result_dict.get("hedging_level", "safe"),
                overall_severity=result_dict.get("overall_severity", "low"),
            )

        except ImportError:
            logger.warning("[llm_review] OpenAI package not installed")
            return LLMReviewResult(error="openai_not_installed")

        except json.JSONDecodeError as e:
            latency_ms = (time.time() - start_time) * 1000
            self._llm_call_count += 1
            self._total_llm_latency_ms += latency_ms
            logger.warning(f"[llm_review] JSON parsing failed: {e}")
            return LLMReviewResult(
                error=f"json_parse_error: {str(e)}", latency_ms=latency_ms
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(f"[llm_review] LLM review failed: {e}")
            return LLMReviewResult(error=str(e), latency_ms=latency_ms)

    def _format_sources_for_prompt(
        self, sources: List[Dict], max_chars: int = 2000
    ) -> str:
        """
        출처 문서를 프롬프트용 텍스트로 포맷팅

        Args:
            sources: 검색된 출처 문서 리스트
            max_chars: 최대 문자 수 (토큰 절약)

        Returns:
            포맷팅된 출처 텍스트
        """
        if not sources:
            return ""

        formatted_parts = []
        total_chars = 0

        for i, source in enumerate(sources[:5], 1):  # 최대 5개
            content = source.get("content", "") or source.get("text", "") or str(source)
            title = source.get("title", "") or source.get("doc_type", f"출처 {i}")

            # 한국어 토큰 특성 고려 (1글자 ≈ 2-3 토큰)
            if len(content) > MAX_SOURCE_CONTENT_CHARS:
                content = content[:MAX_SOURCE_CONTENT_CHARS] + "..."

            # Sanitize to prevent prompt injection
            title = title.replace("{", "").replace("}", "")
            content = content.replace("{", "").replace("}", "")
            part = f"[{title}]\n{content}"

            if total_chars + len(part) > max_chars:
                break

            formatted_parts.append(part)
            total_chars += len(part)

        return "\n\n".join(formatted_parts)

    def _merge_results(self, rule_result: Dict, llm_result: LLMReviewResult) -> Dict:
        """
        규칙/LLM 결과 병합

        규칙 기반: 패턴 매칭으로 명확한 위반 탐지
        LLM 기반: 문맥 이해로 미묘한 위반 탐지

        병합 전략:
        - 규칙 위반이 있으면 우선 적용
        - LLM 이슈를 추가로 병합
        - LLM이 오탐(false positive)으로 판단하면 위반 완화
        - passed는 LLM 결과를 더 신뢰 (문맥 이해)
        """
        # LLM 실패 시 규칙 결과만 반환
        if llm_result.error:
            logger.info(
                f"[HybridLegalReviewer] LLM review failed ({llm_result.error}), using rule result only"
            )
            return rule_result

        combined_violations = rule_result["violations"].copy()

        # LLM에서 추가 이슈 발견 시 병합
        if llm_result.issues:
            for issue in llm_result.issues:
                issue_type = issue.get("type", "unknown")
                issue_text = issue.get("text", "")
                issue_severity = issue.get("severity", "low")
                combined_violations.append(
                    f"[LLM-{issue_severity}] {issue_type}: {issue_text}"
                )

        # 법적 판단 탐지 시 강제 실패
        if llm_result.legal_judgment_detected:
            logger.warning("[HybridLegalReviewer] Legal judgment detected by LLM")
            combined_violations.append("[LLM-high] 법적 판단/결론 탐지됨")

        # 최종 통과 여부
        # LLM이 통과하고 규칙 위반이 경미하면 통과
        # LLM이 법적 판단 탐지하면 실패
        if llm_result.legal_judgment_detected:
            final_passed = False
        elif llm_result.passed and llm_result.overall_severity == "low":
            # LLM이 문맥상 안전하다고 판단하면 규칙 위반 완화
            final_passed = True
            logger.info(
                "[HybridLegalReviewer] LLM verified as safe, relaxing rule violations"
            )
        else:
            final_passed = rule_result["passed"] and llm_result.passed

        return {
            "passed": final_passed,
            "violations": combined_violations,
            "filtered_answer": rule_result.get("filtered_answer"),
            "llm_severity": llm_result.overall_severity,
            "llm_comment": llm_result.overall_comment,
            "legal_judgment_detected": llm_result.legal_judgment_detected,
            "hedging_level": llm_result.hedging_level,
        }

    def _format_final_result(
        self, review_result: Dict, state: "ChatState", retry_count: int
    ) -> Dict:
        """
        최종 결과 포맷팅 (기존 review_node 반환 형식과 호환)

        Returns:
            {
                'review': ReviewResult,
                'final_answer': str (passed=True인 경우),
                'retry_count': int (needs_retry인 경우 증가)
            }
        """
        from ...common.config import AgentConfig

        draft_answer = state.get("draft_answer", "")
        violations = review_result.get("violations", [])
        passed = review_result.get("passed", False)
        filtered = review_result.get("filtered_answer")

        # 재생성 필요 여부 판단
        # prohibited_violations가 있으면 그 수로 판단, 아니면 violations 수로
        prohibited_count = len(review_result.get("prohibited_violations", []))
        if prohibited_count == 0:
            # 규칙 위반 중 금지 표현 관련만 카운트
            prohibited_count = sum(
                1 for v in violations if "금지 표현" in v or "[LLM]" in v
            )

        needs_retry = (
            prohibited_count >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD
            and retry_count < AgentConfig.MAX_REVIEW_RETRIES
        )

        review_output: "ReviewResult" = {
            "passed": passed,
            "violations": violations,
            "filtered_answer": filtered,
        }

        if needs_retry:
            # 재생성 필요
            return {
                "review": review_output,
                "retry_count": retry_count + 1,
            }
        elif passed:
            # 통과
            return {
                "review": review_output,
                "final_answer": draft_answer,
            }
        else:
            # 필터링된 답변 사용
            final = filtered if filtered else draft_answer
            return {
                "review": review_output,
                "final_answer": final,
            }


# =============================================================================
# 노드 함수 (기존 review_node 대체용)
# =============================================================================

# 모듈 레벨 싱글턴 인스턴스
_reviewer_instance: Optional[HybridLegalReviewer] = None
_reviewer_lock = threading.Lock()


def get_reviewer() -> HybridLegalReviewer:
    """싱글턴 reviewer 인스턴스 반환 (thread-safe)"""
    global _reviewer_instance
    if _reviewer_instance is None:
        with _reviewer_lock:
            if _reviewer_instance is None:
                _reviewer_instance = HybridLegalReviewer()
    return _reviewer_instance


def hybrid_review_node(state: "ChatState") -> Dict:
    """
    하이브리드 검토 노드 함수

    기존 review_node를 대체하여 사용 가능.

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트 dict
    """
    reviewer = get_reviewer()
    return reviewer.review(state)


def hybrid_review_node_wrapper(state: "ChatState") -> Dict:
    """
    PR-2: 통합 그래프용 하이브리드 리뷰 노드 래퍼

    chat_type에 따라 리뷰 동작을 분기:
    - general: 자동 통과 (draft_answer → final_answer)
    - dispute: 하이브리드 리뷰 수행

    Args:
        state: 현재 ChatState (또는 UnifiedState)

    Returns:
        부분 상태 업데이트 dict
    """
    chat_type = state.get("chat_type", "dispute")

    if chat_type == "general":
        # 일반 채팅: 리뷰 스킵
        draft_answer = state.get("draft_answer", "")
        review_result: "ReviewResult" = {
            "passed": True,
            "violations": [],
            "filtered_answer": None,
        }
        return {
            "review": review_result,
            "final_answer": draft_answer,
        }

    return hybrid_review_node(state)
