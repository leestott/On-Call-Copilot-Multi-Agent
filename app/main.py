"""
On-Call Copilot – FastAPI server (legacy / mock mode).

This module provides:
  - MOCK_MODE local testing without Azure credentials
  - Legacy single-agent FastAPI endpoint for backward compatibility

For the multi-agent hosted deployment, use the root main.py which runs
4 specialist agents via Microsoft Agent Framework + ConcurrentBuilder.

Runs on port 8088:
  POST /responses   – Foundry Responses API surface
  GET  /health      – liveness probe
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import jsonschema
import uvicorn
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.mock_router import MockModelResponse, get_mock_response
from app.prompting import SYSTEM_INSTRUCTION, build_user_message
from app.schemas import INCIDENT_INPUT_SCHEMA, TRIAGE_OUTPUT_SCHEMA
from app.telemetry import configure_telemetry, get_tracer, new_correlation_id

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
configure_telemetry()
logger = logging.getLogger("oncall-copilot")
tracer = get_tracer()

app = FastAPI(title="On-Call Copilot", version="0.1.0")

# ---------------------------------------------------------------------------
# Configuration (env vars)
# ---------------------------------------------------------------------------
MODEL_ROUTER_DEPLOYMENT = os.environ.get("MODEL_ROUTER_DEPLOYMENT", "model-router")
AZURE_AI_PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
MOCK_MODE = os.environ.get("MOCK_MODE", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Azure AI Projects client (lazy init)
# Foundry Hosted Agents v2 uses endpoint-based init (azure-ai-projects>=2.0.0b3)
# Ref: https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent
# ---------------------------------------------------------------------------
_client: AIProjectClient | None = None


def _get_client() -> AIProjectClient:
    global _client
    if _client is None:
        if not AZURE_AI_PROJECT_ENDPOINT:
            raise RuntimeError(
                "AZURE_AI_PROJECT_ENDPOINT env var is required. "
                "Set it to your Foundry project endpoint URL."
            )
        _client = AIProjectClient(
            endpoint=AZURE_AI_PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SECRET_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key|connection[_-]?string)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def _redact_secrets(text: str) -> str:
    """Replace anything that looks like a credential value with [REDACTED]."""
    return _SECRET_PATTERN.sub(lambda m: m.group().split(":")[0].split("=")[0] + ": [REDACTED]", text)


def _validate_input(payload: dict) -> None:
    jsonschema.validate(instance=payload, schema=INCIDENT_INPUT_SCHEMA)


def _validate_output(payload: dict) -> None:
    jsonschema.validate(instance=payload, schema=TRIAGE_OUTPUT_SCHEMA)


def _extract_json(text: str) -> dict:
    """Parse JSON from the model response, stripping markdown fences if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# POST /responses – Foundry Responses API surface
