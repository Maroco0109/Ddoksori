import logging
import time
from typing import Dict, Any

from .state import ChatState_v2

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 2
DEFAULT_MAX_EXECUTION_TIME_MS = 30000
DEFAULT_ROUNDS_BUDGET = 3


def check_iteration_budget(state: ChatState_v2) -> bool:
    current = state.get('current_iteration', 0)
    max_iter = state.get('max_iterations', DEFAULT_MAX_ITERATIONS)
    
    if current >= max_iter:
        logger.warning(f"[Budget] Max iterations reached: {current}/{max_iter}")
        return False
    return True


def check_time_budget(state: ChatState_v2) -> bool:
    remaining = state.get('budget_remaining_ms', DEFAULT_MAX_EXECUTION_TIME_MS)
    
    if remaining <= 0:
        logger.warning(f"[Budget] Time budget exhausted: {remaining}ms remaining")
        return False
    return True


def check_budget(state: ChatState_v2) -> bool:
    return check_iteration_budget(state) and check_time_budget(state)


def increment_iteration(state: ChatState_v2) -> Dict[str, Any]:
    current = state.get('current_iteration', 0)
    new_iteration = current + 1
    logger.info(f"[Budget] Iteration incremented: {current} -> {new_iteration}")
    return {'current_iteration': new_iteration}


def deduct_time(state: ChatState_v2, elapsed_ms: int) -> Dict[str, Any]:
    remaining = state.get('budget_remaining_ms', DEFAULT_MAX_EXECUTION_TIME_MS)
    new_remaining = remaining - elapsed_ms
    logger.debug(f"[Budget] Time deducted: {remaining}ms - {elapsed_ms}ms = {new_remaining}ms")
    return {'budget_remaining_ms': new_remaining}


def increment_search_round(state: ChatState_v2) -> Dict[str, Any]:
    current = state.get('search_round', 0)
    new_round = current + 1
    logger.info(f"[Budget] Search round incremented: {current} -> {new_round}")
    return {'search_round': new_round}


def increment_retry_count(state: ChatState_v2) -> Dict[str, Any]:
    current = state.get('retry_count', 0)
    new_count = current + 1
    logger.info(f"[Budget] Retry count incremented: {current} -> {new_count}")
    return {'retry_count': new_count}


class BudgetTracker:
    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_execution_time_ms: int = DEFAULT_MAX_EXECUTION_TIME_MS,
    ):
        self.max_iterations = max_iterations
        self.max_execution_time_ms = max_execution_time_ms
        self.start_time: float | None = None
    
    def start(self) -> None:
        self.start_time = time.time()
        logger.info(f"[BudgetTracker] Started with max_iterations={self.max_iterations}, max_time={self.max_execution_time_ms}ms")
    
    def elapsed_ms(self) -> int:
        if self.start_time is None:
            return 0
        return int((time.time() - self.start_time) * 1000)
    
    def remaining_ms(self) -> int:
        return max(0, self.max_execution_time_ms - self.elapsed_ms())
    
    def is_time_exceeded(self) -> bool:
        return self.elapsed_ms() >= self.max_execution_time_ms
    
    def get_initial_state_updates(self) -> Dict[str, Any]:
        self.start()
        return {
            'max_iterations': self.max_iterations,
            'max_execution_time_ms': self.max_execution_time_ms,
            'budget_remaining_ms': self.max_execution_time_ms,
            'current_iteration': 0,
            'search_round': 0,
            'retry_count': 0,
        }
