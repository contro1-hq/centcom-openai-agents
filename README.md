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
