"""M7-4: LangSmith trace tagging (complement — self-built M3/M6 stays canonical).

LangSmith is already enabled via LANGCHAIN_TRACING_V2 / LANGCHAIN_API_KEY /
LANGCHAIN_PROJECT. These helpers attach variant / session / model tags + metadata
to the LangChain/LangGraph RunnableConfig so A/B runs are filterable and
comparable in LangSmith.

This is tagging only. The canonical measurement stack remains the self-built
M3 Postgres event tables + M6 Prometheus/Grafana; LangSmith is a dev-tracing and
eval/annotation convenience layered on top.
"""
from typing import Any, Dict, List, Optional, Tuple


def trace_tags_metadata(
    variant: str,
    session_id: Optional[str] = None,
    chat_type: Optional[str] = None,
    model_spec: Optional[str] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """Build (tags, metadata) for a LangSmith run from A/B request context."""
    tags = [f"variant:{variant}"]
    if model_spec:
        tags.append(f"model_spec:{model_spec}")
    if chat_type:
        tags.append(f"chat_type:{chat_type}")

    metadata: Dict[str, Any] = {"variant": variant}
    if session_id:
        metadata["session_id"] = session_id
    if chat_type:
        metadata["chat_type"] = chat_type
    if model_spec:
        metadata["model_spec"] = model_spec
    return tags, metadata


def with_trace_tags(
    config: Optional[Dict[str, Any]],
    variant: str,
    session_id: Optional[str] = None,
    chat_type: Optional[str] = None,
    model_spec: Optional[str] = None,
) -> Dict[str, Any]:
    """Merge LangSmith tags/metadata into an existing RunnableConfig dict.

    Existing tags/metadata are preserved and extended (not overwritten).
    """
    tags, metadata = trace_tags_metadata(variant, session_id, chat_type, model_spec)
    merged: Dict[str, Any] = dict(config or {})
    merged["tags"] = [*merged.get("tags", []), *tags]
    merged["metadata"] = {**merged.get("metadata", {}), **metadata}
    return merged
