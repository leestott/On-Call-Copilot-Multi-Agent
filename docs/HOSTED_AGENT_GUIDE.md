# Hosted Agent Guide: On-Call Copilot on Microsoft Foundry

This document is the single, canonical reference for hosting On-Call Copilot on Microsoft Foundry Agent Service. It supersedes and consolidates the previous `Hosting_Agent.md`, `docs/MIGRATION.md`, and `docs/MIGRATIONS.md` files.

It is written for engineering teams that want to deploy a multi-agent Python service onto the current Microsoft Foundry Hosted Agents preview, backed by Microsoft Agent Framework 1.2 and Microsoft Foundry Model Router. The same principles apply to C# with package names changed.

## Contents

1. Overview
2. Prerequisites
3. Compatibility matrix (SDKs, CLI, schema)
4. Key configuration files
5. Authenticate and prepare
6. Provision Azure resources
7. Test the agent locally
8. Deploy with Azure Developer CLI
9. Verify and test the deployed agent
10. Deploy with the Python SDK (CI/CD)
11. Migration guide: legacy AgentServer to Preview Hosted Agents
12. Top tips for migrating to Preview Hosted Agents
13. Operations: scaling, updates, environment variables
14. Troubleshooting
15. Cleanup
16. Reference

---

## 1. Overview

A Hosted Agent is a containerised application deployed to Microsoft Foundry Agent Service. Foundry manages the container lifecycle, scaling, health checks, and networking, while your code provides the agent logic. The agent is exposed over the Responses API on port `8088`.

On-Call Copilot runs as a single container that hosts four specialist agents (Triage, Summary, Communications, and PIR) concurrently using the Microsoft Agent Framework `ConcurrentBuilder`. All four agents share a single Microsoft Foundry Model Router deployment, so Foundry routes each request to the most appropriate model automatically.

```
+---------------------------------------------------------+
|              Foundry Agent Service                      |
|                                                         |
|  +---------------------------------------------------+  |
|  |  Hosted Agent Container (port 8088)               |  |
|  |                                                   |  |
|  |  main.py -> ConcurrentBuilder                     |  |
|  |    +-- triage-agent                               |  |
|  |    +-- summary-agent                              |  |
|  |    +-- comms-agent                                |  |
|  |    +-- pir-agent                                  |  |
|  |                                                   |  |
|  |  Protocol: Responses API, version 1.0.0           |  |
|  +---------------------------------------------------+  |
|                          |                              |
|                          v                              |
|              Microsoft Foundry Model Router             |
|              (single deployment)                        |
+---------------------------------------------------------+
```

Hosted Agents are currently in preview.

---

## 2. Prerequisites

| Requirement | Details |
|-------------|---------|
| Azure subscription | Contributor access for resource provisioning. |
| Microsoft Foundry project | An AIServices account with `allowProjectManagement=true` and a child project, both with system-assigned managed identities. |
| Capability hosts | Two `Agents` capability hosts: one at account scope, one at project scope. |
| Model Router deployment | Deployed in the same project as the hosted agent (recommended). |
| Azure Developer CLI | Version 1.23 or newer. Verify with `azd version`. |
| Azure CLI | Version 2.80 or newer (optional, but useful for verification). Verify with `az --version`. |
| Docker Desktop | Required only if you build images locally. ACR remote build is the default and does not require Docker on the developer machine. |
| Python | Version 3.10 or newer. Verify with `python --version`. |
| Authenticated sessions | `az login` and `azd auth login`. |

If you encounter `SubscriptionNotRegistered`, register the Cognitive Services provider:

```bash
az provider register --namespace Microsoft.CognitiveServices
```

### Region availability

The Hosted Agents preview is available in Australia East, Canada Central, North Central US, and Sweden Central. Microsoft Foundry Model Router availability varies by subscription. **Sweden Central is currently the only region that supports both Hosted Agents and Model Router for most subscriptions and is the recommended region.**

---

## 3. Compatibility matrix

The Preview Hosted Agents stack moves quickly. Pin every dependency in this column together. Mixing major versions across SDKs is the most common cause of runtime failures.

