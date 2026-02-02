"""
똑소리 프로젝트 - RAG Answer Generator (S1-1 MVP)
작성일: 2026-01-11
수정일: 2026-01-13 - 4섹션 구조화 응답 추가
수정일: 2026-01-19 - claim_evidence_map 추가
LLM 기반 구조화된 답변 생성
"""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI, OpenAI

from ....common.config import get_config

# S1-1 MVP Answer Template
DISCLAIMER = "본 답변은 정보 제공 목적이며 법률 자문이 아닙니다. 최종 판단·결정은 관련 기관 또는 전문가와 상담하여 진행해 주세요."

SECTIONS = [
    "1. 추천 기관 및 사유",
    "2. 유사 사례",
    "3. 관련 법적 근거",
    "4. 다음 행동 체크리스트",
]

# 3섹션 구조화 응답용 섹션 (PR-6: 2026-01-20)
# 변경: 유사 사례 → 법령/기준 → 추가 안내 (권장 조치 제외)
STRUCTURED_SECTIONS = ["1. 유사 사례 분석", "2. 관련 법령 및 기준", "3. 추가 안내"]

# 기관 추천을 위한 키워드
CONTENT_KEYWORDS = [
    "게임",
    "영화",
    "콘텐츠",
    "앱",
    "어플",
    "애플리케이션",
    "음악",
    "웹툰",
    "만화",
    "동영상",
    "영상",
    "스트리밍",
    "OTT",
    "넷플릭스",
    "왓챠",
    "디즈니",
    "유튜브",
    "인앱",
    "결제",
    "아이템",
    "캐시",
    "다이아",
    "루비",
    "디지털",
    "다운로드",
    "구독",
    "VOD",
    "e북",
    "전자책",
]

INDIVIDUAL_KEYWORDS = [
    "중고",
    "직거래",
    "당근",
    "당근마켓",
    "번개장터",
    "중고나라",
    "개인간",
    "개인거래",
    "개인 판매",
    "개인판매자",
    "직접 거래",
    "직접거래",
    "만나서",
    "택배거래",
    "중고거래",
    "중고 거래",
    "세컨핸드",
    "second hand",
]

AGENCY_INFO = {
    "KCA": {
        "name": "한국소비자원",
        "full_name": "한국소비자원 소비자분쟁조정위원회",
        "description": "일반 소비자 분쟁 조정 (사업자 대 소비자)",
        "url": "https://www.kca.go.kr",
    },
    "ECMC": {
        "name": "전자거래분쟁조정위원회",
        "full_name": "전자거래분쟁조정위원회",
        "description": "전자거래 및 개인간 거래 분쟁 조정",
        "url": "https://www.ecmc.or.kr",
    },
    "KCDRC": {
        "name": "콘텐츠분쟁조정위원회",
        "full_name": "콘텐츠분쟁조정위원회",
        "description": "콘텐츠(게임, 영화, 음악 등) 관련 분쟁 조정",
        "url": "https://www.kcdrc.kr",
    },
}


