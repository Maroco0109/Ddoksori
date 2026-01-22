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
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...orchestrator.state import ChatState, ReviewResult

logger = logging.getLogger(__name__)


def _get_agent_functions():
    from .agent import (
        _check_prohibited_expressions,
        _check_citation_presence,
        _check_evidence_sufficiency,
        _filter_prohibited_expressions,
        _build_violation_messages,
    )
    return (
        _check_prohibited_expressions,
        _check_citation_presence,
        _check_evidence_sufficiency,
        _filter_prohibited_expressions,
        _build_violation_messages,
    )


# =============================================================================
# LLM Review 프롬프트
# =============================================================================

LLM_REVIEW_SYSTEM_PROMPT = """당신은 법률 문서 검토 전문가입니다.

다음 답변을 검토하고, 아래 기준에 따라 문제점을 찾아주세요:

## 검토 기준
1. **법적 단정**: "반드시", "확실히", "100%" 등 확정적 표현
2. **전문가 사칭**: "변호사로서", "법률 전문가로서" 등
3. **근거 없는 주장**: 출처 없이 특정 결과 보장
4. **부적절한 조언**: 소송 권유, 특정 기관 비방 등

## 응답 형식 (JSON만 반환, 다른 텍스트 없이)
{
  "passed": true,
  "issues": [],
  "severity": "low",
  "overall_comment": "전체 평가"
}

또는 문제가 있는 경우:
{
  "passed": false,
  "issues": [
    {"type": "법적 단정", "text": "발견된 텍스트", "suggestion": "수정 제안"}
  ],
  "severity": "medium",
  "overall_comment": "전체 평가"
}"""


# =============================================================================
# LLM Review 결과 데이터 클래스
# =============================================================================