| Tier | Legacy v1 | Preview Hosted Agents (current) | Next preview drop |
|------|-----------|---------------------------------|-------------------|
| Microsoft Agent Framework core (`agent-framework`) | 0.x with `AgentExecutor` and `WorkflowBuilder` only | **1.2.0** with `Agent`, `ConcurrentBuilder`, `WorkflowBuilder.as_agent()` | 1.3.x (planned) |
| MAF Foundry chat client (`agent-framework-foundry`) | Not available; previous releases used `azure-ai-agents` directly | **1.2.0** with `FoundryChatClient(project_endpoint=, model=, credential=)` | Tracks core |
| MAF Foundry hosting (`agent-framework-foundry-hosting`) | Not available; previous releases used `azure-ai-agentserver-core` | **1.0.0a260424** with `ResponsesHostServer(agent).run(port=...)` | 1.0.0aXXXX |
| MAF Orchestrations (`agent-framework-orchestrations`) | Not available | **1.0.0b260424** with `ConcurrentBuilder().participants([...]).build()` | 1.0.0bXXXX |
| Foundry projects SDK (`azure-ai-projects`) | 1.0.0bXX, data-plane agents only | **2.1.0** with `allow_preview=True`, providing `agents.create_version`, `HostedAgentDefinition`, `ContainerConfiguration`, and `ProtocolVersionRecord` | 2.2.x |
| Identity (`azure-identity`) | Any 1.x | **1.19 or newer, less than 2** | 1.x |
| Azure Developer CLI (`azd`) | 1.10.x with App Service or Container Apps targets | **1.23 or newer** with `host: azure.ai.agent` and `remoteBuild: true` | 1.24.x |
| `azd` alpha feature flag | Not applicable | `azd config set alpha.aiagent on` is required | May be promoted to GA |
| `agent.yaml` schema | Not used | `kind: hosted` plus `protocols: [{ protocol: responses, version: 1.0.0 }]` | Adds streaming protocols |
| Hosted Agents data-plane API | `responses` only via direct REST | `responses` 1.0.0; `chat/completions` planned | Adds `chat/completions` and `realtime` |
| Container runtime contract | App Service or Container Apps Dockerfile | `python:3.12-slim`, `EXPOSE 8088`, and `ResponsesHostServer.run(port=8088)` | Unchanged |
| Capability hosts | Not applicable | Two capability hosts of `kind: Agents`: one at account scope, one at project scope (control-plane API version `2025-06-01`) | Unchanged |

**Pinning rule:** treat the `agent-framework*` family, `azure-ai-projects`, and `azd` as a single coordinated bundle. Upgrading one without the others is unsupported in preview.

---

## 4. Key configuration files

The deployment uses three files in the repository root.

### 4.1 `agent.yaml`

This file declares the hosted agent name, the protocol contract, and the environment variables Foundry should inject at runtime.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/microsoft/AgentSchema/refs/heads/main/schemas/v1.0/ContainerAgent.yaml
kind: hosted
name: oncall-copilot
protocols:
  - protocol: responses
    version: 1.0.0
environment_variables:
  - name: AZURE_TENANT_ID
    value: ${AZURE_TENANT_ID}
  - name: AZURE_AI_PROJECT_ENDPOINT
    value: ${AZURE_AI_PROJECT_ENDPOINT}
  - name: AZURE_OPENAI_ENDPOINT
    value: ${AZURE_OPENAI_ENDPOINT}
  - name: AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
    value: ${AZURE_OPENAI_CHAT_DEPLOYMENT_NAME}
  - name: MODEL_ROUTER_DEPLOYMENT
    value: ${MODEL_ROUTER_DEPLOYMENT}
  - name: LOG_LEVEL
    value: INFO
```

Key points:

* `kind: hosted` tells Foundry this is a containerised agent.
* `protocols` is a list of objects, not a list of strings. Each entry must include both `protocol` and `version`. Preview rejects `version: "v1"`; use semantic versioning such as `1.0.0`.
* `environment_variables` are injected into the container by Foundry at startup and resolved from the `azd` environment.

If you are not using an MCP server, do not add an `AZURE_AI_PROJECT_TOOL_CONNECTION_ID` entry to this file.

### 4.2 `azure.yaml`

This file controls infrastructure provisioning and packaging through `azd`.

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
            capacity: 50
            name: GlobalStandard
```

Notes:

* `host: azure.ai.agent` is required for hosted agents. Older values such as `appservice` or `containerapp` are not accepted.
* `docker.remoteBuild: true` instructs `azd` to build the image in Azure Container Registry. Local Docker is not required.
* `cpu` and `memory` are the per-replica resource requests. Two gibibytes of memory is the practical minimum for the four concurrent Model Router calls used in this sample.
* `capacity: 50` is sized for the recommended `N x 4` rule explained in the scaling section.

