"""
Bot_Pro AI Trading System
File: core/decision_validator.py
Version: v1.1.0

Purpose
- Validate candidate decisions before final confirm/execution
- Prevent duplicate setup handling across broker-specific gold aliases
- Preserve raw symbol casing for logs and downstream execution usage
- Keep one approved path per underlying instrument for the same bar/setup

Locked production assumptions
- GOLD / XAUUSD / XAUUSDm are aliases of the same gold instrument
- Canonical analysis symbol for gold = XAUUSD
- Duplicate detection must work across aliases on the same bar/setup
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.symbol_registry import DEFAULT_SYMBOL_REGISTRY, SymbolRegistry


@dataclass
class CandidateDecision:
    """
    Normalized candidate payload used by the validator.

    Required practical fields:
    - symbol
    - decision
    - entry
    - sl
    - tp

    Optional but strongly recommended fields:
    - timeframe
    - bar_time
    - score
    - setup_key
    """
    symbol_raw: str
    symbol_normalized: str
    canonical_symbol: str
    canonical_symbol_normalized: str
    decision: str
    entry: float
    sl: float
    tp: float
    timeframe: str = ""
    bar_time: str = ""
    score: float = 0.0
    setup_key: str = ""
    guard: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """
    Output payload for one candidate after validation.
    """
    status: str
    reason: str
    input_symbol_raw: str
    input_symbol_normalized: str
    canonical_symbol: str
    canonical_symbol_normalized: str
    execution_symbol: str
    setup_key: str
    decision: str
    timeframe: str
    bar_time: str
    score: float
    entry: float
    sl: float
    tp: float
    kept_rank: int
    duplicate_of: str
    guard: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionValidator:
    """
    Production-safe decision validator.

    Responsibilities:
    1) Normalize symbol aliases into one canonical symbol
    2) Detect same-setup duplicates across aliases
    3) Keep only one approved candidate per underlying instrument + setup key
    4) Preserve raw casing in output for logs and execution-safe downstream usage
    """

    def __init__(self, symbol_registry: Optional[SymbolRegistry] = None) -> None:
        self.symbol_registry = symbol_registry or DEFAULT_SYMBOL_REGISTRY

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    def validate_batch(self, candidates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate a batch of candidate dictionaries.

        Expected input example:
        {
            "symbol": "XAUUSDm",
            "timeframe": "M15",
            "bar_time": "2026-03-10 14:30:00",
            "decision": "BUY",
            "score": 0.86,
            "entry": 5186.91,
            "sl": 5158.58,
            "tp": 5243.57,
            "setup_key": "optional-custom-key"
        }

        Returns:
        {
            "items": [ ... per-candidate results ... ],
            "approved": [ ... accepted candidates only ... ],
            "rejected": [ ... rejected candidates only ... ],
            "summary": { ... counters ... }
        }
        """
        normalized_candidates = [self._normalize_candidate(x) for x in candidates]
        ranked_candidates = sorted(normalized_candidates, key=self._ranking_key, reverse=True)

        seen_keys: Dict[str, CandidateDecision] = {}
        results: List[ValidationResult] = []

        for rank, candidate in enumerate(ranked_candidates, start=1):
            dedupe_key = self._build_dedupe_key(candidate)
            execution_symbol = self._safe_execution_symbol(candidate)

            if dedupe_key not in seen_keys:
                seen_keys[dedupe_key] = candidate
                results.append(
                    ValidationResult(
                        status="accepted",
                        reason="primary_candidate_for_underlying_setup",
                        input_symbol_raw=candidate.symbol_raw,
                        input_symbol_normalized=candidate.symbol_normalized,
                        canonical_symbol=candidate.canonical_symbol,
                        canonical_symbol_normalized=candidate.canonical_symbol_normalized,
                        execution_symbol=execution_symbol,
                        setup_key=self._effective_setup_key(candidate),
                        decision=candidate.decision,
                        timeframe=candidate.timeframe,
                        bar_time=candidate.bar_time,
                        score=float(candidate.score),
                        entry=float(candidate.entry),
                        sl=float(candidate.sl),
                        tp=float(candidate.tp),
                        kept_rank=rank,
                        duplicate_of="",
                        guard=candidate.guard,
                        metadata=dict(candidate.metadata),
                    )
                )
            else:
                primary = seen_keys[dedupe_key]
                primary_label = (
                    f"{primary.symbol_raw}|{self._effective_setup_key(primary)}|"
                    f"{primary.timeframe}|{primary.bar_time}|{primary.decision}"
                )

                results.append(
                    ValidationResult(
                        status="rejected_duplicate",
                        reason="duplicate_underlying_setup_across_aliases",
                        input_symbol_raw=candidate.symbol_raw,
                        input_symbol_normalized=candidate.symbol_normalized,
                        canonical_symbol=candidate.canonical_symbol,
                        canonical_symbol_normalized=candidate.canonical_symbol_normalized,
                        execution_symbol=execution_symbol,
                        setup_key=self._effective_setup_key(candidate),
                        decision=candidate.decision,
                        timeframe=candidate.timeframe,
                        bar_time=candidate.bar_time,
                        score=float(candidate.score),
                        entry=float(candidate.entry),
                        sl=float(candidate.sl),
                        tp=float(candidate.tp),
                        kept_rank=rank,
                        duplicate_of=primary_label,
                        guard=candidate.guard,
                        metadata=dict(candidate.metadata),
                    )
                )

        items = [asdict(x) for x in results]
        approved = [x for x in items if x["status"] == "accepted"]
        rejected = [x for x in items if x["status"] != "accepted"]

        summary = {
            "input_candidates": len(normalized_candidates),
            "approved_candidates": len(approved),
            "rejected_candidates": len(rejected),
            "duplicate_rejections": len([x for x in items if x["status"] == "rejected_duplicate"]),
            "unique_underlying_setups": len(seen_keys),
        }

        return {
            "items": items,
            "approved": approved,
            "rejected": rejected,
            "summary": summary,
        }

    def validate_one(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate one candidate only.
        Useful when upstream pipeline evaluates sequentially.
        """
        batch_result = self.validate_batch([candidate])
        return batch_result["items"][0]

    # -------------------------------------------------------------------------
    # Internal normalization
    # -------------------------------------------------------------------------
    def _normalize_candidate(self, raw: Dict[str, Any]) -> CandidateDecision:
        symbol_raw = self._require_text(raw, "symbol")
        decision = self._require_text(raw, "decision").upper()

        if decision not in {"BUY", "SELL"}:
            raise ValueError(f"Unsupported decision '{decision}'. Expected BUY or SELL.")

        entry = self._require_float(raw, "entry")
        sl = self._require_float(raw, "sl")
        tp = self._require_float(raw, "tp")

        timeframe = self._optional_text(raw, "timeframe").upper().strip()
        bar_time = self._optional_text(raw, "bar_time").strip()
        score = self._optional_float(raw, "score", 0.0)
        guard = self._optional_text(raw, "guard").strip()
        setup_key = self._optional_text(raw, "setup_key").strip()

        symbol_normalized = self.symbol_registry.normalize_symbol(symbol_raw)
        canonical_symbol = self.symbol_registry.to_canonical(symbol_raw)
        canonical_symbol_normalized = self.symbol_registry.to_canonical_normalized(symbol_raw)

        known_fields = {
            "symbol",
            "decision",
            "entry",
            "sl",
            "tp",
            "timeframe",
            "bar_time",
            "score",
            "guard",
            "setup_key",
        }
        metadata = {k: v for k, v in raw.items() if k not in known_fields}

        return CandidateDecision(
            symbol_raw=symbol_raw.strip(),
            symbol_normalized=symbol_normalized,
            canonical_symbol=canonical_symbol,
            canonical_symbol_normalized=canonical_symbol_normalized,
            decision=decision,
            entry=entry,
            sl=sl,
            tp=tp,
            timeframe=timeframe,
            bar_time=bar_time,
            score=score,
            setup_key=setup_key,
            guard=guard,
            metadata=metadata,
        )

    # -------------------------------------------------------------------------
    # Duplicate logic
    # -------------------------------------------------------------------------
    def _build_dedupe_key(self, candidate: CandidateDecision) -> str:
        """
        Dedupe key must represent the same underlying instrument and same setup.

        Priority:
        1) canonical_symbol + setup_key + decision
        2) canonical_symbol + timeframe + bar_time + decision
        3) canonical_symbol + decision + rounded trade plan

        This allows robust dedupe even if setup_key is not explicitly supplied.
        """
        effective_setup_key = self._effective_setup_key(candidate)
        return f"{candidate.canonical_symbol_normalized}|{effective_setup_key}|{candidate.decision}"

    def _effective_setup_key(self, candidate: CandidateDecision) -> str:
        """
        Resolve practical setup identity.

        Preferred: explicit setup_key
        Fallback 1: timeframe + bar_time
        Fallback 2: timeframe + rounded trade plan
        Fallback 3: rounded trade plan only
        """
        if candidate.setup_key:
            return candidate.setup_key

        if candidate.timeframe and candidate.bar_time:
            return f"{candidate.timeframe}|{candidate.bar_time}"

        rounded_plan = self._rounded_plan_key(candidate)
        if candidate.timeframe:
            return f"{candidate.timeframe}|{rounded_plan}"

        return rounded_plan

    def _rounded_plan_key(self, candidate: CandidateDecision) -> str:
        return (
            f"E{candidate.entry:.4f}|"
            f"SL{candidate.sl:.4f}|"
            f"TP{candidate.tp:.4f}"
        )

    def _ranking_key(self, candidate: CandidateDecision) -> Tuple[float, int, int, str]:
        """
        Higher rank wins when duplicates compete.

        Ranking order:
        1) Higher score
        2) Candidate with explicit bar_time wins over missing bar_time
        3) Candidate with explicit setup_key wins over fallback-generated key
        4) Stable final tiebreaker on raw symbol text
        """
        has_bar_time = 1 if candidate.bar_time else 0
        has_setup_key = 1 if candidate.setup_key else 0
        return (float(candidate.score), has_bar_time, has_setup_key, candidate.symbol_raw)

    def _safe_execution_symbol(self, candidate: CandidateDecision) -> str:
        """
        Validation layer should preserve usable execution-safe symbol text
        without assuming broker context.

        Strategy:
        - return raw input symbol if provided by upstream runtime
        - do not force upper-case
        - broker-specific mapping should happen later in execution layer
        """
        return candidate.symbol_raw

    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def _require_text(raw: Dict[str, Any], key: str) -> str:
        value = raw.get(key)
        if value is None:
            raise ValueError(f"Missing required field: '{key}'")
        value_str = str(value).strip()
        if not value_str:
            raise ValueError(f"Field '{key}' cannot be empty.")
        return value_str

    @staticmethod
    def _optional_text(raw: Dict[str, Any], key: str, default: str = "") -> str:
        value = raw.get(key, default)
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _require_float(raw: Dict[str, Any], key: str) -> float:
        value = raw.get(key)
        if value is None:
            raise ValueError(f"Missing required field: '{key}'")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Field '{key}' must be numeric.") from exc

    @staticmethod
    def _optional_float(raw: Dict[str, Any], key: str, default: float = 0.0) -> float:
        value = raw.get(key, default)
        if value is None or value == "":
            return float(default)
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Field '{key}' must be numeric when provided.") from exc


def _load_candidates_from_stdin() -> list[Dict[str, Any]]:
    text = sys.stdin.read().strip()
    if not text:
        return []
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("stdin JSON must be an object or an array of objects")


def _load_candidates_from_file(file_path: str) -> list[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("JSON file must contain an object or an array of objects")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="decision_validator")
    parser.add_argument("--file", dest="file_path", default="", help="Path to JSON file (object or array)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(argv)

    if args.file_path:
        candidates = _load_candidates_from_file(args.file_path)
    else:
        if sys.stdin.isatty():
            candidates = []
        else:
            candidates = _load_candidates_from_stdin()

    if not candidates:
        print(
            "No input provided.\n\n"
            "Examples:\n"
            "  echo '[{\"symbol\":\"XAUUSDm\",\"decision\":\"BUY\",\"entry\":1,\"sl\":0.9,\"tp\":1.2}]' | python -m core.decision_validator\n"
            "  python -m core.decision_validator --file candidates.json\n",
            file=sys.stderr,
        )
        return 2

    validator = DecisionValidator(symbol_registry=DEFAULT_SYMBOL_REGISTRY)
    result = validator.validate_batch(candidates)
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
