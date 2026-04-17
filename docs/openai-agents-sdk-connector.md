# OpenAI Agents SDK Connector Guide

This guide shows how to connect OpenAI Agents SDK HITL interruptions with Contro1 approvals using Integration Protocol v1.

## Prerequisites

- Python 3.10+
- OpenAI Agents SDK project already running
- `centcom` installed:

```bash
pip install centcom
```

## Environment setup (required)

Never hardcode API keys in source code.

```bash
CENTCOM_API_KEY=your_centcom_api_key
CENTCOM_BASE_URL=https://api.contro1.com/api/centcom/v1
CENTCOM_WEBHOOK_SECRET=whsec_your_signing_secret
```

## Recommended flow

1. Mark sensitive tools with `needs_approval`.
2. When interruptions appear, create a Contro1 **protocol** request for each interruption.
3. Receive operator decision and apply `state.approve(...)` or `state.reject(...)` (or instruction-mode handling).
4. Resume with `Runner.run(agent, state)`.

## Starter kit

Use `examples/openai_agents_bridge.py` for a local runnable bridge template.

It includes:

- request creation in protocol v1 shape
- signature verification for callbacks
- deterministic idempotency key by `run_id + call_id`
- resume mapping placeholder (`approve` / `reject`)

## End-to-end example

```python
import os
from agents import Agent, Runner, function_tool
from centcom import CentcomClient

centcom = CentcomClient(api_key=os.environ["CENTCOM_API_KEY"])

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
            metadata={"tool_name": item.name},
        )
        out = centcom.wait_for_response(req["id"], interval=3, timeout=600)
        approved = bool((out.get("response") or {}).get("approved"))
        if approved:
            state.approve(item)
        else:
            state.reject(item, rejection_message="Rejected in CENTCOM")
    result = await Runner.run(agent, state)
```

## Decision mapping

- `approved == true` (or boolean `value == true`) -> `state.approve(interruption)`
- anything else -> `state.reject(interruption, ...)`

## Production checklist

- Use `required_role` for sensitive tool categories (`manager`/`admin`).
- Add idempotency protection when creating approval requests on retries.
- Persist serialized run state for long-lived approvals.
- Verify webhook signatures on any callback endpoint that receives CENTCOM events.
- Keep rejection messages explicit so the model handles refusal safely.
- Do not include raw secrets in interruption metadata.

## Troubleshooting

- Duplicate approvals for same interruption: add deterministic idempotency key from run + tool call IDs.
- Run does not resume: verify you're resuming with the same `RunState`.
- Wrong approval routing: verify `required_role` and operator role assignments.