# ---------------------------------------------------------------------------
@app.post("/responses")
async def handle_responses(request: Request) -> JSONResponse:
    correlation_id = new_correlation_id()

    with tracer.start_as_current_span("handle_responses", attributes={"correlation_id": correlation_id}) as span:
        # --- Parse & validate input ---
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        # Support both direct incident envelope and wrapped {"incident": {...}} form
        incident: dict = body.get("incident", body)

        with tracer.start_as_current_span("validate_input"):
            try:
                _validate_input(incident)
            except jsonschema.ValidationError as exc:
                logger.warning("Input validation failed: %s", exc.message)
                raise HTTPException(status_code=422, detail=f"Input validation: {exc.message}")

        logger.info(
            '{"event":"request_received","correlation_id":"%s","incident_id":"%s","severity":"%s"}',
            correlation_id,
            incident.get("incident_id"),
            incident.get("severity"),
        )

        # --- Build prompt ---
        user_message = _redact_secrets(build_user_message(incident))

        # --- Call Foundry Responses API (or mock) ---
        selected_model: str | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None

        with tracer.start_as_current_span(
            "call_model_router",
            attributes={
                "model_router_deployment": MODEL_ROUTER_DEPLOYMENT,
                "correlation_id": correlation_id,
                "mock_mode": MOCK_MODE,
            },
        ):
            if MOCK_MODE:
                # --- Mock path: return golden response without calling Azure ---
                mock_data = get_mock_response(incident.get("incident_id", ""))
                if mock_data is None:
                    raise HTTPException(
                        status_code=501,
                        detail=f"No mock golden output for incident_id={incident.get('incident_id')}",
                    )
                raw_text = json.dumps(mock_data)
                selected_model = "mock-model-router"
                prompt_tokens = len(user_message) // 4
                completion_tokens = len(raw_text) // 4
                logger.info(
                    '{"event":"mock_response","correlation_id":"%s","incident_id":"%s"}',
                    correlation_id,
                    incident.get("incident_id"),
                )
            else:
                # --- Live path: call Foundry Responses API via Azure AI Projects ---
                try:
                    client = _get_client()
                    response = client.agents.create_run(
                        model=MODEL_ROUTER_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": SYSTEM_INSTRUCTION},
                            {"role": "user", "content": user_message},
                        ],
                        response_format={"type": "json_object"},
                    )

                    raw_text = response.choices[0].message.content
                    if hasattr(response, "usage") and response.usage:
                        prompt_tokens = getattr(response.usage, "prompt_tokens", None)
                        completion_tokens = getattr(response.usage, "completion_tokens", None)
                    if hasattr(response, "model"):
                        selected_model = response.model

                except AttributeError:
                    inference = client.inference
                    response = inference.complete(
                        model=MODEL_ROUTER_DEPLOYMENT,
                        messages=[
                            {"role": "system", "content": SYSTEM_INSTRUCTION},
                            {"role": "user", "content": user_message},
                        ],
                        response_format={"type": "json_object"},
                    )
                    raw_text = response.choices[0].message.content
                    if hasattr(response, "usage") and response.usage:
                        prompt_tokens = getattr(response.usage, "prompt_tokens", None)
                        completion_tokens = getattr(response.usage, "completion_tokens", None)
                    if hasattr(response, "model"):
                        selected_model = response.model

                except Exception as exc:
                    logger.error(
                        '{"event":"model_call_failed","correlation_id":"%s","error":"%s"}',
                        correlation_id,
                        str(exc),
                    )
                    raise HTTPException(status_code=502, detail="Model Router call failed")

        logger.info(
            '{"event":"model_response_received","correlation_id":"%s","selected_model":"%s","prompt_tokens":%s,"completion_tokens":%s}',
            correlation_id,
            selected_model,
            prompt_tokens,
            completion_tokens,
        )

        # --- Parse & validate output ---
        with tracer.start_as_current_span("validate_output"):
            try:
                result = _extract_json(raw_text)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    '{"event":"json_parse_failed","correlation_id":"%s","raw_head":"%s"}',
                    correlation_id,
                    raw_text[:200],
                )
                raise HTTPException(status_code=502, detail="Model did not return valid JSON")

            # Inject telemetry block (overwrite whatever the model returned)
            result["telemetry"] = {
                "correlation_id": correlation_id,
                "model_router_deployment": MODEL_ROUTER_DEPLOYMENT,
                "selected_model_if_available": selected_model,
                "tokens_if_available": (
                    {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
                    if prompt_tokens is not None
                    else None
                ),
            }

            try:
                _validate_output(result)
            except jsonschema.ValidationError as exc:
                logger.warning(
                    '{"event":"output_validation_failed","correlation_id":"%s","error":"%s"}',
                    correlation_id,
                    exc.message,
                )
                # Return partial result with a warning header rather than failing completely
                return JSONResponse(
                    content=result,
                    status_code=200,
                    headers={"X-Schema-Valid": "false"},
                )

        span.set_attribute("output.schema_valid", True)
        logger.info('{"event":"request_complete","correlation_id":"%s"}', correlation_id)

        return JSONResponse(content=result, headers={"X-Correlation-ID": correlation_id})


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Local dev server
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8088, reload=True)
