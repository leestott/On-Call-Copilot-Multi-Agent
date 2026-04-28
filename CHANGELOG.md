# Changelog

All notable changes to On-Call Copilot are documented here.

---

## [2026-04-28]

### Added
- **`docs/MIGRATION.md`**: New migration guide for moving from Azure AI AgentServer hosted agents to Microsoft Foundry Hosted Agents on Microsoft Agent Framework 1.2 — covering code changes, `agent.yaml`/`azure.yaml`, infrastructure bootstrap order, required RBAC, validation, and common troubleshooting.
- **Azure Container Registry**: Fresh ACR in Sweden Central with `oncall-copilot:agent-framework-1.2.0` image and AcrPull granted to the project managed identities.

### Changed
- **Single-project Sweden Central topology**: Consolidated hosted agent and Model Router into a single Foundry project in Sweden Central — the only region currently supporting both Hosted Agents preview and Model Router.
- **Environment retargeted** to the new Sweden Central project endpoint with `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=model-router`.

### Deployed
- **Hosted Agent version 1 deployed successfully** via `azd deploy`. The previously known service-side `create_version` 500 error has been resolved. Agent confirmed active via `scripts/verify_agent.py` with all four specialist agents responding correctly.
- **End-to-end validation**: UI server tested with all 8 incident payloads (3 demos + 5 scenarios) with full structured output.

### Fixed
- **UI server authentication (`ui/server.py`)**: Changed from `InteractiveBrowserCredential`-only to trying `AzureCliCredential` first (uses existing `az login` session), with fallback to `InteractiveBrowserCredential`. Resolves 403 errors when the interactive browser identity lacks `agents/action` permissions.
- **UI server `NameError` (`ui/server.py`)**: Added missing `agent_version` variable assignment in `_invoke_agent()` — was referenced in the request URL construction but never defined, causing a crash on every invocation.
- **UI server concurrency (`ui/server.py`)**: Replaced single-threaded `HTTPServer` with `ThreadedHTTPServer` (using `ThreadingMixIn`) so the UI remains responsive while long-running agent calls are in flight.

### Resolved
- **Service-side `create_version` 500 error** (previously listed as Known Issue): The Hosted Agents preview regression has been fixed by Microsoft. Deployment via `azd deploy` now succeeds on the first attempt.

---

## [2026-04-27]

### Fixed
- **Hosted-agent invocation**: Restored `scripts/invoke.py` to use the hosted agent endpoint route with Responses protocol version `1.0.0`.
- **Cross-project Model Router access**: Added documentation for granting hosted-agent managed identities access to the Model Router project.
- **Documentation correctness**: Updated Markdown references for the current Agent Framework stack.

### Changed
- **Microsoft Agent Framework upgrade**: Migrated the hosted entrypoint to the current Agent Framework stack using `Agent`, `FoundryChatClient`, `ConcurrentBuilder`, and `ResponsesHostServer`.
- **Deployment configuration**: Split hosted-agent and model-project configuration with `AZURE_AI_PROJECT_ENDPOINT` and `AZURE_MODEL_PROJECT_ENDPOINT`.
- **Container build**: Updated the Dockerfile to install `requirements.txt` explicitly from `python:3.12-slim`.
- **Repository hygiene**: Hardened ignored local files and Docker build context for public sharing.

---

## [2026-03-18]

### Fixed
- **Starlette compatibility pin** (`requirements.txt`): Added `starlette>=0.36.0,<1.0.0` to prevent startup failure with Starlette 1.0 breaking changes.

---

## [2026-03-02]

### Changed
- **`Hosting_Agent.md`**: Major revision — 360 lines added, 156 removed. Updated hosting and deployment guidance for the Foundry hosted-agent workflow.

---

## [2026-02-27]

### Changed
- **`README.md`**: Updated branding references from Azure AI Foundry to Microsoft Foundry.

---

## [2026-02-26]

