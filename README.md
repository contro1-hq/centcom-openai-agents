# centcom-openai-agents

OpenAI Agents starter kit for Contro1/CENTCOM approval routing.

## Protocol

This starter uses **Contro1 Integration Protocol v1**:

- canonical request object (`Contro1Request`)
- canonical response object (`Contro1Response`)
- continuation mode: `decision` or `instruction`
- routing metadata: `department`, `required_role`, `priority`, `sla_minutes`

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

## Security defaults

- Use env vars only.
- Verify callback signatures with `CENTCOM_WEBHOOK_SECRET`.
- Use deterministic idempotency keys: `openai:{run_id}:{call_id}`.

## Related repositories

- [`centcom`](https://github.com/contro1-hq/centcom)
- [`centcom-langgraph`](https://github.com/contro1-hq/centcom-langgraph)

## Human review vs audit log

Use a Contro1 request when a tool call needs a human before it executes:

```python
created = client.create_protocol_request({
    "title": "Approve tool call: issue_refund",
    "request_type": "decision",
    "source": {"integration": "openai-agents", "run_id": run_id},
    "continuation": {"mode": "decision", "callback_url": callback_url},
    "external_request_id": f"openai:{run_id}:{call_id}",
    "thread_id": thread_id,
})
```

Use `log_action` when the agent already acted within policy and you only need a searchable audit record:

```python
client.log_action(
    action="openai_agents.email_sent",
    summary="Sent approved follow-up email to customer c-8821",
    source={"integration": "openai-agents", "run_id": run_id},
    outcome="success",
    thread_id=thread_id,
)
```

## Threaded follow-up

When an operator answers and the bridge maps that answer back into the OpenAI run, log that mapping in the same thread:

```python
client.log_action(
    action="openai_agents.tool_approve",
    summary="Operator decision mapped to OpenAI Agents approval",
    source={"integration": "openai-agents", "workflow_id": call_id, "run_id": run_id},
    thread_id=thread_id,
    in_reply_to={"type": "request", "id": request_id},
)
```

See the full bridge example at https://github.com/contro1-hq/centcom-openai-agents/blob/main/examples/openai_agents_bridge.py.