### 4.3 `Dockerfile`

A slim Python 3.12 base image that exposes port 8088 and runs `main.py`:

```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . user_agent/
WORKDIR /app/user_agent
EXPOSE 8088
CMD ["python", "main.py"]
```

The Foundry runtime expects the agent to listen on port 8088. Do not change this, and do not parameterise the port through an environment variable.

---

## 5. Authenticate and prepare

Sign in to both CLIs and verify your tenant before any provisioning step:

```bash
az login
azd auth login
az account show --query "{tenant:tenantId, subscription:id}" -o table
```

If you build images locally rather than using ACR remote build, also verify Docker:

```bash
docker info
```

---

## 6. Provision Azure resources

You can provision either through `azd provision` (recommended for the first deployment) or with explicit Bicep or REST calls (recommended for production pipelines that need fine-grained control).

### 6.1 Bootstrap order

Order matters. Skipping or reordering steps is the most common cause of `500 server_error` from `agents.create_version`.

1. Create the AIServices account (`kind: AIServices`, SKU `S0`, `customSubDomainName` set, system-assigned identity).
2. PATCH `properties.allowProjectManagement = true` on the account.
3. Create the project under the account, with `identity: SystemAssigned`.
4. Create the account-scope `Agents` capability host (`/capabilityHosts/accountcaphost`, body `{"properties":{"capabilityHostKind":"Agents"}}`, API version `2025-06-01`).
5. Create the project-scope `Agents` capability host (`/projects/<name>/capabilityHosts/agents`, same body and API version).
6. Wait for both capability hosts to reach `provisioningState: Succeeded`.
7. Deploy Model Router into the same account (for example, `model-router`, version `2025-11-18`, SKU `GlobalStandard`, capacity 50 or higher).
8. Apply the RBAC assignments listed in the next section.
9. Push the agent image to Azure Container Registry.
10. Run `azd deploy`.

### 6.2 Required RBAC

| Principal | Role | Scope | Reason |
|-----------|------|-------|--------|
| Project managed identity | `AcrPull` | ACR | Pull the container image during deployment. |
| Account managed identity | `AcrPull` | ACR | Platform infrastructure pulls. Both identities are needed during preview. |
| Project managed identity | `Azure AI User` | Account | Allow the agent to call Model Router. |
| Project managed identity | `Cognitive Services User` | Account | Allow the agent to call Model Router completions. |
| Deploying user | `Azure AI Project Manager` | Account | Required for `agents.create_version`. |
| Deploying user | `Cognitive Services Contributor` | Account | Manage deployments through `azd`. |

When granting a role to a managed identity, always pass `--assignee-object-id` together with `--assignee-principal-type ServicePrincipal`. This avoids the `PrincipalNotFound` race that occurs when the identity has only just been created.

### 6.3 `azd provision` (quickstart)

```bash
azd provision
```

`azd` prompts for the Azure subscription, region, model SKU, deployment name, and scaling values. If the resource group already exists, `azd` reuses it. To avoid conflicts, choose a unique environment name or delete the existing resource group first.

The provisioning step takes approximately five minutes and creates the resource group, model deployment, Foundry account and project, Azure Container Registry, Log Analytics workspace, Application Insights, and managed identities.

### 6.4 `.env` shape

```env
AZURE_TENANT_ID=<your-tenant-id>
AZURE_SUBSCRIPTION_ID=<your-subscription-id>
AZURE_RESOURCE_GROUP=<your-rg>
AZURE_LOCATION=swedencentral
AZURE_AI_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_OPENAI_ENDPOINT=https://<account>.cognitiveservices.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=model-router
MODEL_ROUTER_DEPLOYMENT=model-router
AZURE_CONTAINER_REGISTRY_ENDPOINT=<registry>.azurecr.io
ACR_IMAGE=<registry>.azurecr.io/oncall-copilot:agent-framework-1.2.0
ENABLE_HOSTED_AGENTS=true
```

After every change to `.env`, mirror each key into the `azd` environment with a separate `azd env set <KEY> <VALUE>` call. Piping `.env` through PowerShell loops silently drops keys.

---

## 7. Test the agent locally

Before investing in a full cloud deployment, verify the agent works on your machine.

### 7.1 Install dependencies

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Bash:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 7.2 Export environment values

```bash
azd env get-values > .env
```

Add the deployment name if it is not already present:

```env
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=model-router
```

### 7.3 Run the agent

