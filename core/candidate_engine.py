"""
OracleBot-Pro
File: core/candidate_engine.py
Version: v1.0.0

Purpose
- Detect locked-v1 trade candidates from a FeatureSnapshot-like object
- Keep logic lean, deterministic, and production-safe
- Return one best candidate per symbol/bar at most

Notes
- This file is intentionally schema-tolerant:
  it can read data from dataclass/object/dict snapshots
- No AI logic here
- No execution logic here
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CandidateConfig:
    min_adx: float = 18.0
    min_bb_width: float = 0.0020
    min_ema_spread_ratio: float = 0.0002
    min_room_to_swing_atr: float = 0.80
    min_score_to_emit: float = 0.60
    min_rsi_buy: float = 52.0
    max_rsi_buy: float = 72.0
    min_rsi_sell: float = 28.0
    max_rsi_sell: float = 48.0
    atr_stop_buffer: float = 0.35


@dataclass(frozen=True)
class CandidateSignal:
    symbol: str
    timeframe: str
    bar_time: str
    direction: str
    score: float
    entry_hint: float
    stop_hint: float
    target_hint: float
    reasons: List[str]
    features: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CandidateEngine:
    """
    Deterministic candidate detector for locked v1 feature set.
    Emits at most one candidate per snapshot.
    """

    def __init__(self, config: Optional[CandidateConfig] = None) -> None:
        self.config = config or CandidateConfig()

    def detect_candidate(self, snapshot: Any) -> Optional[CandidateSignal]:
        symbol = str(self._read(snapshot, "symbol", "UNKNOWN"))
        timeframe = str(self._read(snapshot, "timeframe", "UNKNOWN"))
        bar_time = self._normalize_time(
            self._read(snapshot, "bar_time", self._read(snapshot, "time", datetime.utcnow()))
        )

        long_eval = self._evaluate_long(snapshot)
        short_eval = self._evaluate_short(snapshot)

        best = long_eval if long_eval["score"] >= short_eval["score"] else short_eval

        if best["score"] < self.config.min_score_to_emit:
            return None

        entry_hint = float(self._read(snapshot, "close", 0.0))
        atr = float(self._read(snapshot, "atr_14", self._read(snapshot, "atr", 0.0)))
        swing_low = float(self._read(snapshot, "swing_low", entry_hint))
        swing_high = float(self._read(snapshot, "swing_high", entry_hint))

        if best["direction"] == "BUY":
            stop_hint = min(swing_low, entry_hint - (atr * self.config.atr_stop_buffer))
            risk = max(entry_hint - stop_hint, 0.0)
            target_hint = entry_hint + (risk * 2.0) if risk > 0 else entry_hint
        else:
            stop_hint = max(swing_high, entry_hint + (atr * self.config.atr_stop_buffer))
            risk = max(stop_hint - entry_hint, 0.0)
            target_hint = entry_hint - (risk * 2.0) if risk > 0 else entry_hint

        return CandidateSignal(
            symbol=symbol,
            timeframe=timeframe,
            bar_time=bar_time,
            direction=best["direction"],
            score=round(best["score"], 4),
            entry_hint=round(entry_hint, 5),
            stop_hint=round(stop_hint, 5),
            target_hint=round(target_hint, 5),
            reasons=best["reasons"],
            features=self._extract_feature_subset(snapshot),
        )

    def _evaluate_long(self, snapshot: Any) -> Dict[str, Any]:
        checks: List[bool] = []
        reasons: List[str] = []

        close = float(self._read(snapshot, "close", 0.0))
        ema20 = float(self._read(snapshot, "ema_20", 0.0))
        ema50 = float(self._read(snapshot, "ema_50", 0.0))
        ema200 = float(self._read(snapshot, "ema_200", 0.0))
        ema20_slope = float(self._read(snapshot, "ema20_slope", self._read(snapshot, "ema_20_slope", 0.0)))
        ema_spread_ratio = float(self._read(snapshot, "ema_spread_ratio", 0.0))
        rsi = float(self._read(snapshot, "rsi_14", self._read(snapshot, "rsi", 50.0)))
        macd_hist = float(self._read(snapshot, "macd_histogram", self._read(snapshot, "macd_hist", 0.0)))
        adx = float(self._read(snapshot, "adx_14", self._read(snapshot, "adx", 0.0)))
        di_plus = float(self._read(snapshot, "di_plus", self._read(snapshot, "plus_di", 0.0)))
        di_minus = float(self._read(snapshot, "di_minus", self._read(snapshot, "minus_di", 0.0)))
        bb_width = float(self._read(snapshot, "bb_width", self._read(snapshot, "bollinger_width", 0.0)))
        room_to_high = float(
            self._read(
                snapshot,
                "distance_to_swing_high_atr",
                self._read(snapshot, "dist_to_swing_high_atr", 999.0),
            )
        )
        breakout_state = str(self._read(snapshot, "breakout_state", "")).lower()
        retest_state = str(self._read(snapshot, "retest_state", "")).lower()

        trend_ok = close > ema20 > ema50 > ema200
        if trend_ok:
            reasons.append("trend_alignment_bullish")
        checks.append(trend_ok)

        slope_ok = ema20_slope > 0.0 and ema_spread_ratio >= self.config.min_ema_spread_ratio
        if slope_ok:
            reasons.append("ema_slope_positive")
        checks.append(slope_ok)

        momentum_ok = (
            self.config.min_rsi_buy <= rsi <= self.config.max_rsi_buy
            and macd_hist > 0.0
        )
        if momentum_ok:
            reasons.append("momentum_bullish")
        checks.append(momentum_ok)

        strength_ok = adx >= self.config.min_adx and di_plus > di_minus
        if strength_ok:
            reasons.append("trend_strength_confirmed")
        checks.append(strength_ok)

        volatility_ok = bb_width >= self.config.min_bb_width
        if volatility_ok:
            reasons.append("volatility_sufficient")
        checks.append(volatility_ok)

        structure_ok = (
            breakout_state in {"bullish", "long", "up"}
            or retest_state in {"bullish", "long", "support", "up"}
        )
        if structure_ok:
            reasons.append("structure_bullish")
        checks.append(structure_ok)

        room_ok = room_to_high >= self.config.min_room_to_swing_atr
        if room_ok:
            reasons.append("room_to_high_available")
        checks.append(room_ok)

        score = sum(1 for item in checks if item) / len(checks)
        return {
            "direction": "BUY",
            "score": score,
            "reasons": reasons[:4],
        }

    def _evaluate_short(self, snapshot: Any) -> Dict[str, Any]:
        checks: List[bool] = []
        reasons: List[str] = []

        close = float(self._read(snapshot, "close", 0.0))
        ema20 = float(self._read(snapshot, "ema_20", 0.0))
        ema50 = float(self._read(snapshot, "ema_50", 0.0))
        ema200 = float(self._read(snapshot, "ema_200", 0.0))
        ema20_slope = float(self._read(snapshot, "ema20_slope", self._read(snapshot, "ema_20_slope", 0.0)))
        ema_spread_ratio = float(self._read(snapshot, "ema_spread_ratio", 0.0))
        rsi = float(self._read(snapshot, "rsi_14", self._read(snapshot, "rsi", 50.0)))
        macd_hist = float(self._read(snapshot, "macd_histogram", self._read(snapshot, "macd_hist", 0.0)))
        adx = float(self._read(snapshot, "adx_14", self._read(snapshot, "adx", 0.0)))
        di_plus = float(self._read(snapshot, "di_plus", self._read(snapshot, "plus_di", 0.0)))
        di_minus = float(self._read(snapshot, "di_minus", self._read(snapshot, "minus_di", 0.0)))
        bb_width = float(self._read(snapshot, "bb_width", self._read(snapshot, "bollinger_width", 0.0)))
        room_to_low = float(
            self._read(
                snapshot,
                "distance_to_swing_low_atr",
                self._read(snapshot, "dist_to_swing_low_atr", 999.0),
            )
        )
        breakout_state = str(self._read(snapshot, "breakout_state", "")).lower()
        retest_state = str(self._read(snapshot, "retest_state", "")).lower()

        trend_ok = close < ema20 < ema50 < ema200
        if trend_ok:
            reasons.append("trend_alignment_bearish")
        checks.append(trend_ok)

        slope_ok = ema20_slope < 0.0 and ema_spread_ratio <= (-1.0 * self.config.min_ema_spread_ratio)
        if slope_ok:
            reasons.append("ema_slope_negative")
        checks.append(slope_ok)

        momentum_ok = (
            self.config.min_rsi_sell <= rsi <= self.config.max_rsi_sell
            and macd_hist < 0.0
        )
        if momentum_ok:
            reasons.append("momentum_bearish")
        checks.append(momentum_ok)

        strength_ok = adx >= self.config.min_adx and di_minus > di_plus
        if strength_ok:
            reasons.append("trend_strength_confirmed")
        checks.append(strength_ok)

        volatility_ok = bb_width >= self.config.min_bb_width
        if volatility_ok:
            reasons.append("volatility_sufficient")
        checks.append(volatility_ok)

        structure_ok = (
            breakout_state in {"bearish", "short", "down"}
            or retest_state in {"bearish", "short", "resistance", "down"}
        )
        if structure_ok:
            reasons.append("structure_bearish")
        checks.append(structure_ok)

        room_ok = room_to_low >= self.config.min_room_to_swing_atr
        if room_ok:
            reasons.append("room_to_low_available")
        checks.append(room_ok)

        score = sum(1 for item in checks if item) / len(checks)
        return {
            "direction": "SELL",
            "score": score,
            "reasons": reasons[:4],
        }

    def _extract_feature_subset(self, snapshot: Any) -> Dict[str, Any]:
        keys = [
            "close",
            "ema_20",
            "ema_50",
            "ema_200",
            "ema20_slope",
            "ema_spread_ratio",
            "rsi_14",
            "macd_line",
            "macd_signal",
            "macd_histogram",
            "atr_14",
            "adx_14",
            "di_plus",
            "di_minus",
            "bb_width",
            "swing_high",
            "swing_low",
            "distance_to_swing_high_atr",
            "distance_to_swing_low_atr",
            "breakout_state",
            "retest_state",
            "spread",
            "session",
            "open_position_flag",
        ]

        subset: Dict[str, Any] = {}
        for key in keys:
            value = self._read(snapshot, key, None)
            if value is not None:
                subset[key] = value
        return subset

    @staticmethod
    def _normalize_time(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _read(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(key, default)

        if is_dataclass(obj):
            data = asdict(obj)
            return data.get(key, default)

        if hasattr(obj, key):
            return getattr(obj, key, default)

        return default