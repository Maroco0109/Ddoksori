"""
똑소리 프로젝트 - RAG Answer Generator (S1-1 MVP)
작성일: 2026-01-11
LLM 기반 구조화된 답변 생성
"""
import os
import time
from typing import List, Dict, Tuple, Optional
from openai import OpenAI

# S1-1 MVP Answer Template
DISCLAIMER = "본 답변은 정보 제공 목적이며 법률 자문이 아닙니다. 최종 판단·결정은 관련 기관 또는 전문가와 상담하여 진행해 주세요."

SECTIONS = [
    "1. 추천 기관 및 사유",
    "2. 유사 사례",
    "3. 관련 법적 근거",
    "4. 다음 행동 체크리스트"
]


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

    def __init__(self, model: str = "gpt-4o-mini", use_llm: bool = True):
        """
        Args:
            model: LLM 모델 (기본값: gpt-4o-mini)
            use_llm: LLM 사용 여부 (False면 stub 모드)
        """
        self.model = model
        self.use_llm = use_llm and bool(os.getenv('OPENAI_API_KEY'))

        if self.use_llm:
            self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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
            result.update({
                'system_prompt': '',
                'user_prompt': '',
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'response_time_ms': 0
            })
            return result

        if not self.use_llm:
            result = self._generate_stub_answer(query, chunks)
            result.update({
                'system_prompt': '',
                'user_prompt': '',
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'response_time_ms': 0
            })
            return result

        # LLM mode with instrumentation
        system_prompt = self._get_system_prompt()
        user_prompt = self._build_prompt(query, chunks)

        start = time.time()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        response_time = (time.time() - start) * 1000

        # Extract token usage
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        answer_text = response.choices[0].message.content

        # Safety guardrails
        has_evidence, questions = self._check_evidence(query, chunks)

        if not has_evidence:
            answer_text = self._format_insufficient_evidence(answer_text, questions)

        return {
            'answer': answer_text,
            'chunks_used': len(chunks),
            'model': self.model,
            'has_sufficient_evidence': has_evidence,
            'clarifying_questions': questions,
            # Logging metadata
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'response_time_ms': response_time
        }

    def _generate_llm_answer(self, query: str, chunks: List[Dict]) -> Dict:
        """Generate answer using LLM with S1-1 template"""
        prompt = self._build_prompt(query, chunks)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        answer_text = response.choices[0].message.content

        # Safety guardrails
        has_evidence, questions = self._check_evidence(query, chunks)

        if not has_evidence:
            answer_text = self._format_insufficient_evidence(answer_text, questions)

        return {
            'answer': answer_text,
            'chunks_used': len(chunks),
            'model': self.model,
            'has_sufficient_evidence': has_evidence,
            'clarifying_questions': questions
        }

    def _get_system_prompt(self) -> str:
        return """당신은 한국 소비자 분쟁 조정 전문 상담 어시스턴트입니다.

역할:
- 검색된 사례와 법령을 기반으로 정보를 제공합니다
- 법률 자문이나 확정적인 판단을 하지 않습니다
- 근거가 부족할 경우 추가 질문을 통해 정보를 수집합니다

답변 형식:
""" + DISCLAIMER + "\n\n" + "\n".join(SECTIONS) + """

금지 사항:
- "~해야 합니다", "~입니다" 같은 단정적 표현
- 법률 판단이나 예측
- 개인정보 요구
"""

    def _build_prompt(self, query: str, chunks: List[Dict]) -> str:
        lines = [f"사용자 질문: {query}\n", "관련 검색 결과:\n"]

        for i, chunk in enumerate(chunks[:5], 1):
            lines.append(f"[결과 {i}]")
            lines.append(f"출처: {chunk.get('doc_title', 'Unknown')}")
            lines.append(f"기관: {chunk.get('source_org', 'Unknown')}")
            lines.append(f"문서ID: {chunk.get('doc_id', 'Unknown')}")
            if chunk.get('decision_date'):
                lines.append(f"결정일: {chunk['decision_date']}")
            if chunk.get('url'):
                lines.append(f"URL: {chunk['url']}")
            lines.append(f"유사도: {chunk.get('similarity', 0):.3f}")
            lines.append(f"\n내용:\n{chunk.get('content', '')[:500]}...\n")

        lines.append("\n다음 형식으로 답변하세요:")
        lines.append(DISCLAIMER)
        for section in SECTIONS:
            lines.append(f"\n{section}")

        return "\n".join(lines)

    def _check_evidence(
        self, query: str, chunks: List[Dict]
    ) -> Tuple[bool, List[str]]:
        """Check if evidence is sufficient"""
        if not chunks or chunks[0].get('similarity', 0) < 0.5:
            return False, [
                "분쟁 발생 날짜가 언제인가요?",
                "구입한 제품/서비스의 구체적인 명칭은 무엇인가요?",
                "어떤 문제가 발생했는지 자세히 설명해 주시겠어요?"
            ]
        return True, []

    def _format_insufficient_evidence(
        self, answer: str, questions: List[str]
    ) -> str:
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
            lines.append(f"{i}. [{chunk.get('source_org', '알 수 없음')}] {chunk.get('doc_title', '제목 없음')}")
            lines.append(f"   유사도: {chunk.get('similarity', 0):.2f}")
            if chunk.get('decision_date'):
                lines.append(f"   결정일: {chunk['decision_date']}")
            if chunk.get('url'):
                lines.append(f"   출처: {chunk['url']}")
            lines.append("")

        lines.append("3. 관련 법적 근거")
        lines.append("LLM 연동 후 관련 법령 및 기준이 표시됩니다.\n")

        lines.append("4. 다음 행동 체크리스트")
        lines.append("□ 관련 서류 준비 (영수증, 계약서 등)")
        lines.append("□ 해당 기관 연락처 확인")
        lines.append("□ 사실관계 정리")

        return {
            'answer': "\n".join(lines),
            'chunks_used': len(chunks),
            'model': 'stub',
            'has_sufficient_evidence': True,
            'clarifying_questions': []
        }

    def _no_results_response(self) -> Dict:
        return {
            'answer': f"{DISCLAIMER}\n\n죄송합니다. 관련된 분쟁조정 사례를 찾을 수 없습니다.\n\n다음을 시도해 보세요:\n- 질문을 더 구체적으로 작성\n- 제품/서비스 카테고리 명시\n- 발생한 문제 상황을 자세히 설명",
            'chunks_used': 0,
            'model': self.model,
            'has_sufficient_evidence': False,
            'clarifying_questions': []
        }
