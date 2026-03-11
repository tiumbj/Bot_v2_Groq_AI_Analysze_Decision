"""
Bot_Pro AI Trading System
File: app/smoke_test_candidate.py
Version: v1.0.0

Purpose
- End-to-end smoke test for alias-aware candidate post-processing
- Validate that GOLD / XAUUSD / XAUUSDm do not create duplicate handling
- Provide deterministic console output for quick production sanity check

Run
- PS D:\\Bot_Pro> python app/smoke_test_candidate.py
"""

from __future__ import annotations

from typing import Any, Dict, List

from core.candidate_pipeline_postprocessor import CandidatePipelinePostprocessor


def build_sample_candidates() -> List[Dict[str, Any]]:
    """
    Deterministic smoke-test payload.

    Scenario:
    - GOLD and XAUUSDm represent the same underlying setup on the same bar
    - XAUUSD represents a later bar and should remain a separate setup
    """
    return [
        {
            "symbol": "GOLD",
            "timeframe": "M15",
            "bar_time": "2026-03-10 14:30:00",
            "decision": "BUY",
            "score": 0.86,
            "entry": 5186.91,
            "sl": 5158.58,
            "tp": 5243.57,
            "guard": "allowed",
        },
        {
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "bar_time": "2026-03-10 14:30:00",
            "decision": "BUY",
            "score": 0.86,
            "entry": 5186.91,
            "sl": 5158.58,
            "tp": 5243.57,
            "guard": "allowed",
        },
        {
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "bar_time": "2026-03-10 14:45:00",
            "decision": "BUY",
            "score": 0.82,
            "entry": 5190.10,
            "sl": 5160.00,
            "tp": 5250.00,
            "guard": "allowed",
        },
    ]


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    postprocessor = CandidatePipelinePostprocessor()
    rows = build_sample_candidates()

    result = postprocessor.process(
        candidates=rows,
        timeframe="M15",
        processed_symbols=3,
    )

    print_section("LOG LINES")
    for line in result["log_lines"]:
        print(line)

    print_section("SUMMARY")
    print(result["summary"])

    print_section("ACCEPTED")
    for item in result["accepted"]:
        print(item)

    print_section("REJECTED")
    for item in result["rejected"]:
        print(item)

    summary = result["summary"]

    expected_input_candidates = 3
    expected_approved = 2
    expected_rejected = 1
    expected_duplicates_blocked = 1
    expected_unique_underlying_setups = 2

    checks = [
        (
            summary["input_candidates"] == expected_input_candidates,
            f"input_candidates expected={expected_input_candidates} actual={summary['input_candidates']}",
        ),
        (
            summary["approved"] == expected_approved,
            f"approved expected={expected_approved} actual={summary['approved']}",
        ),
        (
            summary["rejected"] == expected_rejected,
            f"rejected expected={expected_rejected} actual={summary['rejected']}",
        ),
        (
            summary["duplicates_blocked"] == expected_duplicates_blocked,
            f"duplicates_blocked expected={expected_duplicates_blocked} actual={summary['duplicates_blocked']}",
        ),
        (
            summary["unique_underlying_setups"] == expected_unique_underlying_setups,
            f"unique_underlying_setups expected={expected_unique_underlying_setups} actual={summary['unique_underlying_setups']}",
        ),
    ]

    print_section("ASSERTIONS")
    failed = []
    for ok, message in checks:
        status = "PASS" if ok else "FAIL"
        print(f"{status}: {message}")
        if not ok:
            failed.append(message)

    if failed:
        print_section("RESULT")
        print("SMOKE TEST FAILED")
        return 1

    print_section("RESULT")
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())