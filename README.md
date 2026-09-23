# centcom-openai-agents

OpenAI Agents starter kit for Contro1/CENTCOM approval routing.

<!-- contro1:connect:start - generated from contro1.com/docs/connect-an-agent -->
## Connect your OpenAI Agents SDK agent to Contro1

A OpenAI Agents SDK agent runs in your own code, so it connects with an Agent Credential: a key bound to one agent, so every call is attributed to it and nothing in a request can change which agent it is.

1. Register the agent: contro1 init --name "<name>" --framework openai-agents, and finish the setup link it prints (purpose and owner).
2. Connect the application account under Apps, if it is not connected yet.
3. Give the agent the Actions it needs under Access. It starts with none.
4. Create an Agent Credential for it (Settings, API keys) and store it as CONTRO1_API_KEY in your secret manager.
5. Call Actions from your tools as below. The same credential creates approval requests for work your own code does.

Full guide: [Connect an agent: every path, in full](https://contro1.com/docs/connect-an-agent)

### Run an application Action from a OpenAI Agents SDK tool

Contro1 holds the account and makes the call, so the record is what Contro1 observed. The tool returns what the Action produced; when a person has to approve first, it waits and then returns the result. It never re-submits: a retry could send a second email.

Before writing the input, read the exact input_schema with get_action_contract, or from the Action on the Access page.

Install: `pip install "centcom>=1.5.0"`

```python
import os, uuid
from centcom import CentcomClient, needs_human_resolution

contro1 = CentcomClient(api_key=os.environ["CONTRO1_API_KEY"])  # an Agent Credential

def run_action(action_id: str, input: dict, *, account_mode: str = "shared", **kw):
    """Run a Contro1 Action and return what it produced. Never retries a send."""
    out = contro1.actions.invoke(
        action_id, input,
        authority_mode=kw.pop("authority_mode", "agent_principal"),
        account_mode=account_mode,
        idempotency_key=kw.pop("idempotency_key", str(uuid.uuid4())),
        **kw,
    )
    inv = out["invocation"]
    if inv["state"] == "executed":
        return out["result"]
    if inv["state"] == "awaiting_approval":
        settled = contro1.actions.wait_for_invocation(inv["invocation_id"])
        if needs_human_resolution(settled):
            raise RuntimeError("Outcome unknown; a person must check. Do not retry.")
        return contro1.actions.get_result(settled["invocation_id"])
    raise RuntimeError(f"Not run: {inv['state']} {out.get('not_run', '')}")

from agents import Agent, function_tool

@function_tool
def list_recent_emails(max_results: int = 5) -> list:
    """List the most recent emails in the team mailbox."""
    return run_action("gmail.message.list", {"max_results": max_results})

agent = Agent(name="Inbox assistant", tools=[list_recent_emails])
```

Everything below this section covers the other half: asking a person before a step your own code runs, using the same credential.

<!-- contro1:connect:end -->

## Agent Integration Kit

To save time, give your coding agent this skill - it inspects your system, reports governance gaps, and suggests Contro1 integration (optional):

```
https://contro1.com/agent-kit
```

This starter uses **Contro1 Integration Protocol v1**:

- canonical request object (`Contro1Request`) and response (`Contro1Response`)
- continuation mode: `decision` or `instruction`
- routing metadata: `department`, `required_role`, `priority`, `sla_minutes`
- case correlation via `correlation_id`

## Files

- `docs/openai-agents-sdk-connector.md`
- `skills/centcom-openai-agents.md`
- `.env.example`
- `requirements.txt`
- `examples/openai_agents_bridge.py`

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python examples/openai_agents_bridge.py
```

The bridge starts on `http://localhost:8081`.

## Smoke Test

Create a simulated interruption:

```bash
curl -X POST http://localhost:8081/simulate-interruption \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run-42",
    "call_id": "call-1",
    "tool_name": "cancel_order",
    "arguments": {"order_id": 42}
  }'
```

Expected behavior:

1. A Contro1 request is created (Decision mode).
2. Request appears in CENTCOM.
3. After operator action, callback reaches `/centcom-callback`.
4. Bridge prints mapped action (`approve` or `reject`) for OpenAI run resume.

## Human review vs audit log

Use a Contro1 request when a tool call needs a human before it executes. Use the same `correlation_id` across all requests and audit records in the same run to keep a complete case timeline.

```python
case_id = f"openai-{run_id}"

created = client.create_protocol_request({
    "title": "Approve tool call: issue_refund",
    "request_type": "decision",
    "source": {"integration": "openai-agents", "run_id": run_id},
    "continuation": {"mode": "decision", "callback_url": callback_url},
    "external_request_id": f"openai:{run_id}:{call_id}",
    "correlation_id": case_id,
})
```

Use `log_action` when the agent already acted within policy and you only need a searchable audit record:

```python
client.log_action(
    action="openai_agents.email_sent",
    summary="Sent approved follow-up email to customer c-8821",
    source={"integration": "openai-agents", "run_id": run_id},
    outcome="success",
    correlation_id=case_id,
)
```

When an operator answers and the bridge maps that answer back into the OpenAI run, log it in the same case:

```python
client.log_action(
    action="openai_agents.tool_approve",
    summary="Operator decision mapped to OpenAI Agents approval",
    source={"integration": "openai-agents", "workflow_id": call_id, "run_id": run_id},
    correlation_id=case_id,
    in_reply_to={"type": "request", "id": request_id},
)
```

## Control Map preview

For requests with required roles or multi-person approval, Control Map can preview routing readiness. Cache for 5-15 minutes.

```python
preview = client.post("/requests/control-map", {
    "approval_requirements": {"required_roles": ["manager"], "required_approvals": 2},
    "approval_policy": {
        "mode": "threshold",
        "required_approvals": 2,
        "separation_of_duties": True,
        "fail_closed_on_timeout": True,
    },
})

if not preview["satisfiable"]:
    print("Routing setup needed:", preview["warnings"])
```

Still create the approval request when the action needs review; the final signed decision is what resumes or blocks the tool.

## Production pattern: Agent Plugin

Wrap Contro1 calls behind a plugin to reduce per-interruption overhead:

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

## Security defaults

- Use env vars only.
- Verify callback signatures with `CENTCOM_WEBHOOK_SECRET`.
- Use deterministic idempotency keys: `openai:{run_id}:{call_id}`.

## Related repositories

- [`centcom`](https://github.com/contro1-hq/centcom)
- [`centcom-langgraph`](https://github.com/contro1-hq/centcom-langgraph)
- [`contro1-microsoft-agent-governance-toolkit-integration`](https://github.com/contro1-hq/contro1-microsoft-agent-governance-toolkit-integration)

## Governance readiness

For teams operating AI in regulated environments:
- [EU AI Act readiness guide](https://contro1.com/guides/eu-ai-act-readiness)
- [US AI Governance readiness guide](https://contro1.com/guides/us-ai-governance-readiness)
