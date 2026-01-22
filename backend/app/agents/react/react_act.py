"""
똑소리 프로젝트 - ReAct 액션 노드
작성일: 2026-01-17
S2-7: ReAct 패턴 구현 - 액션(Action) 노드
S2-PR1: 액션 레지스트리 패턴 도입 (2026-01-21)
S3-PR3: 하이브리드 도구 실행기 도입 (2026-01-21)

ReAct 패턴의 Action 단계를 담당하는 노드.
HybridToolExecutor를 통해 규칙 기반 또는 LLM 기반 도구 선택/실행.
"""

import os
import logging
from typing import Dict, Any, List, Optional

from ...orchestrator.state import ChatState
from ...llm import ToolCallingClient
from .action_registry import ActionRegistry
from .tools import AVAILABLE_TOOLS, is_allowed_tool, get_tool_by_name
from .prompts import TOOL_SELECTION_SYSTEM_PROMPT
from ...common.metrics import PROM_TOOL_USAGE

logger = logging.getLogger(__name__)


def _build_search_query(state: ChatState) -> str:
    user_query = state.get('user_query', '')
    
    # 이전 검색 쿼리가 있다면 참고 (state에 저장된 경우)
    # 현재는 단순 사용자 쿼리 사용
    # TODO: Query Analysis 결과가 있다면 활용
    
    # 불필요한 조사/어미 제거 등 전처리 가능
    return user_query.strip()


