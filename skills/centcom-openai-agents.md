---
name: centcom-openai-agents
description: Guide for integrating OpenAI Agents SDK HITL interruptions with CENTCOM approvals and resume flow.
user_invocable: true
---

# CENTCOM + OpenAI Agents SDK Skill

Use this skill when a user wants OpenAI Agents SDK tool approvals routed through CENTCOM.

## Implementation steps

1. Identify tools that require approval (`needs_approval=True` or conditional function).
2. On each interruption, create a CENTCOM approval request.
3. Map CENTCOM decision back to `state.approve(...)` or `state.reject(...)`.
4. Resume execution with the same run state.

## Short example

```python
req = centcom.create_request(
    type="approval",
    question=f"Approve tool call: {interruption.name}?",
    context=f"Arguments: {interruption.arguments}",
    required_role="manager",
)
decision = centcom.wait_for_response(req["id"], interval=3, timeout=600)
```
