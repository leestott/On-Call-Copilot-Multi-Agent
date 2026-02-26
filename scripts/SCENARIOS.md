# On-Call Copilot: Demos and Scenarios

This directory contains two categories of test payload:

- **Demos** (`demos/`): Three quick-start payloads designed to be pasted directly into the Foundry Agent Playground or sent via curl. They illustrate increasing complexity and Model Router routing behaviour.
- **Scenarios** (`scenarios/`): Five realistic incident scenarios for integration testing, batch runs, and schema validation. Cover a range of severities, signal volumes, and incident types including post-incident reviews.

---

## Quick Start: Agent Playground

1. Open any JSON file below in your editor
2. Copy the entire file contents
3. Open **Foundry Agent Playground**, select the `oncall-copilot` agent
4. Paste the JSON directly into the chat input and send

---

## Demos

### Demo 1: Simple Alert

| Field | Value |
|---|---|
| **File** | [`demos/demo_1_simple_alert.json`](demos/demo_1_simple_alert.json) |
| **Incident ID** | INC-20260217-001 |
| **Severity** | SEV3 |
| **Status** | Active |
| **Signals** | 1 alert, 0 logs, 1 metric |
| **Region** | eastus2 |
| **Time constraint** | 15 min |

**Title:** API Gateway 5xx spike on payments endpoint

**Signals summary:**
- Alert: `HighErrorRate-payments-api` — 5xx rate exceeded 5% threshold for 5 minutes
- Metric: `http_5xx_rate` jumped from 0.2% to 8.3% at 03:42Z

**Runbook:** 2 steps (check API GW dashboard, verify downstream connectivity)

**What to look for in the output:**
- Model Router routes to a fast, cost-efficient model (low-complexity prompt)
- `suspected_root_causes` should reflect uncertainty (only 1 signal)
- `missing_information` should be non-empty (no logs, limited context)
- `immediate_actions` should include diagnostic steps

**Run it:**
```bash
python scripts/invoke.py --demo 1
# or via curl (local server):
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d @scripts/demos/demo_1_simple_alert.json
```

---

### Demo 2: Multi-Signal Incident

| Field | Value |
|---|---|
| **File** | [`demos/demo_2_multi_signal.json`](demos/demo_2_multi_signal.json) |
| **Incident ID** | INC-20260217-002 |
| **Severity** | SEV1 |
| **Status** | Active |
| **Signals** | 3 alerts, 2 log sources, 3 metrics |
| **Region** | westeurope |
| **Time constraint** | 30 min |

**Title:** Order processing latency degradation with database connection pool exhaustion

**Signals summary:**
- Alerts: `HighLatency-order-service` (P99 12,400ms), `DBConnectionPoolExhausted-orders-db` (pool at 100%), `PodRestarts-order-worker` (OOMKilled)
- Logs: `order-service` (connection pool exhausted errors), `order-worker` (OOMKilled, memory 4GB)
- Metrics: P99 latency peaked 12,400ms; DB pool 100%; worker memory 4GB OOM

**Runbook:** 5 steps (check DB health, scale max_connections, restart OOMKilled pods, read replica failover, notify payments team)

**What to look for in the output:**
- Model Router routes to a highly capable model (multi-source, high-complexity)
- `suspected_root_causes` should contain at least 2 hypotheses with high confidence
- `immediate_actions` should reference DB pool scaling and pod restart
- `runbook_alignment` should show most steps matched

**Run it:**
```bash
python scripts/invoke.py --demo 2
# or via curl (local server):
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d @scripts/demos/demo_2_multi_signal.json
```

---

### Demo 3: Post-Incident Report Synthesis

| Field | Value |
|---|---|
| **File** | [`demos/demo_3_post_incident.json`](demos/demo_3_post_incident.json) |
| **Incident ID** | INC-20260216-099 |
| **Severity** | SEV1 |
| **Status** | Resolved (14:00Z–16:35Z) |
| **Signals** | 4 alerts, 2 log sources, 4 metrics |
| **Region** | global |
| **Time constraint** | 60 min |

**Title:** Completed: Authentication service outage caused by expired TLS certificate

**Signals summary:**
- Alerts: `AuthFailureRate-Critical`, `TLSHandshakeFailures`, `CustomerLoginFailures-Spike`, `IncidentResolved-Auth`
- Logs: `auth-service` (certificate expired, TLS handshake failures), `oncall-chat` (incident timeline)
- Metrics: Auth success rate 99.9% → 2%; login errors 62k/min peak; TLS failures 98%; revenue impact **~$340,000 est.**

**Runbook:** 5 steps (identify expired cert, issue replacement, deploy to LB then edges, verify auth > 99%, post-incident review)

