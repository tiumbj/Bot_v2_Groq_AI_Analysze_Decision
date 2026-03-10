from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.mt5_gateway import MT5Gateway


@dataclass(frozen=True)
class MarketFrame:
    symbol: str
    timeframe: str
    data: pd.DataFrame


class MarketDataService:
    REQUIRED_COLUMNS = [
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
        "real_volume",
    ]

    def __init__(self, gateway: MT5Gateway, timeframe: str, max_bars_fetch: int) -> None:
        self.gateway = gateway
        self.timeframe = timeframe
        self.max_bars_fetch = max_bars_fetch
        self.timeframe_code = self.gateway.timeframe_from_string(timeframe)

    def load_symbol_frame(self, symbol: str) -> MarketFrame:
        frame = self.gateway.get_rates(
            symbol=symbol,
            timeframe_code=self.timeframe_code,
            bars=self.max_bars_fetch,
        )
        validated = self._validate_and_prepare(frame, symbol)
        return MarketFrame(symbol=symbol, timeframe=self.timeframe, data=validated)

    def load_many(self, symbols: list[str]) -> dict[str, MarketFrame]:
        result: dict[str, MarketFrame] = {}
        for symbol in symbols:
            result[symbol] = self.load_symbol_frame(symbol)
        return result

    def _validate_and_prepare(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        missing = [column for column in self.REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing MT5 columns for {symbol}: {', '.join(missing)}")

        data = frame.copy()
        data = data.sort_values("time").reset_index(drop=True)

        for column in self.REQUIRED_COLUMNS:
            if column != "time":
                if data[column].isna().any():
                    raise ValueError(f"Found NaN in {symbol}.{column}")

        if len(data) < 250:
            raise ValueError(f"Not enough bars for {symbol}. Need >= 250, got {len(data)}")

        if (data["high"] < data["low"]).any():
            raise ValueError(f"Invalid candle range detected for {symbol}")

        if (data["open"] <= 0).any() or (data["high"] <= 0).any() or (data["low"] <= 0).any() or (data["close"] <= 0).any():
            raise ValueError(f"Non-positive OHLC detected for {symbol}")

        data["symbol"] = symbol
        data["is_closed_bar"] = True

        # ตัดแถวสุดท้ายทิ้ง เพื่อกันการใช้แท่งที่ยังวิ่งอยู่
        data = data.iloc[:-1].copy().reset_index(drop=True)
        if data.empty:
            raise ValueError(f"No closed bars remain after trimming live bar for {symbol}")

        return data