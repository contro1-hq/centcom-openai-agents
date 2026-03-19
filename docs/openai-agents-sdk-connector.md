# OpenAI Agents SDK Connector Guide

This guide shows how to connect OpenAI Agents SDK HITL interruptions with CENTCOM approvals.

## Recommended flow

1. Mark sensitive tools with `needs_approval`.
2. When interruptions appear, create a CENTCOM request for each interruption.
3. Receive operator decision and apply `state.approve(...)` or `state.reject(...)`.
4. Resume with `Runner.run(agent, state)`.

## Short example

```python
from agents import Agent, Runner, function_tool
from centcom import CentcomClient

centcom = CentcomClient(api_key="cc_live_xxx")

@function_tool(needs_approval=True)
async def cancel_order(order_id: int) -> str:
    return f"Cancelled order {order_id}"

agent = Agent(name="Ops", instructions="Handle safely.", tools=[cancel_order])
result = await Runner.run(agent, "Cancel order 42")

while result.interruptions:
    state = result.to_state()
    for item in result.interruptions:
        req = centcom.create_request(
            type="approval",
            question=f"Approve: {item.name}?",
            context=f"Arguments: {item.arguments}",
            required_role="manager",
        )
        out = centcom.wait_for_response(req["id"], interval=3, timeout=600)
        approved = bool((out.get("response") or {}).get("approved"))
        if approved:
            state.approve(item)
        else:
            state.reject(item, rejection_message="Rejected in CENTCOM")
    result = await Runner.run(agent, state)
```