**What to look for in the output:**
- Model Router routes to a high-capability model (long context, narrative synthesis)
- `suspected_root_causes` should have very high confidence for TLS expiry
- `post_incident_report.timeline` should reconstruct the full incident timeline
- `post_incident_report.customer_impact` should reference the revenue figure
- `post_incident_report.prevention_actions` should include automated cert renewal
- `immediate_actions` should focus on prevention rather than active remediation (incident is resolved)

**Run it:**
```bash
python scripts/invoke.py --demo 3
# or via curl (local server):
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d @scripts/demos/demo_3_post_incident.json
```

---

## Scenarios

Scenarios are designed for batch testing against the live Foundry API via `run_scenarios.py` and for local schema validation via `validate.py`.

### Scenario 1: Redis Cache Outage

| Field | Value |
|---|---|
| **File** | [`scenarios/scenario_1_redis_outage.json`](scenarios/scenario_1_redis_outage.json) |
| **Incident ID** | INC-2026-0401 |
| **Severity** | SEV2 |
| **Status** | Active |
| **Signals** | 2 alerts, 2 log sources, 3 metrics |
| **Region** | westus2 |
| **Time constraint** | 20 min |

**Title:** Redis cache cluster unresponsive — session service returning 503s

**Signals summary:**
- Alerts: `RedisCluster-Unreachable`, `SessionService-5xx-Spike` (error rate 94%)
- Logs: `redis-sentinel` (master unreachable, failover failed, cluster DOWN); `session-service` (RedisConnectionException, circuit breaker OPEN)
- Metrics: connected_clients 1200 → 0; error_rate 0.1% → 94%; memory_used at 7.98GB/8GB limit (near maxmemory)

**Runbook:** 4 steps (check sentinel status, manual failover, check VM/pod health, flush volatile keys)

**Run it:**
```bash
python scripts/run_scenarios.py --scenario 1
python scripts/invoke.py --scenario 1
```

---

### Scenario 2: AKS Node Pool Scaling Failure

| Field | Value |
|---|---|
| **File** | [`scenarios/scenario_2_aks_scaling.json`](scenarios/scenario_2_aks_scaling.json) |
| **Incident ID** | INC-2026-0402 |
| **Severity** | SEV1 |
| **Status** | Active |
| **Signals** | 4 alerts, 3 log sources, 4 metrics |
| **Region** | westus2 |
| **Time constraint** | 30 min |

**Title:** Kubernetes node pool scaling failure causing pod scheduling backlog

**Signals summary:**
- Alerts: `AKS-NodePool-ScaleFailure` (InsufficientCapacity), `PodScheduling-Backlog-Critical` (47 pods pending), `HPA-MaxReplicas-Reached`, `API-Latency-Degraded` (P95 8s)
- Logs: `cluster-autoscaler` (Standard_D8s_v3 and v5 both failed capacity); `kube-scheduler` (0/5 nodes available); `order-processor` (queue depth 3421)
- Metrics: nodes stuck at 5; pending pods 0 → 47; queue 200 → 3421; P95 latency 400ms → 8200ms

**Runbook:** 5 steps (check autoscaler logs, try alternate VM SKU/AZ, manually scale another pool, check PDBs, enable overflow to secondary cluster)

**Run it:**
```bash
python scripts/run_scenarios.py --scenario 2
python scripts/invoke.py --scenario 2
```

---

### Scenario 3: DNS Cascade Failure

| Field | Value |
|---|---|
| **File** | [`scenarios/scenario_3_dns_cascade.json`](scenarios/scenario_3_dns_cascade.json) |
| **Incident ID** | INC-2026-0403 |
| **Severity** | SEV1 |
| **Status** | Active |
| **Signals** | 3 alerts, 2 log sources, 4 metrics |
| **Region** | eastus |
| **Time constraint** | 15 min |

**Title:** DNS resolution failures causing cascading microservice timeouts

**Signals summary:**
- Alerts: `CoreDNS-ErrorRate-Critical` (40% SERVFAIL), `MultiService-Timeout-Cascade` (auth/payment/inventory/notification), `ExternalDNS-Sync-Failure`
- Logs: `coredns` (no healthy upstreams 168.63.129.16, cache miss storm 12k qps); `payment-service` (oversold 340 items due to inventory check bypass)
- Metrics: SERVFAIL rate 0.01% → 42%; queries 800 → 12,000 qps; service timeouts per min; Azure DNS P95 2ms → 4,500ms

**Runbook:** 6 steps (CoreDNS health, verify Azure DNS resolver reachable, check NSG rules, add static hosts, restart CoreDNS, check Azure status page)

**Run it:**
```bash
python scripts/run_scenarios.py --scenario 3
python scripts/invoke.py --scenario 3
```

---

### Scenario 4: Minimal Alert (Sparse Data)

