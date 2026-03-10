"""
OracleBot-Pro
File: core/state_guard.py
Version: v1.0.0

Purpose
- Enforce runtime guards before order execution
- One-trade-per-bar
- Cooldown by bar count
- Open-position block
- Persist minimal guard state in SQLite

Notes
- Uses storage/bot.db directly to avoid coupling
- Safe for multi-symbol runtime
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class GuardDecision:
    symbol: str
    timeframe: str
    bar_time: str
    allowed: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class StateGuard:
    def __init__(
        self,
        db_path: str = "storage/bot.db",
        timeframe: str = "M15",
        cooldown_bars: int = 2,
    ) -> None:
        self.db_path = Path(db_path)
        self.timeframe = timeframe.upper()
        self.cooldown_bars = max(int(cooldown_bars), 0)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def evaluate(
        self,
        symbol: str,
        bar_time: Any,
        gateway: Optional[Any] = None,
    ) -> GuardDecision:
        normalized_bar_time = self._normalize_time(bar_time)

        if self._has_open_position(symbol=symbol, gateway=gateway):
            return GuardDecision(
                symbol=symbol,
                timeframe=self.timeframe,
                bar_time=normalized_bar_time,
                allowed=False,
                reason="blocked_open_position",
            )

        if self._already_traded_this_bar(symbol=symbol, bar_time=normalized_bar_time):
            return GuardDecision(
                symbol=symbol,
                timeframe=self.timeframe,
                bar_time=normalized_bar_time,
                allowed=False,
                reason="blocked_one_trade_per_bar",
            )

        if self._in_cooldown(symbol=symbol, current_bar_time=normalized_bar_time):
            return GuardDecision(
                symbol=symbol,
                timeframe=self.timeframe,
                bar_time=normalized_bar_time,
                allowed=False,
                reason="blocked_cooldown",
            )

        return GuardDecision(
            symbol=symbol,
            timeframe=self.timeframe,
            bar_time=normalized_bar_time,
            allowed=True,
            reason="allowed",
        )

    def record_trade_open(self, symbol: str, bar_time: Any) -> None:
        normalized_bar_time = self._normalize_time(bar_time)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO runtime_guard_events (
                    symbol,
                    timeframe,
                    event_type,
                    bar_time,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    self.timeframe,
                    "TRADE_OPEN",
                    normalized_bar_time,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def record_candidate_seen(self, symbol: str, bar_time: Any) -> None:
        normalized_bar_time = self._normalize_time(bar_time)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO runtime_guard_events (
                    symbol,
                    timeframe,
                    event_type,
                    bar_time,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    self.timeframe,
                    "CANDIDATE_SEEN",
                    normalized_bar_time,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def _already_traded_this_bar(self, symbol: str, bar_time: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM runtime_guard_events
                WHERE symbol = ?
                  AND timeframe = ?
                  AND event_type = 'TRADE_OPEN'
                  AND bar_time = ?
                LIMIT 1
                """,
                (symbol, self.timeframe, bar_time),
            ).fetchone()
        return row is not None

    def _in_cooldown(self, symbol: str, current_bar_time: str) -> bool:
        if self.cooldown_bars <= 0:
            return False

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT bar_time
                FROM runtime_guard_events
                WHERE symbol = ?
                  AND timeframe = ?
                  AND event_type = 'TRADE_OPEN'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (symbol, self.timeframe),
            ).fetchone()

        if not row:
            return False

        last_trade_bar_time = self._parse_time(row[0])
        current_bar_dt = self._parse_time(current_bar_time)
        if last_trade_bar_time is None or current_bar_dt is None:
            return False

        minutes_since = (current_bar_dt - last_trade_bar_time).total_seconds() / 60.0
        cooldown_minutes = self.cooldown_bars * self._timeframe_to_minutes(self.timeframe)

        return minutes_since < cooldown_minutes

    @staticmethod
    def _has_open_position(symbol: str, gateway: Optional[Any]) -> bool:
        if gateway is None:
            return False

        if hasattr(gateway, "has_open_position"):
            try:
                return bool(gateway.has_open_position(symbol))
            except Exception:
                return False

        if hasattr(gateway, "positions_by_symbol"):
            try:
                positions = gateway.positions_by_symbol(symbol)
                return bool(positions)
            except Exception:
                return False

        return False

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_guard_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    bar_time TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_guard_symbol_tf_created
                ON runtime_guard_events(symbol, timeframe, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_runtime_guard_symbol_tf_bar
                ON runtime_guard_events(symbol, timeframe, bar_time)
                """
            )
            conn.commit()

    @staticmethod
    def _normalize_time(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _parse_time(value: Any) -> Optional[datetime]:
        try:
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    @staticmethod
    def _timeframe_to_minutes(timeframe: str) -> int:
        mapping = {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 60,
            "H4": 240,
            "D1": 1440,
        }
        return mapping.get(timeframe.upper(), 15)