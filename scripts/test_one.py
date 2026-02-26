#!/usr/bin/env python3
"""Quick test of just one incident."""
import json, requests, sys, time
BASE = "http://localhost:7860"
ftype, fname = sys.argv[1], sys.argv[2]
r = requests.get(f"{BASE}/api/load", params={"type": ftype, "file": fname}, timeout=10)
content = r.json()["content"]
t0 = time.time()
r2 = requests.post(f"{BASE}/api/invoke", json={"content": content}, timeout=300)
elapsed = round(time.time() - t0, 1)
data = r2.json()
if data.get("error"):
    print(f"ERROR [{elapsed}s]: {data['error']}")
else:
    output = data.get("output", {})
    agent_keys = [k for k in output if k not in (
        'incident_id','title','severity','timeframe','alerts','logs',
        'metrics','runbook_excerpt','constraints')]
    print(f"OK [{elapsed}s] agent keys: {agent_keys}")
