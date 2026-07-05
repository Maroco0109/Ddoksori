"""Variant B (Agentic RAG) — isolated comparison variant for A/B measurement.

A (MAS / Advanced RAG) stays frozen as baseline. B = single strong model +
tools via LangGraph ReAct. This package is NOT imported by A's runtime.

M2-5R minimal skeleton: one retrieval tool + deterministic cosine-gated
single-shot clarification + trace capture.
"""
