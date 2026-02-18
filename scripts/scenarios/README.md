# Scenario Payloads

Five realistic incident scenarios for integration testing, batch runs, and schema validation against the On-Call Copilot agent.

Each file is a self-contained JSON payload matching the [input envelope schema](../../README.md#api-contract). Send any file directly to the agent via the Foundry Agent Playground, curl, or the invoke script.

---

## Scenarios

| # | File | Severity | Status | Alerts | Logs | Metrics | Description |
|---|------|----------|--------|--------|------|---------|-------------|
| 1 | [scenario_1_redis_outage.json](scenario_1_redis_outage.json) | SEV2 | Active | 2 | 2 | 3 | Redis cache cluster unresponsive, session service returning 503s |
| 2 | [scenario_2_aks_scaling.json](scenario_2_aks_scaling.json) | SEV1 | Active | 4 | 3 | 4 | AKS node pool scaling failure, 47 pods pending, P95 latency 8s |
| 3 | [scenario_3_dns_cascade.json](scenario_3_dns_cascade.json) | SEV1 | Active | 3 | 2 | 4 | CoreDNS 40% SERVFAIL causing cascading microservice timeouts |
| 4 | [scenario_4_minimal_alert.json](scenario_4_minimal_alert.json) | SEV4 | Active | 1 | 0 | 1 | Sparse CPU alert on staging — tests low-confidence / high missing-info output |
| 5 | [scenario_5_storage_throttle_pir.json](scenario_5_storage_throttle_pir.json) | SEV2 | Resolved | 4 | 3 | 5 | Storage throttling caused image upload failures — post-incident review |

---

## Running a Scenario

**Via invoke script (from repo root):**
```bash
python scripts/invoke.py --scenario 1   # replace 1-5
```

**Batch run all scenarios against live Foundry API:**
```bash
python scripts/run_scenarios.py
python scripts/run_scenarios.py --scenario 3   # single scenario
python scripts/run_scenarios.py --list         # list available scenarios
```

**Local schema validation (mock mode):**
```bash
python scripts/validate.py
python scripts/validate.py --scenario 2
```

**Via curl (local server on port 8088):**
```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d @scripts/scenarios/scenario_1_redis_outage.json
```

**Agent Playground:**
1. Open the JSON file, copy all contents
2. Open Foundry Agent Playground, select `oncall-copilot`
3. Paste the JSON directly into the chat input and send

---

## Scenario Design Notes

| Scenario | Key test dimension |
|---|---|
| 1 — Redis | Multi-alert + near-maxmemory metric; expects redis sentinel failover steps in `immediate_actions` |
| 2 — AKS | 4 alerts across 3 log sources; expects root cause to identify AZ capacity exhaustion; complex `runbook_alignment` |
| 3 — DNS | 15-minute constraint; expects CoreDNS + Azure DNS resolver steps; business impact (oversold inventory) in logs |
| 4 — Minimal | No logs, no runbook, SEV4 staging; expects high `missing_information` count and `confidence < 0.5` |
| 5 — Storage PIR | Resolved incident; expects full `post_incident_report.timeline`, CDN secondary impact noted, rate-limiter in `prevention_actions` |

---

## Adding a New Scenario

1. Copy an existing file as a template
2. Name it `scenario_N_short_description.json` (increment N)
3. Update `incident_id`, `title`, `severity`, `timeframe`, and all signal arrays
4. Add a row to the table above and to [../SCENARIOS.md](../SCENARIOS.md)
5. Run `python scripts/validate.py --scenario N` to confirm schema compliance

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the full contribution guide.
