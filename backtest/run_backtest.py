#!/usr/bin/env python3
"""
Run the backtest and generate the report.

Usage:
    python -m backtest.run_backtest                  # Default: 3 folds
    python -m backtest.run_backtest --folds 5         # 5 folds
    python -m backtest.run_backtest --stride 24       # 24h stride between folds
    python -m backtest.run_backtest --fetch           # Re-fetch dataset first
    python -m backtest.run_backtest --all             # All possible folds
"""

import argparse
import json
import os
import subprocess
import platform
import sys

from backtest.fetch_dataset import build_dataset
from backtest.engine import run_backtest
from backtest.report import generate_backtest_report


def open_file(path: str):
    abs_path = os.path.abspath(path)
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", abs_path], check=True)
        elif platform.system() == "Linux":
            subprocess.run(["xdg-open", abs_path], check=True)
        else:
            subprocess.run(["start", abs_path], shell=True, check=True)
    except Exception:
        print(f"  Open manually: file://{abs_path}")


def main():
    parser = argparse.ArgumentParser(description="Run backtest with sliding-window CV")
    parser.add_argument("--folds", type=int, default=3, help="Max folds to run (default: 3)")
    parser.add_argument("--stride", type=int, default=48, help="Stride in hours between folds (default: 48)")
    parser.add_argument("--train-days", type=int, default=25, help="Training window in days (default: 25)")
    parser.add_argument("--test-days", type=int, default=5, help="Test window in days (default: 5)")
    parser.add_argument("--fetch", action="store_true", help="Re-fetch dataset before backtesting")
    parser.add_argument("--all", action="store_true", help="Run all possible folds")
    parser.add_argument("--dataset", type=str, default=None, help="Path to dataset JSON")
    args = parser.parse_args()

    print(r"""
     ____             _    _            _
    | __ )  __ _  ___| | _| |_ ___  ___| |_
    |  _ \ / _` |/ __| |/ / __/ _ \/ __| __|
    | |_) | (_| | (__|   <| ||  __/\__ \ |_
    |____/ \__,_|\___|_|\_\\__\___||___/\__|

    Anti-MicroStrategy Backtesting Engine
    """)

    # Optionally re-fetch
    if args.fetch or not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "datasets", "latest.json")):
        print("Fetching fresh dataset...")
        build_dataset(days=30)

    max_folds = None if args.all else args.folds

    # Run backtest
    results = run_backtest(
        dataset_path=args.dataset,
        train_days=args.train_days,
        test_days=args.test_days,
        stride_hours=args.stride,
        max_folds=max_folds,
    )

    # Save raw results
    results_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(results_dir, exist_ok=True)
    results_path = os.path.join(results_dir, "backtest-results-latest.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nRaw results: {results_path}")

    # Generate report
    report_path = generate_backtest_report(results)
    print(f"Report: {report_path}")
    open_file(report_path)


if __name__ == "__main__":
    main()
