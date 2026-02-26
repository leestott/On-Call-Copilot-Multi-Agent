"""Invoke the On-Call Copilot hosted agent via the Foundry Responses API.

Usage:
    python scripts/invoke.py                         # use default incident prompt
    python scripts/invoke.py --prompt "custom text"  # use a custom prompt
    python scripts/invoke.py --demo 1                # send demo JSON (1-3)
    python scripts/invoke.py --scenario 1            # send scenario JSON (1-5)
    python scripts/invoke.py --demo 1 --key comms              # show only comms output
    python scripts/invoke.py --demo 1 --key post_incident_report
    python scripts/invoke.py --demo 1 --key suspected_root_causes
    python scripts/invoke.py --demo 1 --key summary

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
DEMOS_DIR = ROOT / "scripts" / "demos"

DEFAULT_PROMPT = (
    "ALERT: CPU usage at 95% on prod-api-01 for 10 minutes. "
    "P99 latency spiked to 8s. "
    "Service: checkout-api. "
    "Environment: production. "
    "Start time: 2025-06-20T14:32:00Z."
)


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


def invoke(endpoint: str, agent_name: str, agent_version: str, content: str,
           filter_key: str | None = None) -> None:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    agent_spec: dict = {"type": "agent_reference", "name": agent_name}
    if agent_version:
        agent_spec["version"] = agent_version

    # Prefix raw JSON with an instruction so the Responses API doesn't reject
    # minimal payloads with "ID cannot be null or empty".
    user_message = content
    try:
        json.loads(content)
        user_message = (
            "Analyze the following incident data and provide triage, "
            "summary, communications, and a post-incident report:\n\n"
            + content
        )
    except (json.JSONDecodeError, ValueError):
        pass

    body = {
        "input": [{"role": "user", "content": user_message}],
        "agent": agent_spec,
    }

    version_label = agent_version if agent_version else "latest"
    print(f"Endpoint : {endpoint}")
    print(f"Agent    : {agent_name}:{version_label}")
    print(f"Prompt   : {content[:120]}{'...' if len(content) > 120 else ''}")
    print("Invoking agent...")

    t0 = time.time()
    r = requests.post(
        f"{endpoint}/openai/responses?api-version=2025-05-15-preview",
        headers=headers, json=body, timeout=180,
    )
    elapsed = time.time() - t0

    print(f"\nHTTP {r.status_code} ({elapsed:.1f}s)")
    d = r.json()

    if d.get("error"):
        print("ERROR:", json.dumps(d["error"], indent=2))
        sys.exit(1)

    print(f"Status  : {d.get('status')}\n")

    if filter_key == "__debug__":
        print(json.dumps(d, indent=2)[:8000])
        return

    # The agent returns all 4 agent responses concatenated in a single text blob.
    # Use raw_decode to walk through and extract every JSON object.
    merged: dict = {}
    decoder = json.JSONDecoder()
    for o in d.get("output", []):
        for c in o.get("content", []):
            text = c.get("text", "").strip()
            pos = 0
            while pos < len(text):
                # Skip whitespace between JSON objects
                while pos < len(text) and text[pos] in " \t\n\r":
                    pos += 1
                if pos >= len(text):
                    break
                try:
                    obj, end_pos = decoder.raw_decode(text, pos)
                    if isinstance(obj, dict):
                        merged.update(obj)
                    pos += end_pos - pos
                except json.JSONDecodeError:
                    break

    if not merged:
        print("(no structured output returned)")
        return

    LABELS = {
        "suspected_root_causes": "TRIAGE — Root Causes",
        "immediate_actions":     "TRIAGE — Immediate Actions",
        "missing_information":   "TRIAGE — Missing Information",
        "runbook_alignment":     "TRIAGE — Runbook Alignment",
        "summary":               "SUMMARY",
        "comms":                 "COMMS",
        "post_incident_report":  "POST-INCIDENT REPORT",
    }

    if filter_key:
        if filter_key not in merged:
            available = ", ".join(merged.keys())
            print(f"ERROR: key '{filter_key}' not found. Available: {available}")
            sys.exit(1)
        label = LABELS.get(filter_key, filter_key.upper())
        print(f"{'='*60}")
        print(f"  {label}")
        print(f"{'='*60}")
        print(json.dumps(merged[filter_key], indent=2))
    else:
        for key in LABELS:
            if key not in merged:
                continue
            label = LABELS[key]
            print(f"{'='*60}")
            print(f"  {label}")
            print(f"{'='*60}")
            print(json.dumps(merged[key], indent=2))
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke the On-Call Copilot agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prompt", help="Custom plain-text prompt")
    group.add_argument("--demo", type=int, metavar="N",
                       help="Send demo JSON payload (1-3)")
    group.add_argument("--scenario", type=int, metavar="N",
                       help="Send structured scenario JSON (1-5)")
    parser.add_argument(
        "--key", metavar="KEY",
        help="Show only this top-level key from the response "
             "(e.g. comms, post_incident_report, suspected_root_causes, summary)"
    )
    args = parser.parse_args()

    endpoint, agent_name, agent_version = get_config()

    if args.demo:
        files = sorted(DEMOS_DIR.glob(f"demo_{args.demo}_*.json"))
        if not files:
            print(f"ERROR: No demo file matching demo_{args.demo}_*.json in {DEMOS_DIR}")
            sys.exit(1)
        content = files[0].read_text(encoding="utf-8")
    elif args.scenario:
        files = sorted(SCENARIOS_DIR.glob(f"scenario_{args.scenario}_*.json"))
        if not files:
            print(f"ERROR: No scenario file matching scenario_{args.scenario}_*.json")
            sys.exit(1)
        content = files[0].read_text(encoding="utf-8")
    else:
        content = args.prompt or DEFAULT_PROMPT

    invoke(endpoint, agent_name, agent_version, content, filter_key=args.key)


if __name__ == "__main__":
    main()
