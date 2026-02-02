# Decisions - PR1: Agent Communication Analysis

- **Blackboard Pattern Retention**: Decided to keep the Blackboard pattern for now to maintain flexibility and compatibility with LangGraph's state management, but recommended moving towards more explicit sub-states and protocols.
- **Documentation as Contract**: Used the `NODE_SNAPSHOT_FIELDS` in `graph.py` as the source of truth for mapping agent I/O, as it represents the actual runtime monitoring and debugging contract.
- **Categorization**: Grouped 40+ fields into 6 logical categories (Session, Agent Results, Output, Control, ReAct, Memory) to make the state more manageable for developers.
