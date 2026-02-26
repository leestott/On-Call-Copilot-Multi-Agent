# Agents

This document describes the multi-agent architecture of On-Call Copilot: how the agents are orchestrated, what each specialist does, and how to extend or customize them.

---

## Overview

On-Call Copilot uses **four specialist agents** running **concurrently** via `ConcurrentBuilder` from the Microsoft Agent Framework. Each agent receives the full incident payload, processes it through Azure OpenAI Model Router, and returns a JSON fragment covering its designated output keys. The orchestrator merges all fragments into a single unified response.

```
                         Incident JSON
                              │
                              ▼
                    ┌───────────────────┐
                    │  OncallCopilotAgent│
                    │  (orchestrator)    │
                    └────────┬──────────┘
                             │
              asyncio.gather() — all 4 run in parallel
           ┌─────────┬──────┴──────┬──────────┐
           ▼         ▼            ▼          ▼
      ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────────┐
      │ Triage  │ │ Summary │ │ Comms  │ │  PIR   │
      │ Agent   │ │ Agent   │ │ Agent  │ │ Agent  │
      └────┬────┘ └────┬────┘ └───┬────┘ └───┬────┘
           │           │          │           │
           └───────────┴──────────┴───────────┘
                              │
                     Merge JSON fragments
                              │
                              ▼
                    Structured JSON response
```

All agents share a single **Model Router** deployment (`AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=model-router`). Model Router automatically routes each request to the best model based on prompt complexity — no model-selection logic is needed in agent code.

---

## Agent Reference

### Triage Agent

| Property | Value |
|----------|-------|
| **Name** | `triage-agent` |
| **File** | [`app/agents/triage.py`](app/agents/triage.py) |
| **Role** | Root cause analysis, immediate actions, missing data identification, runbook alignment |

**Output keys:**

| Key | Type | Description |
|-----|------|-------------|
| `suspected_root_causes` | array | Each entry has `hypothesis` (string), `evidence` (string array), `confidence` (0–1 float) |
| `immediate_actions` | array | Each entry has `step` (string), `owner_role` (string), `priority` (P0–P3) |
| `missing_information` | array | Each entry has `question` (string), `why_it_matters` (string) |
| `runbook_alignment` | object | `matched_steps` (string array), `gaps` (string array) |

**Guardrails:**
- Secrets are redacted as `[REDACTED]`
- Insufficient data → `confidence: 0` and `missing_information` populated (no hallucination)
- Sparse incidents get diagnostic steps in `immediate_actions` rather than remediation

---

### Summary Agent

| Property | Value |
|----------|-------|
| **Name** | `summary-agent` |
| **File** | [`app/agents/summary.py`](app/agents/summary.py) |
| **Role** | Concise incident narrative for SRE teams |

**Output keys:**

| Key | Type | Description |
|-----|------|-------------|
| `summary.what_happened` | string | 2–4 sentence factual summary: trigger event, affected services, failure mode, scope |
| `summary.current_status` | string | Prefixed with `ONGOING` / `MITIGATED` / `MONITORING` / `RESOLVED` plus brief detail |

**Behaviour:**
- Presence of `timeframe.end` → resolved status
- No `end` timestamp → ongoing unless other signals indicate otherwise

---

### Comms Agent

| Property | Value |
|----------|-------|
| **Name** | `comms-agent` |
| **File** | [`app/agents/comms.py`](app/agents/comms.py) |
| **Role** | Audience-appropriate incident communications |

**Output keys:**

| Key | Type | Description |
|-----|------|-------------|
| `comms.slack_update` | string | Slack-formatted message with emoji, severity, status, impact, next steps |
| `comms.stakeholder_update` | string | Non-technical executive summary: business impact, customer effect, resolution status |

**Slack emoji conventions:**

| Condition | Emoji |
|-----------|-------|
| Active SEV1/SEV2 | `:rotating_light:` |
| Degraded | `:warning:` |
| Resolved | `:white_check_mark:` |

**Stakeholder update rules:**
- No jargon or unexplained acronyms
- Focus on customer experience and business impact
- Blameless tone

---

### PIR Agent

| Property | Value |
|----------|-------|
| **Name** | `pir-agent` |
| **File** | [`app/agents/pir.py`](app/agents/pir.py) |
| **Role** | Post-incident report: timeline reconstruction, customer impact, prevention actions |

**Output keys:**

