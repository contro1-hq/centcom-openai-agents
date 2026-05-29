# Contro1 OpenAI Agents Skill

Use this when adding Contro1 to an OpenAI Agents SDK project.

## Rules

- Use `create_protocol_request` for tool calls that must wait for a human decision.
- Use `log_action` for autonomous actions that were already allowed by policy.
- Derive one stable `correlation_id` per OpenAI run and pass it to every related request and audit record. Use `f"openai-{run_id}"` or any stable string that ties to the run.
- When mapping an operator callback back into the OpenAI run, call `log_action(..., in_reply_to={"type": "request", "id": request_id})` so the dashboard case shows the full story.
- `in_reply_to` must reference an item in the same organization; if you send both `correlation_id` and `in_reply_to`, they must belong to the same case.
- Keep `external_request_id` scoped to the specific tool call, not the whole run.

## Pattern

```python
case_id = f"openai-{run_id}"

request = client.create_protocol_request({
    "title": f"Approve tool call: {tool_name}",
    "request_type": "decision",
    "source": {"integration": "openai-agents", "run_id": run_id},
    "continuation": {"mode": "decision", "callback_url": callback_url},
    "external_request_id": f"openai:{run_id}:{call_id}",
    "correlation_id": case_id,
})

client.log_action(
    action="openai_agents.tool_result_mapped",
    summary="Mapped operator answer back to OpenAI Agents state",
    source={"integration": "openai-agents", "run_id": run_id},
    correlation_id=case_id,
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
2. Check Control Map routing before creating approval requests (see below).
3. Create CENTCOM approval request per interruption.
4. Apply operator decision to run state.
5. Resume the same run from state.

## Check routing before submitting (Control Map)

For sensitive tools with required roles or multi-person approval, verify routing is ready before submitting the request. Cache the result for 5–15 minutes.

```python
preview = centcom.post("/requests/control-map", {
    "approval_requirements": {"required_roles": ["manager"], "required_approvals": 2},
    "approval_policy": {
        "mode": "threshold",
        "required_approvals": 2,
        "separation_of_duties": True,
        "fail_closed_on_timeout": True,
    },
})

if not preview["satisfiable"]:
    # preview["warnings"] describes the gap; preview["suggested_action"] explains what to fix
    raise RuntimeError(f"Cannot route review: {preview['warnings']}")
```

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
    external_request_id=f"openai:{run_id}:{interruption.call_id}",
    correlation_id=f"openai-{run_id}",
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
- Include idempotency key (`external_request_id`) for retried request creation.
- Do not lose run state between interruption and resume.
- Verify webhook signatures for all CENTCOM callback endpoints.
- Keep model-facing rejection messages explicit and safe.

## Common mistakes to avoid

- Creating duplicate approval requests for the same interruption.
- Resuming with the wrong run state object.
- Not handling mixed outcomes when multiple interruptions exist.
- Resuming the agent after the first approval while quorum is still pending.

## Production pattern: Agent Plugin

Wrap Contro1 calls behind a plugin to reduce per-call token overhead and standardize policy across your agent:

```python
from datetime import datetime, timedelta
from centcom import CentcomClient

class Contro1Plugin:
    def __init__(self, client: CentcomClient, cache_ttl_minutes: int = 10):
        self._client = client
        self._cache: dict = {}
        self._ttl = timedelta(minutes=cache_ttl_minutes)

    def preview_policy(self, approval_requirements: dict, approval_policy: dict) -> dict:
        key = str(sorted(approval_requirements.items()))
        cached = self._cache.get(key)
        if cached and datetime.utcnow() < cached["expires"]:
            return cached["data"]
        result = self._client.post("/requests/control-map", {
            "approval_requirements": approval_requirements,
            "approval_policy": approval_policy,
        })
        self._cache[key] = {"data": result, "expires": datetime.utcnow() + self._ttl}
        return result

    def request_human_review(self, payload: dict) -> dict:
        return self._client.create_protocol_request(payload)

    def log_audit_action(self, payload: dict) -> dict:
        return self._client.log_action(**payload)

    def resume_from_decision(self, case_id: str) -> dict:
        return self._client.get(f"/cases/{case_id}")
```

## Full reference links

- Repo: https://github.com/contro1-hq/centcom-openai-agents
- Runnable bridge example: https://github.com/contro1-hq/centcom-openai-agents/blob/main/examples/openai_agents_bridge.py
- Skill file source: https://github.com/contro1-hq/centcom-openai-agents/blob/main/skills/centcom-openai-agents.md
- Core Python SDK: https://github.com/contro1-hq/centcom
- Microsoft AGT companion skill: https://github.com/contro1-hq/contro1-microsoft-agent-governance-toolkit-integration/blob/main/skills/contro1-microsoft-agent-governance-toolkit-integration.md
- Protocol docs: https://contro1.com/docs/audit-records-and-cases

## Governance readiness

For teams operating under EU or US AI governance requirements, see:
- https://contro1.com/guides/eu-ai-act-readiness
- https://contro1.com/guides/us-ai-governance-readiness
