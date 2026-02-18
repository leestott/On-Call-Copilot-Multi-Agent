#!/usr/bin/env python3
"""
Playwright-based demo video capture for On-Call Copilot UI.

Drives http://localhost:7860, captures screenshots of every key UI state,
then runs ffmpeg to stitch them into docs/demo_ui.mp4.

Usage:
    .venv-1/Scripts/python.exe scripts/make_demo_video.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

# ── dependency check ──────────────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    print("Installing playwright …")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium", "--quiet"])
    from playwright.sync_api import sync_playwright, Page

ROOT    = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "screenshots" / "ui"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://localhost:7860"

DEMOS_DIR     = ROOT / "scripts" / "demos"
SCENARIOS_DIR = ROOT / "scripts" / "scenarios"


# ── helpers ──────────────────────────────────────────────────────────────────
def shot(page: Page, name: str, msg: str = "") -> Path:
    """Take a full-page screenshot and print progress."""
    p = OUT_DIR / name
    page.screenshot(path=str(p), full_page=False)
    print(f"  📸 {name}{' — ' + msg if msg else ''}")
    return p


def wait_for_presets(page: Page, timeout_ms: int = 6000) -> None:
    """Wait until the Quick Load buttons have loaded."""
    page.wait_for_function(
        "document.querySelector('#load-buttons .load-btn') !== null",
        timeout=timeout_ms,
    )


def load_incident(page: Page, file_stem: str) -> None:
    """Click the quick-load button whose id contains file_stem."""
    # Buttons have id="btn-<filename>" e.g. btn-demo_1_simple_alert.json
    btn = page.locator(f"[id^='btn-'][id*='{file_stem}']").first
    btn.click()
    # Wait for textarea to populate
    page.wait_for_function(
        "document.getElementById('json-editor').value.trim().length > 10",
        timeout=5000,
    )


def wait_for_results(page: Page, timeout_ms: int = 180_000) -> None:
    """Wait until the agent output appears (skeleton disappears, first tab button shows)."""
    page.wait_for_function(
        """() => {
            const body = document.getElementById('body-triage');
            return body && body.querySelector('.tab-btn, .error-banner') !== null;
        }""",
        timeout=timeout_ms,
    )


def inject_mock_output(page: Page, incident_json: dict) -> None:
    """
    Inject a realistic-looking mock result directly into the DOM so screenshots
    show populated panels without waiting for the live agent call.
    Used for the animated loading / result frames.
    """
    sev   = incident_json.get("severity", "SEV2")
    title = incident_json.get("title", "Unknown incident")
    iid   = incident_json.get("incident_id", "INC-DEMO")

    mock = {
        "http_status": 200,
        "agent_status": "completed",
        "elapsed_seconds": 8.3,
        "agent": "oncall-copilot:latest",
        "output": {
            "suspected_root_causes": [
                {
                    "hypothesis": "Connection pool exhaustion caused by runaway query in order-worker v2.3.1",
                    "evidence": [
                        "orders-db metric shows connections at 1,995 / 2,000 (99.75%)",
                        "order-worker logs: 'connection timeout after 30s' x 847 in 5 min",
                        "Deployment of order-worker v2.3.1 at 14:02Z matches onset"
                    ],
                    "confidence": 0.87
                },
                {
                    "hypothesis": "Missing index on orders.created_at causing full-table scans",
                    "evidence": [
                        "Slow query log: SELECT * FROM orders WHERE created_at > … (avg 4.2s)",
                        "DB CPU spiked from 22% to 89% at 14:03Z"
                    ],
                    "confidence": 0.64
                }
            ],
            "immediate_actions": [
                {"step": "Scale orders-db max_connections to 4000 (pg config + restart)", "owner_role": "DBA", "priority": "P0"},
                {"step": "Rollback order-worker to v2.3.0 via kubectl rollout undo", "owner_role": "oncall-eng", "priority": "P0"},
                {"step": "Enable read-replica failover for SELECT queries", "owner_role": "DBA", "priority": "P1"},
                {"step": "Throttle order-worker replicas to 3 to reduce DB load", "owner_role": "oncall-eng", "priority": "P1"}
            ],
            "missing_information": [
                {"question": "Was a query index dropped in the v2.3.1 release?", "why_it_matters": "Confirms root cause and determines if hotfix or rollback is the right fix"},
                {"question": "Is read replica replication lag > 0?", "why_it_matters": "Failover to read replica is only safe if lag is near zero"}
            ],
            "runbook_alignment": {
                "matched_steps": ["Step 1: Check DB connection dashboard", "Step 2: Review slow query log", "Step 3: Scale connections"],
                "gaps": ["No automated rollback step", "No read-replica failover procedure"]
            },
            "summary": {
                "what_happened": f"At 14:02Z, deployment of order-worker v2.3.1 caused a rapid exhaustion of the PostgreSQL connection pool on orders-db-primary. By 14:07Z the pool was at 99.75% utilisation, causing checkout requests to queue and time out. The checkout-api returned HTTP 503 for 68% of requests during the incident window. The {sev} incident '{title}' remains ONGOING.",
                "current_status": "ONGOING — connection pool at 99.75%, checkout-api degraded, rollback in progress"
            },
            "comms": {
                "slack_update": ":rotating_light: *INCIDENT ONGOING* :rotating_light:\n\n*{sev} | {title}*\n*Started:* 14:02Z | *Duration:* ~12 min\n*Impact:* Checkout service degraded — 68% of orders failing\n*Root cause (suspected):* DB connection pool exhaustion after order-worker v2.3.1 deploy\n*Actions:* Rolling back order-worker, scaling DB connections\n*ETA to resolution:* ~15 min\n*IC:* @oncall-eng | *Updates:* every 10 min".format(sev=sev, title=title),
                "stakeholder_update": f"We are currently experiencing degraded performance in our checkout service ({sev}: {title}). A configuration change deployed at 14:02 UTC is suspected to have caused a database resource constraint. Our on-call team has identified the issue and a rollback is in progress. We expect full recovery within 15 minutes. We will provide an update at 14:30 UTC."
            },
            "post_incident_report": {
                "timeline": [
                    {"time": "14:02Z", "event": f"order-worker v2.3.1 deployed to production ({sev})"},
                    {"time": "14:03Z", "event": "DB connection pool crossed 80% threshold — first alert fired"},
                    {"time": "14:05Z", "event": f"PagerDuty page: {iid} opened, on-call engineer engaged"},
                    {"time": "14:07Z", "event": "Connection pool at 99.75%, checkout-api 503 rate reached 68%"},
                    {"time": "14:09Z", "event": "Root cause identified: order-worker v2.3.1 runaway query"},
                    {"time": "14:14Z", "event": "kubectl rollout undo initiated, DB connections beginning to drop"},
                    {"time": "ONGOING", "event": "Recovery in progress — error rate declining"}
                ],
                "customer_impact": "Approximately 68% of checkout requests failed with HTTP 503 during the 12-minute window. Estimated 4,200 failed order attempts. Revenue impact: est. $52,000 in deferred or lost transactions during the incident window.",
                "prevention_actions": [
                    "Add connection-pool utilisation alert at 70% (currently only at 90%)",
                    "Add db query performance regression tests to order-worker CI pipeline",
                    "Implement automated rollback trigger when checkout-api 5xx rate exceeds 20% for 2 min",
                    "Document read-replica failover procedure in runbook steps 4–6",
                    "Require DBA sign-off on releases that touch database query paths"
                ]
            }
        }
    }

    page.evaluate(f"""
    (function() {{
        window.__MOCK_RESULT__ = {json.dumps(mock)};
        if (typeof renderResult === 'function') {{
            renderResult(window.__MOCK_RESULT__);
        }}
    }})();
    """)


# ── main capture flow ─────────────────────────────────────────────────────────
def capture(page: Page) -> list[tuple[Path, float]]:
    """
    Drive the UI through all states and return list of (screenshot_path, duration_seconds).
    """
    frames: list[tuple[Path, float]] = []

    def add(name: str, dur: float, msg: str = "") -> None:
        p = shot(page, name, msg)
        frames.append((p, dur))

    # ── 1. Empty / initial state ──────────────────────────────────────────────
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(800)
    add("ui_01_initial.png", 3.5, "Initial UI — empty state")

    # ── 2. Quick Load buttons visible ────────────────────────────────────────
    try:
        wait_for_presets(page)
    except Exception:
        pass
    page.wait_for_timeout(400)
    add("ui_02_presets_loaded.png", 2.5, "Quick-load presets loaded")

    # ── 3. Hover over Demo 1 button ──────────────────────────────────────────
    try:
        btn = page.locator("[id^='btn-demo_1']").first
        btn.hover()
        page.wait_for_timeout(300)
    except Exception:
        pass
    add("ui_03_hover_demo1.png", 2.0, "Hovering Demo 1 button")

    # ── 4. Load Demo 1 (Simple Alert SEV3) ───────────────────────────────────
    try:
        load_incident(page, "demo_1")
        page.wait_for_timeout(500)
    except Exception:
        pass
    add("ui_04_demo1_loaded.png", 3.5, "Demo 1 loaded — API Gateway SEV3")

    # ── 5. Close-up: JSON editor populated ────────────────────────────────────
    page.evaluate("document.getElementById('json-editor').scrollTop = 0")
    add("ui_05_json_editor.png", 3.0, "Incident JSON in editor")

    # ── 6. Load Demo 2 (Multi-signal SEV1) ───────────────────────────────────
    try:
        load_incident(page, "demo_2")
        page.wait_for_timeout(500)
    except Exception:
        pass
    add("ui_06_demo2_loaded.png", 3.0, "Demo 2 loaded — DB pool SEV1")

    # ── 7. Skeleton / submitting state ────────────────────────────────────────
    # Trigger skeleton by calling showSkeletons()
    page.evaluate("""
    (function() {
        if (typeof showSkeletons === 'function') { showSkeletons(); }
        const btn = document.getElementById('run-btn');
        if (btn) {
            btn.disabled = true;
            btn.classList.add('loading');
            btn.querySelector('.btn-label').textContent = 'Invoking agents\u2026';
        }
        const bar = document.getElementById('output-status-bar');
        if (bar) bar.style.display = 'none';
    })();
    """)
    page.wait_for_timeout(400)
    add("ui_07_submitting.png", 3.0, "Submitting — skeleton loading state")

    # ── 8. Results rendered (inject mock) ────────────────────────────────────
    demo2_path = DEMOS_DIR / "demo_2_multi_signal.json"
    demo2_data = json.loads(demo2_path.read_text()) if demo2_path.exists() else {}

    # Reset button state first
    page.evaluate("""
    (function() {
        const btn = document.getElementById('run-btn');
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('loading');
            btn.querySelector('.btn-label').textContent = '▶ Run Analysis';
        }
    })();
    """)

    inject_mock_output(page, demo2_data)
    page.wait_for_timeout(600)
    add("ui_08_results_overview.png", 5.0, "Results — all 4 agent panels populated")

    # ── 9. Triage panel close-up ─────────────────────────────────────────────
    triage_panel = page.locator("#panel-triage")
    triage_panel.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    add("ui_09_triage_panel.png", 4.0, "Triage panel — root causes with confidence bars")

    # ── 10. Click Actions tab in Triage ──────────────────────────────────────
    try:
        actions_tab = page.locator("#body-triage .tab-btn").nth(1)
        actions_tab.click()
        page.wait_for_timeout(400)
    except Exception:
        pass
    add("ui_10_triage_actions.png", 3.5, "Triage panel — immediate actions tab")

    # ── 11. Summary panel ────────────────────────────────────────────────────
    summary_panel = page.locator("#panel-summary")
    summary_panel.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    add("ui_11_summary_panel.png", 4.0, "Summary panel — narrative + ONGOING status")

    # ── 12. Comms panel ──────────────────────────────────────────────────────
    comms_panel = page.locator("#panel-comms")
    comms_panel.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    add("ui_12_comms_panel.png", 4.0, "Comms panel — Slack card + stakeholder update")

    # ── 13. PIR panel ────────────────────────────────────────────────────────
    pir_panel = page.locator("#panel-pir")
    pir_panel.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    add("ui_13_pir_panel.png", 4.0, "PIR panel — timeline + prevention actions")

    # ── 14. Scroll PIR body to show prevention actions ───────────────────────
    page.evaluate("""
    (function() {
        const b = document.getElementById('body-pir');
        if (b) b.scrollTop = b.scrollHeight;
    })();
    """)
    page.wait_for_timeout(300)
    add("ui_14_pir_prevention.png", 3.5, "PIR — prevention actions")

    # ── 15. Load Scenario 1 (Redis SEV2) ─────────────────────────────────────
    # Scroll back up first & reset PIR scroll
    page.evaluate("""
    (function() {
        const b = document.getElementById('body-pir');
        if (b) b.scrollTop = 0;
    })();
    """)
    try:
        load_incident(page, "scenario_1")
        page.wait_for_timeout(500)
    except Exception:
        pass
    add("ui_15_scenario1_loaded.png", 3.0, "Scenario 1 loaded — Redis cluster SEV2")

    # ── 16. Status bar close up (inject result again with different timing) ──
    inject_mock_output(page, {
        "incident_id": "INC-2026-0401",
        "title": "Redis Cache Cluster Unresponsive",
        "severity": "SEV2"
    })
    page.wait_for_timeout(500)
    add("ui_16_status_bar.png", 3.0, "Status bar — HTTP 200, elapsed time, agent name")

    # ── 17. Full UI final state ───────────────────────────────────────────────
    add("ui_17_final.png", 4.0, "Final overview — complete incident analysis")

    return frames


def build_video(frames: list[tuple[Path, float]]) -> Path:
    """Write filelist.txt and run ffmpeg."""
    filelist = OUT_DIR / "filelist.txt"
    lines = []
    for path, dur in frames:
        lines.append(f"file '{path.as_posix()}'")
        lines.append(f"duration {dur}")
    # ffmpeg needs the last file repeated with no duration for seamless end
    last_path = frames[-1][0]
    lines.append(f"file '{last_path.as_posix()}'")
    filelist.write_text("\n".join(lines))

    out_mp4 = ROOT / "docs" / "demo_ui.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(filelist),
        "-vf", "scale=1400:900:force_original_aspect_ratio=decrease,"
               "pad=1400:900:(ow-iw)/2:(oh-ih)/2,fps=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_mp4),
    ]
    print(f"\n🎬 Running ffmpeg → {out_mp4.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Try without scale filter (simpler fallback)
        cmd2 = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(filelist),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(out_mp4),
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        if result2.returncode != 0:
            print("ffmpeg stderr:", result2.stderr[-1000:])
            raise RuntimeError("ffmpeg failed")

    size_kb = round(out_mp4.stat().st_size / 1024)
    print(f"✅ Video created: {out_mp4}  ({size_kb} KB)")
    return out_mp4


# ── entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    print(f"🎥 On-Call Copilot UI Demo Capture")
    print(f"   Output dir : {OUT_DIR}")
    print(f"   Target URL : {BASE_URL}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            device_scale_factor=1.5,
        )
        page = ctx.new_page()

        try:
            frames = capture(page)
        finally:
            browser.close()

    print(f"\n✅ Captured {len(frames)} frames\n")
    mp4_path = build_video(frames)
    print(f"\n🎬 Demo video ready: {mp4_path}")


if __name__ == "__main__":
    main()
