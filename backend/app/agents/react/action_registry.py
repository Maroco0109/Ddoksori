"""
똑소리 프로젝트 - ReAct 액션 레지스트리
작성일: 2026-01-21
S2-PR1: 액션 레지스트리 패턴 도입

기존 if-elif 구조를 플러그인 방식의 레지스트리로 대체하여
확장성과 유지보수성을 향상.

사용 예시:
    from .action_registry import ActionRegistry
    
    # 액션 실행
    result = ActionRegistry.execute('search_all', state, query)
    
    # 새 액션 등록
    ActionRegistry.register(MyCustomAction())
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from ...orchestrator.state import ChatState, RetrievalResult, ReActStep

logger = logging.getLogger(__name__)


class ActionResult:
    """액션 실행 결과를 담는 데이터 클래스"""
    
    def __init__(
        self,
        observation: str,
        retrieval: Optional[RetrievalResult] = None,
        sources: Optional[List[Dict]] = None,
        clarifying_questions: Optional[List[str]] = None,
        awaiting_user_choice: bool = False,
        should_continue: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.observation = observation
        self.retrieval = retrieval
        self.sources = sources
        self.clarifying_questions = clarifying_questions
        self.awaiting_user_choice = awaiting_user_choice
        self.should_continue = should_continue
        self.extra = extra or {}
    
    def to_state_update(self, thought: str, action: str, action_input: Dict) -> Dict:
        """상태 업데이트 dict로 변환"""
        react_step: ReActStep = {
            'thought': thought,
            'action': action,
            'action_input': action_input,
            'observation': self.observation,
        }
        
        update = {
            'last_observation': self.observation,
            'react_steps': [react_step],
        }
        
        if self.retrieval is not None:
            update['retrieval'] = self.retrieval
        
        if self.sources is not None:
            update['sources'] = self.sources
        
        if self.clarifying_questions is not None:
            update['clarifying_questions'] = self.clarifying_questions
        
        if self.awaiting_user_choice:
            update['awaiting_user_choice'] = True
        
        if not self.should_continue:
            update['should_continue'] = False
        
        # 추가 필드
        update.update(self.extra)
        
        return update


class BaseAction(ABC):
    """
    액션 기본 추상 클래스
    
    새로운 액션을 추가하려면 이 클래스를 상속하고
    name, description, execute() 메서드를 구현합니다.
    
    Example:
        class MyAction(BaseAction):
            name = "my_action"
            description = "내 커스텀 액션"
            
            def execute(self, state: ChatState, query: str) -> ActionResult:
                # 실행 로직
                return ActionResult(observation="완료")
    """
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def execute(self, state: ChatState, query: str) -> ActionResult:
        """
        액션 실행
        
        Args:
            state: 현재 ChatState
            query: 검색 쿼리
            
        Returns:
            ActionResult 객체
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}')>"


class ActionRegistry:
    """
    액션 레지스트리
    
    등록된 액션을 관리하고 이름으로 실행할 수 있게 합니다.
    싱글톤 패턴으로 구현되어 전역에서 동일한 레지스트리를 사용합니다.
    
    Example:
        # 액션 등록
        ActionRegistry.register(SearchAllAction())
        
        # 액션 실행
        result = ActionRegistry.execute('search_all', state, query)
        
        # 등록된 액션 목록
        actions = ActionRegistry.list_actions()
    """
    
    _actions: Dict[str, BaseAction] = {}
    _initialized: bool = False
    
    @classmethod
    def register(cls, action: BaseAction) -> None:
        """
        액션 등록
        
        Args:
            action: 등록할 액션 인스턴스
        """
        if not action.name:
            raise ValueError(f"Action must have a name: {action}")
        
        if action.name in cls._actions:
            logger.warning(
                f"[ActionRegistry] Overwriting action: {action.name}"
            )
        
        cls._actions[action.name] = action
        logger.debug(f"[ActionRegistry] Registered action: {action.name}")
    
    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        액션 등록 해제
        
        Args:
            name: 해제할 액션 이름
            
        Returns:
            성공 여부
        """
        if name in cls._actions:
            del cls._actions[name]
            logger.debug(f"[ActionRegistry] Unregistered action: {name}")
            return True
        return False
    
    @classmethod
    def get(cls, name: str) -> Optional[BaseAction]:
        """
        액션 조회
        
        Args:
            name: 액션 이름
            
        Returns:
            액션 인스턴스 또는 None
        """
        cls._ensure_initialized()
        return cls._actions.get(name)
    
    @classmethod
    def execute(
        cls,
        name: str,
        state: ChatState,
        query: str,
        thought: str = '',
    ) -> Dict[str, Any]:
        """
        액션 실행
        
        Args:
            name: 액션 이름
            state: 현재 ChatState
            query: 검색 쿼리
            thought: ReAct 단계의 thought (로깅용)
            
        Returns:
            상태 업데이트 dict
        """
        cls._ensure_initialized()
        
        action = cls._actions.get(name)
        
        if action:
            try:
                logger.info(f"[ActionRegistry] Executing action: {name}")
                result = action.execute(state, query)
                
                # action_input 구성
                action_input = {'query': query}
                if result.clarifying_questions:
                    action_input = {'questions': result.clarifying_questions}
                
                return result.to_state_update(thought, name, action_input)
                
            except Exception as e:
                logger.error(f"[ActionRegistry] Action '{name}' failed: {e}")
                return {
                    'last_observation': f"액션 실행 실패: {str(e)}",
                    'react_steps': [{
                        'thought': thought,
                        'action': name,
                        'action_input': {'query': query},
                        'observation': f"액션 실행 실패: {str(e)}",
                    }],
                }
        else:
            logger.warning(f"[ActionRegistry] Unknown action: {name}")
            return {
                'last_observation': f"알 수 없는 액션: {name}",
                'react_steps': [{
                    'thought': thought,
                    'action': name or 'unknown',
                    'action_input': {},
                    'observation': f"알 수 없는 액션: {name}",
                }],
            }
    
    @classmethod
    def list_actions(cls) -> Dict[str, str]:
        """
        등록된 액션 목록 반환
        
        Returns:
            {액션명: 설명} 형태의 dict
        """
        cls._ensure_initialized()
        return {name: action.description for name, action in cls._actions.items()}
    
    @classmethod
    def get_action_names(cls) -> List[str]:
        """
        등록된 액션 이름 목록 반환
        
        Returns:
            액션 이름 리스트
        """
        cls._ensure_initialized()
        return list(cls._actions.keys())
    
    @classmethod
    def clear(cls) -> None:
        """
        모든 액션 제거 (테스트용)
        """
        cls._actions.clear()
        cls._initialized = False
        logger.debug("[ActionRegistry] Cleared all actions")
    
    @classmethod
    def _ensure_initialized(cls) -> None:
        """기본 액션이 등록되었는지 확인하고 없으면 등록"""
        if not cls._initialized:
            _register_default_actions()
            cls._initialized = True


# ============================================================================
# 기본 액션 구현
# ============================================================================

def _register_default_actions() -> None:
    """기본 액션들을 레지스트리에 등록"""
    from .actions import (
        SearchAllAction,
        SearchCriteriaAction,
        SearchLawsAction,
        AskClarificationAction,
    )
    
    ActionRegistry.register(SearchAllAction())
    ActionRegistry.register(SearchCriteriaAction())
    ActionRegistry.register(SearchLawsAction())
    ActionRegistry.register(AskClarificationAction())
    
    logger.info(
        f"[ActionRegistry] Registered {len(ActionRegistry._actions)} default actions"
    )
