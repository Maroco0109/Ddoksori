"""
똑소리 프로젝트 - 에이전트 공통 설정 모듈
작성일: 2026-01-21
S1-PR3: 설정값 외부화 (환경 변수)

하드코딩된 설정값들을 환경 변수로 외부화하여 운영 환경에서 쉽게 조정 가능하게 함.
"""

import os
from typing import Dict


class AgentConfig:
    """
    에이전트 공통 설정
    
    환경 변수로 설정 가능한 값들을 중앙 관리.
    기본값은 기존 하드코딩 값과 동일하게 유지.
    
    사용 예시:
        from app.common.config import AgentConfig
        
        threshold = AgentConfig.get_similarity_threshold('dispute')
        max_iter = AgentConfig.MAX_REACT_ITERATIONS
    """
    
    # ==========================================================================
    # ReAct 설정
    # ==========================================================================
    
    # 유사도 임계값 (기본값: 0.55)
    # 검색 결과의 유사도가 이 값 이상이면 "관련성 높음"으로 판단
    SIMILARITY_THRESHOLD: float = float(os.getenv('SIMILARITY_THRESHOLD', '0.55'))
    
    # ReAct 최대 반복 횟수 (기본값: 2)
    # 검색 결과가 불충분할 때 추가 검색을 시도하는 최대 횟수
    MAX_REACT_ITERATIONS: int = int(os.getenv('MAX_REACT_ITERATIONS', '2'))
    
    # ==========================================================================
    # Legal Review 설정
    # ==========================================================================
    
    # 금지 표현 위반 임계값 (기본값: 3)
    # 이 수 이상의 금지 표현이 발견되면 답변 재생성 필요로 판단
    PROHIBITED_VIOLATION_THRESHOLD: int = int(os.getenv('PROHIBITED_VIOLATION_THRESHOLD', '3'))
    
    # 최대 재생성 시도 횟수 (기본값: 2)
    # 금지 표현 위반 시 답변을 재생성하는 최대 횟수
    MAX_REVIEW_RETRIES: int = int(os.getenv('MAX_REVIEW_RETRIES', '2'))
    
    # ==========================================================================
    # 쿼리 타입별 유사도 임계값 (선택적)
    # ==========================================================================
    # 
    # 쿼리 유형에 따라 다른 유사도 임계값을 적용할 수 있음.
    # - dispute: 분쟁조정 관련 쿼리 (정확도 필요)
    # - law: 법령 관련 쿼리 (더 엄격한 매칭)
    # - criteria: 기준 관련 쿼리 (완화된 매칭)
    # - general: 일반 대화 (가장 완화된 매칭)
    #
    SIMILARITY_THRESHOLDS: Dict[str, float] = {
        'dispute': float(os.getenv('SIMILARITY_THRESHOLD_DISPUTE', '0.55')),
        'law': float(os.getenv('SIMILARITY_THRESHOLD_LAW', '0.60')),
        'criteria': float(os.getenv('SIMILARITY_THRESHOLD_CRITERIA', '0.50')),
        'general': float(os.getenv('SIMILARITY_THRESHOLD_GENERAL', '0.45')),
    }
    
    @classmethod
    def get_similarity_threshold(cls, query_type: str = None) -> float:
        """
        쿼리 타입별 유사도 임계값 반환
        
        Args:
            query_type: 쿼리 타입 (dispute, law, criteria, general)
                       None이면 기본 임계값 반환
        
        Returns:
            해당 쿼리 타입의 유사도 임계값
        
        Example:
            >>> AgentConfig.get_similarity_threshold('dispute')
            0.55
            >>> AgentConfig.get_similarity_threshold('law')
            0.60
            >>> AgentConfig.get_similarity_threshold()  # 기본값
            0.55
        """
        if query_type and query_type in cls.SIMILARITY_THRESHOLDS:
            return cls.SIMILARITY_THRESHOLDS[query_type]
        return cls.SIMILARITY_THRESHOLD
    
    @classmethod
    def reload(cls) -> None:
        """
        환경 변수에서 설정 다시 로드
        
        런타임 중 환경 변수가 변경된 경우 호출하여 설정 갱신.
        주로 테스트에서 사용.
        
        Example:
            >>> os.environ['SIMILARITY_THRESHOLD'] = '0.60'
            >>> AgentConfig.reload()
            >>> AgentConfig.SIMILARITY_THRESHOLD
            0.60
        """
        cls.SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.55'))
        cls.MAX_REACT_ITERATIONS = int(os.getenv('MAX_REACT_ITERATIONS', '2'))
        cls.PROHIBITED_VIOLATION_THRESHOLD = int(os.getenv('PROHIBITED_VIOLATION_THRESHOLD', '3'))
        cls.MAX_REVIEW_RETRIES = int(os.getenv('MAX_REVIEW_RETRIES', '2'))
        
        cls.SIMILARITY_THRESHOLDS = {
            'dispute': float(os.getenv('SIMILARITY_THRESHOLD_DISPUTE', '0.55')),
            'law': float(os.getenv('SIMILARITY_THRESHOLD_LAW', '0.60')),
            'criteria': float(os.getenv('SIMILARITY_THRESHOLD_CRITERIA', '0.50')),
            'general': float(os.getenv('SIMILARITY_THRESHOLD_GENERAL', '0.45')),
        }
    
    @classmethod
    def to_dict(cls) -> Dict:
        """
        현재 설정을 딕셔너리로 반환 (로깅/디버깅용)
        
        Returns:
            설정 딕셔너리
        """
        return {
            'SIMILARITY_THRESHOLD': cls.SIMILARITY_THRESHOLD,
            'MAX_REACT_ITERATIONS': cls.MAX_REACT_ITERATIONS,
            'PROHIBITED_VIOLATION_THRESHOLD': cls.PROHIBITED_VIOLATION_THRESHOLD,
            'MAX_REVIEW_RETRIES': cls.MAX_REVIEW_RETRIES,
            'SIMILARITY_THRESHOLDS': cls.SIMILARITY_THRESHOLDS,
        }
