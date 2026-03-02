# Deploying to Microsoft Foundry Agent Service (Hosted Agent)

This guide walks through deploying On-Call Copilot as a **Hosted Agent** on Microsoft Foundry Agent Service — from prerequisites through local testing to production verification.

> **Official quickstart:** [Deploy your first hosted agent using Azure Developer CLI](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry)
>
> **How-to guide:** [Deploy a hosted agent](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent?view=foundry&tabs=bash)

> **Note:** Hosted agents are currently in preview.

---

## Table of Contents

- [What Is a Hosted Agent?](#what-is-a-hosted-agent)
- [Prerequisites](#prerequisites)
- [Key Configuration Files](#key-configuration-files)
- [Step 1: Authenticate and Prepare](#step-1-authenticate-and-prepare)
- [Step 2: Provision Azure Resources](#step-2-provision-azure-resources)
- [Step 3: Test the Agent Locally](#step-3-test-the-agent-locally)
- [Step 4: Deploy to Foundry Agent Service](#step-4-deploy-to-foundry-agent-service)
- [Step 5: Verify and Test the Deployed Agent](#step-5-verify-and-test-the-deployed-agent)
- [Option B: Deploy with Python SDK (CI/CD)](#option-b-deploy-with-python-sdk-cicd)
- [Environment Variables](#environment-variables)
- [Container Configuration](#container-configuration)
- [Authentication](#authentication)
- [Scaling and Resources](#scaling-and-resources)
- [Updating the Agent](#updating-the-agent)
- [Using the Foundry Portal Playground](#using-the-foundry-portal-playground)
- [Deploy via VS Code Extension](#deploy-via-vs-code-extension)
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
| **Azure subscription** | With **Contributor** access for resource provisioning ([create a free account](https://azure.microsoft.com/free/)) |
| **Microsoft Foundry project** | With a capability host that has `enablePublicHostingEnvironment=true` ([quickstart](https://learn.microsoft.com/en-us/azure/foundry/tutorials/quickstart-create-foundry-resources)) |
| **Model Router deployment** | Deployed in your Azure OpenAI resource — or use `gpt-4.1`/`gpt-5` if Model Router is unavailable in your region ([model catalog](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/model-router)) |
| **Azure Developer CLI** | v1.23.0+ — `azd version` ([install](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)) |
| **Azure CLI** | v2.80+ (optional, for verification and SDK deploy) — `az --version` ([install](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)) |
| **Docker Desktop** | Running — verify with `docker info` ([install](https://docs.docker.com/get-docker/)) |
| **Python 3.10+** | `python --version` ([download](https://www.python.org/downloads/)) |
| **Authenticated sessions** | `az login` and `azd auth login` |

Register the Cognitive Services provider if you hit `SubscriptionNotRegistered`:

```bash
az provider register --namespace Microsoft.CognitiveServices
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

> **Note:** If you are not using an MCP server, remove or comment out any `AZURE_AI_PROJECT_TOOL_CONNECTION_ID` lines from `agent.yaml` before deploying.

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

`azd` will prompt you for the following during `azd provision` if not already set:

- **Azure subscription** — select the subscription for Foundry resources
- **Location** — choose a region that supports Model Router (e.g. `eastus2`, `swedencentral`)
- **Model SKU** — the SKU available for your region and subscription
- **Deployment name** — name for the model deployment
- **Container memory / CPU** — resource allocation (or accept defaults)
- **Minimum / Maximum replicas** — scaling configuration

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

## Step 1: Authenticate and Prepare

Sign in to both CLIs before any provisioning or deployment:

```bash
az login
azd auth login
```

Verify Docker Desktop is running — this is required for the build step:

```bash
docker info
```

If this command fails, start Docker Desktop and wait for it to initialise before continuing.

---

## Step 2: Provision Azure Resources

> **Requires:** Contributor access on your Azure subscription.

Run `azd provision` to create all required Azure resources (~5 minutes):

```bash
azd provision
```

This creates the following resources:

| Resource | Purpose | Cost |
|----------|---------|------|
| Resource group | Organises all related resources | No cost |
| Model deployment | Model used by the agent | See [Foundry pricing](https://azure.microsoft.com/pricing/details/cognitive-services/) |
| Foundry project | Hosts your agent and provides AI capabilities | Consumption-based |
| Azure Container Registry | Stores agent container images | Basic tier |
| Log Analytics Workspace | Centralises log data | No direct cost |
| Application Insights | Monitors agent performance and logs | Pay-as-you-go |
| Managed identity | Authenticates the agent to Azure services | No cost |

> **Tip:** Run `azd down` when you finish to delete resources and stop charges.

If the resource group name already exists, `azd provision` reuses the existing group. To avoid conflicts, choose a unique environment name or delete the existing resource group first.

---

## Step 3: Test the Agent Locally

Before investing in a full cloud deployment, verify the agent works on your machine.

### 3a. Create a virtual environment and install dependencies

**Bash:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3b. Export environment variables from your provisioned Azure environment

**Bash:**
```bash
azd env get-values > .env
```

**PowerShell:**
```powershell
azd env get-values > .env
```

Then add the model deployment name to `.env`:

```
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="model-router"
```

### 3c. Start the agent locally

```bash
python main.py
```

The agent binds to port 8088. If it fails to start, check:

| Error | Cause | Fix |
|-------|-------|-----|
| `AuthenticationError` or `DefaultAzureCredential` failure | Stale login session | Run `azd auth login` again |
| `ResourceNotFound` | Wrong endpoint URL | Verify endpoint URLs in the Foundry portal |
| `DeploymentNotFound` | Wrong deployment name | Check Build → Deployments in the portal |
| `Connection refused` | Port 8088 in use | Stop any other process using that port |

### 3d. Test with a REST client

The local server accepts the raw incident JSON body directly at `/responses` — no wrapping required.

**Bash:**
```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{
      "incident_id": "INC-TEST-001",
      "title": "SEV2: Redis master down",
      "severity": "SEV2",
      "timeframe": {"start": "2026-01-01T10:00:00Z", "end": null},
      "alerts": [{"name": "RedisDown", "description": "Redis master unreachable", "timestamp": "2026-01-01T10:00:00Z"}],
      "logs": [],
      "metrics": []
    }'
```

**PowerShell:**
```powershell
$body = Get-Content -Raw scripts/demos/demo_1_simple_alert.json
Invoke-RestMethod -Method Post `
    -Uri "http://localhost:8088/responses" `
    -ContentType "application/json" `
    -Body $body
```

Or use the existing test script directly:

```powershell
.\scripts\test_local.ps1 -Demo 1
```

You should see a structured JSON response with `suspected_root_causes`, `summary`, `comms`, and `post_incident_report` keys.

Stop the local server with `Ctrl+C`.

---

## Step 4: Deploy to Foundry Agent Service

`azd up` combines provisioning, packaging, and deployment into one command — equivalent to running `azd provision`, `azd package`, and `azd deploy` separately. If you already ran `azd provision` in Step 2, `azd up` will skip re-provisioning unchanged infrastructure.

> **Verify Docker is running** before this step: `docker info`

```bash
azd up
```

`azd up` will:
1. Provision infrastructure (if not already done)
2. Build the Docker image (remote build — no local Docker build required by default)
3. Push the image to Azure Container Registry
4. Register the hosted agent with Foundry Agent Service
5. Start the container

The first deployment takes longer because Docker needs to pull base layers. Subsequent deployments are faster.

When finished, `azd up` outputs:

```
Deploying services (azd deploy)
  (✓) Done: Deploying service oncall-copilot
  - Agent playground (portal): https://ai.azure.com/nextgen/.../build/agents/oncall-copilot/build?version=1
  - Agent endpoint: https://ai-account-<name>.services.ai.azure.com/api/projects/<project>/agents/oncall-copilot/versions/1
```

Save the **Agent endpoint** URL — you need it to call the agent programmatically.

> **Warning:** Your hosted agent incurs charges while deployed. Run `azd down` when finished testing to stop charges.

---

## Step 5: Verify and Test the Deployed Agent

### Check agent status (CLI)

Find your resource names first:

| Value | Where to find it |
|-------|-----------------|
| Account name | Foundry portal → your project → Overview → first part of the project endpoint URL (before `.services.ai.azure.com`) |
| Project name | Foundry portal → your project → Overview → project name |
| Agent name | Foundry portal → Build → Agents → agent name in the list |

Then run:

```bash
az cognitiveservices agent show \
    --account-name <your-account-name> \
    --project-name <your-project-name> \
    --name oncall-copilot
```

Look for `status: Started` in the output.

| Status | Meaning | Action |
|--------|---------|--------|
| `Provisioning` | Agent is still starting | Wait 2–3 minutes and check again |
| `Started` | Agent is running | Ready to use |
| `Failed` | Deployment error | Run `azd deploy` to retry; check portal logs |
| `Stopped` | Manually stopped | Run `az cognitiveservices agent start` |
| `Unhealthy` | Container crashing | Check deployment logs in the Foundry portal |

### Test via REST (deployed endpoint)

The deployed agent uses the Responses API. The body must include an `agent` reference and the incident JSON as the user message content.

**Bash:**
```bash
curl -X POST "<project-endpoint>/openai/responses?api-version=2025-05-15-preview" \
  -H "Authorization: Bearer $(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": {"type": "agent_reference", "name": "oncall-copilot"},
    "input": [
      {
        "role": "user",
        "content": "Analyze the following incident data and provide triage, summary, communications, and a post-incident report:\n\n{\"incident_id\":\"INC-TEST-001\",\"title\":\"Test incident\",\"severity\":\"SEV2\",\"alerts\":[{\"name\":\"HighCPU\",\"description\":\"CPU at 95%\",\"timestamp\":\"2026-01-01T10:00:00Z\"}],\"logs\":[{\"source\":\"app\",\"lines\":[\"ERROR: timeout\"]}],\"metrics\":[{\"name\":\"cpu_percent\",\"window\":\"5m\",\"values_summary\":\"95%\"}]}"
      }
    ]
  }'
```

**PowerShell:**
```powershell
$token = (az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
$body = @{
  agent = @{ type = "agent_reference"; name = "oncall-copilot" }
  input = @(@{
    role = "user"
    content = 'Analyze the following incident data and provide triage, summary, communications, and a post-incident report:\n\n{"incident_id":"INC-TEST-001","title":"Test incident","severity":"SEV2"}'
  })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
    -Uri "<project-endpoint>/openai/responses?api-version=2025-05-15-preview" `
    -Headers @{ Authorization = "Bearer $token" } `
    -ContentType "application/json" `
    -Body $body
```

Or use the provided script (handles authentication and body format automatically):

```bash
python scripts/invoke.py --demo 1
```

### Run all scenarios

```bash
python scripts/invoke.py --demo 1
python scripts/run_scenarios.py
```

### Automated verification script

```bash
python scripts/verify_agent.py
```

This script queries agent info (name, version, image, kind), runs a smoke test, and prints the first 500 chars of the response.

### Validate output schema (offline, no Azure needed)

```bash
MOCK_MODE=true python scripts/validate.py
```

---

## Option B: Deploy with Python SDK (CI/CD)

Use this for automated pipelines or when you need fine-grained control over the image tag and deployment.

### Step 1: Build and Push the Container Image

```bash
# Build for linux/amd64 (required by Foundry)
docker build --platform linux/amd64 -t oncall-copilot:v1 .

# Push to your Azure Container Registry
az acr login --name <your-registry>
docker tag oncall-copilot:v1 <your-registry>.azurecr.io/oncall-copilot:v1
docker push <your-registry>.azurecr.io/oncall-copilot:v1
```

> **Note (Apple Silicon / ARM):** Foundry requires `linux/amd64` images. Always pass `--platform linux/amd64`. Windows x64 users do not need this flag.

### Step 2: Grant Container Registry Repository Reader Access

The Foundry project's managed identity needs **Container Registry Repository Reader** on your ACR:

```bash
# Get the project managed identity principal ID
PRINCIPAL_ID=$(az cognitiveservices account show \
    --name <your-account-name> \
    --resource-group <your-rg> \
    --query identity.principalId -o tsv)

# Get the ACR resource ID
ACR_ID=$(az acr show --name <your-registry> --query id -o tsv)

# Assign Container Registry Repository Reader role
az role assignment create \
    --assignee "$PRINCIPAL_ID" \
    --role "Container Registry Repository Reader" \
    --scope "$ACR_ID"
```

### Step 3: Install SDK Prerequisites

```bash
pip install --pre "azure-ai-projects>=2.0.0b3" azure-identity
```

### Step 4: Set Environment Variables

**Bash:**
```bash
export AZURE_AI_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_OPENAI_ENDPOINT="https://<account>.openai.azure.com/"
export ACR_IMAGE="<your-registry>.azurecr.io/oncall-copilot:v1"
export MODEL_ROUTER_DEPLOYMENT="model-router"
```

**PowerShell:**
```powershell
$env:AZURE_AI_PROJECT_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_OPENAI_ENDPOINT     = "https://<account>.openai.azure.com/"
$env:ACR_IMAGE                 = "<your-registry>.azurecr.io/oncall-copilot:v1"
$env:MODEL_ROUTER_DEPLOYMENT   = "model-router"
```

### Step 5: Deploy

```bash
python scripts/deploy_sdk.py
```

The script uses the `azure-ai-projects` SDK (`ImageBasedHostedAgentDefinition` with `ProtocolVersionRecord`) to create a hosted agent version, injects the environment variables, and registers the agent.

### Step 6: Verify

```bash
python scripts/verify_agent.py
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Your Azure OpenAI resource endpoint |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Yes | Model deployment name (typically `model-router`) |
| `AZURE_AI_PROJECT_ENDPOINT` | Yes | Full project endpoint URL |
| `MODEL_ROUTER_DEPLOYMENT` | Yes | Model Router deployment name |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

These are set in `agent.yaml` and injected automatically by Foundry at container startup. For local development, export them from your provisioned environment using `azd env get-values > .env`.

> **Finding your values:**
>
> | Variable | Where to find it |
> |----------|-----------------|
> | `AZURE_OPENAI_ENDPOINT` | [Foundry portal](https://ai.azure.com/) → your project → Overview → Endpoint |
> | `AZURE_AI_PROJECT_ENDPOINT` | [Foundry portal](https://ai.azure.com/) → your project → Overview → Project endpoint |
> | `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | [Foundry portal](https://ai.azure.com/) → Build → Deployments → your Model Router deployment name |

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
azd auth login
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

## Using the Foundry Portal Playground

The fastest way to interact with a deployed agent is through the [Foundry portal](https://ai.azure.com/):

1. Open the [Foundry portal](https://ai.azure.com/) and sign in with your Azure account
2. Select your project from the **Recent projects** list (or **All projects**)
3. In the left navigation, select **Build** → **Agents**
4. Find `oncall-copilot` in the agents list and select it
5. Select **Open in playground** in the top toolbar
6. Paste an incident JSON payload in the chat input and press Enter

You can also use the direct playground link printed by `azd up` after a successful deployment:

```
Agent playground (portal): https://ai.azure.com/nextgen/.../build/agents/oncall-copilot/build?version=1
```

> **Tip:** If the playground doesn't load or the agent doesn't respond, verify the agent status is `Started` using the CLI command in [Step 5](#step-5-verify-and-test-the-deployed-agent).

---

## Deploy via VS Code Extension

You can deploy directly from the IDE using the [Microsoft Foundry for Visual Studio Code extension](https://marketplace.visualstudio.com/items?itemName=TeamsDevApp.vscode-ai-foundry):

1. Install the extension: Extensions (`Ctrl+Shift+X`) → search **Microsoft Foundry** → Install
2. Open Command Palette (`Ctrl+Shift+P`) → **Microsoft Foundry: Set Default Project**
3. Sign in and select your subscription, resource group, and Foundry project
4. Right-click the project in the Foundry Explorer and select **Deploy Hosted Agent**
5. Once deployed, select **Open in Playground** to test

See the [VS Code extension documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/vs-code-agents-workflow-pro-code?tabs=windows-powershell&pivots=python) for the full workflow.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `azd init` fails | Outdated `azd` version | Run `winget upgrade Microsoft.Azd` (Windows) or `brew upgrade azd` (macOS). Verify version 1.23.0+. |
| Docker build errors | Docker Desktop not running | Run `docker info` to verify. Start Docker Desktop if needed. |
| `SubscriptionNotRegistered` | Resource provider not registered | `az provider register --namespace Microsoft.CognitiveServices` |
| `AuthorizationFailed` during `azd provision` | Missing Contributor role | Request Contributor on your subscription or resource group |
| `AuthenticationError` / `DefaultAzureCredential` failure | Stale login | Run `az login` and `azd auth login` again |
| Agent not found after deployment | Propagation delay | Wait 2–3 minutes, then re-run `az cognitiveservices agent show` |
| Container fails to start | Missing env vars or dependency conflict | Run `python scripts/get_logs.py`; check `agent.yaml` env vars; rebuild the image |
| `UnauthorizedAcrPull` (403) / `InvalidAcrPullCredentials` (401) | Managed identity missing registry role | Grant `Container Registry Repository Reader` to the project's managed identity on the ACR |
| `401 Unauthorized` | Missing RBAC role | Grant `Cognitive Services OpenAI User` to the managed identity on the Azure OpenAI resource |
| `403 Forbidden` | Hosted agent capability not enabled | Ensure `enablePublicHostingEnvironment=true` on the capability host |
| Timeout / slow first response | Cold start (no warm replicas) | Increase `minReplicas: 1` in `azure.yaml`; redeploy |
| Port 8088 already in use (local) | Another process | Stop conflicting process; verify with `netstat -an \| findstr 8088` (Windows) |
| Model not found in catalog | Model unavailable in your region | Edit `agent.yaml` to use `gpt-4.1` or another available model deployment |

---

## Cleanup

> **Warning:** The commands below permanently delete all Azure resources created for this deployment, including the Foundry project, Container Registry, Application Insights, and your hosted agent. This action cannot be undone.

Preview what will be deleted before confirming:

```bash
azd down --preview
```

When ready, delete everything:

```bash
azd down
```

The cleanup process takes approximately 2–5 minutes. To verify, open the [Azure portal](https://portal.azure.com/), go to your resource group, and confirm the resources no longer appear.

### Remove with SDK (agent only)

```bash
python scripts/deploy_sdk.py --delete
```

### Remove resources manually

```bash
# Delete the agent registration
az cognitiveservices agent delete \
    --account-name <account> \
    --project-name <project> \
    --name oncall-copilot

# Delete the ACR image (SDK deploy only)
az acr repository delete \
    --name <your-registry> \
    --image oncall-copilot:v1 \
    --yes
```

---

## Further Reading

- [Quickstart: Deploy your first hosted agent (Azure Developer CLI)](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry)
- [Deploy a hosted agent (how-to guide)](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/deploy-hosted-agent?view=foundry&tabs=bash)
- [What are hosted agents?](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Manage hosted agent lifecycle](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent)
- [Agent development lifecycle](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/development-lifecycle)
- [Python hosted agent samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents)
- [Microsoft Agent Framework documentation](https://learn.microsoft.com/azure/ai-foundry/agents/)
- [Model Router overview](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/model-router)
- [AGENTS.md](AGENTS.md) — Agent architecture and customisation guide
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — Agent instruction configuration reference
