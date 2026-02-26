#!/usr/bin/env python3
"""Test all demos and scenarios via the UI server API at localhost:7860."""
import json
import sys
import time
import requests

BASE = "http://localhost:7860"
REQUIRED_KEYS = {
    "triage": ["suspected_root_causes", "immediate_actions"],
    "summary": ["summary"],
    "comms": ["comms"],
    "pir": ["post_incident_report"],
}

def test_incident(item: dict) -> dict:
    """Load and invoke one incident, return results."""
    label = item["label"]
    fname = item["file"]
    ftype = item["type"]

    # Load the incident JSON
    r = requests.get(f"{BASE}/api/load", params={"type": ftype, "file": fname}, timeout=10)
    r.raise_for_status()
    content = r.json()["content"]

    # Invoke the agent
    t0 = time.time()
    r2 = requests.post(
        f"{BASE}/api/invoke",
        json={"content": content},
        timeout=300,
    )
    elapsed = round(time.time() - t0, 1)
    data = r2.json()

    if data.get("error"):
        return {"label": label, "status": "ERROR", "error": data["error"], "elapsed": elapsed}

    output = data.get("output", {})
    output_keys = list(output.keys())

    # Check which agent panels would populate
    panels = {}
    panels["triage"] = any(k in output_keys for k in REQUIRED_KEYS["triage"])
    panels["summary"] = any(k in output_keys for k in REQUIRED_KEYS["summary"])
    panels["comms"] = any(k in output_keys for k in REQUIRED_KEYS["comms"])
    panels["pir"] = any(k in output_keys for k in REQUIRED_KEYS["pir"])

    missing = [p for p, ok in panels.items() if not ok]

    return {
        "label": label,
        "status": "PASS" if not missing else "PARTIAL",
        "panels": panels,
        "missing_panels": missing,
        "output_keys": output_keys,
        "elapsed": elapsed,
        "http_status": data.get("http_status"),
    }


def main():
    # Get all incidents
    r = requests.get(f"{BASE}/api/incidents", timeout=10)
    r.raise_for_status()
    incidents = r.json()["incidents"]
    print(f"Found {len(incidents)} incidents to test\n")

    results = []
    for i, item in enumerate(incidents):
        tag = f"[{i+1}/{len(incidents)}]"
        print(f"{tag} Testing: {item['label']} ({item['type']}/{item['file']}) ...")
        try:
            result = test_incident(item)
            results.append(result)
            if result["status"] == "PASS":
                print(f"  ✓ PASS ({result['elapsed']}s) — all 4 panels populated")
            elif result["status"] == "PARTIAL":
                print(f"  ⚠ PARTIAL ({result['elapsed']}s) — missing: {', '.join(result['missing_panels'])}")
                print(f"    Output keys: {result['output_keys']}")
            else:
                print(f"  ✗ ERROR ({result['elapsed']}s) — {result.get('error','unknown')}")
        except Exception as e:
            print(f"  ✗ EXCEPTION: {e}")
            results.append({"label": item["label"], "status": "EXCEPTION", "error": str(e)})

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r["status"] == "PASS")
    partial = sum(1 for r in results if r["status"] == "PARTIAL")
    failed = sum(1 for r in results if r["status"] in ("ERROR", "EXCEPTION"))
    print(f"  Total: {len(results)}  |  Pass: {passed}  |  Partial: {partial}  |  Failed: {failed}")
    for r in results:
        icon = "✓" if r["status"] == "PASS" else ("⚠" if r["status"] == "PARTIAL" else "✗")
        detail = ""
        if r.get("missing_panels"):
            detail = f" — missing: {', '.join(r['missing_panels'])}"
        if r.get("error") and r["status"] != "PASS":
            detail = f" — {r['error'][:80]}"
        print(f"  {icon} {r['label']} [{r.get('elapsed','?')}s]{detail}")

    # Dump full results for debugging
    print("\n\nDETAILED OUTPUT KEYS:")
    for r in results:
        print(f"  {r['label']}: {r.get('output_keys', r.get('error', '?'))}")

    sys.exit(0 if failed == 0 and partial == 0 else 1)


if __name__ == "__main__":
    main()
