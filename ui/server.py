#!/usr/bin/env python3
"""
On-Call Copilot local UI server.

Usage:
    cd "c:/Users/leestott/On Call"
    set AZURE_AI_PROJECT_ENDPOINT=https://...
    .venv-1\Scripts\python.exe ui\server.py

Opens at http://localhost:7860
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DEMOS_DIR     = ROOT / "scripts" / "demos"
SCENARIOS_DIR = ROOT / "scripts" / "scenarios"
HTML_FILE     = Path(__file__).resolve().parent / "index.html"
PORT          = int(os.environ.get("UI_PORT", "7860"))

DEMO_LABELS = {
    "demo_1_simple_alert.json":          "Demo 1 — API Gateway 5xx (SEV3)",
    "demo_2_multi_signal.json":          "Demo 2 — DB Connection Pool (SEV1)",
    "demo_3_post_incident.json":         "Demo 3 — Auth TLS Cert Expiry",
}
SCENARIO_LABELS = {
    "scenario_1_redis_outage.json":      "Scenario 1 — Redis Cluster Down (SEV2)",
    "scenario_2_aks_scaling.json":       "Scenario 2 — AKS Scaling Failure",
    "scenario_3_dns_cascade.json":       "Scenario 3 — DNS Cascade Failure",
    "scenario_4_minimal_alert.json":     "Scenario 4 — Minimal Alert",
    "scenario_5_storage_throttle_pir.json": "Scenario 5 — Storage Throttle PIR",
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _get_token() -> str:
    r = subprocess.run(
        ["az", "account", "get-access-token",
         "--resource", "https://ai.azure.com",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError("az login required – run `az login` first")
    return r.stdout.strip()


def _invoke_agent(content: str) -> dict:
    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "").rstrip("/")
    if not endpoint:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT env var is not set.\n"
            "Set it to: https://<account>.services.ai.azure.com/api/projects/<project>"
        )
    agent_name    = os.environ.get("AGENT_NAME", "oncall-copilot")
    agent_version = os.environ.get("AGENT_VERSION", "")

    token   = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    spec: dict = {"type": "agent_reference", "name": agent_name}
    if agent_version:
        spec["version"] = agent_version

    body = {
        "input": [{"role": "user", "content": content}],
        "agent": spec,
    }

    t0 = time.time()
    r = requests.post(
        f"{endpoint}/openai/responses?api-version=2025-05-15-preview",
        headers=headers, json=body, timeout=180,
    )
    elapsed = round(time.time() - t0, 1)

    raw = r.json()
    if raw.get("error"):
        raise RuntimeError(
            f"Agent error ({r.status_code}): {raw['error'].get('message', json.dumps(raw['error']))}"
        )

    # Extract & merge all JSON objects from the concatenated text blob
    merged: dict = {}
    decoder = json.JSONDecoder()
    for output in raw.get("output", []):
        for c in output.get("content", []):
            text = c.get("text", "").strip()
            pos  = 0
            while pos < len(text):
                while pos < len(text) and text[pos] in " \t\n\r":
                    pos += 1
                if pos >= len(text):
                    break
                try:
                    obj, end = decoder.raw_decode(text, pos)
                    if isinstance(obj, dict):
                        merged.update(obj)
                    pos += end - pos
                except json.JSONDecodeError:
                    break

    return {
        "http_status": r.status_code,
        "agent_status": raw.get("status"),
        "elapsed_seconds": elapsed,
        "agent": f"{agent_name}:{agent_version or 'latest'}",
        "output": merged,
    }


# ─── request handler ──────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter logs
        if args and str(args[1]) not in ("200", "304"):
            super().log_message(fmt, *args)

    # helpers
    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    # routing
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"
        qs     = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_html(HTML_FILE.read_bytes())
            return

        if path == "/api/config":
            endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
            self._send_json({
                "endpoint": endpoint,
                "agent_name": os.environ.get("AGENT_NAME", "oncall-copilot"),
                "agent_version": os.environ.get("AGENT_VERSION", "latest"),
                "configured": bool(endpoint),
            })
            return

        if path == "/api/incidents":
            items = []
            for f in sorted(DEMOS_DIR.glob("demo_*.json")):
                items.append({
                    "type": "demo",
                    "file": f.name,
                    "label": DEMO_LABELS.get(f.name, f.stem),
                    "severity": json.loads(f.read_text())["severity"],
                })
            for f in sorted(SCENARIOS_DIR.glob("scenario_*.json")):
                items.append({
                    "type": "scenario",
                    "file": f.name,
                    "label": SCENARIO_LABELS.get(f.name, f.stem),
                    "severity": json.loads(f.read_text())["severity"],
                })
            self._send_json({"incidents": items})
            return

        if path == "/api/load":
            ftype = qs.get("type", ["demo"])[0]
            fname = qs.get("file", [""])[0]
            base_dir = DEMOS_DIR if ftype == "demo" else SCENARIOS_DIR
            fpath = base_dir / fname
            if not fpath.exists() or not fname:
                self._send_json({"error": f"File not found: {fname}"}, 404)
                return
            data = json.loads(fpath.read_text())
            self._send_json({"content": json.dumps(data, indent=2), "meta": data})
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/api/invoke":
            try:
                body_bytes = self._read_body()
                payload    = json.loads(body_bytes)
                content    = payload.get("content", "")
                if not content.strip():
                    self._send_json({"error": "content is required"}, 400)
                    return
                result = _invoke_agent(content)
                self._send_json(result)
            except requests.Timeout:
                self._send_json({"error": "Request timed out (180s). The agent may be busy."}, 504)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
            return

        self._send_json({"error": "Not found"}, 404)


# ─── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not HTML_FILE.exists():
        print(f"ERROR: {HTML_FILE} not found.")
        sys.exit(1)

    endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
    agent    = os.environ.get("AGENT_NAME", "oncall-copilot")
    version  = os.environ.get("AGENT_VERSION", "") or "latest"

    print("=" * 60)
    print("  On-Call Copilot UI")
    print("=" * 60)
    print(f"  URL     : http://localhost:{PORT}")
    print(f"  Agent   : {agent}:{version}")
    if endpoint:
        print(f"  Endpoint: {endpoint[:60]}...")
    else:
        print("  Endpoint: ⚠  AZURE_AI_PROJECT_ENDPOINT not set")
    print("=" * 60)
    print("  Press Ctrl+C to stop.")
    print()

    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
