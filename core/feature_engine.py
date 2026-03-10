"""
OracleBot-Pro
File: core/feature_engine.py
Version: v1.1.0

Purpose
- Build locked-v1 feature snapshot from OHLCV frame
- Production-safe, schema-tolerant
- No extra indicators beyond locked architecture

Locked v1 features
Trend
- EMA 20
- EMA 50
- EMA 200
- EMA20 slope
- EMA spread ratio

Momentum
- RSI 14
- MACD line
- MACD signal
- MACD histogram

Volatility
- ATR 14
- Bollinger upper/mid/lower
- Bollinger width

Trend strength
- ADX 14
- +DI / -DI

Structure
- swing high
- swing low
- distance to swing high in ATR
- distance to swing low in ATR
- breakout state
- retest state

Context
- spread
- session
- open position flag
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    timeframe: str
    bar_time: str

    open: float
    high: float
    low: float
    close: float
    tick_volume: float

    ema_20: float
    ema_50: float
    ema_200: float
    ema20_slope: float
    ema_spread_ratio: float

    rsi_14: float
    macd_line: float
    macd_signal: float
    macd_histogram: float

    atr_14: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    bb_width: float

    adx_14: float
    di_plus: float
    di_minus: float

    swing_high: float
    swing_low: float
    distance_to_swing_high_atr: float
    distance_to_swing_low_atr: float
    breakout_state: str
    retest_state: str

    spread: float
    session: str
    open_position_flag: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeatureEngine:
    def __init__(self, swing_lookback: int = 20) -> None:
        self.swing_lookback = max(int(swing_lookback), 5)

    def build_snapshot(
        self,
        symbol: str,
        timeframe: str,
        frame: Any,
        spread: float = 0.0,
        open_position_flag: bool = False,
    ) -> FeatureSnapshot:
        df = self._normalize_frame(frame)
        df = self._add_trend_features(df)
        df = self._add_momentum_features(df)
        df = self._add_volatility_features(df)
        df = self._add_trend_strength_features(df)
        df = self._add_structure_features(df)

        row = df.iloc[-1]

        bar_time = row["time"]
        if isinstance(bar_time, pd.Timestamp):
            bar_time = bar_time.to_pydatetime().isoformat()
        else:
            bar_time = str(bar_time)

        return FeatureSnapshot(
            symbol=str(symbol),
            timeframe=str(timeframe).upper(),
            bar_time=bar_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            tick_volume=float(row["tick_volume"]),
            ema_20=float(row["ema_20"]),
            ema_50=float(row["ema_50"]),
            ema_200=float(row["ema_200"]),
            ema20_slope=float(row["ema20_slope"]),
            ema_spread_ratio=float(row["ema_spread_ratio"]),
            rsi_14=float(row["rsi_14"]),
            macd_line=float(row["macd_line"]),
            macd_signal=float(row["macd_signal"]),
            macd_histogram=float(row["macd_histogram"]),
            atr_14=float(row["atr_14"]),
            bb_upper=float(row["bb_upper"]),
            bb_mid=float(row["bb_mid"]),
            bb_lower=float(row["bb_lower"]),
            bb_width=float(row["bb_width"]),
            adx_14=float(row["adx_14"]),
            di_plus=float(row["di_plus"]),
            di_minus=float(row["di_minus"]),
            swing_high=float(row["swing_high"]),
            swing_low=float(row["swing_low"]),
            distance_to_swing_high_atr=float(row["distance_to_swing_high_atr"]),
            distance_to_swing_low_atr=float(row["distance_to_swing_low_atr"]),
            breakout_state=str(row["breakout_state"]),
            retest_state=str(row["retest_state"]),
            spread=float(spread),
            session=self._detect_session(bar_time),
            open_position_flag=bool(open_position_flag),
        )

    def _normalize_frame(self, frame: Any) -> pd.DataFrame:
        if frame is None:
            raise ValueError("frame is None")

        if isinstance(frame, pd.DataFrame):
            df = frame.copy()
        elif is_dataclass(frame):
            df = pd.DataFrame(asdict(frame))
        elif isinstance(frame, list):
            df = pd.DataFrame(frame)
        elif isinstance(frame, dict):
            df = pd.DataFrame(frame)
        else:
            try:
                df = pd.DataFrame(frame)
            except Exception as exc:
                raise ValueError(f"Unsupported frame type: {type(frame)}") from exc

        if df.empty:
            raise ValueError("frame is empty")

        rename_map = {
            "datetime": "time",
            "date": "time",
            "timestamp": "time",
        }
        df = df.rename(columns=rename_map)

        if "tick_volume" not in df.columns:
            for volume_col in ["tickvol", "real_volume", "vol", "volume"]:
                if volume_col in df.columns:
                    df["tick_volume"] = df[volume_col]
                    break

        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()].copy()

        required = ["time", "open", "high", "low", "close"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing OHLCV columns: {missing}")

        if "tick_volume" not in df.columns:
            df["tick_volume"] = 0.0

        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

        numeric_cols = ["open", "high", "low", "close", "tick_volume"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

        if len(df) < 50:
            raise ValueError("Not enough bars to build feature snapshot")

        return df

    def _add_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out["ema_20"] = out["close"].ewm(span=20, adjust=False).mean()
        out["ema_50"] = out["close"].ewm(span=50, adjust=False).mean()
        out["ema_200"] = out["close"].ewm(span=200, adjust=False).mean()

        out["ema20_slope"] = out["ema_20"].diff()
        out["ema_spread_ratio"] = np.where(
            out["ema_200"].abs() > 1e-12,
            (out["ema_20"] - out["ema_50"]) / out["ema_200"],
            0.0,
        )

        fill_cols = ["ema_20", "ema_50", "ema_200", "ema20_slope", "ema_spread_ratio"]
        for col in fill_cols:
            out[col] = out[col].replace([np.inf, -np.inf], np.nan).bfill().ffill().fillna(0.0)

        return out

    def _add_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        delta = out["close"].diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)

        avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        out["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
        out["rsi_14"] = out["rsi_14"].replace([np.inf, -np.inf], np.nan).bfill().ffill().fillna(50.0)

        ema_fast = out["close"].ewm(span=12, adjust=False).mean()
        ema_slow = out["close"].ewm(span=26, adjust=False).mean()
        out["macd_line"] = ema_fast - ema_slow
        out["macd_signal"] = out["macd_line"].ewm(span=9, adjust=False).mean()
        out["macd_histogram"] = out["macd_line"] - out["macd_signal"]

        fill_cols = ["macd_line", "macd_signal", "macd_histogram"]
        for col in fill_cols:
            out[col] = out[col].replace([np.inf, -np.inf], np.nan).bfill().ffill().fillna(0.0)

        return out

    def _add_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        prev_close = out["close"].shift(1)
        tr_components = pd.concat(
            [
                (out["high"] - out["low"]).abs(),
                (out["high"] - prev_close).abs(),
                (out["low"] - prev_close).abs(),
            ],
            axis=1,
        )
        true_range = tr_components.max(axis=1)
        out["atr_14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        out["atr_14"] = out["atr_14"].replace([np.inf, -np.inf], np.nan).bfill().ffill().fillna(0.0)

        out["bb_mid"] = out["close"].rolling(window=20, min_periods=20).mean()
        rolling_std = out["close"].rolling(window=20, min_periods=20).std(ddof=0)
        out["bb_upper"] = out["bb_mid"] + (2.0 * rolling_std)
        out["bb_lower"] = out["bb_mid"] - (2.0 * rolling_std)

        out["bb_width"] = np.where(
            out["bb_mid"].abs() > 1e-12,
            (out["bb_upper"] - out["bb_lower"]) / out["bb_mid"].abs(),
            0.0,
        )

        fill_cols = ["bb_mid", "bb_upper", "bb_lower", "bb_width"]
        for col in fill_cols:
            out[col] = out[col].replace([np.inf, -np.inf], np.nan).bfill().ffill().fillna(0.0)

        return out

    def _add_trend_strength_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        high_diff = out["high"].diff()
        low_diff = -out["low"].diff()

        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0.0), high_diff, 0.0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0.0), low_diff, 0.0)

        prev_close = out["close"].shift(1)
        tr_components = pd.concat(
            [
                (out["high"] - out["low"]).abs(),
                (out["high"] - prev_close).abs(),
                (out["low"] - prev_close).abs(),
            ],
            axis=1,
        )
        tr = tr_components.max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

        plus_dm_smooth = pd.Series(plus_dm, index=out.index).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        minus_dm_smooth = pd.Series(minus_dm, index=out.index).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

        out["di_plus"] = np.where(atr.abs() > 1e-12, (plus_dm_smooth / atr) * 100.0, 0.0)
        out["di_minus"] = np.where(atr.abs() > 1e-12, (minus_dm_smooth / atr) * 100.0, 0.0)

        di_sum = out["di_plus"] + out["di_minus"]
        dx = np.where(di_sum.abs() > 1e-12, ((out["di_plus"] - out["di_minus"]).abs() / di_sum) * 100.0, 0.0)
        out["adx_14"] = pd.Series(dx, index=out.index).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

        fill_cols = ["di_plus", "di_minus", "adx_14"]
        for col in fill_cols:
            out[col] = out[col].replace([np.inf, -np.inf], np.nan).bfill().ffill().fillna(0.0)

        return out

    def _add_structure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out["swing_high"] = out["high"].rolling(window=self.swing_lookback, min_periods=self.swing_lookback).max()
        out["swing_low"] = out["low"].rolling(window=self.swing_lookback, min_periods=self.swing_lookback).min()

        out["swing_high"] = out["swing_high"].bfill().ffill().fillna(out["high"])
        out["swing_low"] = out["swing_low"].bfill().ffill().fillna(out["low"])

        atr = out["atr_14"].replace(0.0, np.nan)

        out["distance_to_swing_high_atr"] = np.where(
            atr.abs() > 1e-12,
            (out["swing_high"] - out["close"]) / atr,
            0.0,
        )
        out["distance_to_swing_low_atr"] = np.where(
            atr.abs() > 1e-12,
            (out["close"] - out["swing_low"]) / atr,
            0.0,
        )

        out["distance_to_swing_high_atr"] = (
            pd.Series(out["distance_to_swing_high_atr"], index=out.index)
            .replace([np.inf, -np.inf], np.nan)
            .bfill()
            .ffill()
            .fillna(0.0)
        )
        out["distance_to_swing_low_atr"] = (
            pd.Series(out["distance_to_swing_low_atr"], index=out.index)
            .replace([np.inf, -np.inf], np.nan)
            .bfill()
            .ffill()
            .fillna(0.0)
        )

        prev_swing_high = out["swing_high"].shift(1)
        prev_swing_low = out["swing_low"].shift(1)

        breakout_conditions = [
            out["close"] > prev_swing_high,
            out["close"] < prev_swing_low,
        ]
        breakout_choices = ["bullish", "bearish"]
        out["breakout_state"] = np.select(breakout_conditions, breakout_choices, default="none")

        retest_conditions = [
            (out["close"] >= out["ema_20"]) & (out["low"] <= out["ema_20"]) & (out["ema20_slope"] > 0),
            (out["close"] <= out["ema_20"]) & (out["high"] >= out["ema_20"]) & (out["ema20_slope"] < 0),
        ]
        retest_choices = ["bullish", "bearish"]
        out["retest_state"] = np.select(retest_conditions, retest_choices, default="none")

        return out

    @staticmethod
    def _detect_session(bar_time: str) -> str:
        try:
            dt = datetime.fromisoformat(str(bar_time))
            hour = dt.hour
        except Exception:
            return "unknown"

        if 0 <= hour < 7:
            return "asia"
        if 7 <= hour < 13:
            return "london"
        if 13 <= hour < 22:
            return "newyork"
        return "afterhours"
