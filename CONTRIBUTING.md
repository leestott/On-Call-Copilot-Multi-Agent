# Contributing to On-Call Copilot

Thank you for your interest in contributing! This project is a reference implementation for Microsoft Agent Framework with Microsoft Foundry Hosted Agents. Contributions that improve the sample, fix bugs, or add new scenarios are welcome.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Adding New Scenarios](#adding-new-scenarios)
- [Adding New Agents](#adding-new-agents)
- [Pull Request Checklist](#pull-request-checklist)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

This project adheres to the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). By participating, you agree to abide by it. Please report any unacceptable behavior to [opencode@microsoft.com](mailto:opencode@microsoft.com).

---

## Getting Started

1. **Fork** the repository and create a feature branch from `main`.
2. Make your changes on the feature branch.
3. Submit a **pull request** against `main`.

---

## Development Setup

### Prerequisites

- Python 3.12+
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli)
- A Microsoft Foundry project (for live testing)

### Local Setup

```bash
# Clone (or your fork)
git clone https://github.com/<org>/on-call-copilot.git
cd on-call-copilot

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Running Locally (Mock Mode)

The recommended way to test prompt/schema changes without deploying:

```bash
# Terminal 1 — start mock router
python app/mock_router.py

# Terminal 2 — submit a test scenario
python scripts/validate.py
# or using the .http file with VS Code REST Client:
# open scripts/test_local.http
```

### Running Against Foundry (Live Mode)

Set the required environment variables, then invoke the deployed agent:

```bash
# Copy the template and fill in your values
cp .env.example .env   # (create this from the env vars listed in README.md)

# Invoke with a custom prompt
python scripts/invoke.py --prompt "CPU alert: node cpu-pool-1 at 95% for 30 min"

# Run all 5 built-in scenarios
python scripts/run_scenarios.py
```

---

## Project Structure

```
on-call-copilot/
├── app/
│   ├── agents/          # One file per specialist agent
│   │   ├── triage.py    # TriageAgent — priority + affected services
│   │   ├── summary.py   # SummaryAgent — human-readable summary
│   │   ├── comms.py     # CommsAgent — stakeholder messages
│   │   └── pir.py       # PIRAgent — post-incident review template
│   ├── main.py          # ConcurrentBuilder orchestrator entrypoint
│   ├── schemas.py       # JSON schema validation for all agent outputs
│   ├── prompting.py     # Shared prompt construction helpers
│   ├── mock_router.py   # Local mock for OpenAI Responses API
│   └── telemetry.py     # OpenTelemetry setup
├── scripts/
│   ├── scenarios/       # Incident scenario JSON files (used by run_scenarios.py)
│   ├── golden_outputs/  # Expected outputs for validation
│   ├── deploy_sdk.py    # Deploy agent to Foundry via SDK
│   ├── invoke.py        # Invoke deployed agent
│   ├── run_scenarios.py # Batch scenario runner
│   ├── verify_agent.py  # Smoke-test deployed agent
│   └── validate.py      # Schema validation against golden outputs
├── infra/
│   └── main.bicep       # Azure infrastructure (Foundry project, container app)
├── Dockerfile
├── agent.yaml           # Declarative agent definition
└── azure.yaml           # azd configuration
```

---

## Making Changes

### Code Style

- Use [**ruff**](https://docs.astral.sh/ruff/) for linting: `ruff check .`
- Format with [**black**](https://black.readthedocs.io/): `black .`
- Add type annotations to new functions and methods.
- Keep individual files under 250 lines; split if they grow larger.

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) convention:

```
feat: add DatabaseAgent for runbook DB lookups
fix: remove trailing period from default prompt (gateway 400)
docs: update README quickstart section
refactor: extract build_incident_prompt to prompting.py
```

---

## Adding New Scenarios

Scenario files live in `scripts/scenarios/` and are plain JSON matching the format the agent accepts. To add a new scenario:

1. Create `scripts/scenarios/scenario_<N>_<description>.json`:

    ```json
    {
      "incident_id": "INC-2026-NNNN",
      "title": "Short description of the incident",
      "severity": "SEV1",
      "timeframe": { "start": "2026-03-01T10:00:00Z", "end": null },
      "alerts": [
        { "name": "AlertName", "description": "...", "timestamp": "..." }
      ],
      "logs": [
        { "source": "service-name", "lines": ["ERROR ..."] }
      ],
      "metrics": [
        { "name": "metric_name", "window": "5m", "values_summary": "..." }
      ],
      "runbook_excerpt": "Step 1: ...",
      "constraints": {
        "max_time_minutes": 15,
        "environment": "production",
        "region": "eastus2"
      }
    }
    ```

2. Optionally add a matching golden output to `scripts/golden_outputs/INC-2026-NNNN.json` for validation.

3. Run `python scripts/run_scenarios.py --list` to confirm it is discovered.

4. Run `python scripts/run_scenarios.py --scenario <N>` to test it live.

---

## Adding New Agents

All specialist agents live in `app/agents/`. Each agent is a pure Python class that accepts the incident payload and returns a typed schema-validated dict. To add a new agent:

1. **Create `app/agents/<name>.py`** following the existing pattern:

    ```python
    from azure.ai.agents.models import ...
    
    SYSTEM_PROMPT = """You are ..."""
    
    class MyAgent:
        name = "my-agent"
        instructions = SYSTEM_PROMPT
    
        def build_messages(self, incident: dict) -> list[dict]:
            ...
    ```

2. **Add the output schema** to `app/schemas.py`.

3. **Register the agent** in `app/main.py`:

    ```python
    from app.agents.myagent import MyAgent
    builder.participants([..., MyAgent()])
    ```

4. **Add mock response** to `app/mock_router.py` if you want `validate.py` to exercise it.

5. **Add a golden output file** for CI validation.

---

## Pull Request Checklist

Before submitting a PR, please verify:

- [ ] `ruff check .` passes with no errors
- [ ] `black --check .` passes
- [ ] No hardcoded endpoints, resource names, or subscription IDs
- [ ] No credentials, API keys, or secrets in code or test fixtures
- [ ] New scripts read config from environment variables (not `sys.argv` defaults that expose internals)
- [ ] `python scripts/validate.py` passes in mock mode
- [ ] New scenarios include a golden output file (or clearly note why not)
- [ ] Documentation updated (README, docstrings) if the public interface changed
- [ ] `SECURITY.md` reviewed — confirm change does not introduce new attack surface

---

## Reporting Issues

- Search [existing issues](../../issues) before opening a new one.
- For **security vulnerabilities**, see [SECURITY.md](SECURITY.md) — do **not** open a public issue.
- For **bugs**, provide: OS, Python version, full error traceback, and the command you ran.
- For **feature requests**, describe the use case and what success looks like.

We appreciate your time and effort in making this sample better!
