# centcom-openai-agents

Official CENTCOM connector guides and examples for OpenAI Agents SDK human-in-the-loop approvals.

## What this repo provides

- A production-oriented integration guide for interruption -> approval -> resume flows.
- Decision mapping patterns from CENTCOM responses to `state.approve()` / `state.reject()`.
- A reusable skill file for AI-assisted implementation in real projects.

## Security defaults (required)

- Use environment variables only. Never hardcode secrets.
- Required API auth:

```bash
CENTCOM_API_KEY=your_centcom_api_key
```

- If your bridge exposes callback endpoints, verify CENTCOM signatures:

```bash
CENTCOM_WEBHOOK_SECRET=whsec_your_signing_secret
```

## Recommended architecture

1. Mark sensitive tools as requiring approval.
2. For each interruption, create a CENTCOM request with `required_role`.
3. Wait for operator decision.
4. Apply decision to run state and resume the same run.

## Quick Start

```bash
pip install centcom
```

```python
import os
from agents import Agent, Runner, function_tool
from centcom import CentcomClient

centcom = CentcomClient(api_key=os.environ["CENTCOM_API_KEY"])

@function_tool(needs_approval=True)
async def cancel_order(order_id: int) -> str:
    return f"Cancelled order {order_id}"

agent = Agent(name="Ops", instructions="Handle requests safely.", tools=[cancel_order])
result = await Runner.run(agent, "Cancel order 42")

while result.interruptions:
    state = result.to_state()
    for interruption in result.interruptions:
        req = centcom.create_request(
            type="approval",
            question=f"Approve tool call: {interruption.name}?",
            context=f"Arguments: {interruption.arguments}",
            required_role="manager",
            metadata={"tool_name": interruption.name, "call_id": interruption.call_id},
        )
        decision = centcom.wait_for_response(req["id"], interval=3, timeout=600)
        approved = bool((decision.get("response") or {}).get("approved"))
        if approved:
            state.approve(interruption)
        else:
            state.reject(interruption, rejection_message="Rejected in CENTCOM")
    result = await Runner.run(agent, state)
```

## Decision mapping

- `approved == true` (or boolean `value == true`) -> `state.approve(interruption)`
- `approved == false` / timeout / expired -> `state.reject(interruption, ...)`

## Production checklist

- Add idempotency key per interruption to prevent duplicate pending requests.
- Persist run state if approvals may take minutes or longer.
- Use `required_role` for sensitive tool categories (`manager` / `admin`).
- Verify callback signatures on every public endpoint.
- Keep rejection messaging explicit and safe for downstream model behavior.

## Troubleshooting

- Duplicate approvals: use deterministic idempotency key from run and call IDs.
- Resume does not continue: confirm resume is applied to the same `RunState`.
- Wrong queue routing: validate `required_role` and operator role assignments.

## Documentation in this repo

- Guide: `docs/openai-agents-sdk-connector.md`
- Skill: `skills/centcom-openai-agents.md`

## Related repositories

- [`centcom`](https://github.com/contro1-hq/centcom)
- [`centcom-langgraph`](https://github.com/contro1-hq/centcom-langgraph)
