"""
똑소리 프로젝트 - 답변생성 노드
작성일: 2026-01-14
S2-3: RAGGenerator를 활용한 구조화된 답변 생성

답변생성 노드의 역할:
1. retrieval 결과와 user_query를 기반으로 LLM 답변 생성
2. RAGGenerator.generate_structured_answer() 호출
3. 생성된 답변을 draft_answer로 저장 (review 전 초안)
"""

import os
from typing import Dict, List

from langchain_core.messages import AIMessage

from ..state import ChatState


def _get_llm_model() -> str:
    """LLM 모델명 반환"""
    return os.getenv('LLM_MODEL', 'gpt-4o-mini')


def _build_general_response(user_query: str) -> str:
    """
    일반 대화에 대한 응답 생성
    
    분쟁 상담이 아닌 일반 인사/대화에 대한 응답.
    """
    greetings = ['안녕', '반가', 'hello', 'hi']
    thanks = ['감사', '고마', 'thanks', 'thank']
    
    query_lower = user_query.lower()
    
    for g in greetings:
        if g in query_lower:
            return "안녕하세요! 저는 소비자 분쟁 상담을 도와드리는 똑소리입니다. 궁금하신 분쟁 관련 사항이 있으시면 말씀해 주세요."
    
    for t in thanks:
        if t in query_lower:
            return "도움이 되셨다면 다행이에요. 추가로 궁금하신 사항이 있으시면 언제든 물어봐 주세요!"
    
    return "네, 무엇을 도와드릴까요? 소비자 분쟁 관련 상담을 원하시면 자세한 상황을 알려주세요."


def generation_node(state: ChatState) -> Dict:
    """
    답변생성 노드 함수
    
    RAGGenerator를 사용하여 구조화된 답변 생성.
    retrieval 결과가 없으면 빈 답변 생성.
    
    Args:
        state: 현재 ChatState
        
    Returns:
        부분 상태 업데이트 dict:
        {
            'draft_answer': str,
            'has_sufficient_evidence': bool,
            'clarifying_questions': List[str],
            'messages': List[AIMessage]  # add_messages reducer로 추가
        }
    """
    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis')
    retrieval = state.get('retrieval')
    
    # 일반 대화인 경우
    if query_analysis and query_analysis.get('query_type') == 'general':
        general_response = _build_general_response(user_query)
        return {
            'draft_answer': general_response,
            'has_sufficient_evidence': True,
            'clarifying_questions': [],
            'messages': [AIMessage(content=general_response)],
        }
    
    # retrieval 결과가 없으면 빈 답변
    if not retrieval:
        no_result_msg = "죄송합니다. 관련 정보를 찾을 수 없습니다. 질문을 더 구체적으로 작성해 주시면 도움이 될 것 같습니다."
        return {
            'draft_answer': no_result_msg,
            'has_sufficient_evidence': False,
            'clarifying_questions': [
                "어떤 제품/서비스에 대한 분쟁인가요?",
                "언제 구매하셨나요?",
                "어떤 문제가 발생했나요?"
            ],
            'messages': [AIMessage(content=no_result_msg)],
        }
    
    try:
        # RAGGenerator import (지연 import)
        from rag.generator import RAGGenerator
        
        model = _get_llm_model()
        generator = RAGGenerator(model=model, use_llm=True)
        
        # agency_info 구성
        agency_info = retrieval.get('agency', {})
        if not agency_info:
            # 기본 agency_info
            agency_info = {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원 소비자분쟁조정위원회',
                    'description': '일반 소비자 분쟁 조정',
                    'url': 'https://www.kca.go.kr'
                },
                'dispute_type': '1:N',
                'reason': '일반 소비자 분쟁으로 판단됩니다',
                'confidence': 0.7
            }
        
        # 구조화된 답변 생성
        result = generator.generate_structured_answer(
            query=user_query,
            agency_info=agency_info,
            disputes=retrieval.get('disputes', []),
            counsels=retrieval.get('counsels', []),
            laws=retrieval.get('laws', []),
            criteria=retrieval.get('criteria', []),
        )
        
        draft_answer = result.get('answer', '')
        has_evidence = result.get('has_sufficient_evidence', True)
        questions = result.get('clarifying_questions', [])
        
        return {
            'draft_answer': draft_answer,
            'has_sufficient_evidence': has_evidence,
            'clarifying_questions': questions,
            'messages': [AIMessage(content=draft_answer)],
        }
        
    except Exception as e:
        # LLM 호출 실패 시 fallback
        print(f"[generation_node] Error: {e}")
        fallback_msg = "죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        return {
            'draft_answer': fallback_msg,
            'has_sufficient_evidence': False,
            'clarifying_questions': [],
            'messages': [AIMessage(content=fallback_msg)],
        }