@dataclass
class LLMReviewResult:
    """LLM 기반 검토 결과"""
    passed: bool = True
    issues: List[Dict[str, str]] = field(default_factory=list)
    severity: str = "low"  # low, medium, high
    overall_comment: str = ""
    error: Optional[str] = None
    latency_ms: float = 0.0


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
            self.enable_llm = os.getenv('ENABLE_LLM_REVIEW', 'false').lower() == 'true'
        
        self._llm_call_count = 0
        self._total_llm_latency_ms = 0.0
        
        logger.info(f"[HybridLegalReviewer] initialized, enable_llm={self.enable_llm}")
    
    # =========================================================================
    # 공개 API
    # =========================================================================
    
    def review(self, state: "ChatState") -> Dict:
        """
        2단계 하이브리드 검토
        
        1단계: 규칙 기반 검토 (빠름, 명확한 패턴)
        2단계: LLM 기반 검토 (문맥 이해, 미묘한 위반) - 선택적
        
        Args:
            state: 현재 ChatState
            
        Returns:
            부분 상태 업데이트 dict (review, final_answer, retry_count 등)
        """
        draft_answer = state.get('draft_answer', '') or ''
        query_analysis = state.get('query_analysis')
        sources = state.get('sources', [])
        retry_count = state.get('retry_count', 0) or 0
        
        # 일반 대화는 검토 스킵
        if query_analysis and query_analysis.get('query_type') == 'general':
            review_result: "ReviewResult" = {
                'passed': True,
                'violations': [],
                'filtered_answer': None,
            }
            return {
                'review': review_result,
                'final_answer': draft_answer,
            }
        
        # 1단계: 규칙 기반 검토
        rule_result = self._rule_based_review(state)
        
        # 규칙 기반에서 심각한 위반 발견 시 즉시 반환 (LLM 스킵)
        from ...common.config import AgentConfig
        rule_violation_count = len(rule_result.get('violations', []))
        
        if not rule_result['passed'] and rule_violation_count >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD:
            logger.info(f"[HybridLegalReviewer] severe rule violations ({rule_violation_count}), skipping LLM review")
            return self._format_final_result(rule_result, state, retry_count)
        
        # 2단계: LLM 기반 검토 (규칙 통과 또는 경미한 위반)
        if self.enable_llm and rule_result['passed']:
            llm_result = self._llm_based_review(draft_answer)
            merged_result = self._merge_results(rule_result, llm_result)
            return self._format_final_result(merged_result, state, retry_count)
        
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
            if self._llm_call_count > 0 else 0.0
        )
        return {
            'llm_call_count': self._llm_call_count,
            'total_llm_latency_ms': round(self._total_llm_latency_ms, 2),
            'avg_llm_latency_ms': round(avg_latency, 2),
            'enable_llm': self.enable_llm,
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
        
        draft_answer = state.get('draft_answer', '') or ''
        sources = state.get('sources', [])
        
        prohibited_violations = _check_prohibited_expressions(draft_answer)
        
        has_sources = len(sources) > 0
        has_citation = _check_citation_presence(draft_answer, has_sources)
        
        has_evidence = _check_evidence_sufficiency(state)
        
        violation_messages = _build_violation_messages(
            prohibited_violations, has_citation, has_evidence
        )
        
        passed = (
            len(prohibited_violations) == 0 
            and (has_citation or not has_sources)
        )
        
        from ...common.config import AgentConfig
        needs_retry = (
            len(prohibited_violations) >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD
        )
        
        if prohibited_violations and not needs_retry:
            filtered = _filter_prohibited_expressions(draft_answer, prohibited_violations)
        else:
            filtered = None
        
        return {
            'passed': passed,
            'violations': violation_messages,
            'filtered_answer': filtered,
            'prohibited_violations': prohibited_violations,
        }
    
    def _llm_based_review(self, draft_answer: str) -> LLMReviewResult:
        """
        LLM 기반 검토
        
        Args:
            draft_answer: 검토할 답변 텍스트
            
        Returns:
            LLMReviewResult
        """
        start_time = time.time()
        
        try:
            from openai import OpenAI
            client = OpenAI()
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": LLM_REVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": f"검토할 답변:\n\n{draft_answer}"}
                ],
                response_format={"type": "json_object"},
                timeout=10,
            )
            
            # 메트릭 업데이트
            latency_ms = (time.time() - start_time) * 1000
            self._llm_call_count += 1
            self._total_llm_latency_ms += latency_ms
            
            # JSON 파싱
            content = response.choices[0].message.content
            result_dict = json.loads(content)
            
            return LLMReviewResult(
                passed=result_dict.get('passed', True),
                issues=result_dict.get('issues', []),
                severity=result_dict.get('severity', 'low'),
                overall_comment=result_dict.get('overall_comment', ''),
                latency_ms=latency_ms,
            )
            
        except ImportError:
            logger.warning("[llm_review] OpenAI package not installed")
            return LLMReviewResult(error="openai_not_installed")
            
        except json.JSONDecodeError as e:
            latency_ms = (time.time() - start_time) * 1000
            self._llm_call_count += 1
            self._total_llm_latency_ms += latency_ms
            logger.warning(f"[llm_review] JSON parsing failed: {e}")
            return LLMReviewResult(error=f"json_parse_error: {str(e)}", latency_ms=latency_ms)
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.warning(f"[llm_review] LLM review failed: {e}")
            return LLMReviewResult(error=str(e), latency_ms=latency_ms)
    
    def _merge_results(self, rule_result: Dict, llm_result: LLMReviewResult) -> Dict:
        """
        규칙/LLM 결과 병합
        
        규칙 기반: 패턴 매칭으로 명확한 위반 탐지
        LLM 기반: 문맥 이해로 미묘한 위반 탐지
        
        병합 전략:
        - 규칙 위반이 있으면 우선 적용
        - LLM 이슈를 추가로 병합
        - passed는 둘 다 통과해야 최종 통과
        """
        # LLM 실패 시 규칙 결과만 반환
        if llm_result.error:
            logger.info(f"[HybridLegalReviewer] LLM review failed ({llm_result.error}), using rule result only")
            return rule_result
        
        # LLM에서 추가 이슈 발견 시 병합
        combined_violations = rule_result['violations'].copy()
        
        if llm_result.issues:
            for issue in llm_result.issues:
                issue_type = issue.get('type', 'unknown')
                issue_text = issue.get('text', '')
                combined_violations.append(f"[LLM] {issue_type}: {issue_text}")
        
        # 최종 통과 여부: 규칙 통과 AND LLM 통과
        final_passed = rule_result['passed'] and llm_result.passed
        
        return {
            'passed': final_passed,
            'violations': combined_violations,
            'filtered_answer': rule_result.get('filtered_answer'),
            'llm_severity': llm_result.severity,
            'llm_comment': llm_result.overall_comment,
        }
    
    def _format_final_result(
        self, 
        review_result: Dict, 
        state: "ChatState", 
        retry_count: int
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
        
        draft_answer = state.get('draft_answer', '')
        violations = review_result.get('violations', [])
        passed = review_result.get('passed', False)
        filtered = review_result.get('filtered_answer')
        
        # 재생성 필요 여부 판단
        # prohibited_violations가 있으면 그 수로 판단, 아니면 violations 수로
        prohibited_count = len(review_result.get('prohibited_violations', []))
        if prohibited_count == 0:
            # 규칙 위반 중 금지 표현 관련만 카운트
            prohibited_count = sum(
                1 for v in violations 
                if '금지 표현' in v or '[LLM]' in v
            )
        
        needs_retry = (
            prohibited_count >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD 
            and retry_count < AgentConfig.MAX_REVIEW_RETRIES
        )
        
        review_output: "ReviewResult" = {
            'passed': passed,
            'violations': violations,
            'filtered_answer': filtered,
        }
        
        if needs_retry:
            # 재생성 필요
            return {
                'review': review_output,
                'retry_count': retry_count + 1,
            }
        elif passed:
            # 통과
            return {
                'review': review_output,
                'final_answer': draft_answer,
            }
        else:
            # 필터링된 답변 사용
            final = filtered if filtered else draft_answer
            return {
                'review': review_output,
                'final_answer': final,
            }


# =============================================================================
# 노드 함수 (기존 review_node 대체용)
# =============================================================================

# 모듈 레벨 싱글턴 인스턴스
_reviewer_instance: Optional[HybridLegalReviewer] = None


def get_reviewer() -> HybridLegalReviewer:
    """싱글턴 reviewer 인스턴스 반환"""
    global _reviewer_instance
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
    chat_type = state.get('chat_type', 'dispute')
    
    if chat_type == 'general':
        # 일반 채팅: 리뷰 스킵
        draft_answer = state.get('draft_answer', '')
        review_result: "ReviewResult" = {
            'passed': True,
            'violations': [],
            'filtered_answer': None,
        }
        return {
            'review': review_result,
            'final_answer': draft_answer,
        }
    
    return hybrid_review_node(state)