```bash
python main.py
```

The agent binds to port 8088. If it fails to start, check the table in the troubleshooting section.

### 7.4 Send a request

The local server accepts the raw incident JSON body directly at `/responses`, with no Responses API wrapping required.

PowerShell:

```powershell
$body = Get-Content -Raw scripts/demos/demo_1_simple_alert.json
Invoke-RestMethod -Method Post -Uri http://localhost:8088/responses -ContentType application/json -Body $body
```

Bash:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  --data @scripts/demos/demo_1_simple_alert.json
```

You should see a structured JSON response containing `suspected_root_causes`, `summary`, `comms`, and `post_incident_report` keys. Stop the server with `Ctrl+C`.

---

## 8. Deploy with Azure Developer CLI

`azd up` combines provisioning, packaging, and deployment in one command. It is equivalent to `azd provision`, `azd package`, and `azd deploy` run in sequence. If you have already provisioned, `azd up` skips unchanged infrastructure.

```bash
azd up
```

`azd up` performs the following steps:

1. Provisions infrastructure if it is not already present.
2. Builds the Docker image (using ACR remote build by default).
3. Pushes the image to Azure Container Registry.
4. Registers the hosted agent version with Foundry Agent Service.
5. Starts the container.

When the deployment completes, `azd` prints the agent playground URL and the agent endpoint. Save the endpoint, as you need it to call the agent programmatically.

The first deployment is slower because Docker pulls the base image layers. Subsequent deployments are faster.

The hosted agent incurs charges while it is deployed. Run `azd down` when you have finished testing to stop charges.

---

## 9. Verify and test the deployed agent

### 9.1 Check agent status

```bash
azd ai agent show oncall-copilot -o json
```

The `status` field should be `Started` (or `Running`, depending on `azd` version).

| Status | Meaning | Action |
|--------|---------|--------|
| Provisioning | Starting up. | Wait two to three minutes and check again. |
| Started or Running | Ready to use. | Continue. |
| Failed | Deployment error. | Run `azd deploy` to retry; check the portal logs. |
| Stopped | Manually stopped. | Start it again from the portal or with `az`. |
| Unhealthy | Container is crashing. | Inspect logs in the portal or with `azd ai agent logs`. |

### 9.2 Invoke the deployed endpoint

The deployed hosted agent uses the Responses API at:

```
{project_endpoint}/agents/{name}/endpoint/protocols/openai/v1/responses
```

For convenience, this repository provides a helper script that handles authentication, the Responses API body shape, and tenant-aware token acquisition:

```bash
python scripts/invoke.py --demo 1
python scripts/run_scenarios.py
```

Or run the automated verification script, which queries the agent metadata and runs a smoke test:

```bash
python scripts/verify_agent.py
```

### 9.3 Validate output schema offline

```bash
MOCK_MODE=true python scripts/validate.py
```

This validates the agent's JSON contract against the golden outputs without requiring Azure access.

---

## 10. Deploy with the Python SDK (CI/CD)

Use this path for automated pipelines or when you need fine-grained control over the image tag and the deployment definition.

### 10.1 Build and push the container image

If your developer machine is x86_64 (Windows or Linux), a normal `docker build` is sufficient. On Apple Silicon you must pass `--platform linux/amd64`, because Foundry runs `linux/amd64` images.

The simplest path is to build remotely in ACR, which works on every developer platform:

```bash
az acr build --registry <registry> --image oncall-copilot:v1 --file Dockerfile .
```

### 10.2 Grant `AcrPull`

The Foundry project's managed identity, and the account's managed identity, both need `AcrPull` on the registry. See the RBAC table in section 6.2.

### 10.3 Install SDK prerequisites

```bash
pip install "azure-ai-projects>=2.1.0" "azure-identity>=1.19,<2"
```

### 10.4 Set environment variables

Set, at minimum, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_OPENAI_ENDPOINT`, `ACR_IMAGE`, and `MODEL_ROUTER_DEPLOYMENT`.

### 10.5 Create the agent version

```bash
python scripts/deploy_sdk.py
```

The script uses `azure-ai-projects` 2.1.0 with `allow_preview=True`, builds a `HostedAgentDefinition` with a `ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES, version="1.0.0")`, and calls `client.agents.create_version(agent_name=..., definition=...)`.

### 10.6 Verify

```bash
python scripts/verify_agent.py
```

---

## 11. Migration guide: legacy AgentServer to Preview Hosted Agents

