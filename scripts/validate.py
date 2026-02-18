"""
validate.py – End-to-end local validation of the On-Call Copilot in MOCK_MODE.

Usage:
    python scripts/validate.py          # run all scenarios
    python scripts/validate.py --scenario 1  # run a specific scenario

Starts the FastAPI server with MOCK_MODE=true, sends each scenario payload to
POST /responses, and validates the response against the triage output schema.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
import requests

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "scripts" / "scenarios"
SCHEMA_FILE = ROOT / "app" / "schemas.py"

BASE_URL = "http://localhost:8088"
STARTUP_TIMEOUT = 15  # seconds

# ── Load output schema directly from the module ──────────────────────────────
sys.path.insert(0, str(ROOT))
from app.schemas import TRIAGE_OUTPUT_SCHEMA  # noqa: E402


def discover_scenarios(only: int | None = None) -> list[Path]:
    """Return sorted list of scenario JSON files."""
    files = sorted(SCENARIOS_DIR.glob("scenario_*.json"))
    if only is not None:
        files = [f for f in files if f"scenario_{only}" in f.name]
    if not files:
        print(f"ERROR: No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)
    return files


def wait_for_server(url: str, timeout: int) -> bool:
    """Poll /health until the server is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    return False


def validate_response(data: dict, scenario_name: str) -> list[str]:
    """Validate response against schema and run content checks. Returns errors."""
    errors: list[str] = []

    # 1. JSON Schema validation
    try:
        jsonschema.validate(instance=data, schema=TRIAGE_OUTPUT_SCHEMA)
    except jsonschema.ValidationError as exc:
        errors.append(f"Schema validation: {exc.message}")

    # 2. Content checks
    if "summary" in data:
        if not data["summary"].get("what_happened"):
            errors.append("summary.what_happened is empty")
        if not data["summary"].get("current_status"):
            errors.append("summary.current_status is empty")

    if "suspected_root_causes" in data:
        for i, rc in enumerate(data["suspected_root_causes"]):
            conf = rc.get("confidence", -1)
            if not (0 <= conf <= 1):
                errors.append(f"root_cause[{i}].confidence={conf} out of [0,1]")
            if not rc.get("evidence"):
                errors.append(f"root_cause[{i}].evidence is empty")

    if "immediate_actions" in data:
        valid_priorities = {"P0", "P1", "P2", "P3"}
        for i, act in enumerate(data["immediate_actions"]):
            if act.get("priority") not in valid_priorities:
                errors.append(f"action[{i}].priority={act.get('priority')} invalid")

    if "telemetry" in data:
        tel = data["telemetry"]
        if not tel.get("correlation_id"):
            errors.append("telemetry.correlation_id is missing")
        if not tel.get("model_router_deployment"):
            errors.append("telemetry.model_router_deployment is missing")

    # 3. Schema-valid header check
    if "X-Schema-Valid" in data:
        errors.append("Response included X-Schema-Valid=false header")

    return errors


def run_scenario(scenario_file: Path) -> tuple[bool, str]:
    """Send a scenario to the server and validate. Returns (passed, message)."""
    payload = json.loads(scenario_file.read_text(encoding="utf-8"))
    incident_id = payload.get("incident_id", "unknown")
    name = scenario_file.stem

    try:
        r = requests.post(
            f"{BASE_URL}/responses",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except requests.ConnectionError:
        return False, f"{name}: Connection refused – is the server running?"

    if r.status_code != 200:
        return False, f"{name}: HTTP {r.status_code} – {r.text[:200]}"

    try:
        data = r.json()
    except json.JSONDecodeError:
        return False, f"{name}: Response is not valid JSON"

    # Check X-Schema-Valid header
    schema_valid_header = r.headers.get("X-Schema-Valid")

    errors = validate_response(data, name)
    if schema_valid_header == "false":
        errors.append("Server returned X-Schema-Valid: false header")

    if errors:
        bullet_errors = "\n    ".join(errors)
        return False, f"{name} (INC {incident_id}): FAIL\n    {bullet_errors}"

    return True, f"{name} (INC {incident_id}): PASS"


def main():
    parser = argparse.ArgumentParser(description="Validate On-Call Copilot locally")
    parser.add_argument("--scenario", type=int, help="Run only scenario N")
    parser.add_argument("--no-server", action="store_true", help="Skip starting the server (assume it is running)")
    args = parser.parse_args()

    scenarios = discover_scenarios(args.scenario)

    server_proc = None
    if not args.no_server:
        print("Starting server with MOCK_MODE=true ...")
        env = os.environ.copy()
        env["MOCK_MODE"] = "true"
        env["MODEL_ROUTER_DEPLOYMENT"] = "model-router"
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8088"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not wait_for_server(BASE_URL, STARTUP_TIMEOUT):
            server_proc.terminate()
            print("ERROR: Server failed to start within timeout")
            sys.exit(1)
        print("Server is ready.\n")

    try:
        passed = 0
        failed = 0
        results: list[str] = []

        print(f"Running {len(scenarios)} scenario(s) ...\n")
        print("-" * 60)

        for sf in scenarios:
            ok, msg = run_scenario(sf)
            results.append(msg)
            if ok:
                passed += 1
                print(f"  PASS  {msg}")
            else:
                failed += 1
                print(f"  FAIL  {msg}")

        print("-" * 60)
        print(f"\nResults: {passed} passed, {failed} failed, {passed + failed} total")

        if failed > 0:
            sys.exit(1)
        else:
            print("\nAll scenarios validated successfully!")

    finally:
        if server_proc is not None:
            server_proc.terminate()
            server_proc.wait(timeout=5)
            print("\nServer stopped.")


if __name__ == "__main__":
    main()
