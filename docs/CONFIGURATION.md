# Agent Configuration Guide

This document covers the configuration of the **Comms Agent** and **PIR Agent** — the two output-facing specialist agents in the On-Call Copilot pipeline. It also provides a full reference for all four agents.

---

## Overview

All four specialist agents are defined as plain Python strings (`*_INSTRUCTIONS`) in `app/agents/`. Each constant is injected as the `system` prompt when the agent is created via `AzureOpenAIChatClient`. To change agent behaviour, edit the corresponding instruction constant and rebuild/redeploy the container.

| Agent | File | Output keys |
|-------|------|-------------|
| Triage | [app/agents/triage.py](../app/agents/triage.py) | `suspected_root_causes`, `immediate_actions`, `missing_information`, `runbook_alignment` |
| Summary | [app/agents/summary.py](../app/agents/summary.py) | `summary.what_happened`, `summary.current_status` |
| **Comms** | [app/agents/comms.py](../app/agents/comms.py) | `comms.slack_update`, `comms.stakeholder_update` |
| **PIR** | [app/agents/pir.py](../app/agents/pir.py) | `post_incident_report.timeline`, `post_incident_report.customer_impact`, `post_incident_report.prevention_actions` |

All agents run concurrently via `ConcurrentBuilder` and each returns a **JSON-only** response — no prose, no markdown wrapping.

---

## Comms Agent

**File:** [app/agents/comms.py](../app/agents/comms.py)

### Purpose

Translates raw incident signals into two audience-appropriate communications:
- A Slack channel update for the on-call engineering team
- A stakeholder summary for executives and product managers

### Output Schema

```json
{
  "comms": {
    "slack_update": "<string>",
    "stakeholder_update": "<string>"
  }
}
```

### Slack Update Format

| Element | Detail |
|---------|--------|
| Emoji prefix | `:rotating_light:` for active SEV1/2, `:warning:` for degraded, `:white_check_mark:` for resolved |
| Required fields | Incident ID, severity, one-line summary, affected services, next update ETA |
| Tone | Calm, factual, action-oriented |

Example output for an active SEV1:
```
:rotating_light: *SEV1 ACTIVE* | INC-2024-0847
*Summary:* Checkout API degraded — P95 latency 8s, 62% requests timing out
*Services:* checkout-api, order-service (AKS us-east-1)
*Status:* Investigating AZ node capacity exhaustion
*Next update:* 14:30 UTC
```

### Stakeholder Update Format

| Element | Detail |
|---------|--------|
| Audience | Executives, product managers — no technical jargon |
| Focus | Customer experience, business impact, what the team is doing, next update time |
| Prohibited | Blame language, acronyms without explanation, raw log/metric data |

### Configuration Options

| Behaviour | How to change |
|-----------|--------------|
| Emoji set for Slack | Edit the emoji prefix rules in `COMMS_INSTRUCTIONS` |
| Add a third channel (e.g. Teams) | Add a third key to the output schema in `COMMS_INSTRUCTIONS` and handle the new key in downstream consumers |
| Change update interval wording | Edit the "next update" guidance text |
| Enforce message length limit | Add a character-count constraint to the guidelines section |
| Add incident priority/SLA language | Add a "Priority" line to the Slack format rules |

### Customisation Example

To add a `pagerduty_note` field alongside the existing keys, update the task block in `COMMS_INSTRUCTIONS`:

```python
COMMS_INSTRUCTIONS = """\
...
## Task
Return a single JSON object with ONLY this key:

{
  "comms": {
    "slack_update": "...",
    "stakeholder_update": "...",
    "pagerduty_note": "string – one-line note for PagerDuty incident timeline"
  }
}
...
"""
```

---

## PIR Agent

**File:** [app/agents/pir.py](../app/agents/pir.py)

### Purpose

Constructs a post-incident report from resolved or partially-resolved incident signals. Produces a structured timeline, quantified customer impact, and actionable prevention measures.

> The PIR Agent is only meaningful when the incident payload contains sufficient signal history. Use demo 3 (`scripts/demos/`) or scenario 5 (`scripts/scenarios/`) for best results.

### Output Schema

```json
{
  "post_incident_report": {
    "timeline": [
      { "time": "HH:MMZ or ISO 8601", "event": "<string>" }
    ],
    "customer_impact": "<string>",
    "prevention_actions": [
      "<string>"
    ]
  }
}
```

### Timeline Construction

