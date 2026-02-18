"""
Incident input envelope and structured output schemas for the On-Call Copilot.
Used for validation at the API boundary and for JSON-schema enforcement in prompts.
"""

from __future__ import annotations

INCIDENT_INPUT_SCHEMA: dict = {
    "type": "object",
    "required": ["incident_id", "title", "severity", "timeframe"],
    "properties": {
        "incident_id": {"type": "string"},
        "title": {"type": "string"},
        "severity": {"type": "string", "enum": ["SEV1", "SEV2", "SEV3", "SEV4"]},
        "timeframe": {
            "type": "object",
            "required": ["start"],
            "properties": {
                "start": {"type": "string", "format": "date-time"},
                "end": {"type": ["string", "null"], "format": "date-time"},
            },
        },
        "alerts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                },
            },
        },
        "logs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "lines": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "metrics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "window": {"type": "string"},
                    "values_summary": {"type": "string"},
                },
            },
        },
        "runbook_excerpt": {"type": "string"},
        "constraints": {
            "type": "object",
            "properties": {
                "max_time_minutes": {"type": "integer"},
                "environment": {"type": "string"},
                "region": {"type": "string"},
            },
        },
    },
}

TRIAGE_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "required": [
        "summary",
        "suspected_root_causes",
        "immediate_actions",
        "missing_information",
        "runbook_alignment",
        "comms",
        "post_incident_report",
        "telemetry",
    ],
    "properties": {
        "summary": {
            "type": "object",
            "required": ["what_happened", "current_status"],
            "properties": {
                "what_happened": {"type": "string"},
                "current_status": {"type": "string"},
            },
        },
        "suspected_root_causes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["hypothesis", "evidence", "confidence"],
                "properties": {
                    "hypothesis": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "immediate_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["step", "owner_role", "priority"],
                "properties": {
                    "step": {"type": "string"},
                    "owner_role": {"type": "string"},
                    "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                },
            },
        },
        "missing_information": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question", "why_it_matters"],
                "properties": {
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
            },
        },
        "runbook_alignment": {
            "type": "object",
            "required": ["matched_steps", "gaps"],
            "properties": {
                "matched_steps": {"type": "array", "items": {"type": "string"}},
                "gaps": {"type": "array", "items": {"type": "string"}},
            },
        },
        "comms": {
            "type": "object",
            "required": ["slack_update", "stakeholder_update"],
            "properties": {
                "slack_update": {"type": "string"},
                "stakeholder_update": {"type": "string"},
            },
        },
        "post_incident_report": {
            "type": "object",
            "required": ["timeline", "customer_impact", "prevention_actions"],
            "properties": {
                "timeline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "string"},
                            "event": {"type": "string"},
                        },
                    },
                },
                "customer_impact": {"type": "string"},
                "prevention_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "telemetry": {
            "type": "object",
            "required": ["correlation_id", "model_router_deployment"],
            "properties": {
                "correlation_id": {"type": "string"},
                "model_router_deployment": {"type": "string"},
                "selected_model_if_available": {"type": ["string", "null"]},
                "tokens_if_available": {
                    "type": ["object", "null"],
                    "properties": {
                        "prompt_tokens": {"type": "integer"},
                        "completion_tokens": {"type": "integer"},
                    },
                },
            },
        },
    },
}
