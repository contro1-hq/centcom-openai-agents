---
name: centcom-openai-agents
description: Guide for integrating OpenAI Agents SDK HITL interruptions with CENTCOM approvals and resume flow.
user_invocable: true
---

# CENTCOM + OpenAI Agents SDK Skill

Use this skill when a user wants OpenAI Agents SDK tool approvals routed through CENTCOM with explicit resume control.

## Required configuration

Set your CENTCOM API key before creating requests:

```bash
CENTCOM_API_KEY=cc_live_xxx
```

Initialize the client from environment:

```python
import os
from centcom import CentcomClient

centcom = CentcomClient(api_key=os.environ["CENTCOM_API_KEY"])
```

## What to build

Implement a deterministic approval bridge:

1. Detect tool interruptions (`result.interruptions`).
2. Create CENTCOM approval request per interruption.
3. Apply operator decision to run state.
4. Resume the same run from state.

## Implementation steps

1. Identify tools that require approval (`needs_approval=True` or conditional function).
2. On each interruption, create a CENTCOM approval request with stable metadata.
3. Map CENTCOM decision back to `state.approve(...)` or `state.reject(...)`.
4. Resume execution with the same run state via `Runner.run(agent, state)`.
5. Persist serialized state when approvals may take a long time.

## Bridge snippet

```python
req = centcom.create_request(
    type="approval",
    question=f"Approve tool call: {interruption.name}?",
    context=f"Arguments: {interruption.arguments}",
    required_role="manager",
    metadata={"tool_name": interruption.name, "call_id": interruption.call_id},
)
decision = centcom.wait_for_response(req["id"], interval=3, timeout=600)
```

## Decision mapping

- If `approved` (or boolean `value`) is true -> `state.approve(interruption)`.
- Else -> `state.reject(interruption, rejection_message="Rejected in CENTCOM")`.

## Production checklist

- Enforce `required_role` for sensitive tool classes.
- Include idempotency key for retried request creation.
- Do not lose run state between interruption and resume.
- Keep model-facing rejection messages explicit and safe.

## Common mistakes to avoid

- Creating duplicate approval requests for the same interruption.
- Resuming with the wrong run state object.
- Not handling mixed outcomes when multiple interruptions exist.
