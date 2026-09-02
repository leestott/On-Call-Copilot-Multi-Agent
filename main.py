# Copyright (c) Microsoft. All rights reserved.
# On-Call Copilot - Multi-Agent Hosted Agent

import os
import sys
from pathlib import Path

from agent_framework import Agent
from agent_framework_foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework_orchestrations import ConcurrentBuilder
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from app.agents.comms import COMMS_INSTRUCTIONS
from app.agents.pir import PIR_INSTRUCTIONS
from app.agents.summary import SUMMARY_INSTRUCTIONS
from app.agents.triage import TRIAGE_INSTRUCTIONS

load_dotenv(Path(__file__).resolve().parent / ".env")


def _presence(name: str) -> str:
    return "set" if os.environ.get(name) else "unset"


print(f"[oncall-copilot] Starting... Python {sys.version}", flush=True)
print(f"[oncall-copilot] AZURE_AI_PROJECT_ENDPOINT={_presence('AZURE_AI_PROJECT_ENDPOINT')}", flush=True)
print(f"[oncall-copilot] AZURE_MODEL_PROJECT_ENDPOINT={_presence('AZURE_MODEL_PROJECT_ENDPOINT')}", flush=True)
print(f"[oncall-copilot] AZURE_OPENAI_CHAT_DEPLOYMENT_NAME={_presence('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME')}", flush=True)

_credential = DefaultAzureCredential()


def create_workflow():
    """Create 4 specialist agents and wire them into a concurrent workflow."""

    project_endpoint = os.environ.get("AZURE_MODEL_PROJECT_ENDPOINT") or os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "model-router")
    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=_credential,
    )

    triage = Agent(
        client=chat_client,
        instructions=TRIAGE_INSTRUCTIONS,
        name="triage-agent",
    )
    summary = Agent(
        client=chat_client,
        instructions=SUMMARY_INSTRUCTIONS,
        name="summary-agent",
    )
    comms = Agent(
        client=chat_client,
        instructions=COMMS_INSTRUCTIONS,
        name="comms-agent",
    )
    pir = Agent(
        client=chat_client,
        instructions=PIR_INSTRUCTIONS,
        name="pir-agent",
    )

    return ConcurrentBuilder(
        participants=[triage, summary, comms, pir],
    ).build()


def main():
    print("[oncall-copilot] Building workflow...", flush=True)
    workflow_agent = create_workflow().as_agent(
        name="oncall-copilot",
        description="Runs triage, summary, comms, and PIR agents for incident response.",
    )
    print("[oncall-copilot] Starting server on port 8088...", flush=True)
    ResponsesHostServer(workflow_agent).run(port=8088)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[oncall-copilot] FATAL: {e}", flush=True)
        import traceback

        traceback.print_exc()
        sys.exit(1)
