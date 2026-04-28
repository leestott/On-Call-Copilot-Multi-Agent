#!/usr/bin/env bash
# On-Call Copilot – curl-based local test script
# Usage: bash scripts/test_local.sh [1|2|3]
#   1 = simple alert, 2 = multi-signal, 3 = post-incident (default: 1)

set -euo pipefail

BASE="http://localhost:8088"
DEMO="${1:-1}"

case "$DEMO" in
  1) FILE="scripts/demos/demo_1_simple_alert.json" ;;
  2) FILE="scripts/demos/demo_2_multi_signal.json" ;;
  3) FILE="scripts/demos/demo_3_post_incident.json" ;;
  *) echo "Usage: $0 [1|2|3]"; exit 1 ;;
esac

echo "==> Sending $FILE to $BASE/responses ..."
BODY=$(python -c 'import json,sys; print(json.dumps({"input":[{"role":"user","content":open(sys.argv[1],encoding="utf-8").read()}]}))' "$FILE")
curl -s -X POST "$BASE/responses" \
  -H "Content-Type: application/json" \
  -d "$BODY" | python -m json.tool

echo ""
echo "==> Readiness check:"
curl -s "$BASE/readiness" | python -m json.tool
