#!/usr/bin/env python3
"""
BearDAO Trading Agent — Inverse MicroStrategy
An AI-powered BTC short-selling agent guided by Claude.

Usage:
    python run.py              # Run one analysis cycle + generate report
    python run.py --loop       # Run continuously (every 15 min)
    python run.py --report     # Generate report from existing data only
"""

import sys
import time
import os
import subprocess
import platform

from agent.trader import TradingAgent
from agent.report import generate_report
from agent.config import Config


def open_report(path: str):
    """Open HTML report in the default browser."""
    abs_path = os.path.abspath(path)
    url = f"file://{abs_path}"
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", abs_path], check=True)
        elif platform.system() == "Linux":
            subprocess.run(["xdg-open", abs_path], check=True)
        else:
            subprocess.run(["start", abs_path], shell=True, check=True)
    except Exception:
        print(f"  Open manually: {url}")


def validate_config():
    """Check that required credentials are set."""
    errors = []
    if not Config.ANTHROPIC_API_KEY or Config.ANTHROPIC_API_KEY == "sk-ant-...":
        errors.append("ANTHROPIC_API_KEY not set")
    if not Config.DERIBIT_CLIENT_ID or Config.DERIBIT_CLIENT_ID == "your_client_id":
        errors.append("DERIBIT_CLIENT_ID not set")
    if not Config.DERIBIT_CLIENT_SECRET or Config.DERIBIT_CLIENT_SECRET == "your_client_secret":
        errors.append("DERIBIT_CLIENT_SECRET not set")

    if errors:
        print("\n  CONFIGURATION ERROR")
        print("  " + "-" * 40)
        for e in errors:
            print(f"  ! {e}")
        print()
        print("  Copy .env.example to .env and fill in your credentials.")
        print("  See README.md for setup instructions.")
        print()
        sys.exit(1)


def main():
    # Report-only mode: skip trading, just generate from DB
    if "--report" in sys.argv:
        print("Generating report from existing data...")
        path = generate_report()
        print(f"Report saved: {path}")
        open_report(path)
        return

    validate_config()

    agent = TradingAgent()
    loop = "--loop" in sys.argv
    interval = 900  # 15 minutes

    print(r"""
     ____                  ____    _    ___
    | __ )  ___  __ _ _ __|  _ \  / \  / _ \
    |  _ \ / _ \/ _` | '__| | | |/ _ \| | | |
    | |_) |  __/ (_| | |  | |_| / ___ \ |_| |
    |____/ \___|\__,_|_|  |____/_/   \_\___/

    Inverse MicroStrategy — AI BTC Short Desk
    """)

    if Config.DERIBIT_LIVE:
        print("  !! LIVE MODE — REAL MONEY AT RISK !!")
    else:
        print("  Testnet mode — paper trading (safe)")
    print()

    while True:
        try:
            result = agent.run_cycle()

            # Generate report
            print("\nGenerating report...")
            report_path = generate_report(result)
            print(f"Report: {report_path}")
            open_report(report_path)

        except KeyboardInterrupt:
            print("\n\nShutting down gracefully...")
            break
        except Exception as e:
            print(f"\n[ERROR] Cycle failed: {e}")
            import traceback
            traceback.print_exc()

        if not loop:
            break

        print(f"\nNext cycle in {interval // 60} minutes... (Ctrl+C to stop)")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n\nShutting down gracefully...")
            break


if __name__ == "__main__":
    main()