| Key | Type | Description |
|-----|------|-------------|
| `post_incident_report.timeline` | array | Each entry has `time` (HH:MMZ or ISO) and `event` (string), chronologically ordered |
| `post_incident_report.customer_impact` | string | Quantified impact: users affected, error rates, revenue estimates |
| `post_incident_report.prevention_actions` | array | Specific, actionable measures with suggested owner roles |

**Behaviour:**
- Timeline is reconstructed from `alerts`, `logs`, and `metrics` timestamps
- Ongoing incidents end with `{"time": "ONGOING", "event": "..."}`
- Incidents with no customer impact state so explicitly
- Prevention actions are specific (name the system/config/process to change)

---

## Orchestration

### Entry Point

The orchestrator is defined in [`main.py`](main.py):

```python
from agent_framework import ConcurrentBuilder
from agent_framework.azure import AzureOpenAIChatClient

workflow = ConcurrentBuilder().participants([triage, summary, comms, pir])
```

`ConcurrentBuilder` runs all four agents via `asyncio.gather()` — each agent processes the full incident independently and returns its JSON fragment. The orchestrator merges all fragments with `merged.update(agent_output)` and injects a `telemetry` block.

### Hosted Agent Definition

The agent is defined declaratively in [`agent.yaml`](agent.yaml):

```yaml
kind: hosted
name: oncall-copilot
protocols:
  - protocol: responses
```

This registers the agent with the Foundry Responses API protocol on port 8088.

### Authentication

- **Production**: `DefaultAzureCredential` with managed identity (no API keys)
- **Local development**: `az login` session via `DefaultAzureCredential`
- **UI server**: `InteractiveBrowserCredential` with scope `https://ai.azure.com/.default`

---

## Output Merge

Each agent returns a JSON fragment with its designated keys. The orchestrator merges them into a single response:

```json
{
  "suspected_root_causes": [...],     // from Triage Agent
  "immediate_actions": [...],         // from Triage Agent
  "missing_information": [...],       // from Triage Agent
  "runbook_alignment": {...},         // from Triage Agent
  "summary": {...},                   // from Summary Agent
  "comms": {...},                     // from Comms Agent
  "post_incident_report": {...},      // from PIR Agent
  "telemetry": {                      // injected by orchestrator
    "correlation_id": "...",
    "model_router_deployment": "...",
    "selected_model_if_available": null,
    "tokens_if_available": null
  }
}
```

---

## Customising Agents

### Changing Agent Behaviour

Each agent's instructions are a plain Python string constant (`*_INSTRUCTIONS`) in its source file. To modify behaviour:

1. Edit the instruction string in `app/agents/<name>.py`
2. Test locally with `python scripts/invoke.py --demo 1`
3. Rebuild and redeploy the container

No Python code changes are needed — only the instruction text.

### Adding a New Agent

1. Create `app/agents/<name>.py` with an `*_INSTRUCTIONS` constant following the existing pattern
2. Add the agent's output keys to [`app/schemas.py`](app/schemas.py)
3. Register it in [`main.py`](main.py):
   ```python
   new_agent = AzureOpenAIChatClient(ad_token_provider=_token_provider).create_agent(
       instructions=NEW_INSTRUCTIONS,
       name="new-agent",
   )
   workflow = ConcurrentBuilder().participants([triage, summary, comms, pir, new_agent])
   ```
4. Add a mock response in [`app/mock_router.py`](app/mock_router.py) for local validation
5. Add a golden output file in `scripts/golden_outputs/`

### Configuration Reference

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for detailed configuration options for the Comms and PIR agents, including output format customization, adding new output fields, and tone adjustments.

---

## Testing Agents

| Command | What it tests |
|---------|---------------|
| `python scripts/invoke.py --demo 1` | Single demo against live Foundry agent |
| `python scripts/run_scenarios.py` | All 5 scenarios against live Foundry agent |
| `python scripts/test_all_demos.py` | All 8 incidents via UI server (3 demos + 5 scenarios) |
| `MOCK_MODE=true python scripts/validate.py` | Schema validation against golden outputs (no Azure needed) |

---

## Design Principles

| Principle | Implementation |
|-----------|---------------|
| **Parallel execution** | `asyncio.gather()` cuts latency 3–4× vs sequential |
| **JSON-only output** | Every agent returns pure JSON — trivially mergeable |
| **No hardcoded models** | Single Model Router deployment handles model selection |
| **Separation of concerns** | Each agent owns distinct output keys — no overlap |
| **Instructions as config** | Agent behaviour is a text string, not code logic |
| **No hallucination** | Sparse data → `confidence: 0` + `missing_information` |
| **Secret redaction** | Credential patterns scrubbed before reaching model output |
