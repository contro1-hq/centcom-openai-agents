# Contro1 OpenAI Agents Skill

Use this when adding Contro1 to an OpenAI Agents SDK project.

## Rules

- Use `create_protocol_request` for tool calls that must wait for a human decision.
- Use `log_action` for autonomous actions that were already allowed by policy.
- Generate or derive one stable `thread_id` per OpenAI run and pass it to every related request or audit record.
- When mapping an operator callback back into the OpenAI run, call `log_action(..., in_reply_to={"type": "request", "id": request_id})` so the dashboard thread shows the full story.
- Keep `external_request_id` scoped to the specific tool call, not the whole thread.

## Pattern

```python
thread_id = f"thr_openai_{stable_hash(run_id)}"

request = client.create_protocol_request({
    "title": f"Approve tool call: {tool_name}",
    "request_type": "decision",
    "source": {"integration": "openai-agents", "run_id": run_id},
    "continuation": {"mode": "decision", "callback_url": callback_url},
    "external_request_id": f"openai:{run_id}:{call_id}",
    "thread_id": thread_id,
})

client.log_action(
    action="openai_agents.tool_result_mapped",
    summary="Mapped operator answer back to OpenAI Agents state",
    source={"integration": "openai-agents", "run_id": run_id},
    thread_id=thread_id,
    in_reply_to={"type": "request", "id": request["id"]},
)
```
---
name: centcom-openai-agents
description: Guide for integrating OpenAI Agents SDK HITL interruptions with CENTCOM approvals and resume flow.
user_invocable: true
---

# CENTCOM + OpenAI Agents SDK Skill

Use this skill when a user wants OpenAI Agents SDK tool approvals routed through CENTCOM with explicit resume control.

## Installation

```bash
pip install centcom flask python-dotenv
```

## Required configuration

```bash
CENTCOM_API_KEY=your_centcom_api_key
CENTCOM_BASE_URL=https://api.contro1.com/api/centcom/v1
CENTCOM_WEBHOOK_SECRET=whsec_your_signing_secret
```

Initialize the client from environment:

```python
import os
from centcom import CentcomClient

centcom = CentcomClient(api_key=os.environ["CENTCOM_API_KEY"])
```

## Webhook endpoint (production)

CENTCOM sends the operator's decision to a URL you own. Expose an endpoint that:
1. Verifies `centcom-signature` using `CENTCOM_WEBHOOK_SECRET`.
2. Reads `approved` / `value` from the payload body.
3. Resumes the paused agent run.

Use the runnable webhook template at https://github.com/contro1-hq/centcom-openai-agents/blob/main/examples/openai_agents_bridge.py.

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
    approval_policy={
        "mode": "threshold",
        "required_approvals": 2,
        "required_roles": ["manager", "admin"],
        "separation_of_duties": True,
        "fail_closed_on_timeout": True,
    },
    metadata={"tool_name": interruption.name, "call_id": interruption.call_id},
)
decision = centcom.wait_for_response(req["id"], interval=3, timeout=600)
```

For sensitive tools, use `approval_policy` so the agent resumes only after quorum. Partial approvals are visible in Contro1 Activity but are not final decisions.

## Decision mapping

- If `approved` (or boolean `value`) is true -> `state.approve(interruption)`.
- Else -> `state.reject(interruption, rejection_message="Rejected in CENTCOM")`.

## Production checklist

- Enforce `required_role` for sensitive tool classes.
- Require two-person approval for production deploy, vendor payment, bulk data deletion, and privilege escalation tools.
- Include idempotency key for retried request creation.
- Do not lose run state between interruption and resume.
- Verify webhook signatures for all CENTCOM callback endpoints.
- Keep model-facing rejection messages explicit and safe.

## Common mistakes to avoid

- Creating duplicate approval requests for the same interruption.
- Resuming with the wrong run state object.
- Not handling mixed outcomes when multiple interruptions exist.
- Resuming the agent after the first approval while quorum is still pending.

## Full reference links

- Repo: https://github.com/contro1-hq/centcom-openai-agents
- Runnable bridge example: https://github.com/contro1-hq/centcom-openai-agents/blob/main/examples/openai_agents_bridge.py
- Skill file source: https://github.com/contro1-hq/centcom-openai-agents/blob/main/skills/centcom-openai-agents.md
- Core Python SDK: https://github.com/contro1-hq/centcom
- Protocol docs: https://contro1.com/docs/audit-records-and-threads