This section is for teams already running an `azure-ai-agentserver-core` based hosted agent who want to move onto Microsoft Agent Framework 1.2 and Foundry Hosted Agents.

### 11.1 At a glance

| Area | Original hosted agents | Foundry hosted agents (1.2) |
|------|------------------------|------------------------------|
| Server library | `azure-ai-agentserver-agentframework` | `agent-framework-foundry-hosting` |
| Chat client | `AzureOpenAIChatClient` | `FoundryChatClient` from `agent-framework-foundry` |
| Workflow API | `WorkflowBuilder` plus custom dispatch | `ConcurrentBuilder` plus `WorkflowBuilder.as_agent(...)` |
| Server entrypoint | `AgentServer().run(...)` | `ResponsesHostServer(agent).run(port=...)` |
| `agent.yaml` kind | `agent` | `hosted` |
| Protocol declaration | `protocol: openai-responses` | `protocols: [{ protocol: responses, version: 1.0.0 }]` |
| Project endpoint shape | `{project}/openai/responses` | `{project_endpoint}/agents/{name}/endpoint/protocols/openai/v1/responses` |
| Identity model | Project-level managed identity | Per-agent Entra identity plus project managed identity |
| Capability host | Implicit | Explicit `Agents` capability host on the account and the project |
| Region | Multiple | Australia East, Canada Central, North Central US, Sweden Central |
| Model Router co-location | Often split across projects | Recommended: single project, Sweden Central |

### 11.2 SDK-by-SDK breaking changes

#### `agent-framework` core (0.x to 1.2.0)

| Old | New |
|-----|-----|
| `AgentExecutor(name=, model=, instructions=)` | `Agent(client=FoundryChatClient(...), instructions=, name=)` |
| `WorkflowBuilder().add_executor(...).build()` | `ConcurrentBuilder().participants([...]).build()` for fan-out, or `WorkflowBuilder` for graphs |
| Workflow ran in process only | `workflow.as_agent(name=...)` to expose as a single Agent for hosting |

Construct one shared `FoundryChatClient` and pass it to every agent. Do not create a client per agent.

#### `agent-framework-foundry` (new, 1.2.0)

This package replaces the previous `azure-ai-agents` direct usage:

```python
from agent_framework_foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

chat_client = FoundryChatClient(
    project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"],
    credential=DefaultAzureCredential(),
)
```

Pitfalls:

* `model=` must be a deployment name in the Foundry project, not a model identifier. With Model Router this is `model-router`.
* `project_endpoint` is the project endpoint that ends in `/api/projects/<project>`, not the account endpoint that ends in `.cognitiveservices.azure.com`. Mixing these produces `401 Unauthorized` or `404 deployment not found`.
* API keys are not supported. Always use `DefaultAzureCredential`.

#### `agent-framework-foundry-hosting` (new, 1.0.0a)

This replaces the older Starlette-based entrypoint:

```python
from agent_framework_foundry_hosting import ResponsesHostServer

agent = workflow.as_agent(name="oncall-copilot")
ResponsesHostServer(agent).run(port=8088)
```

The previous `app = Starlette(...)` and `@app.on_event("startup")` patterns are gone. Do not import `starlette` or `fastapi` in `main.py` for hosted agents. Health probes are added by the host server, so do not register your own `/healthz`.

#### `agent-framework-orchestrations` (new, 1.0.0b)

```python
from agent_framework_orchestrations import ConcurrentBuilder

workflow = ConcurrentBuilder().participants([triage, summary, comms, pir]).build()
```

Each participant must be an `Agent` (post 1.2.0). Passing an `AgentExecutor` raises a `TypeError`. The merged output is the union of each agent's JSON keys; conflicts go to the last writer, so keep the agents' output keys disjoint.

#### `azure-ai-projects` (1.0.0bXX to 2.1.0)

`create_version` is only available on 2.1.0 or newer, and only when you pass `allow_preview=True`:

```python
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentProtocol,
    ContainerConfiguration,
    HostedAgentDefinition,
    ProtocolVersionRecord,
)

client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
    allow_preview=True,
)

definition = HostedAgentDefinition(
    protocol_versions=[ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES, version="1.0.0")],
    cpu="1",
    memory="2Gi",
    container_configuration=ContainerConfiguration(image="<acr>.azurecr.io/<repo>:<tag>"),
    environment_variables={...},
)
client.agents.create_version(agent_name="oncall-copilot", definition=definition)
```