| Rule | Detail |
|------|--------|
| Source | Derived from `alerts[].timestamp`, `logs[].timestamp`, `metrics[].timestamp` in input |
| Ordering | Strictly chronological; earliest signal is the start anchor |
| Ongoing incidents | Final entry uses `"time": "ONGOING"` |
| Time format | Prefer `HH:MMZ` for same-day incidents; ISO 8601 for multi-day |

### Customer Impact

The agent is instructed to quantify impact wherever the input data supports it:

| Data present | Expected output |
|---|---|
| `revenue_impact` in payload | Dollar figure included verbatim |
| Error rate metrics | Percentage quoted |
| Affected service with SLA | Impact framed against SLA |
| No customer-facing impact | Explicit "No customer-visible impact" statement |

### Prevention Actions

Each prevention action should be:
- **Specific** — names the exact system, config, or process to change
- **Actionable** — describes the change, not just the goal
- **Owned** — suggests a responsible role (e.g. `Platform Engineering`, `DBA`, `SRE`)

Example:
```
"Add Redis maxmemory-policy alert at 70% threshold – owner: Platform Engineering"
```

### Configuration Options

| Behaviour | How to change |
|-----------|--------------|
| Number of prevention actions | Add `"Provide at least N prevention actions"` to the guidelines |
| Timeline timestamp format | Specify format preference in the Timeline guidelines section |
| Include root cause section | Add `"root_cause": "string"` to the output schema in `PIR_INSTRUCTIONS` |
| Suppress revenue data | Add `"Do not include revenue estimates"` to guidelines |
| Add blameless postmortem framing | Add a tone guideline: `"Use blameless postmortem language throughout"` |
| Add a lessons-learned section | Extend the schema with `"lessons_learned": ["string"]` |

### Customisation Example

To add a `root_cause` field and enforce blameless language:

```python
PIR_INSTRUCTIONS = """\
...
## Task
Return a single JSON object with ONLY this key:

{
  "post_incident_report": {
    "timeline": [...],
    "root_cause": "string – concise description of the confirmed root cause",
    "customer_impact": "...",
    "prevention_actions": [...]
  }
}

## Guidelines
...
- **Blameless language**: Focus on systems and processes, not individuals.
- **Root cause**: State the confirmed root cause. If not yet confirmed, write
  \"Under investigation\" and list the leading hypotheses.
...
"""
```

---

## Triage Agent (reference)

**File:** [app/agents/triage.py](../app/agents/triage.py)

Output keys: `suspected_root_causes` (array with `hypothesis`, `evidence`, `confidence`), `immediate_actions` (array with `step`, `owner_role`, `priority`), `missing_information`, `runbook_alignment`.

Key guardrails: credentials are redacted as `[REDACTED]`; if data is too sparse, `confidence` is set to `0` and `missing_information` is populated rather than hallucinating a root cause.

---

## Summary Agent (reference)

**File:** [app/agents/summary.py](../app/agents/summary.py)

Output keys: `summary.what_happened` (2–4 sentence factual summary), `summary.current_status` (prefixed with `ONGOING` / `MITIGATED` / `MONITORING` / `RESOLVED`).

Status is inferred from the payload: presence of `timeframe.end` implies resolved; absence implies ongoing.

---

## Rebuilding and Redeploying After Changes

After editing any `*_INSTRUCTIONS` constant:

```bash
# 1. Rebuild the container image
docker build -t oncall-copilot:v9 .

# 2. Push to your registry
docker push <registry>/oncall-copilot:v9

# 3. Create a new agent version in Microsoft Foundry
az cognitiveservices agent create-version \
  --account-name <account> \
  --project-name <project> \
  --name oncall-copilot \
  --image <registry>/oncall-copilot:v9

# 4. Start the new version
az cognitiveservices agent start \
  --account-name <account> \
  --project-name <project> \
  --name oncall-copilot \
  --agent-version 9
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full build and deployment guide.

---

## Testing Agent Output

**Smoke test against live Foundry deployment:**
```bash
python scripts/invoke.py --demo 3   # rich payload — exercises comms + PIR
python scripts/invoke.py --scenario 5  # resolved storage incident — PIR-focused
```

**Direct model test (no container needed):**
```bash
python scripts/test_agents_direct.py          # tests comms + PIR with demo 3
python scripts/test_agents_direct.py --demo 1 # use a different demo payload
```

**Validate JSON schema only:**
```bash
python scripts/validate.py
```
