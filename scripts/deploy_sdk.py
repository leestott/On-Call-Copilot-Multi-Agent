"""
deploy_sdk.py – Deploy the On-Call Copilot as a Foundry Hosted Agent using the Python SDK.

Ref: https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent

Prerequisites:
  1. azure-ai-projects >= 2.0.0b3
  2. Container image pushed to Azure Container Registry
  3. Project managed identity has Container Registry Repository Reader on ACR
  4. Account-level capability host with enablePublicHostingEnvironment=true

Usage:
    # Set required environment variables
    export AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
    export ACR_IMAGE="myregistry.azurecr.io/oncall-copilot:v1"
    export MODEL_ROUTER_DEPLOYMENT="model-router"

    python scripts/deploy_sdk.py
    python scripts/deploy_sdk.py --delete          # clean up
"""

from __future__ import annotations

import argparse
import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentProtocol,
    ImageBasedHostedAgentDefinition,
    ProtocolVersionRecord,
)
from azure.identity import DefaultAzureCredential

AGENT_NAME = "oncall-copilot"


def get_config() -> dict:
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
    openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    image = os.environ.get("ACR_IMAGE", "")
    model = os.environ.get("MODEL_ROUTER_DEPLOYMENT", "model-router")

    if not endpoint:
        print("ERROR: AZURE_AI_PROJECT_ENDPOINT env var is required.")
        sys.exit(1)
    if not image:
        print("ERROR: ACR_IMAGE env var is required (e.g. myregistry.azurecr.io/oncall-copilot:v1).")
        sys.exit(1)
    if not openai_endpoint:
        print("ERROR: AZURE_OPENAI_ENDPOINT env var is required.")
        sys.exit(1)

    return {"endpoint": endpoint, "openai_endpoint": openai_endpoint, "image": image, "model": model}


def deploy(cfg: dict) -> None:
    """Create a new hosted agent version using the Python SDK."""
    client = AIProjectClient(
        endpoint=cfg["endpoint"],
        credential=DefaultAzureCredential(),
    )

    print(f"Creating hosted agent version: {AGENT_NAME}")
    print(f"  Image:    {cfg['image']}")
    print(f"  Endpoint: {cfg['endpoint']}")
    print(f"  Model:    {cfg['model']}")
    print()

    definition = ImageBasedHostedAgentDefinition(
        container_protocol_versions=[
            ProtocolVersionRecord(
                protocol=AgentProtocol.RESPONSES,
                version="v1",
            )
        ],
        cpu="1",
        memory="2Gi",
        image=cfg["image"],
        environment_variables={
            "AZURE_AI_PROJECT_ENDPOINT": cfg["endpoint"],
            "AZURE_OPENAI_ENDPOINT": cfg["openai_endpoint"],
            "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": cfg["model"],
            "MODEL_ROUTER_DEPLOYMENT": cfg["model"],
            "LOG_LEVEL": "INFO",
        },
    )

    agent = client.agents.create(
        name=AGENT_NAME,
        definition=definition,
    )

    print(f"Agent deployed successfully!")
    print(f"  Name:    {agent.name}")
    print(f"  ID:      {agent.id}")
    print()
    print("Verify with:")
    print(f"  az cognitiveservices agent show --account-name <account> --project-name <project> --name {AGENT_NAME}")
    print()
    print("Test with (after deployment completes):")
    print(f'  az rest --method POST --url "<project-endpoint>/responses?api-version=2025-03-01-preview" --body \'{{\"model\":\"{AGENT_NAME}\",\"input\":\"test\"}}\' --resource "https://cognitiveservices.azure.com"')


def delete(cfg: dict) -> None:
    """Delete the latest hosted agent version."""
    client = AIProjectClient(
        endpoint=cfg["endpoint"],
        credential=DefaultAzureCredential(),
    )

    # List and delete the latest version
    print(f"Deleting hosted agent: {AGENT_NAME}")
    try:
        client.agents.delete_version(agent_name=AGENT_NAME, agent_version="latest")
        print("Agent version deleted.")
    except Exception as exc:
        print(f"Delete failed: {exc}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Deploy On-Call Copilot to Foundry Agent Service")
    parser.add_argument("--delete", action="store_true", help="Delete the agent instead of deploying")
    args = parser.parse_args()

    cfg = get_config()

    if args.delete:
        delete(cfg)
    else:
        deploy(cfg)


if __name__ == "__main__":
    main()