| Old | New |
|-----|-----|
| `client.agents.create_agent(...)` | `client.agents.create_version(agent_name=, definition=...)` |
| Not applicable | `HostedAgentDefinition` |
| Not applicable | `AgentProtocol.RESPONSES` enum (do not pass strings) |
| `AIProjectClient(...)` | `AIProjectClient(..., allow_preview=True)` |
| Endpoint inferred | `{project_endpoint}/agents/{name}/endpoint/protocols/openai/v1/responses` |

#### `azure-identity`

Always use `DefaultAzureCredential()` with no positional `tenant_id`. The constructor signature is keyword-only in 1.19 and newer, and silently mis-binds otherwise.

For local Windows debugging, ensure that `AZURE_TENANT_ID` in `.env`, the `azd` environment, and `az account show` all match. Otherwise the cached CLI token is for a different tenant from the project's account.

#### Azure Developer CLI

| Old (1.10.x) | Preview (1.23 or newer) |
|--------------|-------------------------|
| `host: appservice` or `containerapp` | `host: azure.ai.agent` |
| `docker.remoteBuild: false` | `docker.remoteBuild: true` |
| Not applicable | `azd config set alpha.aiagent on` (one-time) |
| Not applicable | `agent.yaml` is the source of truth, referenced from `azure.yaml` |

#### `agent.yaml` schema

* `kind` is now required, and only `hosted` is supported in preview.
* `protocols` is a list of objects, not a list of strings, and each entry needs `protocol` and `version`.
* `version: "v1"` is rejected. Use semantic versioning, such as `1.0.0`.

#### Capability hosts (control plane, REST)

You need two capability hosts of kind `Agents`. The body for both is identical:

```json
{ "properties": { "capabilityHostKind": "Agents" } }
```

* Account scope: `PUT https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/capabilityHosts/accountcaphost?api-version=2025-06-01`
* Project scope: `PUT https://management.azure.com/.../accounts/{account}/projects/{project}/capabilityHosts/agents?api-version=2025-06-01`

Both must reach `provisioningState: Succeeded` before any `create_version` call. A missing project-scope host is the most common cause of `404 capability host not found`.

---

## 12. Top tips for migrating to Preview Hosted Agents

A practical, ordered checklist distilled from real migrations.

### 12.1 Region and topology

1. **Choose one region that supports both Hosted Agents and Model Router.** Today this is Sweden Central for almost all subscriptions. Cross-region project-to-model wiring works, but it adds 401 and timeout failure modes that you do not want during preview.
2. **Use one project, not two.** The original split (a hosted-agent project and a separate model project) is no longer necessary, and it doubles the RBAC surface area. Place the hosted agent and the `model-router` deployment in the same Foundry project.
3. **Start from a fresh project for the cutover.** Capability hosts and managed identities cannot be retrofitted reliably onto a project that previously hosted a v1 agent. Repair attempts repeatedly hit `500 server_error`.

### 12.2 Bootstrap order

Follow the ten-step sequence in section 6.1. The two most-skipped steps are the project-scope capability host (step 5) and granting `AcrPull` to both managed identities (step 8).

### 12.3 Identity and RBAC

4. **Always use managed identity, never API keys.** `FoundryChatClient` will silently fall back to AAD if you set `AZURE_OPENAI_API_KEY`, but the hosted runtime will not have it, so you will succeed locally and fail in the cloud.
5. **Grant `AcrPull` to both the project managed identity and the account managed identity.** During preview, the puller principal is unstable and can be either.
6. **Wait 30 seconds after granting `AcrPull` before the first `azd deploy`.** AAD propagation latency on `AcrPull` is the most common false-positive 500.

### 12.4 `.env` discipline

7. `AZURE_AI_PROJECT_ENDPOINT` must be the project endpoint, with the `/api/projects/<project>` suffix.
8. `AZURE_OPENAI_ENDPOINT` is the account endpoint, ending in `.cognitiveservices.azure.com`.
9. `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` and `MODEL_ROUTER_DEPLOYMENT` should both equal the Model Router deployment name (typically `model-router`). Setting only one of them works locally, but it breaks once you move from `FoundryChatClient` to the hosted runtime.
10. After every change to `.env`, run `azd env set <KEY> <VALUE> --environment <name>` for each key. The pipe-from-file PowerShell pattern silently drops keys.

### 12.5 Container