### Added
- **`AGENTS.md`**: Full multi-agent architecture reference added (255 lines) — documents all four specialist agents (Triage, Summary, Comms, PIR), their output schemas, orchestration via `ConcurrentBuilder`, and the output merge contract.
- **`Hosting_Agent.md`**: New guide (604 lines) covering end-to-end deployment of the hosted agent to Microsoft Foundry including Docker, ACR, and `agent-dev-cli` workflows.
- **`scripts/test_all_demos.py`**: New script (114 lines) that runs all 8 incident scenarios (3 demos + 5 scenarios) against the UI server.
- **`scripts/test_one.py`**: New helper script (19 lines) for running a single scenario.
- **`.env.example`**: Added 47-line example environment file documenting all required environment variables.
- **`.vscode/mcp.json`**: Added VS Code MCP server configuration.

### Changed
- **`CONTRIBUTING.md`**: Extended contributing guide with additional workflow detail.
- **`scripts/invoke.py`**: Updated invocation script with revised argument handling.
- **`scripts/scenarios/README.md`**: Updated scenario documentation.
- **`scripts/scenarios/scenario_4_minimal_alert.json`**: Updated minimal alert scenario payload.
- **`ui/server.py`**: Extended UI server with improved request handling and endpoint configuration.
- **`docs/blog_post.md`**: Revised and expanded blog post content.
- **`app/main.py`**: Minor additions to application startup.
- **`main.py`**: Minor additions to entry-point startup.
- **`requirements.txt`**: Dependency updates.
- **`README.md`**: Comprehensive rewrite — restructured setup, configuration, testing, and architecture sections. Consolidated and compressed existing content.
- **`docs/architecture.excalidraw`**: Architecture diagram updated.
- **`docs/screenshots/`**: Screenshot assets reorganised — old per-panel screenshots under `ui/` subfolder removed; consolidated set published at top-level `screenshots/`.

---

## [2026-02-18]

### Added
- **`ui/index.html`**: Full web UI (1 479 lines) — four-panel results view with Triage, Summary, Comms, and PIR panels; Quick Load presets for 3 demos and 5 scenarios; JSON editor with validation; live status bar.
- **`ui/server.py`**: Static-file and proxy server (258 lines) for the web UI using `InteractiveBrowserCredential`.
- **`scripts/make_demo_video.py`**: Automated demo-video generation script (397 lines) using Playwright.
- **`docs/blog_post.md`**: Technical blog post describing the architecture and design decisions.
- **`docs/screenshots/`**: Full screenshot set for README and documentation (17 UI screenshots + model router and model selection screenshots).
- **`docs/demo_ui.mp4`**: Recorded demo video.

### Changed
- **`README.md`**: Major expansion — added UI walkthrough, Foundry Playground screenshots, architecture diagram updates, and additional setup instructions.
- **`docs/architecture.excalidraw`**: Architecture diagram substantially revised.

### Initial release — [2026-02-18, commit `06b7034`]

First public commit establishing the full project:

- **Four specialist agents** (`app/agents/`): `triage.py`, `summary.py`, `comms.py`, `pir.py` — each with its own system-prompt instructions and designated JSON output keys.
- **Orchestrator** (`main.py`, `app/main.py`): `ConcurrentBuilder` wiring all four agents via `asyncio.gather()`; JSON fragment merge with telemetry injection.
- **Schema validation** (`app/schemas.py`): Pydantic models for all agent output keys.
- **Mock router** (`app/mock_router.py`): Local `MOCK_MODE` responses for schema-only validation without Azure.
- **Prompting utilities** (`app/prompting.py`), **telemetry** (`app/telemetry.py`).
- **Agent definition** (`agent.yaml`): Declarative hosted-agent registration for Foundry Responses API on port 8088.
- **Infrastructure** (`infra/main.bicep`, `azure.yaml`): Minimal Bicep stub and `azd` configuration.
- **Dockerfile**: Multi-stage container build.
- **Scripts**: `invoke.py`, `run_scenarios.py`, `validate.py`, `verify_agent.py`, `deploy_sdk.py`, `get_logs.py`, local test helpers (`test_local.http`, `test_local.ps1`, `test_local.sh`).
- **Scenarios**: 5 JSON incident scenarios + 3 demos; 5 golden output files for schema validation.
- **Documentation**: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/CONFIGURATION.md`, `scripts/SCENARIOS.md`.
