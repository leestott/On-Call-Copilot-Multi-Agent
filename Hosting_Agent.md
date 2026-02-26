# Deploying to Microsoft Foundry Agent Service (Hosted Agent)

This guide walks through deploying On-Call Copilot as a **Hosted Agent** on Microsoft Foundry Agent Service — from prerequisites to production verification.

> **Official docs:** [Deploy a hosted agent](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent?view=foundry&tabs=bash)

---

## Table of Contents

- [What Is a Hosted Agent?](#what-is-a-hosted-agent)
- [Prerequisites](#prerequisites)
- [Key Configuration Files](#key-configuration-files)
- [Option A: Deploy with Azure Developer CLI (azd)](#option-a-deploy-with-azure-developer-cli-azd)
- [Option B: Deploy with Python SDK (CI/CD)](#option-b-deploy-with-python-sdk-cicd)
- [Verify the Deployment](#verify-the-deployment)
- [Environment Variables](#environment-variables)
- [Container Configuration](#container-configuration)
- [Authentication](#authentication)
- [Scaling and Resources](#scaling-and-resources)
- [Updating the Agent](#updating-the-agent)
- [Testing the Deployed Agent](#testing-the-deployed-agent)
- [Using the Foundry Agent Playground (VS Code)](#using-the-foundry-agent-playground-vs-code)
- [Troubleshooting](#troubleshooting)
- [Cleanup](#cleanup)

---

## What Is a Hosted Agent?

A **Hosted Agent** is a containerised application deployed to Microsoft Foundry Agent Service. Foundry manages the container lifecycle (scaling, health checks, networking) while your code handles the agent logic. The agent is exposed via the **Responses API** protocol at port `8088`.

On-Call Copilot runs as a single container that hosts four specialist agents (Triage, Summary, Comms, PIR) concurrently using the Microsoft Agent Framework `ConcurrentBuilder`. All four agents share a single **Model Router** deployment — Foundry routes each request to the best model automatically.

```
┌─────────────────────────────────────────────────────────┐
│              Foundry Agent Service                      │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Hosted Agent Container (port 8088)               │  │
│  │                                                   │  │
│  │  main.py → ConcurrentBuilder                      │  │
│  │    ├── triage-agent                               │  │
│  │    ├── summary-agent                              │  │
│  │    ├── comms-agent                                │  │
│  │    └── pir-agent                                  │  │
│  │                                                   │  │
│  │  Protocol: Responses API                          │  │
│  └───────────────────────────────────────────────────┘  │
│                          │                              │
│                          ▼                              │
│              Microsoft Foundry Model Router                  │
│              (single deployment)                        │
└─────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Azure subscription** | With permissions to create Microsoft Foundry resources |
| **Microsoft Foundry project** | With a capability host that has `enablePublicHostingEnvironment=true` |
| **Model Router deployment** | Deployed in your Azure OpenAI resource ([how-to](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/model-router)) |
| **Azure CLI** | v2.80+ (`az --version`) |
| **Azure Developer CLI** | v1.23.0+ (`azd version`) — for Option A |
| **Docker Desktop** | For building the container image |
| **Python 3.12+** | For Option B (SDK deployment) |
| **`az login`** | Authenticated with the correct subscription |

Install the Azure CLI extensions if needed:

```bash
az extension add --name ai
az extension add --name containerapp --upgrade
```

---

## Key Configuration Files

The deployment uses three files in the repo root:

### `agent.yaml` — Agent Definition

Declares the agent name, protocols, and environment variables for Foundry:

```yaml
kind: hosted
name: oncall-copilot
protocols:
  - protocol: responses
environment_variables:
  - name: AZURE_OPENAI_ENDPOINT
    value: ${AZURE_OPENAI_ENDPOINT}
  - name: AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
    value: model-router
  - name: AZURE_AI_PROJECT_ENDPOINT
    value: ${AZURE_AI_PROJECT_ENDPOINT}
  - name: MODEL_ROUTER_DEPLOYMENT
    value: ${MODEL_ROUTER_DEPLOYMENT}
  - name: LOG_LEVEL
    value: INFO
```

Key fields:
- **`kind: hosted`** — tells Foundry this is a containerised agent
- **`protocol: responses`** — exposes the Responses API on port 8088
- **`environment_variables`** — injected into the container at runtime

### `azure.yaml` — Azure Developer CLI Config

Controls infrastructure provisioning via `azd`:

```yaml
name: oncall-copilot
services:
  oncall-copilot:
    project: .
    host: azure.ai.agent
    language: docker
    docker:
      remoteBuild: true
    config:
      container:
        resources:
          cpu: "1"
          memory: 2Gi
        scale:
          maxReplicas: 3
          minReplicas: 1
      deployments:
        - model:
            format: OpenAI
            name: model-router
            version: "2025-11-18"
          name: model-router
          sku:
            capacity: 10
            name: GlobalStandard
```

### `Dockerfile` — Container Image

Standard Python 3.12 slim image exposing port 8088:

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . user_agent/
WORKDIR /app/user_agent
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
EXPOSE 8088
CMD ["python", "main.py"]
```

> **Important:** The Foundry runtime expects the agent to listen on port **8088**. Do not change this.

---

## Option A: Deploy with Azure Developer CLI (azd)

This is the fastest path. `azd` handles infrastructure provisioning, image building (remote), and agent registration in one command.

### Step 1: Initialise

```bash
az login
azd auth login
```

### Step 2: Deploy

```bash
azd up
```

`azd up` will:
1. Provision the Microsoft Foundry project (if needed)
2. Deploy the Model Router model
3. Build the Docker image remotely
4. Register the hosted agent with Foundry
5. Start the container

You will be prompted for:
- **Subscription** — select the one with your Foundry project
- **Region** — choose a region that supports Model Router (e.g. `eastus2`, `swedencentral`)

### Step 3: Verify

```bash
az cognitiveservices agent show \
    --account-name <your-account-name> \
    --project-name <your-project-name> \
    --name oncall-copilot
```

---

## Option B: Deploy with Python SDK (CI/CD)

Use this for automated pipelines or when you need fine-grained control.

### Step 1: Build and Push the Container Image

```bash
# Build for linux/amd64 (required by Foundry)
docker build --platform linux/amd64 -t oncall-copilot:v1 .

# Push to your Azure Container Registry
az acr login --name <your-registry>
docker tag oncall-copilot:v1 <your-registry>.azurecr.io/oncall-copilot:v1
docker push <your-registry>.azurecr.io/oncall-copilot:v1
```

### Step 2: Grant ACR Access

The Foundry project's managed identity needs **Container Registry Repository Reader** on your ACR:

```bash
# Get the project managed identity principal ID
PRINCIPAL_ID=$(az cognitiveservices account show \
    --name <your-account-name> \
    --resource-group <your-rg> \
    --query identity.principalId -o tsv)

# Get the ACR resource ID
ACR_ID=$(az acr show --name <your-registry> --query id -o tsv)

# Assign the role
az role assignment create \
    --assignee "$PRINCIPAL_ID" \
    --role "Container Registry Repository Reader" \
    --scope "$ACR_ID"
```

### Step 3: Set Environment Variables

```bash
export AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_OPENAI_ENDPOINT="https://<account>.openai.azure.com/"
export ACR_IMAGE="<your-registry>.azurecr.io/oncall-copilot:v1"
export MODEL_ROUTER_DEPLOYMENT="model-router"
```

### Step 4: Deploy

```bash
python scripts/deploy_sdk.py
```

The script uses `azure-ai-projects` SDK to create an `ImageBasedHostedAgentDefinition` with the Responses protocol, injects the environment variables, and registers the agent.

### Step 5: Verify

```bash
python scripts/verify_agent.py
```

---

## Verify the Deployment

### Quick check (CLI)

```bash
az cognitiveservices agent show \
    --account-name <your-account-name> \
    --project-name <your-project-name> \
    --name oncall-copilot
```

### Smoke test (REST)

```bash
az rest --method POST \
    --url "<project-endpoint>/openai/responses?api-version=2025-05-15-preview" \
    --body '{"model":"oncall-copilot","input":"SEV2: Redis master down in us-east-1"}' \
    --resource "https://cognitiveservices.azure.com"
```

### Automated verification script

```bash
python scripts/verify_agent.py
```

This script:
1. Queries agent info (name, version, image, kind)
2. Runs a smoke test with a sample incident prompt
3. Prints the first 500 chars of the response

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Your Azure OpenAI resource endpoint |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Yes | Model deployment name (typically `model-router`) |
| `AZURE_AI_PROJECT_ENDPOINT` | Yes | Full project endpoint URL |
| `MODEL_ROUTER_DEPLOYMENT` | Yes | Model Router deployment name |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

These are set in `agent.yaml` and injected automatically by Foundry at container startup. For SDK deployments, they are passed via `deploy_sdk.py`.

> **Finding your values:**
>
> | Variable | Where to find it |
> |----------|-----------------|
> | `AZURE_OPENAI_ENDPOINT` | Microsoft Foundry portal → your project → Overview → Endpoint |
> | `AZURE_AI_PROJECT_ENDPOINT` | Microsoft Foundry portal → your project → Overview → Project endpoint |
> | `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Microsoft Foundry portal → Deployments → your Model Router deployment name |

---

## Container Configuration

### Resources

Defined in `azure.yaml`:

```yaml
container:
  resources:
    cpu: "1"
    memory: 2Gi
```

These are minimum recommended values. The agent runs four concurrent LLM calls per request so memory usage scales with concurrent requests.

### Port

The Foundry runtime expects the agent to listen on **port 8088**. This is set in the `Dockerfile` (`EXPOSE 8088`) and handled by `from_agent_framework()` in `main.py`.

### Health Checks

Foundry automatically monitors container health. If the container fails to start or crashes, Foundry will restart it based on the scaling configuration.

---

## Authentication

### Production (Foundry-hosted)

In production, the container uses **`DefaultAzureCredential`** with the project's **managed identity** — no API keys or secrets are needed:

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)
```

Foundry automatically provides the managed identity to the container.

### Required RBAC Roles

| Role | Scope | Purpose |
|------|-------|---------|
| **Cognitive Services OpenAI User** | Azure OpenAI resource | Call Model Router completions |
| **Container Registry Repository Reader** | ACR (SDK deploy only) | Pull container image |

### Local Development

For local development, `DefaultAzureCredential` picks up your `az login` session:

```bash
az login
python main.py
```

---

## Scaling and Resources

### Auto-scaling

Configured in `azure.yaml`:

```yaml
scale:
  maxReplicas: 3
  minReplicas: 1
```

- **`minReplicas: 1`** — always keep one instance warm (avoids cold starts)
- **`maxReplicas: 3`** — scale out under load

Adjust these based on expected traffic:

| Scenario | minReplicas | maxReplicas |
|----------|-------------|-------------|
| Dev/test | 0 | 1 |
| Production (low traffic) | 1 | 3 |
| Production (high traffic) | 2 | 10 |

### Model Deployment Capacity

The Model Router deployment quota is set in `azure.yaml`:

```yaml
deployments:
  - name: model-router
    sku:
      capacity: 10
      name: GlobalStandard
```

Each On-Call Copilot request triggers 4 concurrent Model Router calls. If you expect N concurrent users, set capacity to at least `N × 4`.

---

## Updating the Agent

### Updating Agent Code

1. Make your changes (edit agent instructions, add new agents, update schemas)
2. Rebuild and redeploy:

**With `azd`:**
```bash
azd up
```

**With SDK:**
```bash
docker build --platform linux/amd64 -t oncall-copilot:v2 .
docker tag oncall-copilot:v2 <your-registry>.azurecr.io/oncall-copilot:v2
docker push <your-registry>.azurecr.io/oncall-copilot:v2

export ACR_IMAGE="<your-registry>.azurecr.io/oncall-copilot:v2"
python scripts/deploy_sdk.py
```

### Updating Agent Instructions Only

Agent instructions are plain text strings in `app/agents/*.py`. To change behaviour:

1. Edit the `*_INSTRUCTIONS` constant in the relevant file
2. Rebuild the container and redeploy (instructions are baked into the image)
3. No infrastructure changes needed

See [AGENTS.md](AGENTS.md) for details on each agent's instruction format.

### Adding a New Agent

1. Create `app/agents/<name>.py` with a `*_INSTRUCTIONS` constant
2. Add output keys to `app/schemas.py`
3. Register in `main.py`:
   ```python
   new_agent = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
       instructions=NEW_INSTRUCTIONS, name="new-agent",
   )
   workflow = ConcurrentBuilder().participants([triage, summary, comms, pir, new_agent])
   ```
4. Rebuild and redeploy the container

---

## Testing the Deployed Agent

### Run all scenarios against the deployed agent

```bash
python scripts/invoke.py --demo 1
python scripts/run_scenarios.py
```

### Run a REST call directly

```bash
curl -X POST "<project-endpoint>/openai/responses?api-version=2025-05-15-preview" \
  -H "Authorization: Bearer $(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "oncall-copilot",
    "input": [
      {
        "role": "user",
        "content": "{\"incident_id\":\"INC-TEST-001\",\"title\":\"Test incident\",\"severity\":\"SEV2\",\"alerts\":[{\"name\":\"HighCPU\",\"description\":\"CPU at 95%\",\"timestamp\":\"2026-01-01T10:00:00Z\"}],\"logs\":[{\"source\":\"app\",\"lines\":[\"ERROR: timeout\"]}],\"metrics\":[{\"name\":\"cpu_percent\",\"window\":\"5m\",\"values_summary\":\"95%\"}]}"
      }
    ]
  }'
```

### Validate output schema (offline, no Azure needed)

```bash
MOCK_MODE=true python scripts/validate.py
```

---

## Using the Foundry Agent Playground (VS Code)

1. Install the **Microsoft Foundry** extension (Extensions → search "Microsoft Foundry" → Install)
2. Open Command Palette (`Ctrl+Shift+P`) → **Microsoft Foundry: Set Default Project**
3. Sign in and select your subscription, resource group, and Foundry project
4. Open the **Agent Playground** panel
5. Select `oncall-copilot` from the agent dropdown
6. Paste an incident JSON payload and send

---

## Troubleshooting

### Agent not found after deployment

```
ERROR: Agent 'oncall-copilot' not found
```

- Wait 2–3 minutes for the deployment to propagate
- Check the agent name matches exactly: `oncall-copilot`
- Verify the deployment succeeded:
  ```bash
  az cognitiveservices agent list \
      --account-name <account> \
      --project-name <project>
  ```

### Container fails to start

- Check container logs:
  ```bash
  python scripts/get_logs.py
  ```
- Common causes:
  - Missing environment variables → check `agent.yaml`
  - Python dependency conflicts → rebuild the image
  - Port conflict → ensure `main.py` uses port 8088

### 401 Unauthorized

- **Managed identity not configured:** Ensure the project's managed identity has `Cognitive Services OpenAI User` on the Azure OpenAI resource
- **ACR access denied (SDK deploy):** Ensure the managed identity has `Container Registry Repository Reader` on the ACR

### 403 Forbidden

- The account or project doesn't have hosted agent capability enabled
- Ensure `enablePublicHostingEnvironment=true` on the capability host
- Reference: [Hosted agent prerequisites](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent?view=foundry&tabs=bash#prerequisites)

### Timeout / slow responses

- Each request runs 4 concurrent Model Router calls — cold starts can take 30–60 seconds
- Increase `minReplicas` to keep instances warm
- Check Model Router deployment quota — if exhausted, requests queue

### Docker build fails on Apple Silicon / ARM

Foundry requires `linux/amd64` images. Build with the platform flag:

```bash
docker build --platform linux/amd64 -t oncall-copilot:v1 .
```

---

## Cleanup

### Remove with `azd`

```bash
azd down
```

### Remove with SDK

```bash
python scripts/deploy_sdk.py --delete
```

### Remove resources manually

```bash
# Delete the agent
az cognitiveservices agent delete \
    --account-name <account> \
    --project-name <project> \
    --name oncall-copilot

# Delete the ACR image (if using SDK deploy)
az acr repository delete \
    --name <your-registry> \
    --image oncall-copilot:v1 \
    --yes
```

---

## Further Reading

- [Microsoft Agent Framework documentation](https://learn.microsoft.com/azure/ai-foundry/agents/)
- [Deploy a hosted agent (official guide)](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent?view=foundry&tabs=bash)
- [Model Router overview](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/model-router)
- [Manage hosted agents](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/manage-hosted-agent)
- [AGENTS.md](AGENTS.md) — Agent architecture and customisation guide
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — Agent instruction configuration reference
