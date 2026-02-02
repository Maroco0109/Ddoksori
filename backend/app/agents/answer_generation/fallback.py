"""
똑소리 프로젝트 - 답변 생성 폴백 체인
작성일: 2026-01-21
S1-PR5: LLM API 오류 시 다중 폴백 전략

폴백 순서:
1. GPT-4o (OpenAI) - 기본 (config.models.draft_agent)
2. GPT-4o-mini (OpenAI) - 폴백 1
3. 규칙 기반 (Local) - 폴백 2
4. 안전 메시지 (최종 폴백)
"""

import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

SAFE_FALLBACK_MESSAGE = """일시적인 오류가 발생했습니다.

소비자 분쟁 관련 상담은 다음 기관에 문의해 주세요:
- 한국소비자원: 1372
- 공정거래위원회: 044-200-4010
- 소비자24: https://www.consumer.go.kr
"""


class AnswerGenerationFallback:
    """답변 생성 폴백 체인"""

    FALLBACK_CHAIN = [
        ("gpt-4o", "OpenAI"),
        ("gpt-4o-mini", "OpenAI"),
        ("rule_based", "Local"),
    ]

    @classmethod
    def generate_with_fallback(
        cls,
        query: str,
        retrieval: Mapping[str, Any],
        agency_info: Mapping[str, Any],
        include_disclaimer: bool = True,
        retry_supplement: Optional[str] = None,
        onboarding: Optional[Mapping[str, Any]] = None,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> Tuple[str, str, List[Dict]]:
        """
        폴백 체인을 통한 답변 생성

        Returns:
            (generated_answer, model_used, claim_evidence_map)
        """
        last_error = None

        for model, provider in cls.FALLBACK_CHAIN:
            try:
                if model == "rule_based":
                    answer = cls._rule_based_generation(retrieval, agency_info)
                    logger.info(f"[fallback] Using rule_based generation")
                    return answer, model, []

                answer, claim_evidence_map = cls._try_llm_generation(
                    model=model,
                    provider=provider,
                    query=query,
                    retrieval=retrieval,
                    agency_info=agency_info,
                    include_disclaimer=include_disclaimer,
                    retry_supplement=retry_supplement,
                    onboarding=onboarding,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                logger.info(
                    f"[fallback] Successfully generated with {provider}/{model}"
                )
                return answer, model, claim_evidence_map

            except Exception as e:
                logger.warning(f"[fallback] {provider}/{model} failed: {e}")
                last_error = e
                continue

        logger.error(
            f"[fallback] All LLMs failed, using safe fallback. Last error: {last_error}"
        )
        return cls._safe_fallback_message(), "safe_fallback", []

    @classmethod
    def _try_llm_generation(
        cls,
        model: str,
        provider: str,
        query: str,
        retrieval: Mapping[str, Any],
        agency_info: Mapping[str, Any],
        include_disclaimer: bool,
        retry_supplement: Optional[str] = None,
        onboarding: Optional[Mapping[str, Any]] = None,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> Tuple[str, List[Dict]]:
        """LLM을 통한 답변 생성 시도"""
        from .tools.generator import RAGGenerator

        generator = RAGGenerator(model=model, use_llm=True)

        result = generator.generate_structured_answer(
            query=query,
            agency_info=dict(agency_info),
            disputes=list(retrieval.get("disputes", [])),
            counsels=list(retrieval.get("counsels", [])),
            laws=list(retrieval.get("laws", [])),
            criteria=list(retrieval.get("criteria", [])),
            include_disclaimer=include_disclaimer,
            retry_supplement=retry_supplement,
            onboarding=dict(onboarding) if onboarding else None,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        answer = result.get("answer", "")
        claim_evidence_map = result.get("claim_evidence_map", [])

        if not answer:
            raise ValueError("Empty answer from LLM")

        return answer, claim_evidence_map

    @classmethod
    def _rule_based_generation(
        cls,
        retrieval: Mapping[str, Any],
        agency_info: Mapping[str, Any],
    ) -> str:
        """규칙 기반 답변 생성 (템플릿)"""
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])
        laws = retrieval.get("laws", [])
        criteria = retrieval.get("criteria", [])

        lines = ["본 답변은 정보 제공 목적이며 법률 자문이 아닙니다.", ""]

        agency_name = agency_info.get("agency_info", {}).get("name", "한국소비자원")
        agency_url = agency_info.get("agency_info", {}).get(
            "url", "https://www.kca.go.kr"
        )

        lines.append("## 1. 추천 기관")
        lines.append(f"- {agency_name}: {agency_url}")
        lines.append("")

        if disputes or counsels:
            lines.append("## 2. 관련 사례")

            if disputes:
                lines.append(f"- 분쟁조정사례 {len(disputes)}건 발견")
                for i, d in enumerate(disputes[:2], 1):
                    title = d.get("doc_title", "제목 없음")
                    org = d.get("source_org", "")
                    lines.append(f"  {i}. [{org}] {title}")

            if counsels:
                lines.append(f"- 상담사례 {len(counsels)}건 발견")
                for i, c in enumerate(counsels[:2], 1):
                    title = c.get("doc_title", "제목 없음")
                    lines.append(f"  {i}. {title}")

            lines.append("")

        if laws:
            lines.append("## 3. 관련 법령")
            for i, law in enumerate(laws[:2], 1):
                law_name = law.get("law_name", "")
                full_path = law.get("full_path", "")
                lines.append(f"- {law_name} {full_path}")
            lines.append("")

        if criteria:
            lines.append("## 4. 관련 기준")
            for i, c in enumerate(criteria[:2], 1):
                item = c.get("item", "")
                source = c.get("source_label", "")
                lines.append(f"- {source}: {item}")
            lines.append("")

        lines.append("## 다음 단계")
        lines.append(f"1. 위 기관({agency_name})에 상담 신청")
        lines.append("2. 구매 영수증, 계약서 등 증빙자료 준비")
        lines.append("3. 분쟁 경위를 시간순으로 정리")

        return "\n".join(lines)

    @classmethod
    def _safe_fallback_message(cls) -> str:
        """안전 폴백 메시지"""
        return SAFE_FALLBACK_MESSAGE

    # ========================================
    # 토큰 스트리밍 지원 (2026-01-28)
    # ========================================

    @classmethod
    async def generate_with_fallback_streaming(
        cls,
        query: str,
        retrieval: Mapping[str, Any],
        agency_info: Mapping[str, Any],
        include_disclaimer: bool = True,
        retry_supplement: Optional[str] = None,
        onboarding: Optional[Mapping[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        폴백 체인을 통한 스트리밍 답변 생성

        각 LLM을 순차적으로 시도하며, 실패 시 다음 모델로 전환합니다.
        토큰은 생성 즉시 yield하고, fallback 전환 시 알림 이벤트를 전송합니다.

        Yields:
            Dict with keys:
            - type: 'token' | 'fallback' | 'complete' | 'error'
            - content: str (for token/error)
            - model: str (현재 사용중인 모델)
            - claim_evidence_map: List[Dict] (complete일 때만)
        """
        last_error = None
        full_answer = ""

        for model, provider in cls.FALLBACK_CHAIN:
            try:
                # rule_based 처리
                if model == "rule_based":
                    answer = cls._rule_based_generation(retrieval, agency_info)
                    logger.info(f"[fallback_streaming] Using rule_based generation")
                    yield {
                        "type": "complete",
                        "content": answer,
                        "model": model,
                        "claim_evidence_map": [],
                    }
                    return

                # Fallback 전환 알림 (첫 번째 시도 제외)
                if last_error:
                    yield {
                        "type": "fallback",
                        "model": model,
                        "previous_error": str(last_error),
                    }

                # LLM 스트리밍 시도
                logger.info(f"[fallback_streaming] Trying {provider}/{model}")
                generator = cls._try_llm_streaming(
                    model=model,
                    provider=provider,
                    query=query,
                    retrieval=retrieval,
                    agency_info=agency_info,
                    include_disclaimer=include_disclaimer,
                    retry_supplement=retry_supplement,
                    onboarding=onboarding,
                )

                # 토큰 스트리밍
                async for token in generator:
                    full_answer += token
                    yield {"type": "token", "content": token, "model": model}

                # 완료
                logger.info(
                    f"[fallback_streaming] Successfully generated with {provider}/{model}"
                )

                # claim_evidence_map 생성
                disputes = retrieval.get("disputes", [])
                counsels = retrieval.get("counsels", [])
                laws = retrieval.get("laws", [])
                criteria = retrieval.get("criteria", [])

                # RAGGenerator._extract_claim_evidence_map 재사용
                from .tools.generator import RAGGenerator

                temp_gen = RAGGenerator(model=model)
                claim_evidence_map = temp_gen._extract_claim_evidence_map(
                    full_answer, disputes, counsels, laws, criteria
                )

                yield {
                    "type": "complete",
                    "content": full_answer,
                    "model": model,
                    "claim_evidence_map": claim_evidence_map,
                }
                return

            except Exception as e:
                logger.warning(f"[fallback_streaming] {provider}/{model} failed: {e}")
                last_error = e
                full_answer = ""  # 초기화 (다음 LLM 시도)
                continue

        # 모든 LLM 실패 시 safe fallback
        logger.error(f"[fallback_streaming] All LLMs failed. Last error: {last_error}")
        yield {
            "type": "error",
            "content": cls._safe_fallback_message(),
            "model": "safe_fallback",
        }

    @classmethod
    async def _try_llm_streaming(
        cls,
        model: str,
        provider: str,
        query: str,
        retrieval: Mapping[str, Any],
        agency_info: Mapping[str, Any],
        include_disclaimer: bool,
        retry_supplement: Optional[str] = None,
        onboarding: Optional[Mapping[str, Any]] = None,
    ) -> AsyncGenerator[str, None]:
        """단일 LLM으로 스트리밍 시도"""
        from .tools.generator import RAGGenerator

        generator = RAGGenerator(model=model, use_llm=True)

        async for token in generator.generate_structured_answer_streaming(
            query=query,
            agency_info=dict(agency_info),
            disputes=list(retrieval.get("disputes", [])),
            counsels=list(retrieval.get("counsels", [])),
            laws=list(retrieval.get("laws", [])),
            criteria=list(retrieval.get("criteria", [])),
            include_disclaimer=include_disclaimer,
            retry_supplement=retry_supplement,
            onboarding=dict(onboarding) if onboarding else None,
        ):
            yield token
