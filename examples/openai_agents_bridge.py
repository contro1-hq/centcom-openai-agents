"""Local bridge template for OpenAI Agents interruptions -> Contro1 approvals.

This starter is intentionally minimal and framework-agnostic:
- /simulate-interruption emulates an OpenAI Agents interruption event
- /centcom-callback receives signed callback payloads from Contro1
"""

from __future__ import annotations

import json
import os
from typing import Any

from centcom import CentcomClient, verify_webhook
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)

CENTCOM_API_KEY = os.environ["CENTCOM_API_KEY"]
CENTCOM_BASE_URL = os.environ.get("CENTCOM_BASE_URL", "https://contro1.com/api/centcom/v1")
CENTCOM_WEBHOOK_SECRET = os.environ["CENTCOM_WEBHOOK_SECRET"]
PORT = int(os.environ.get("BRIDGE_PORT", "8081"))

client = CentcomClient(api_key=CENTCOM_API_KEY, base_url=CENTCOM_BASE_URL)

# run_id:call_id -> request_id
PENDING: dict[str, str] = {}


@app.post("/simulate-interruption")
def simulate_interruption():
    payload = request.get_json(force=True, silent=False) or {}
    run_id = str(payload.get("run_id", "")).strip()
    call_id = str(payload.get("call_id", "")).strip()
    tool_name = str(payload.get("tool_name", "tool_call")).strip()
    arguments: Any = payload.get("arguments", {})

    if not run_id or not call_id:
        return jsonify({"error": "run_id and call_id are required"}), 400

    protocol_request = {
        "title": f"Approve tool call: {tool_name}",
        "request_type": "decision",
        "source": {
            "integration": "openai-agents",
            "framework": "openai-agents-sdk",
            "run_id": run_id,
        },
        "routing": {
            "required_role": "manager",
            "priority": "normal",
        },
        "context": {
            "tool_name": tool_name,
            "tool_input": arguments,
            "summary": "OpenAI Agents interruption requires operator approval",
        },
        "continuation": {
            "mode": "decision",
            "callback_url": f"http://localhost:{PORT}/centcom-callback",
        },
        "external_request_id": f"openai:{run_id}:{call_id}",
        "metadata": {
            "run_id": run_id,
            "call_id": call_id,
        },
    }

    created = client.create_protocol_request(protocol_request)
    key = f"{run_id}:{call_id}"
    PENDING[key] = created["id"]

    return jsonify(
        {
            "request_id": created["id"],
            "pending_key": key,
            "message": "Interruption mapped to Contro1 request",
        }
    )


@app.post("/centcom-callback")
def centcom_callback():
    raw_body = request.get_data(as_text=True)
    signature = request.headers.get("X-CentCom-Signature", "")
    timestamp = request.headers.get("X-CentCom-Timestamp", "")

    if not verify_webhook(raw_body, signature, timestamp, CENTCOM_WEBHOOK_SECRET):
        return jsonify({"error": "invalid signature"}), 401

    payload = json.loads(raw_body)
    response = payload.get("response") or {}
    approved = bool(response.get("approved")) if isinstance(response, dict) else False
    action = "approve" if approved else "reject"

    # Replace this with actual OpenAI Agents run-state resume calls:
    # state.approve(interruption) / state.reject(interruption, ...)
    app.logger.info("Mapped callback to OpenAI action=%s payload=%s", action, payload)

    return jsonify({"status": "ok", "mapped_action": action})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
