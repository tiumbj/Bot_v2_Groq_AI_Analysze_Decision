from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import MetaTrader5 as mt5
import pandas as pd


@dataclass(frozen=True)
class SymbolTick:
    symbol: str
    bid: float
    ask: float
    last: float
    spread_points: float
    time_utc: datetime


@dataclass(frozen=True)
class SymbolAccountInfo:
    login: int
    server: str
    balance: float
    equity: float
    margin_free: float
    leverage: int


class MT5Gateway:
    def __init__(self) -> None:
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        ok = mt5.initialize()
        if not ok:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 initialize failed: code={code}, message={message}")

        self._initialized = True

    def shutdown(self) -> None:
        if self._initialized:
            mt5.shutdown()
            self._initialized = False

    def ensure_connection(self) -> None:
        terminal_info = mt5.terminal_info()
        if terminal_info is None:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 terminal_info failed: code={code}, message={message}")

        if not terminal_info.connected:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 terminal not connected: code={code}, message={message}")

    def get_account_info(self) -> SymbolAccountInfo:
        account = mt5.account_info()
        if account is None:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 account_info failed: code={code}, message={message}")

        return SymbolAccountInfo(
            login=int(account.login),
            server=str(account.server),
            balance=float(account.balance),
            equity=float(account.equity),
            margin_free=float(account.margin_free),
            leverage=int(account.leverage),
        )

    def ensure_symbol_selected(self, symbol: str) -> None:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 symbol_info failed for {symbol}: code={code}, message={message}")

        if not symbol_info.visible:
            ok = mt5.symbol_select(symbol, True)
            if not ok:
                code, message = mt5.last_error()
                raise RuntimeError(
                    f"MT5 symbol_select failed for {symbol}: code={code}, message={message}"
                )

    def get_symbol_info_dict(self, symbol: str) -> dict[str, Any]:
        self.ensure_symbol_selected(symbol)
        info = mt5.symbol_info(symbol)
        if info is None:
            code, message = mt5.last_error()
            raise RuntimeError(f"MT5 symbol_info failed for {symbol}: code={code}, message={message}")

        return info._asdict()

    def get_tick(self, symbol: str) -> SymbolTick:
        self.ensure_symbol_selected(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            code, message = mt5.last_error()
            raise RuntimeError(
                f"MT5 symbol_info_tick failed for {symbol}: code={code}, message={message}"
            )

        spread_points = 0.0
        if tick.ask is not None and tick.bid is not None:
            spread_points = float(tick.ask) - float(tick.bid)

        return SymbolTick(
            symbol=symbol,
            bid=float(tick.bid),
            ask=float(tick.ask),
            last=float(tick.last),
            spread_points=spread_points,
            time_utc=datetime.fromtimestamp(int(tick.time), tz=timezone.utc),
        )

    def get_positions_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        positions = mt5.positions_get(symbol=symbol)
        if positions is None:
            code, message = mt5.last_error()
            raise RuntimeError(
                f"MT5 positions_get failed for {symbol}: code={code}, message={message}"
            )
        return [position._asdict() for position in positions]

    def has_open_position(self, symbol: str) -> bool:
        positions = self.get_positions_by_symbol(symbol)
        return len(positions) > 0

    def get_rates(self, symbol: str, timeframe_code: int, bars: int) -> pd.DataFrame:
        self.ensure_symbol_selected(symbol)

        rates = mt5.copy_rates_from_pos(symbol, timeframe_code, 0, bars)
        if rates is None:
            code, message = mt5.last_error()
            raise RuntimeError(
                f"MT5 copy_rates_from_pos failed for {symbol}: code={code}, message={message}"
            )

        frame = pd.DataFrame(rates)
        if frame.empty:
            raise RuntimeError(f"MT5 returned empty rates for {symbol}")

        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
        ]
        for column in numeric_columns:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

        return frame

    @staticmethod
    def timeframe_from_string(timeframe: str) -> int:
        mapping = {
            "M1": mt5.TIMEFRAME_M1,
            "M2": mt5.TIMEFRAME_M2,
            "M3": mt5.TIMEFRAME_M3,
            "M4": mt5.TIMEFRAME_M4,
            "M5": mt5.TIMEFRAME_M5,
            "M6": mt5.TIMEFRAME_M6,
            "M10": mt5.TIMEFRAME_M10,
            "M12": mt5.TIMEFRAME_M12,
            "M15": mt5.TIMEFRAME_M15,
            "M20": mt5.TIMEFRAME_M20,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H2": mt5.TIMEFRAME_H2,
            "H3": mt5.TIMEFRAME_H3,
            "H4": mt5.TIMEFRAME_H4,
            "H6": mt5.TIMEFRAME_H6,
            "H8": mt5.TIMEFRAME_H8,
            "H12": mt5.TIMEFRAME_H12,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN1": mt5.TIMEFRAME_MN1,
        }
        if timeframe not in mapping:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return mapping[timeframe]