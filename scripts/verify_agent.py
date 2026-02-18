"""Verify the deployed agent status and run a quick smoke test.

Usage:
    python scripts/verify_agent.py

Required environment variables:
    AZURE_AI_PROJECT_ENDPOINT  -- e.g. https://<account>.services.ai.azure.com/api/projects/<project>

Optional:
    AGENT_NAME     -- defaults to oncall-copilot
    AGENT_VERSION  -- defaults to latest

Ref: https://learn.microsoft.com/azure/ai-foundry/agents/how-to/manage-hosted-agent
"""
import json
import os
import subprocess
import sys

import requests

SMOKE_PROMPT = (
    "Severity 2 incident: Database connection pool exhausted on prod-db-01. "
    "Error rate spiking to 45%. Started 10 minutes ago. "
    "Affected services: checkout-api, payment-service."
)


def get_token(resource: str = "https://ai.azure.com") -> str:
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
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
    agent_version = os.environ.get("AGENT_VERSION", "latest")
    return endpoint, agent_name, agent_version


def main() -> None:
    endpoint, agent_name, agent_version = get_config()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1. Show agent info
    print("=== Agent Info ===")
    r = requests.get(
        f"{endpoint}/agents/{agent_name}?api-version=2025-05-15-preview",
        headers=headers, timeout=30,
    )
    if r.ok:
        info = r.json()
        print(f"  Name: {info.get('name')}")
        latest = info.get("versions", {}).get("latest", {})
        print(f"  Version: {latest.get('version')}")
        print(f"  Image: {latest.get('definition', {}).get('image')}")
        print(f"  Kind: {latest.get('definition', {}).get('kind')}")
    else:
        print(f"  Error: {r.status_code} {r.text[:300]}")

    # 2. Smoke test
    print("\n=== Smoke Test ===")
    payload = {
        "input": [{"role": "user", "content": SMOKE_PROMPT}],
        "agent": {"type": "agent_reference", "name": agent_name, "version": agent_version},
    }
    try:
        resp = requests.post(
            f"{endpoint}/openai/responses?api-version=2025-05-15-preview",
            json=payload, headers=headers, timeout=180,
        )
        print(f"  HTTP {resp.status_code}")
        if resp.ok:
            data = resp.json()
            print(f"  Status: {data.get('status')}")
            for item in data.get("output", []):
                for content in item.get("content", []):
                    text = content.get("text", "")
                    if text:
                        print(f"\n  Response (first 500 chars):\n  {text[:500]}")
                        break
        else:
            print(f"  Error: {resp.text[:500]}")
    except requests.exceptions.Timeout:
        print("  TIMEOUT after 180s – agent may still be starting up")
    except Exception as exc:
        print(f"  Error: {exc}")


if __name__ == "__main__":
    main()