class RAGGenerator:
    """
    LLM 기반 답변 생성기 (S1-1 MVP Template)

    Generates structured answers with:
    - Fixed disclaimer
    - Agency recommendation + reason
    - Similar cases (2-3 with sources)
    - Legal basis (criteria/laws with citations)
    - Next action checklist
    """

    def __init__(self, model: str = None, use_llm: bool = True):
        """
        Args:
            model: LLM 모델 (기본값: config.models.draft_agent = gpt-4o)
            use_llm: LLM 사용 여부 (False면 stub 모드)
        """
        if model is None:
            config = get_config()
            model = config.models.draft_agent
        self.model = model
        self.use_llm = use_llm and bool(os.getenv("OPENAI_API_KEY"))

        if self.use_llm:
            # 동기 클라이언트 (기존 메서드용)
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            # 비동기 클라이언트 (스트리밍 메서드용)
            self.async_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate_answer(self, query: str, chunks: List[Dict]) -> Dict:
        """
        검색 결과 기반 구조화된 답변 생성

        Args:
            query: 사용자 질문
            chunks: 검색된 청크 리스트 (SearchResult dict 형식)

        Returns:
            {
                'answer': str,
                'chunks_used': int,
                'model': str,
                'has_sufficient_evidence': bool,
                'clarifying_questions': List[str]
            }
        """
        if not chunks:
            return self._no_results_response()

        if self.use_llm:
            return self._generate_llm_answer(query, chunks)
        else:
            return self._generate_stub_answer(query, chunks)

    def generate_answer_instrumented(self, query: str, chunks: List[Dict]) -> Dict:
        """
        검색 결과 기반 구조화된 답변 생성 with logging metadata

        Returns standard fields plus:
        - 'system_prompt': str
        - 'user_prompt': str
        - 'prompt_tokens': int
        - 'completion_tokens': int
        - 'response_time_ms': float
        """
        if not chunks:
            result = self._no_results_response()
            result.update(
                {
                    "system_prompt": "",
                    "user_prompt": "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "response_time_ms": 0,
                }
            )
            return result

        if not self.use_llm:
            result = self._generate_stub_answer(query, chunks)
            result.update(
                {
                    "system_prompt": "",
                    "user_prompt": "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "response_time_ms": 0,
                }
            )
            return result

        # LLM mode with instrumentation
        system_prompt = self._get_system_prompt()
        user_prompt = self._build_prompt(query, chunks)

        start = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        response_time = (time.time() - start) * 1000

        # Extract token usage
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        answer_text = response.choices[0].message.content or ""

        has_evidence, questions = self._check_evidence(query, chunks)

        if not has_evidence:
            answer_text = self._format_insufficient_evidence(answer_text, questions)

        return {
            "answer": answer_text,
            "chunks_used": len(chunks),
            "model": self.model,
            "has_sufficient_evidence": has_evidence,
            "clarifying_questions": questions,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "response_time_ms": response_time,
        }

    def _generate_llm_answer(self, query: str, chunks: List[Dict]) -> Dict:
        prompt = self._build_prompt(query, chunks)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        answer_text = response.choices[0].message.content or ""

        has_evidence, questions = self._check_evidence(query, chunks)

        if not has_evidence:
            answer_text = self._format_insufficient_evidence(answer_text, questions)

        return {
            "answer": answer_text,
            "chunks_used": len(chunks),
            "model": self.model,
            "has_sufficient_evidence": has_evidence,
            "clarifying_questions": questions,
        }

    def _get_system_prompt(self) -> str:
        return (
            """당신은 한국 소비자 분쟁 조정 전문 상담 어시스턴트입니다.

역할:
- 검색된 사례와 법령을 기반으로 정보를 제공합니다
- 법률 자문이나 확정적인 판단을 하지 않습니다
- 근거가 부족할 경우 추가 질문을 통해 정보를 수집합니다

답변 형식:
"""
            + DISCLAIMER
            + "\n\n"
            + "\n".join(SECTIONS)
            + """

금지 사항:
- "~해야 합니다", "~입니다" 같은 단정적 표현
- 법률 판단이나 예측
- 개인정보 요구
"""
        )

    def _build_prompt(self, query: str, chunks: List[Dict]) -> str:
        lines = [f"사용자 질문: {query}\n", "관련 검색 결과:\n"]

        for i, chunk in enumerate(chunks[:5], 1):
            lines.append(f"[결과 {i}]")
            lines.append(f"출처: {chunk.get('doc_title', 'Unknown')}")
            lines.append(f"기관: {chunk.get('source_org', 'Unknown')}")
            lines.append(f"문서ID: {chunk.get('doc_id', 'Unknown')}")
            if chunk.get("decision_date"):
                lines.append(f"결정일: {chunk['decision_date']}")
            if chunk.get("url"):
                lines.append(f"URL: {chunk['url']}")
            lines.append(f"유사도: {chunk.get('similarity', 0):.3f}")
            lines.append(f"\n내용:\n{chunk.get('content', '')[:500]}...\n")

        lines.append("\n다음 형식으로 답변하세요:")
        lines.append(DISCLAIMER)
        for section in SECTIONS:
            lines.append(f"\n{section}")

        return "\n".join(lines)

    def _check_evidence(self, query: str, chunks: List[Dict]) -> Tuple[bool, List[str]]:
        """Check if evidence is sufficient"""
        similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.01"))
        if not chunks or chunks[0].get("similarity", 0) < similarity_threshold:
            return False, [
                "분쟁 발생 날짜가 언제인가요?",
                "구입한 제품/서비스의 구체적인 명칭은 무엇인가요?",
                "어떤 문제가 발생했는지 자세히 설명해 주시겠어요?",
            ]
        return True, []

    def _format_insufficient_evidence(self, answer: str, questions: List[str]) -> str:
        prefix = "제공하신 정보만으로는 정확한 안내가 어렵습니다. 다음 정보를 추가로 알려주시면 더 도움이 될 것 같습니다:\n\n"
        prefix += "\n".join(f"- {q}" for q in questions)
        prefix += "\n\n참고로 알려드릴 수 있는 정보:\n\n"
        return prefix + answer

    def _generate_stub_answer(self, query: str, chunks: List[Dict]) -> Dict:
        """Stub mode (no LLM) - structured format with citations"""
        lines = [DISCLAIMER, "\n"]

        lines.append("1. 추천 기관 및 사유")
        lines.append("현재 LLM 연동 전 단계입니다. 검색 결과를 참고하세요.\n")

        lines.append("2. 유사 사례")
        for i, chunk in enumerate(chunks[:3], 1):
            lines.append(
                f"{i}. [{chunk.get('source_org', '알 수 없음')}] {chunk.get('doc_title', '제목 없음')}"
            )
            lines.append(f"   유사도: {chunk.get('similarity', 0):.2f}")
            if chunk.get("decision_date"):
                lines.append(f"   결정일: {chunk['decision_date']}")
            if chunk.get("url"):
                lines.append(f"   출처: {chunk['url']}")
            lines.append("")

        lines.append("3. 관련 법적 근거")
        lines.append("LLM 연동 후 관련 법령 및 기준이 표시됩니다.\n")

        lines.append("4. 다음 행동 체크리스트")
        lines.append("□ 관련 서류 준비 (영수증, 계약서 등)")
        lines.append("□ 해당 기관 연락처 확인")
        lines.append("□ 사실관계 정리")

        return {
            "answer": "\n".join(lines),
            "chunks_used": len(chunks),
            "model": "stub",
            "has_sufficient_evidence": True,
            "clarifying_questions": [],
        }

    def _no_results_response(self) -> Dict:
        return {
            "answer": f"{DISCLAIMER}\n\n죄송합니다. 관련된 분쟁조정 사례를 찾을 수 없습니다.\n\n다음을 시도해 보세요:\n- 질문을 더 구체적으로 작성\n- 제품/서비스 카테고리 명시\n- 발생한 문제 상황을 자세히 설명",
            "chunks_used": 0,
            "model": self.model,
            "has_sufficient_evidence": False,
            "clarifying_questions": [],
        }

    # ========================================
    # 4섹션 구조화 응답 생성 메서드
    # ========================================

    def determine_agency(self, query: str) -> Dict:
        """
        질문을 분석하여 적절한 기관 추천

        Args:
            query: 사용자 질문

        Returns:
            {
                'agency': 'KCA' | 'ECMC' | 'KCDRC',
                'agency_info': {...},
                'dispute_type': '1:N' | '1:1' | 'contents',
                'reason': '추천 이유',
                'confidence': 0.0 ~ 1.0
            }
        """
        query_lower = query.lower()

        # 콘텐츠 관련 키워드 체크
        content_matches = [kw for kw in CONTENT_KEYWORDS if kw in query_lower]
        if content_matches:
            return {
                "agency": "KCDRC",
                "agency_info": AGENCY_INFO["KCDRC"],
                "dispute_type": "contents",
                "reason": f"콘텐츠 관련 분쟁으로 판단됩니다 (키워드: {', '.join(content_matches[:3])})",
                "confidence": min(0.6 + len(content_matches) * 0.1, 1.0),
            }

        # 개인간 거래 키워드 체크
        individual_matches = [kw for kw in INDIVIDUAL_KEYWORDS if kw in query_lower]
        if individual_matches:
            return {
                "agency": "ECMC",
                "agency_info": AGENCY_INFO["ECMC"],
                "dispute_type": "1:1",
                "reason": f"개인간 거래 분쟁으로 판단됩니다 (키워드: {', '.join(individual_matches[:3])})",
                "confidence": min(0.6 + len(individual_matches) * 0.1, 1.0),
            }

        # 기본값: KCA (일반 소비자 분쟁)
        return {
            "agency": "KCA",
            "agency_info": AGENCY_INFO["KCA"],
            "dispute_type": "1:N",
            "reason": "일반 소비자 분쟁으로 판단됩니다 (사업자 대 소비자)",
            "confidence": 0.7,
        }

    def generate_structured_answer(
        self,
        query: str,
        agency_info: Dict,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict],
        include_disclaimer: bool = True,
        retry_supplement: Optional[str] = None,
        onboarding: Optional[Dict] = None,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
    ) -> Dict:
        """
        4개 섹션을 포함한 구조화된 응답 생성

        Args:
            query: 사용자 질문
            agency_info: 기관 추천 정보
            disputes: 분쟁조정사례 리스트
            counsels: 상담사례 리스트
            laws: 관련 법령 리스트
            criteria: 관련 기준 리스트
            include_disclaimer: 면책 문구 포함 여부 (PR-2: mode==NEED_RAG일 때만 True)

        Returns:
            {
                'answer': str,
                'agency': {...},
                'disputes': [...],
                'counsels': [...],
                'laws': [...],
                'criteria': [...],
                'chunks_used': int,
                'model': str,
                'has_sufficient_evidence': bool,
                'clarifying_questions': List[str],
                # Logging metadata
                'system_prompt': str,
                'user_prompt': str,
                'prompt_tokens': int,
                'completion_tokens': int,
                'response_time_ms': float
            }
        """
        # 총 청크 수 계산
        total_chunks = len(disputes) + len(counsels) + len(laws) + len(criteria)

        # 충분한 근거 여부 판단
        has_evidence = total_chunks > 0 and (len(disputes) > 0 or len(laws) > 0)
        clarifying_questions = []

        if not has_evidence:
            clarifying_questions = [
                "분쟁 발생 날짜가 언제인가요?",
                "구입한 제품/서비스의 구체적인 명칭은 무엇인가요?",
                "어떤 문제가 발생했는지 자세히 설명해 주시겠어요?",
            ]

        if not self.use_llm:
            result = self._generate_structured_stub(
                query,
                agency_info,
                disputes,
                counsels,
                laws,
                criteria,
                include_disclaimer=include_disclaimer,
            )
            # Add empty logging metadata for stub mode
            result.update(
                {
                    "system_prompt": "",
                    "user_prompt": "",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "response_time_ms": 0.0,
                }
            )
            return result

        # LLM 프롬프트 생성
        if system_prompt is None:
            # 외부 프롬프트가 없으면 기존 방식 사용 (하위 호환)
            system_prompt = self._get_structured_system_prompt(
                include_disclaimer=include_disclaimer
            )
        if retry_supplement:
            system_prompt += f"\n\n## 재생성 지침\n{retry_supplement}"
        if user_prompt is None:
            # 외부 프롬프트가 없으면 기존 방식 사용 (하위 호환)
            user_prompt = self._build_structured_prompt(
                query, agency_info, disputes, counsels, laws, criteria, onboarding
            )

        # LLM 호출 with timing
        start_time = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        response_time_ms = (time.time() - start_time) * 1000

        answer_text = response.choices[0].message.content or ""

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        claim_evidence_map = self._extract_claim_evidence_map(
            answer_text, disputes, counsels, laws, criteria
        )

        return {
            "answer": answer_text,
            "agency": agency_info,
            "disputes": disputes,
            "counsels": counsels,
            "laws": laws,
            "criteria": criteria,
            "chunks_used": total_chunks,
            "model": self.model,
            "has_sufficient_evidence": has_evidence,
            "clarifying_questions": clarifying_questions,
            "claim_evidence_map": claim_evidence_map,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "response_time_ms": response_time_ms,
        }

    def _get_structured_system_prompt(self, include_disclaimer: bool = True) -> str:
        """3섹션 구조화 응답용 시스템 프롬프트 (PR-6: 2026-01-20)

        [DEPRECATED] 이 메서드는 하위 호환성을 위해 유지됩니다.
        새 코드는 formats.PromptBuilder를 사용하세요.

        Args:
            include_disclaimer: 면책 문구 포함 여부 (PR-2: mode==NEED_RAG일 때만 True)

        PR-6 변경사항:
        - 섹션 순서: 유사 사례 → 법령/기준 → 추가 안내 (3섹션)
        - 면책 문구 위치: 맨 위 → 맨 아래

        Track 2 변경사항:
        - formats.PromptBuilder로 통합 (backward compatibility 유지)
        """
        # PR-6: 면책 문구는 답변 끝에 배치
        disclaimer_section = f"\n\n---\n*{DISCLAIMER}*" if include_disclaimer else ""

        return f"""당신은 한국 소비자 분쟁 조정 전문 상담 어시스턴트입니다.

역할:
- 검색된 사례, 법령, 기준을 기반으로 정보를 제공합니다
- 법률 자문이나 확정적인 판단을 하지 않습니다
- 근거가 부족할 경우 추가 질문을 통해 정보를 수집합니다

답변 구조 (반드시 아래 순서와 형식을 따르세요):

## 1. 유사 사례 분석
   - 분쟁조정사례: 법적 효력이 있는 조정 결과 (출처, 결정일 명시)
   - 상담사례: 참고용 정보

## 2. 관련 법령 및 기준
   - 관련 법령: 법령명과 조항을 정확히 인용
   - 분쟁해결기준: 해당 품목의 분쟁조정기준(별표) 안내

## 3. 추가 안내
   - 담당 기관: 분쟁 유형에 맞는 기관 안내
   - 연락처 및 웹사이트 정보
{disclaimer_section}

금지 사항:
- "~해야 합니다", "~입니다" 같은 단정적 표현
- 법률 판단이나 예측
- 개인정보 요구
"""

    def _build_structured_prompt(
        self,
        query: str,
        agency_info: Dict,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict],
        onboarding: Optional[Dict] = None,
    ) -> str:
        """3섹션 구조화 프롬프트 생성 (PR-6: 2026-01-20)

        섹션 순서:
        1. 유사 사례 분석 (disputes + counsels)
        2. 관련 법령 및 기준 (laws + criteria)
        3. 추가 안내 (agency_info)
        """
        lines = [f"사용자 질문: {query}\n"]

        # 온보딩 컨텍스트 추가
        if onboarding:
            parts = []
            if onboarding.get("purchase_item"):
                parts.append(f"구매 품목: {onboarding['purchase_item']}")
            if onboarding.get("purchase_amount"):
                parts.append(f"구매 금액: {onboarding['purchase_amount']}")
            if onboarding.get("purchase_date"):
                parts.append(f"구매일: {onboarding['purchase_date']}")
            if onboarding.get("days_since_purchase") is not None:
                days = onboarding["days_since_purchase"]
                parts.append(f"구매 후 경과일: {days}일")
                if days <= 7:
                    parts.append("→ 청약철회 기간(7일) 이내")
                elif days <= 14:
                    parts.append(
                        "→ 청약철회 기간(7일) 경과, 단 전자상거래법상 14일 이내 가능할 수 있음"
                    )
                elif days <= 30:
                    parts.append(
                        "→ 구매 후 1개월 이내, 소비자분쟁해결기준 품질보증기간 확인 필요"
                    )
            if onboarding.get("product_category"):
                parts.append(f"품목 카테고리: {onboarding['product_category']}")
            if onboarding.get("dispute_details"):
                parts.append(f"분쟁 내용: {onboarding['dispute_details']}")

            if parts:
                lines.append("\n## 사용자 상황 정보")
                lines.extend([f"- {p}" for p in parts])
                lines.append("")

        # 섹션 1: 유사 사례 분석 (disputes + counsels)
        lines.append("=" * 50)
        lines.append("[섹션 1: 유사 사례 분석]")

        lines.append("\n### 분쟁조정사례 (법적 효력 있음)")
        if disputes:
            for i, case in enumerate(disputes[:3], 1):
                lines.append(
                    f"\n{i}. [{case.get('source_org', '알 수 없음')}] {case.get('doc_title', '제목 없음')}"
                )
                if case.get("decision_date"):
                    lines.append(f"   결정일: {case['decision_date']}")
                lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
                content = case.get("content", "")[:300]
                lines.append(f"   내용: {content}...")
        else:
            lines.append("   관련 분쟁조정사례를 찾지 못했습니다.")

        lines.append("\n### 상담사례 (참고용)")
        if counsels:
            for i, case in enumerate(counsels[:3], 1):
                lines.append(f"\n{i}. {case.get('doc_title', '제목 없음')}")
                lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
                content = case.get("content", "")[:200]
                lines.append(f"   내용: {content}...")
        else:
            lines.append("   관련 상담사례를 찾지 못했습니다.")

        # 섹션 2: 관련 법령 및 기준 (laws + criteria 병합)
        lines.append("\n" + "=" * 50)
        lines.append("[섹션 2: 관련 법령 및 기준]")

        lines.append("\n### 관련 법령")
        if laws:
            for i, law in enumerate(laws[:3], 1):
                law_name = law.get("law_name", "법령")
                full_path = law.get("full_path", "")
                lines.append(f"\n{i}. {law_name} {full_path}")
                lines.append(f"   유사도: {law.get('similarity', 0):.2%}")
                text = law.get("text", law.get("content", ""))[:300]
                lines.append(f"   내용: {text}...")
        else:
            lines.append("   관련 법령을 찾지 못했습니다.")

        lines.append("\n### 분쟁해결기준")
        if criteria:
            for i, crit in enumerate(criteria[:3], 1):
                source_label = crit.get("source_label", "기준")
                category = crit.get("category", "")
                item = crit.get("item", crit.get("item_group", ""))
                path = (
                    f"{category} > {item}"
                    if category and item
                    else category or item or ""
                )

                lines.append(f"\n{i}. [{source_label}] {path}")
                lines.append(f"   유사도: {crit.get('similarity', 0):.2%}")
                text = crit.get("unit_text", crit.get("content", ""))[:300]
                lines.append(f"   내용: {text}...")
        else:
            lines.append("   관련 기준을 찾지 못했습니다.")

        # 섹션 3: 추가 안내 (agency_info)
        lines.append("\n" + "=" * 50)
        lines.append("[섹션 3: 추가 안내]")
        lines.append(
            f"\n담당 기관: {agency_info.get('agency_info', {}).get('full_name', '한국소비자원')}"
        )
        lines.append(f"분쟁 유형: {agency_info.get('dispute_type', '1:N')}")
        lines.append(f"추천 이유: {agency_info.get('reason', '')}")
        agency_url = agency_info.get("agency_info", {}).get("url", "")
        if agency_url:
            lines.append(f"웹사이트: {agency_url}")

        lines.append("\n" + "=" * 50)
        lines.append("\n위 정보를 바탕으로 사용자의 질문에 답변해 주세요.")
        lines.append("각 섹션별로 정리하여 답변하고, 출처를 명확히 밝혀 주세요.")
        lines.append("답변 마지막에 면책 문구를 포함하세요.")

        return "\n".join(lines)

    def _extract_claim_evidence_map(
        self,
        answer: str,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict],
    ) -> List[Dict[str, Any]]:
        all_chunks = disputes + counsels + laws + criteria
        if not all_chunks:
            return []

        chunk_map = {
            c.get("chunk_id", c.get("unit_id", f"chunk_{i}")): c
            for i, c in enumerate(all_chunks)
        }

        claim_evidence_map = []
        sentences = re.split(r"[.!?]\s+", answer)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 15:
                continue

            matched_chunks = []
            sentence_lower = sentence.lower()

            for chunk_id, chunk in chunk_map.items():
                content = chunk.get(
                    "content", chunk.get("text", chunk.get("unit_text", ""))
                )
                if not content:
                    continue

                content_lower = content.lower()

                sentence_words = set(w for w in sentence_lower.split() if len(w) > 1)
                content_words = set(w for w in content_lower.split() if len(w) > 1)
                overlap = len(sentence_words & content_words)

                key_terms = [
                    "소비자",
                    "분쟁",
                    "환불",
                    "조정",
                    "법",
                    "기준",
                    "신청",
                    "피해",
                    "배상",
                ]
                key_match = sum(
                    1
                    for term in key_terms
                    if term in sentence_lower and term in content_lower
                )

                score = overlap + (key_match * 2)

                if score >= 2:
                    matched_chunks.append(
                        {"chunk_id": chunk_id, "text": content[:200], "score": score}
                    )

            if matched_chunks:
                matched_chunks.sort(key=lambda x: x["score"], reverse=True)
                top_matches = matched_chunks[:2]

                claim_evidence_map.append(
                    {
                        "claim": sentence,
                        "evidence_chunk_ids": [m["chunk_id"] for m in top_matches],
                        "evidence_texts": [m["text"] for m in top_matches],
                        "grounded": True,
                    }
                )

        return claim_evidence_map

    def _generate_structured_stub(
        self,
        query: str,
        agency_info: Dict,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict],
        include_disclaimer: bool = True,
    ) -> Dict:
        """Stub 모드 (LLM 없이) 구조화된 응답 생성 (PR-6: 2026-01-20)

        Args:
            include_disclaimer: 면책 문구 포함 여부 (PR-2: mode==NEED_RAG일 때만 True)

        PR-6 변경사항:
        - 섹션 순서: 유사 사례 → 법령/기준 → 추가 안내 (3섹션)
        - 면책 문구 위치: 맨 위 → 맨 아래
        """
        lines = []

        # 섹션 1: 유사 사례 분석
        lines.append("## 1. 유사 사례 분석")
        lines.append("\n### 분쟁조정사례 (법적 효력 있음)")
        for i, case in enumerate(disputes[:3], 1):
            lines.append(
                f"{i}. [{case.get('source_org', '알 수 없음')}] {case.get('doc_title', '제목 없음')}"
            )
            if case.get("decision_date"):
                lines.append(f"   결정일: {case['decision_date']}")
            lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
        if not disputes:
            lines.append("   관련 사례 없음")

        lines.append("\n### 상담사례 (참고용)")
        for i, case in enumerate(counsels[:3], 1):
            lines.append(f"{i}. {case.get('doc_title', '제목 없음')}")
            lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
        if not counsels:
            lines.append("   관련 사례 없음")
        lines.append("")

        # 섹션 2: 관련 법령 및 기준
        lines.append("## 2. 관련 법령 및 기준")
        lines.append("\n### 관련 법령")
        for i, law in enumerate(laws[:3], 1):
            law_name = law.get("law_name", "법령")
            full_path = law.get("full_path", "")
            lines.append(f"{i}. {law_name} {full_path}")
            lines.append(f"   유사도: {law.get('similarity', 0):.2%}")
        if not laws:
            lines.append("   관련 법령 없음")

        lines.append("\n### 분쟁해결기준")
        for i, crit in enumerate(criteria[:3], 1):
            source_label = crit.get("source_label", "기준")
            category = crit.get("category", "")
            item = crit.get("item", "")
            lines.append(f"{i}. [{source_label}] {category} > {item}")
            lines.append(f"   유사도: {crit.get('similarity', 0):.2%}")
        if not criteria:
            lines.append("   관련 기준 없음")
        lines.append("")

        # 섹션 3: 추가 안내
        lines.append("## 3. 추가 안내")
        lines.append(
            f"- 담당 기관: {agency_info.get('agency_info', {}).get('full_name', '한국소비자원')}"
        )
        lines.append(f"- 분쟁 유형: {agency_info.get('dispute_type', '1:N')}")
        lines.append(f"- 추천 이유: {agency_info.get('reason', '일반 소비자 분쟁')}")
        agency_url = agency_info.get("agency_info", {}).get("url", "")
        if agency_url:
            lines.append(f"- 웹사이트: {agency_url}")

        # PR-6: 면책 문구는 맨 아래에 배치
        if include_disclaimer:
            lines.append("\n---")
            lines.append(f"*{DISCLAIMER}*")

        total_chunks = len(disputes) + len(counsels) + len(laws) + len(criteria)

        return {
            "answer": "\n".join(lines),
            "agency": agency_info,
            "disputes": disputes,
            "counsels": counsels,
            "laws": laws,
            "criteria": criteria,
            "chunks_used": total_chunks,
            "model": "stub",
            "has_sufficient_evidence": total_chunks > 0,
            "clarifying_questions": [],
        }

    # ========================================
    # Track 2: 유연한 답변 형식 지원 (2026-01-28)
    # ========================================

    def generate_flexible_answer(
        self,
        query: str,
        query_analysis: Dict,
        retrieval: Dict,
        agency_info: Dict,
    ) -> Dict:
        """
        유연한 답변 형식을 사용하여 답변 생성 (Track 2)

        FormatSelector를 사용하여 쿼리 타입과 검색 결과에 따라
        적절한 답변 형식을 자동 선택합니다.

        Args:
            query: 사용자 질문
            query_analysis: 쿼리 분석 결과
            retrieval: 검색 결과
            agency_info: 기관 정보

        Returns:
            {
                'answer': str,
                'format_id': str,
                'chunks_used': int,
                'model': str,
                'has_sufficient_evidence': bool,
                'clarifying_questions': List[str],
                'claim_evidence_map': List[Dict],
                'system_prompt': str,
                'user_prompt': str,
                'prompt_tokens': int,
                'completion_tokens': int,
                'response_time_ms': float
            }
        """
        from ..formats import FormatSelector, PromptBuilder

        # 1. 형식 선택
        selector = FormatSelector()
        response_format = selector.select_format(query_analysis, retrieval)
        context = selector.build_context(retrieval)

        # 2. 프롬프트 생성
        prompt_builder = PromptBuilder()
        system_prompt = prompt_builder.build_system_prompt(response_format)
        user_prompt = prompt_builder.build_user_prompt(
            response_format, query, retrieval, agency_info, context
        )

        # 3. LLM 호출
        if not self.use_llm:
            # Stub 모드
            return self._generate_flexible_stub(
                query, response_format, retrieval, agency_info
            )

        start_time = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        response_time_ms = (time.time() - start_time) * 1000

        answer_text = response.choices[0].message.content or ""

        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        # 4. claim_evidence_map 생성
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])
        laws = retrieval.get("laws", [])
        criteria = retrieval.get("criteria", [])

        claim_evidence_map = self._extract_claim_evidence_map(
            answer_text, disputes, counsels, laws, criteria
        )

        # 5. 충분한 근거 여부 판단
        total_chunks = len(disputes) + len(counsels) + len(laws) + len(criteria)
        has_evidence = total_chunks > 0 and (len(disputes) > 0 or len(laws) > 0)

        return {
            "answer": answer_text,
            "format_id": response_format.format_id,
            "chunks_used": total_chunks,
            "model": self.model,
            "has_sufficient_evidence": has_evidence,
            "clarifying_questions": [],
            "claim_evidence_map": claim_evidence_map,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "response_time_ms": response_time_ms,
        }

    def _generate_flexible_stub(
        self, query: str, response_format, retrieval: Dict, agency_info: Dict
    ) -> Dict:
        """Stub 모드 (LLM 없이) 유연한 형식 답변 생성"""
        # simple_general 형식인 경우
        if response_format.format_id == "simple_general":
            answer = "안녕하세요! 똑소리입니다. (Stub 모드) 궁금하신 분쟁 관련 사항이 있으시면 말씀해 주세요."
        elif response_format.format_id == "info_only":
            info = agency_info.get("agency_info", {})
            answer = f"전문 기관 상담이 필요한 영역입니다.\n\n담당 기관: {info.get('full_name', '한국소비자원')}\n웹사이트: {info.get('url', '')}"
        else:
            # full_dispute (기본)
            disputes = retrieval.get("disputes", [])
            counsels = retrieval.get("counsels", [])
            laws = retrieval.get("laws", [])
            criteria = retrieval.get("criteria", [])

            # 기존 stub 로직 재사용
            result = self._generate_structured_stub(
                query,
                agency_info,
                disputes,
                counsels,
                laws,
                criteria,
                include_disclaimer=response_format.include_disclaimer,
            )
            result["format_id"] = response_format.format_id
            return result

        return {
            "answer": answer,
            "format_id": response_format.format_id,
            "chunks_used": 0,
            "model": "stub",
            "has_sufficient_evidence": False,
            "clarifying_questions": [],
            "claim_evidence_map": [],
            "system_prompt": "",
            "user_prompt": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "response_time_ms": 0.0,
        }

    # ========================================
    # 토큰 스트리밍 지원 (2026-01-28)
    # ========================================

    async def generate_structured_answer_streaming(
        self,
        query: str,
        agency_info: Dict,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict],
        include_disclaimer: bool = True,
        retry_supplement: Optional[str] = None,
        onboarding: Optional[Dict] = None,
    ):
        """
        구조화된 답변을 스트리밍 방식으로 생성 (토큰 단위)

        OpenAI streaming API를 사용하여 토큰이 생성되는 즉시 yield합니다.

        Args:
            query: 사용자 질문
            agency_info: 기관 정보
            disputes: 분쟁조정사례 리스트
            counsels: 상담사례 리스트
            laws: 관련 법령 리스트
            criteria: 분쟁해결기준 리스트
            include_disclaimer: 면책 문구 포함 여부

        Yields:
            str: 개별 토큰 (부분 문자열)

        Example:
            >>> generator = rag_gen.generate_structured_answer_streaming(...)
            >>> async for token in generator:
            ...     print(token, end='', flush=True)
        """
        # Stub 모드
        if not self.use_llm:
            result = self._generate_structured_stub(
                query,
                agency_info,
                disputes,
                counsels,
                laws,
                criteria,
                include_disclaimer=include_disclaimer,
            )
            yield result["answer"]
            return

        # 프롬프트 생성
        system_prompt = self._get_structured_system_prompt(include_disclaimer)
        if retry_supplement:
            system_prompt += f"\n\n## 재생성 지침\n{retry_supplement}"
        user_prompt = self._build_structured_prompt(
            query, agency_info, disputes, counsels, laws, criteria, onboarding
        )

        # OpenAI Streaming API 호출
        stream = await self.async_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            stream=True,  # 스트리밍 활성화
        )

        # 토큰 스트리밍
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