| Field | Value |
|---|---|
| **File** | [`scenarios/scenario_4_minimal_alert.json`](scenarios/scenario_4_minimal_alert.json) |
| **Incident ID** | INC-2026-0404 |
| **Severity** | SEV4 |
| **Status** | Active |
| **Signals** | 1 alert, 0 logs, 1 metric |
| **Region** | northeurope |
| **Time constraint** | 30 min |

**Title:** Minimal: CPU alert on staging batch processor

**Signals summary:**
- Alert: `HighCPU-batch-processor-staging` (85% CPU for 10 minutes)
- Log: `batch-processor-staging` (CPU at 89%, above threshold)
- Metric: `cpu_utilization` 87–91% since 10:50Z
- Runbook: Check CPU, restart pod if sustained above 90%

**What to look for in the output:**
- `missing_information` should be extensive (no logs, no runbook, minimal context)
- `suspected_root_causes` should have low confidence scores
- `immediate_actions` should consist of diagnostic steps rather than remediation
- Tests agent behaviour with sparse, ambiguous data

**Run it:**
```bash
python scripts/run_scenarios.py --scenario 4
python scripts/invoke.py --scenario 4
```

---

### Scenario 5: Storage Throttle — Post-Incident Review

| Field | Value |
|---|---|
| **File** | [`scenarios/scenario_5_storage_throttle_pir.json`](scenarios/scenario_5_storage_throttle_pir.json) |
| **Incident ID** | INC-2026-0405 |
| **Severity** | SEV2 |
| **Status** | Resolved (18:00Z–20:45Z) |
| **Signals** | 4 alerts, 3 log sources, 5 metrics |
| **Region** | eastus2 |
| **Time constraint** | 60 min |

**Title:** Resolved: Storage account throttling caused image upload failures — Post-Incident Review

**Signals summary:**
- Alerts: `StorageThrottling` (429s, >500 req/s), `ImageUpload-FailureRate` (67%), `CDN-CacheMiss-Spike` (45%), `IncidentResolved-Storage`
- Logs: `image-upload-service` (bulk 12k product images hit IOPS limit, tier upgraded to Premium); `cdn-edge` (stale cache serving, 8400 invalidation backlog); `oncall-chat` (incident timeline)
- Metrics: throttle 0 → 2800/min; upload success 99.8% → 33%; CDN origin error 0.5% → 45%; batch 97.2% succeeded; revenue impact **~$18,000**

**Runbook:** 6 steps (identify throttled account, check bulk operation, request tier upgrade/queue retry, CDN stale-if-error, post-incident rate limiter, early warning alert)

**What to look for in the output:**
- `post_incident_report.timeline` should reconstruct the throttling and recovery timeline
- `post_incident_report.prevention_actions` should include rate limiting and IOPS tier pre-provisioning
- `runbook_alignment` should show all 6 steps matched or exceeded

**Run it:**
```bash
python scripts/run_scenarios.py --scenario 5
python scripts/invoke.py --scenario 5
```

---

## Reference: All Files at a Glance

| # | File | Category | Severity | Status | Alerts | Logs | Metrics |
|---|------|----------|----------|--------|--------|------|---------|
| D1 | [`demos/demo_1_simple_alert.json`](demos/demo_1_simple_alert.json) | Demo | SEV3 | Active | 1 | 0 | 1 |
| D2 | [`demos/demo_2_multi_signal.json`](demos/demo_2_multi_signal.json) | Demo | SEV1 | Active | 3 | 2 | 3 |
| D3 | [`demos/demo_3_post_incident.json`](demos/demo_3_post_incident.json) | Demo | SEV1 | Resolved | 4 | 2 | 4 |
| S1 | [`scenarios/scenario_1_redis_outage.json`](scenarios/scenario_1_redis_outage.json) | Scenario | SEV2 | Active | 2 | 2 | 3 |
| S2 | [`scenarios/scenario_2_aks_scaling.json`](scenarios/scenario_2_aks_scaling.json) | Scenario | SEV1 | Active | 4 | 3 | 4 |
| S3 | [`scenarios/scenario_3_dns_cascade.json`](scenarios/scenario_3_dns_cascade.json) | Scenario | SEV1 | Active | 3 | 2 | 4 |
| S4 | [`scenarios/scenario_4_minimal_alert.json`](scenarios/scenario_4_minimal_alert.json) | Scenario | SEV4 | Active | 1 | 1 | 1 |
| S5 | [`scenarios/scenario_5_storage_throttle_pir.json`](scenarios/scenario_5_storage_throttle_pir.json) | Scenario | SEV2 | Resolved | 4 | 3 | 5 |

## Run All Scenarios

```bash
# Run all 5 scenarios against live Foundry API
python scripts/run_scenarios.py

# Validate all scenarios against local mock server
python scripts/validate.py
```
