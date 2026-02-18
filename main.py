# Copyright (c) Microsoft. All rights reserved.
# On-Call Copilot – Multi-Agent Hosted Agent
#
# Uses ConcurrentBuilder to run 4 specialist agents in parallel.
# Pattern follows the official agents-in-workflow sample:
#   github.com/microsoft-foundry/foundry-samples/.../agents-in-workflow
#
# Ref: https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent

import sys
import os
print(f"[oncall-copilot] Starting... Python {sys.version}", flush=True)
print(f"[oncall-copilot] AZURE_OPENAI_ENDPOINT={os.environ.get('AZURE_OPENAI_ENDPOINT','<unset>')}", flush=True)
print(f"[oncall-copilot] AZURE_OPENAI_CHAT_DEPLOYMENT_NAME={os.environ.get('AZURE_OPENAI_CHAT_DEPLOYMENT_NAME','<unset>')}", flush=True)

from agent_framework import ConcurrentBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from app.agents.triage import TRIAGE_INSTRUCTIONS
from app.agents.comms import COMMS_INSTRUCTIONS
from app.agents.pir import PIR_INSTRUCTIONS
from app.agents.summary import SUMMARY_INSTRUCTIONS

# Create a token provider that refreshes tokens automatically for long-running servers.
# This avoids 401 errors when the initial token expires (typically after 1 hour).
_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)


def create_workflow_builder():
    """Create 4 specialist agents and wire them into a ConcurrentBuilder."""

    # SDK reads AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME from env vars
    triage = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
        instructions=TRIAGE_INSTRUCTIONS,
        name="triage-agent",
    )
    summary = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
        instructions=SUMMARY_INSTRUCTIONS,
        name="summary-agent",
    )
    comms = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
        instructions=COMMS_INSTRUCTIONS,
        name="comms-agent",
    )
    pir = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
        instructions=PIR_INSTRUCTIONS,
        name="pir-agent",
    )

    workflow_builder = ConcurrentBuilder().participants([triage, summary, comms, pir])
    return workflow_builder


def main():
    print("[oncall-copilot] Building workflow...", flush=True)
    builder = create_workflow_builder()
    print("[oncall-copilot] Starting server on port 8088...", flush=True)
    from_agent_framework(builder.build).run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[oncall-copilot] FATAL: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