class HybridToolExecutor:
    """
    하이브리드 도구 실행기 (규칙 기반 + @tool)
    
    USE_LLM_TOOLS=true일 때 LLM 기반 도구 선택을 활성화하고,
    실패/타임아웃 시 규칙 기반으로 즉시 폴백합니다.
    """
    
    def __init__(
        self, 
        client: Optional[ToolCallingClient] = None, 
        use_llm_tools: Optional[bool] = None
    ):
        if use_llm_tools is None:
            use_llm_tools = os.getenv('USE_LLM_TOOLS', 'false').lower() == 'true'
        
        self.use_llm_tools = use_llm_tools
        self.client = client or ToolCallingClient()
        self._llm_with_tools: Optional[Any] = None
        self._tools_bound = False
        
        logger.info(f"[HybridToolExecutor] Initialized: use_llm_tools={self.use_llm_tools}")
    
    def _ensure_tools_bound(self) -> bool:
        if self._tools_bound:
            return True
        
        if not self.use_llm_tools:
            return False
        
        try:
            if not self.client.is_available():
                logger.warning("[HybridToolExecutor] Tool calling LLM not available")
                return False
            
            self._llm_with_tools = self.client.bind_tools(AVAILABLE_TOOLS)
            self._tools_bound = True
            logger.info("[HybridToolExecutor] Tools bound successfully")
            return True
            
        except Exception as e:
            logger.warning(f"[HybridToolExecutor] Failed to bind tools: {e}")
            return False
    
    def execute(self, state: ChatState) -> Dict:
        action = state.get('last_action')
        thought = state.get('last_thought') or ''
        query = _build_search_query(state)
        
        # 1. 규칙 기반 액션 우선 확인 (명시적 액션이 있는 경우)
        registered_actions = ActionRegistry.get_action_names()
        if action and action in registered_actions:
            logger.debug(f"[HybridToolExecutor] Rule-based execution: {action}")
            PROM_TOOL_USAGE.labels(tool_name=action, mode="rule").inc()
            return self._execute_rule_based(action, state, query, thought)
        
        # 2. LLM 기반 도구 선택 시도
        if self.use_llm_tools and self._ensure_tools_bound():
            logger.info("[HybridToolExecutor] Attempting LLM-based tool selection")
            try:
                # LLM execution success tracked inside _execute_with_tools (via tool calls)
                return self._execute_with_tools(state, query, thought)
            except Exception as e:
                logger.warning(f"[HybridToolExecutor] LLM tool calling failed: {e}, falling back")
                PROM_TOOL_USAGE.labels(tool_name="fallback_to_search_all", mode="fallback").inc()
        
        # 3. 폴백: 기본 검색 (search_all)
        default_action = 'search_all'
        logger.debug(f"[HybridToolExecutor] Fallback to rule-based: {default_action}")
        if not (action and action in registered_actions): # Don't double count if it was explicit rule
             PROM_TOOL_USAGE.labels(tool_name=default_action, mode="rule_fallback").inc()
        return self._execute_rule_based(default_action, state, query, thought)
    
    def _execute_rule_based(
        self,
        action: str,
        state: ChatState,
        query: str,
        thought: str
    ) -> Dict:
        return ActionRegistry.execute(action, state, query, thought)
    
    def _execute_with_tools(
        self,
        state: ChatState,
        query: str,
        thought: str
    ) -> Dict:
        messages = self._build_tool_messages(state, query)
        
        try:
            # LLM 호출
            response = self._llm_with_tools.invoke(messages)
            
            # 도구 호출이 있는 경우 처리
            if hasattr(response, 'tool_calls') and response.tool_calls:
                return self._process_tool_calls(response.tool_calls, state, query, thought)
            
            # 도구 호출이 없는 경우 -> 종료
            return {
                'last_observation': '도구 호출 없음. 검색 종료.',
                'should_continue': False,
                'react_steps': [{
                    'thought': thought,
                    'action': 'finish_search',
                    'action_input': {},
                    'observation': '도구 호출 없음. 검색 종료.',
                }],
            }
            
        except Exception as e:
            logger.error(f"[HybridToolExecutor] Tool execution error: {e}")
            raise
    
    def _build_tool_messages(self, state: ChatState, query: str) -> List[dict]:
        user_query = state.get('user_query', '')
        last_observation = state.get('last_observation', '')
        
        user_content = f"사용자 질문: {user_query}\n검색 쿼리: {query}"
        if last_observation:
            user_content += f"\n이전 검색 결과: {last_observation}"
        
        return [
            {"role": "system", "content": TOOL_SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    
    def _process_tool_calls(
        self,
        tool_calls: List[Any],
        state: ChatState,
        query: str,
        thought: str
    ) -> Dict:
        observations = []
        react_steps = []
        should_continue = True
        
        for tool_call in tool_calls:
            tool_name = tool_call.get('name', '') if isinstance(tool_call, dict) else getattr(tool_call, 'name', '')
            tool_args = tool_call.get('args', {}) if isinstance(tool_call, dict) else getattr(tool_call, 'args', {})
            
            if not is_allowed_tool(tool_name):
                logger.warning(f"[HybridToolExecutor] Blocked disallowed tool: {tool_name}")
                observations.append(f"허용되지 않은 도구: {tool_name}")
                continue
            
            if tool_name == 'finish_search':
                should_continue = False
                observations.append("검색 완료. 답변 생성 단계로 진행합니다.")
                PROM_TOOL_USAGE.labels(tool_name=tool_name, mode="llm").inc()
                react_steps.append({
                    'thought': thought,
                    'action': tool_name,
                    'action_input': {},
                    'observation': "검색 완료",
                })
                continue
            
            tool_fn = get_tool_by_name(tool_name)
            if tool_fn:
                try:
                    # 쿼리 파라미터가 없으면 기본 쿼리 사용
                    tool_query = tool_args.get('query', query)
                    result = tool_fn.invoke(tool_query)
                    observations.append(result)
                    PROM_TOOL_USAGE.labels(tool_name=tool_name, mode="llm").inc()
                    react_steps.append({
                        'thought': thought,
                        'action': tool_name,
                        'action_input': {'query': tool_query},
                        'observation': result,
                    })
                except Exception as e:
                    logger.error(f"[HybridToolExecutor] Tool {tool_name} execution error: {e}")
                    observations.append(f"도구 실행 실패: {tool_name}")
                    PROM_TOOL_USAGE.labels(tool_name=tool_name, mode="llm_error").inc()
        
        observation = " | ".join(observations) if observations else "도구 실행 결과 없음"
        
        return {
            'last_observation': observation,
            'should_continue': should_continue,
            'react_steps': react_steps if react_steps else [{
                'thought': thought,
                'action': 'tool_call',
                'action_input': {},
                'observation': observation,
            }],
        }


# 모듈 레벨 인스턴스 (Lazy Initialization)
_hybrid_executor: Optional[HybridToolExecutor] = None

def react_act_node(state: ChatState) -> Dict:
    """
    ReAct 액션 노드 (하이브리드 지원)

    HybridToolExecutor를 통해 last_action에 따라 적절한 도구를 실행.
    """
    global _hybrid_executor
    
    if _hybrid_executor is None:
        _hybrid_executor = HybridToolExecutor()
    
    return _hybrid_executor.execute(state)