11. `python:3.12-slim` is the only base image currently validated by the Hosted Agents runtime.
12. Keep `EXPOSE 8088` and `CMD ["python", "main.py"]`. Do not parameterise the port through an environment variable.
13. Use ACR remote build (`az acr build`). Locally built images on Windows occasionally produce subtle `linux/amd64` mismatches that surface as `image pull backoff` after a clean `create_version`.

### 12.6 Validation

14. Validate locally first:
    ```bash
    python -c "from main import create_workflow; create_workflow().as_agent(name='probe')"
    ```
    The output should be an `Agent`-typed object.
15. Probe the data plane directly before `azd deploy`:
    ```python
    client.agents.create_version(agent_name="probe-only", definition=...)
    ```
    If this call and `azd deploy` produce the same error, the failure is service-side, not in your `azure.yaml`.
16. Capture every `request_id` from a 5xx response and attach all of them to the support case. The Hosted Agents preview debug pipeline correlates by request ID, not by subscription.

### 12.7 Don'ts

* Do not pin `azure-ai-projects` to a 1.0.0bXX release and expect `create_version` to be available.
* Do not pass `version="v1"` in `ProtocolVersionRecord`; preview rejects non-semantic versions.
* Do not put `azure-ai-agentserver-core` in `requirements.txt` alongside `agent-framework-foundry-hosting`. They conflict on `starlette`.
* Do not enable private endpoints on the account during preview. The hosted runtime cannot reach a privately networked AIServices account in the current build.
* Do not reuse a project that ever hosted a v1 agent. Cut a fresh one.
* Do not host a raw `WorkflowBuilder` workflow. `ResponsesHostServer` requires an `Agent`. Use `.as_agent(name=...)`.
* Do not put state on the local filesystem outside `$HOME` or the `/files` endpoint. Anything else is wiped when the session is deprovisioned (after 15 minutes of idle time).

### 12.8 When you hit `500 server_error` on `create_version`

Triage in this order before opening a support case.

1. Run `az resource show` against the project capability host. It must be `Succeeded` and `kind: Agents`. This is the most-common gap.
2. Run `az role assignment list` on the ACR scope. Both the project managed identity and the account managed identity must show `AcrPull`.
3. Confirm that `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` matches an actual deployment under the same project endpoint, and not the account endpoint.
4. Run the direct-SDK probe described in section 12.6, step 15. If it also returns 500, stop changing client configuration and file the support case with all request IDs.

---

## 13. Operations

### 13.1 Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes | The account endpoint for the AIServices resource. |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Yes | The model deployment name, typically `model-router`. |
| `AZURE_AI_PROJECT_ENDPOINT` | Yes | The full project endpoint URL. |
| `MODEL_ROUTER_DEPLOYMENT` | Yes | The Model Router deployment name. |
| `AZURE_TENANT_ID` | Recommended | Disambiguates token acquisition for local development. |
| `LOG_LEVEL` | No | Logging level. Defaults to `INFO`. |

These values are declared in `agent.yaml` and injected by Foundry at container startup. For local development, export them with `azd env get-values > .env`.

### 13.2 Authentication

In production, the container uses `DefaultAzureCredential` with the project's managed identity. No API keys or secrets are needed:

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

credential = DefaultAzureCredential()
token_provider = get_bearer_token_provider(
    credential, "https://cognitiveservices.azure.com/.default"
)
```

For local development, `DefaultAzureCredential` picks up your `az login` session.

### 13.3 Scaling

```yaml
scale:
  maxReplicas: 3
  minReplicas: 1
```

| Scenario | minReplicas | maxReplicas |
|----------|-------------|-------------|
| Development or test | 0 | 1 |
| Production, low traffic | 1 | 3 |
| Production, high traffic | 2 | 10 |

`minReplicas: 1` keeps one instance warm and avoids cold starts.

### 13.4 Model Router capacity sizing

Each On-Call Copilot request triggers four concurrent Model Router calls. If you expect `N` concurrent users, set the deployment capacity to at least `N x 4`.

### 13.5 Updating the agent

To change agent code or instructions, edit the relevant file (typically `app/agents/<name>.py`), rebuild, and redeploy:

```bash
azd up
```

For an SDK-driven update, build a new image tag, set `ACR_IMAGE` to the new tag, and run `python scripts/deploy_sdk.py`. Instructions are baked into the image, so no infrastructure changes are required for an instruction-only update.

To add a new agent:

1. Create `app/agents/<name>.py` with a `*_INSTRUCTIONS` constant.
2. Add the new output keys to `app/schemas.py`.
3. Register the new agent in `main.py`:
   ```python
   new_agent = Agent(
       client=chat_client,
       instructions=NEW_INSTRUCTIONS,
       name="new-agent",
   )
   workflow = ConcurrentBuilder().participants([triage, summary, comms, pir, new_agent]).build()
   ```
4. Rebuild and redeploy the container.

### 13.6 Foundry portal playground

The fastest way to interact with a deployed agent is through the Foundry portal at `https://ai.azure.com/`:

1. Sign in and select your project.
2. From the left navigation, choose **Build**, then **Agents**.
3. Select `oncall-copilot` from the list.
4. Click **Open in playground**.
5. Paste an incident JSON payload into the chat input and press Enter.

The playground link is also printed by `azd up` after a successful deployment.

### 13.7 Deploy from VS Code

You can deploy from VS Code using the Microsoft Foundry extension. Install it from the marketplace, sign in, set a default project, then right-click the project in the Foundry Explorer and choose **Deploy Hosted Agent**. After deployment, click **Open in Playground** to test.

---

## 14. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `create_version` returns `500 server_error` despite valid configuration | Project-scope `Agents` capability host missing, or service-side regression | Verify both capability hosts (`accountcaphost` on the account and `agents` on the project) are `Succeeded`. If both are healthy and the error persists across requests, capture the `request_id` and open a Microsoft support case. |
| `RESPONSE 401: AADSTS500011` from the agent at runtime | Cross-project model access | Move Model Router into the same project as the hosted agent, or grant the per-agent identity `Azure AI User` on the other project's account scope. A single project is simpler. |
| `RESPONSE 404: agent ... version N not found` | `azd deploy` failed before version creation but `azd ai agent show` was run anyway | Re-run `azd deploy` and watch for the version-create step. |
| Container starts and then fails readiness | Missing dependency in `requirements.txt`, for example `agent-framework-foundry` | Add the package, rebuild, and redeploy. The hosted runtime does not install missing packages for you. |
| `MODEL_ROUTER_DEPLOYMENT` works locally but returns 404 in the cloud | The deployment lives in a different account from `AZURE_AI_PROJECT_ENDPOINT` | Make `AZURE_OPENAI_ENDPOINT` and `AZURE_AI_PROJECT_ENDPOINT` point at the same account and project. |
| `azd deploy` succeeds but `/responses` returns 500 on the first call | Cold start exceeded the readiness window | Re-invoke. Sessions are provisioned on the first use and reuse warm compute for 15 minutes. |
| `SubscriptionNotRegistered` | Resource provider not registered | `az provider register --namespace Microsoft.CognitiveServices`. |
| `AuthorizationFailed` during `azd provision` | Missing Contributor role | Request Contributor on your subscription or resource group. |
| `AuthenticationError` or `DefaultAzureCredential` failure | Stale login session | Run `az login` and `azd auth login` again. |
| `UnauthorizedAcrPull` (403) or `InvalidAcrPullCredentials` (401) | The managed identity is missing the registry role | Grant `AcrPull` to both the project and account managed identities on the ACR scope. |
| `403 Forbidden` from the deployed endpoint | Hosted-agent capability not enabled | Ensure both `Agents` capability hosts are present and `Succeeded`. |
| Model not found in the catalogue | Model unavailable in your region | Edit `agent.yaml` to use a model that is available in your region, or move to Sweden Central. |

---

## 15. Cleanup

The commands below permanently delete all Azure resources created for this deployment, including the Foundry project, the Container Registry, Application Insights, and the hosted agent. This action cannot be undone.

Preview what will be deleted:

```bash
azd down --preview
```

Delete:

```bash
azd down
```

The cleanup process takes between two and five minutes. To verify, open the Azure portal, navigate to your resource group, and confirm that the resources are no longer present.

To remove only the agent registration (SDK path):

```bash
python scripts/deploy_sdk.py --delete
```

---

## 16. Reference

* Hosted Agents concepts: <https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents>
* Quickstart: <https://learn.microsoft.com/azure/foundry/agents/quickstart-hosted-agents>
* Microsoft Agent Framework: <https://github.com/microsoft/agent-framework>
* Foundry samples: <https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents>
* Microsoft Foundry Model Router: <https://learn.microsoft.com/azure/ai-foundry/openai/how-to/model-router>
* `AGENTS.md` in this repository: agent architecture and customisation guide.
* `docs/CONFIGURATION.md` in this repository: agent instruction configuration reference.
