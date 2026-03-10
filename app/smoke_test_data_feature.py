from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.feature_engine import FeatureEngine  # noqa: E402
from core.market_data import MarketDataService  # noqa: E402
from core.mt5_gateway import MT5Gateway  # noqa: E402
from models.schemas import AppSettings  # noqa: E402


def load_yaml(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)
    if not isinstance(content, dict):
        raise ValueError(f"Config file must contain YAML object: {file_path}")
    return content


def main() -> int:
    app_settings = AppSettings.model_validate(load_yaml(PROJECT_ROOT / "config" / "settings.yaml"))

    gateway = MT5Gateway()
    gateway.initialize()
    gateway.ensure_connection()

    market_service = MarketDataService(
        gateway=gateway,
        timeframe=app_settings.timeframe,
        max_bars_fetch=app_settings.max_bars_fetch,
    )
    feature_engine = FeatureEngine()

    result = {}
    for symbol in app_settings.symbols:
        market_frame = market_service.load_symbol_frame(symbol)
        tick = gateway.get_tick(symbol)
        has_position = gateway.has_open_position(symbol)

        snapshot = feature_engine.build_snapshot(
            symbol=symbol,
            timeframe=market_frame.timeframe,
            frame=market_frame.data,
            spread=tick.spread_points,
            open_position_flag=has_position,
        )

        result[symbol] = {
            "bar_time": snapshot.bar_time,
            "ema_20": snapshot.ema_20,
            "ema_50": snapshot.ema_50,
            "ema_200": snapshot.ema_200,
            "rsi_14": snapshot.rsi_14,
            "macd_histogram": snapshot.macd_histogram,
            "atr_14": snapshot.atr_14,
            "adx_14": snapshot.adx_14,
            "session": snapshot.session,
            "spread": snapshot.spread,
            "open_position_flag": snapshot.open_position_flag,
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    gateway.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
