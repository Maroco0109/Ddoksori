"""똑소리 프로젝트 - Agent/RAG workflow 관측(observability) 서브시스템.

M3 모니터링 백본의 영속화 계층. 요청 단위 run 기록을 시작으로
이후 step/retrieval/llm/guardrail 저장이 이 패키지에서 확장된다.

- M3-3: workflow_runs (요청 단위 run)  ← 현재
- M3-4: workflow_steps
- M3-5: retrieval_events
- M3-6: llm_calls
- M3-7: guardrail_events
"""

from .workflow_runs import WorkflowRunDB, save_workflow_run

__all__ = ["WorkflowRunDB", "save_workflow_run"]
