# Learnings - PR1: Agent Communication Analysis

- The `ChatState` is highly centralized, acting as a "Blackboard" where all agents read and write.
- LangGraph's reducer pattern (`operator.add`) is used for `sources` and `react_steps`, which can lead to memory growth issues if not managed.
- `NODE_SNAPSHOT_FIELDS` in `graph.py` provides a very clear (though potentially manually maintained) view of what each node is expected to read and write.
- The current implementation has a mix of legacy linear pipeline logic and newer ReAct pattern logic, which is reflected in the state fields.
- Many fields are `Optional` or have default values, making the state flexible but also making it harder to enforce strict data contracts between agents.
