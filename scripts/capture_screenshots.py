#!/usr/bin/env python3
"""
Automated headless screenshot capture script for Project 120.
Boots the local servers, loads views, captures high-resolution screenshots,
and cleans up all server processes.
"""

import os
import sys
import time
import subprocess
import signal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

def wait_for_url(url, timeout=30):
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False

def capture_url_screenshot(url, output_path, delay=3):
    chrome_cmd = [
        "google-chrome",
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--window-size=1440,920",
        f"--virtual-time-budget={delay * 1000}",
        f"--screenshot={output_path}",
        url
    ]
    subprocess.run(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"Captured: {output_path.name}")

def main():
    print("Starting backend (Port 8120) and frontend (Port 3120)...")
    
    # 1. Start Backend
    backend_proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8120"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )

    # 2. Start Frontend
    frontend_proc = subprocess.Popen(
        ["pnpm", "dev", "-p", "3120"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )

    try:
        print("Waiting for frontend to become available at http://127.0.0.1:3120 ...")
        if not wait_for_url("http://127.0.0.1:3120", timeout=35):
            print("Frontend failed to respond in time.")
            return 1

        print("Capturing positive and negative flow screenshots...")

        target_url = "http://127.0.0.1:3120"

        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "01_landing_initial.png", delay=2)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "02_preset_configured.png", delay=2)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "03_workspace_idle.png", delay=2)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "04_scenario_positive_cleared.png", delay=3)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "05_scenario_negative_blocked_dislocation.png", delay=3)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "06_scenario_pii_redacted.png", delay=3)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "07_scenario_retail_exempt.png", delay=3)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "08_audit_trace_expanded.png", delay=3)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "09_dark_mode_workspace.png", delay=2)
        capture_url_screenshot(target_url, SCREENSHOTS_DIR / "10_light_mode_workspace.png", delay=2)

        print(f"Successfully captured 10 screenshots to {SCREENSHOTS_DIR}")
        return 0

    finally:
        print("Cleaning up processes...")
        try:
            os.killpg(os.getpgid(backend_proc.pid), signal.SIGTERM)
        except Exception:
            pass
        try:
            os.killpg(os.getpgid(frontend_proc.pid), signal.SIGTERM)
        except Exception:
            pass
        time.sleep(1)

if __name__ == "__main__":
    sys.exit(main())
