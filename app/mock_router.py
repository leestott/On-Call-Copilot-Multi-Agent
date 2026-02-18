"""
Mock Model Router – returns deterministic golden responses for local validation.

When MOCK_MODE=true, main.py uses this instead of calling Azure.
Each scenario maps incident_id -> pre-built triage JSON that passes schema validation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("oncall-copilot.mock")

# Load all golden responses from scripts/golden_outputs/
_GOLDEN_DIR = Path(__file__).resolve().parent.parent / "scripts" / "golden_outputs"
_GOLDEN_RESPONSES: dict[str, dict] = {}


def _load_golden_responses() -> None:
    if _GOLDEN_RESPONSES:
        return
    if not _GOLDEN_DIR.exists():
        logger.warning("Golden output directory not found: %s", _GOLDEN_DIR)
        return
    for f in sorted(_GOLDEN_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            iid = data.get("_incident_id", f.stem)
            _GOLDEN_RESPONSES[iid] = data
            logger.info("Loaded golden response for %s from %s", iid, f.name)
        except Exception as exc:
            logger.warning("Failed to load %s: %s", f.name, exc)


def get_mock_response(incident_id: str) -> dict | None:
    """Return a golden triage response for the given incident_id, or None."""
    _load_golden_responses()
    resp = _GOLDEN_RESPONSES.get(incident_id)
    if resp is None:
        # Fall back to the generic catch-all if present
        resp = _GOLDEN_RESPONSES.get("_default")
    if resp is not None:
        # Strip the internal _incident_id key before returning
        resp = {k: v for k, v in resp.items() if not k.startswith("_")}
    return resp


class MockModelResponse:
    """Mimics the shape of a chat completion response for the mock path."""

    def __init__(self, content: str, model: str = "mock-model-router"):
        self.content = content
        self.model = model
        self.usage = type("Usage", (), {
            "prompt_tokens": len(content) // 4,
            "completion_tokens": len(content) // 4,
        })()

    class _Choice:
        def __init__(self, content: str):
            self.message = type("Message", (), {"content": content})()

    @property
    def choices(self):
        return [self._Choice(self.content)]
