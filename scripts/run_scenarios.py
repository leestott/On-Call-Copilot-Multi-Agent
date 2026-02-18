"""Run all scenario JSON files against the live Foundry-hosted agent and print results.

Unlike validate.py (which uses MOCK_MODE / local server), this script calls the
deployed Foundry Responses API directly — useful for smoke-testing a live deployment.

Usage:
    python scripts/run_scenarios.py           # run all scenarios
    python scripts/run_scenarios.py --scenario 2   # run a single scenario
    python scripts/run_scenarios.py --list    # list available scenarios

Required environment variables:
    AZURE_AI_PROJECT_ENDPOINT  – e.g. https://<account>.services.ai.azure.com/api/projects/<project>

Optional:
    AGENT_NAME     – defaults to oncall-copilot
    AGENT_VERSION  – defaults to latest
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "scripts" / "scenarios"

EXPECTED_KEYS = {
    "suspected_root_causes",
    "immediate_actions",
    "missing_information",
    "runbook_alignment",
    "summary",
    "comms",
    "post_incident_report",
}


def get_token() -> str:
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://ai.azure.com",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True,
    )
    if result.returncode != 0:
        print(f"ERROR: az login required: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def get_config() -> tuple[str, str, str]:
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        print("ERROR: AZURE_AI_PROJECT_ENDPOINT env var is required.")
        print("  e.g. https://<account>.services.ai.azure.com/api/projects/<project>")
        sys.exit(1)
    agent_name = os.environ.get("AGENT_NAME", "oncall-copilot")
    agent_version = os.environ.get("AGENT_VERSION", "")
    return endpoint, agent_name, agent_version


def discover_scenarios(only: int | None = None) -> list[Path]:
    files = sorted(SCENARIOS_DIR.glob("scenario_*.json"))
    if only is not None:
        files = [f for f in files if f"scenario_{only}" in f.name]
    if not files:
        print(f"ERROR: No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)
    return files


def validate_output(text: str) -> list[str]:
    """Basic structural checks on the agent's response text."""
    issues: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        issues.append("Response is not valid JSON")
        return issues

    present = {k for k in EXPECTED_KEYS if k in data}
    missing = EXPECTED_KEYS - present
    if missing:
        issues.append(f"Missing keys: {sorted(missing)}")

    if "suspected_root_causes" in data:
        for i, rc in enumerate(data["suspected_root_causes"]):
            conf = rc.get("confidence", -1)
            if not (0 <= conf <= 1):
                issues.append(f"root_cause[{i}].confidence={conf!r} out of [0,1]")

    if "immediate_actions" in data:
        valid_p = {"P0", "P1", "P2", "P3"}
        for i, act in enumerate(data["immediate_actions"]):
            if act.get("priority") not in valid_p:
                issues.append(f"action[{i}].priority={act.get('priority')!r} invalid")

    return issues


def run_scenario(
    scenario_file: Path,
    endpoint: str,
    agent_name: str,
    agent_version: str,
) -> tuple[bool, str, float]:
    """Run one scenario. Returns (passed, message, elapsed_seconds)."""
    payload = json.loads(scenario_file.read_text(encoding="utf-8"))
    incident_id = payload.get("incident_id", scenario_file.stem)
    content = json.dumps(payload)

    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    agent_spec: dict = {"type": "agent_reference", "name": agent_name}
    if agent_version:
        agent_spec["version"] = agent_version
    body = {
        "input": [{"role": "user", "content": content}],
        "agent": agent_spec,
    }

    t0 = time.time()
    try:
        r = requests.post(
            f"{endpoint}/openai/responses?api-version=2025-05-15-preview",
            headers=headers, json=body, timeout=180,
        )
        elapsed = time.time() - t0
    except requests.exceptions.Timeout:
        elapsed = time.time() - t0
        return False, f"{incident_id}: TIMEOUT after {elapsed:.0f}s", elapsed
    except Exception as exc:
        elapsed = time.time() - t0
        return False, f"{incident_id}: Exception – {exc}", elapsed

    if r.status_code != 200:
        return False, f"{incident_id}: HTTP {r.status_code} – {r.text[:200]}", elapsed

    d = r.json()
    if d.get("error"):
        msg = d["error"].get("message", "unknown error")
        return False, f"{incident_id}: API error – {msg}", elapsed

    if d.get("status") != "completed":
        return False, f"{incident_id}: status={d.get('status')!r}", elapsed

    # Collect all text content
    all_text = ""
    for o in d.get("output", []):
        for c in o.get("content", []):
            all_text += c.get("text", "")

    issues = validate_output(all_text)
    if issues:
        return False, f"{incident_id}: FAIL – {'; '.join(issues)}", elapsed

    return True, f"{incident_id}: PASS", elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scenario tests against the live agent")
    parser.add_argument("--scenario", type=int, metavar="N", help="Run only scenario N")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    args = parser.parse_args()

    if args.list:
        files = sorted(SCENARIOS_DIR.glob("scenario_*.json"))
        print("Available scenarios:")
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            print(f"  {f.stem}: [{data.get('severity','?')}] {data.get('title','?')}")
        return

    endpoint, agent_name, agent_version = get_config()
    scenarios = discover_scenarios(args.scenario)

    version_label = agent_version if agent_version else "latest"
    print(f"Endpoint : {endpoint}")
    print(f"Agent    : {agent_name}:{version_label}")
    print(f"Scenarios: {len(scenarios)}")
    print("-" * 60)

    passed = failed = 0
    for sf in scenarios:
        print(f"  Running {sf.name} ...", end="", flush=True)
        ok, msg, elapsed = run_scenario(sf, endpoint, agent_name, agent_version)
        status = "PASS" if ok else "FAIL"
        print(f"\r  {status}  {msg}  ({elapsed:.1f}s)")
        if ok:
            passed += 1
        else:
            failed += 1

    print("-" * 60)
    print(f"\nResults: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    else:
        print("All scenarios passed!")


if __name__ == "__main__":
    main()
